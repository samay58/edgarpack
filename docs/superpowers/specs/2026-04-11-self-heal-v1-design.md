# Self-heal v1 — design spec

**Date**: 2026-04-11
**Status**: Approved via grill-me brainstorm
**Scope**: Layer 0 (alias map) + Layer A (concept drift self-heal). Layer B (KPI extraction from prose/tables) deferred.

## Problem

`edgarpack query` silently returns `N/A` in two distinct failure modes:

1. **Typo-class miss**: user types `fcf` but the canonical name is `free_cash_flow`. `METRIC_MAP.get("fcf")` returns `None`, `_result_metrics[metric] = None`, user sees `Fcf: N/A`. No warning, no suggestion.
2. **Concept drift**: user types a real metric name but the company tags the underlying GAAP concept with a name not in the priority tuple (e.g. a niche `RevenueContract` variant). `resolve_concept` returns `None` for the same silent outcome.

Scaling `METRIC_MAP` by hand doesn't work over time. The XBRL taxonomy grows, filers use inconsistent tags, and industry-specific KPIs (ARR, DAU, same-store-sales) aren't in companyfacts at all. We need a layer that self-heals: when the deterministic path fails, discover the right concept, verify it, cache it, and surface the discovery in the citation so the trust property is preserved.

## Goals

- Make `edgarpack query` return useful, cited answers where it currently returns `N/A`.
- Keep the deterministic fast path unchanged for existing metrics. Zero added cost on a hit.
- Cache every learning so subsequent queries are free.
- Preserve the "every number has a visible source" trust property — learned values are clearly marked.
- Keep the v1 implementation under ~500 LOC plus tests.
- No new third-party runtime dependencies.

## Non-goals (v1)

- **Layer B (KPI extraction from pack prose/tables).** Deferred to v2. Biggest coverage gain but requires a different mechanism (pack markdown walk, not companyfacts walk) and blows up the PR.
- **Cross-company triangulation.** Needs a much larger learned dataset before the signal is useful.
- **Embedding models.** Fuzzy match + LLM covers v1's cases; embeddings are 200MB of binary bloat.
- **Automatic PRs back to `METRIC_MAP`.** A `learned list --hit-count > 5` query tells you what to promote by hand.
- **Pre-warming during `build`.** Adds latency to the build path. Learning stays reactive to `query`.

## The resolution ladder

```
query(company, metric)
  |
  v
[Layer 0] Alias map (layer_zero.resolve_alias)
  "fcf" -> "free_cash_flow"
  Unknown name -> raise MetricNotFound with suggestions
  |
  v
[Deterministic path] METRIC_MAP + resolve_concept + select_period (unchanged)
  hit  -> CitedValue(source="hardcoded")                 no badge
  miss
  |
  v
[Layer A] self_heal.try_learn(metric, facts, cik, prior_year_cited)
  1. registry lookup: (cik, metric) -> hit -> CitedValue(source="learned:cached")
  2. fuzzy match over this company's concept list + metric hint dict
     match -> verify -> CitedValue(source="learned:fuzzy")
  3. LLM propose via codex/claude subprocess (if on PATH)
     match -> verify -> CitedValue(source="learned:llm")
  4. verifier: order-of-magnitude check against prior_year_cited
     pass -> verified=true;  fail -> verified=false (kept, but badged warning)
  miss
  |
  v
Return None with structured diagnostic:
  - what metric name was requested
  - what alias resolved it to
  - which concepts were tried
  - what the fuzzy match score was
  - whether LLM was available
  - what the user can do next
```

## Module layout

```
edgarpack/query/
├── concepts.py              (modified — add METRIC_ALIASES + resolve_alias)
├── models.py                (modified — add `source` field to CitedValue)
├── layer_zero.py            (new — ~40 LOC, alias map + resolve_alias helper
│                             + MetricNotFound exception)
├── learned_registry.py      (new — ~120 LOC, SQLite DAO for learned_concepts table)
├── self_heal.py             (new — ~300 LOC, fuzzy + llm + verify + orchestrator)
└── financials.py            (modified — one fallback call site, alias dereference)

edgarpack/cli.py             (modified — source badge rendering,
                               --strict flag, `edgarpack learned` subcommand)
```

Total new/modified: 6 files. Total new LOC: ~500 in source + ~300 in tests.

## Data: the learned_concepts table

New table in the existing `~/.edgarpack/registry.db` (owned by `edgarpack/query/learned_registry.py`, separate from `harvest/registry.py` which owns the `packs` table).

```sql
CREATE TABLE IF NOT EXISTS learned_concepts (
    cik           TEXT NOT NULL,
    metric        TEXT NOT NULL,
    concept       TEXT NOT NULL,
    taxonomy      TEXT NOT NULL,
    source        TEXT NOT NULL,        -- 'fuzzy' | 'llm' | 'user'
    verified      INTEGER NOT NULL,     -- 0 or 1
    verif_method  TEXT,                 -- 'order_of_magnitude' | 'manual' | NULL
    value_sample  REAL,
    learned_at    TEXT NOT NULL,        -- ISO-8601
    hit_count     INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (cik, metric)
);

CREATE INDEX IF NOT EXISTS idx_learned_source ON learned_concepts(source);
CREATE INDEX IF NOT EXISTS idx_learned_hit_count ON learned_concepts(hit_count DESC);
```

## Layer 0 — alias map

```python
# edgarpack/query/layer_zero.py

METRIC_ALIASES: dict[str, str] = {
    "fcf":    "free_cash_flow",
    "opinc":  "operating_income",
    "rev":    "revenue",
    "ni":     "net_income",
    "da":     "depreciation_amortization",
    "sbc":    "stock_based_compensation",
    "rd":     "rd_expense",
    "sga":    "sga_expense",
    "cogs":   "cost_of_revenue",
    "gp":     "gross_profit",
    "ocf":    "operating_cash_flow",
    "capex":  "capex",                 # identity mapping, harmless
    "eps":    "eps_diluted",           # diluted is the common request
    "shares": "shares_diluted",
}
```

`resolve_alias(name)` lowercases + strips the input, returns the canonical name if it's an alias, otherwise returns the input unchanged. Called in `financials.financials()` before `METRIC_MAP.get()`.

If the resolved name is still not in `METRIC_MAP`, raise `MetricNotFound(name, suggestions=close_matches(name, METRIC_MAP.keys(), n=3))` instead of returning `None`. The CLI catches `MetricNotFound` and prints a clear "did you mean" error.

## Layer A — self-heal

### Inputs
- `metric` (str, canonical name after alias resolution)
- `meta` (MetricMeta from METRIC_MAP)
- `facts` (companyfacts blob already loaded)
- `cik` (str)
- `company` (str)
- `prior_year_cited` (CitedValue | None — for verification. Passed in from `financials()` which computes it on demand.)
- `doc_map` (dict — for building CitedValue with primary_document)

### Output
- `CitedValue | DerivedValue | None`. `source` field on the returned value reflects how it was learned.

### Orchestration

```python
async def try_learn(metric, meta, facts, cik, company, prior_year_cited, doc_map):
    # 1. Registry hit
    cached = LearnedRegistry().lookup(cik, metric)
    if cached is not None:
        LearnedRegistry().bump_hit_count(cik, metric)
        return _resolve_cached(cached, facts, company, cik, doc_map)

    # 2. Build candidate list from company's actual concepts
    candidates = _company_concepts(facts)
    if not candidates:
        return None

    # 3. Fuzzy match
    proposed = _fuzzy_match(metric, candidates, hints=METRIC_HINTS.get(metric, ()))
    source = "fuzzy"

    # 4. LLM fallback
    if proposed is None and _llm_backend_available():
        proposed = await _llm_propose(metric, company, candidates)
        source = "llm"

    if proposed is None:
        return None

    # 5. Verify
    cited, verified = _verify_and_build_cited(
        proposed, facts, meta, company, cik, metric, prior_year_cited, doc_map
    )
    if cited is None:
        return None

    # 6. Persist
    LearnedRegistry().upsert(
        cik=cik, metric=metric, concept=cited.concept, taxonomy=cited.taxonomy,
        source=source, verified=verified,
        verif_method="order_of_magnitude" if prior_year_cited else None,
        value_sample=cited.value,
    )
    cited.source = f"learned:{source}"
    return cited
```

### Fuzzy match

Tokenize both sides on CamelCase boundaries. Metric side also expands via a small hint dict:

```python
METRIC_HINTS: dict[str, tuple[str, ...]] = {
    "revenue":               ("revenue", "revenues", "sales", "contract"),
    "operating_income":      ("operating", "income", "profit", "loss"),
    "net_income":            ("net", "income", "profit", "loss"),
    "free_cash_flow":        ("free", "cash", "flow"),
    "operating_cash_flow":   ("cash", "flow", "operating"),
    "capex":                 ("capital", "expenditure", "propertyplant"),
    # ...~20 entries total
}
```

Score = `|metric_tokens ∩ concept_tokens| / |metric_tokens|`. Return the highest-scoring concept if score >= 0.5 AND the concept reports at least one non-None `val` in the companyfacts blob. Tie-break on the concept with the most recent fiscal year value.

### LLM propose

Subprocess dispatch to `codex` or `claude` CLI. Module-level detection at import time:

```python
import shutil
_LLM_CMD = None
for candidate in ("codex", "claude"):
    if shutil.which(candidate):
        _LLM_CMD = candidate
        break
```

Prompt (150 tokens including concept list):

```
You are resolving a financial metric to an XBRL concept.

Company: NVIDIA CORP
Requested metric: "operating_cash_flow"

Candidate concepts reported by this company (name: latest value in USD):
  NetCashProvidedByUsedInOperatingActivities: 28090000000
  NetCashProvidedByUsedInInvestingActivities: -9800000000
  NetCashProvidedByUsedInFinancingActivities: -12900000000
  ... [truncated to 30 concepts]

Which concept represents the requested metric? Return strict JSON, no prose:
{"concept": "ExactConceptName", "taxonomy": "us-gaap"}
or
null
```

`subprocess.run(..., capture_output=True, timeout=30, text=True)`. Parse stdout as JSON. Validate concept is in `candidates` (reject hallucinations). One LLM call per novel `(cik, metric)`, cached forever in the registry after the call succeeds.

### Order-of-magnitude verification

```python
def verify_order_of_magnitude(proposed_value: float, prior_year_value: float | None) -> bool:
    if prior_year_value is None or prior_year_value == 0:
        return False  # No ground truth -> mark unverified, still store
    ratio = abs(proposed_value / prior_year_value)
    return 0.25 <= ratio <= 4.0
```

Values within 4x up or down pass. Anything more is rejected as likely wrong-concept. Rejected mappings still get stored with `verified=0` so the user can manually promote via `edgarpack learned verify <cik> <metric>`.

## CitedValue.source field

```python
# edgarpack/query/models.py
class CitedValue(BaseModel):
    # ... existing fields ...
    source: str = "hardcoded"  # 'hardcoded' | 'learned:cached' | 'learned:fuzzy' | 'learned:llm' | 'learned:user'
```

Propagates through `DerivedValue` subclass automatically (it inherits). `to_cited_dict`, `to_lean_metric`, and `to_citation_record` all include it when it's not `"hardcoded"`.

## CLI surface

### Query-time changes

- Badge in table output: `$5.3B [L1 learned:fuzzy ✓]` for verified, `[L1 learned:llm ⚠]` for unverified. No badge for `hardcoded`.
- `--strict` flag: rejects any result with `source != "hardcoded"`, prints them as `N/A [strict mode]` with a footer explaining. For analysts who need zero-learned-mapping guarantees.
- `--format json` / `--format json-full`: the `source` field appears on every metric.

### New subcommand: `edgarpack learned`

```
edgarpack learned list [--cik X] [--metric Y] [--source fuzzy|llm|user] [--unverified]
edgarpack learned show <cik> <metric>
edgarpack learned verify <cik> <metric>
edgarpack learned clear [--cik X] [--metric Y] [--all]
```

- `list` prints a table of learned mappings, default shows verified ones only, `--unverified` flips it.
- `show` prints one row in full, including sample value and hit count.
- `verify` promotes an unverified mapping to `verified=1, verif_method='manual'`.
- `clear` deletes rows matching filters. `--all` required to clear everything, to prevent accidents.

## Failure modes and diagnostics

When `try_learn` returns `None`, `financials()` records a structured diagnostic on the `QueryResult` (new field `diagnostics: list[dict]`). Each diagnostic records:

```python
{
    "metric": "novel_metric",
    "alias_resolved_to": None,  # or the dereferenced name
    "concepts_tried": ["Revenues", "SalesRevenueNet", ...],
    "fuzzy_best_score": 0.33,
    "llm_backend_available": True,
    "llm_proposed": None,
    "verification_passed": False,
    "hint": "No matching concept found. Try `edgarpack query --force` to bypass cache, or inspect `edgarpack/query/concepts.py:METRIC_MAP` for the canonical metric names."
}
```

Table output adds a "Diagnostics" footer when any diagnostics are present.

## Trust properties preserved

1. Every number still has a citation with a filing URL and an anchor URL. Self-heal changes *which concept* was pulled, not *how* it was cited.
2. The default fast path is untouched — no LLM call, no subprocess, no registry hit on any value that resolves through `METRIC_MAP`.
3. Every learned value is visually distinct in table output.
4. `--strict` gives a one-flag escape hatch.
5. Every learned mapping has provenance in `registry.db`: who proposed it, when, what verified it, what sample validated it.
6. Layer 0 (alias map) is an explicit rename, not a learning mechanism — it's as trustworthy as METRIC_MAP itself.

## Anti-bloat guardrails

- No new third-party runtime dependencies. Alias map = dict literal. Fuzzy match = stdlib `re` + 20-entry hint dict. LLM = subprocess to an optional external binary. SQLite = stdlib.
- `self_heal.py` capped at 500 LOC. If it grows past that, split intentionally.
- `LearnedRegistry` is a thin DAO — no ORM, no migrations framework, just raw SQL.
- Fallback call site in `financials.py` is one conditional line. Rip it out and the system reverts to current behavior.
- Registry schema is append-only and drops cleanly. Delete a row -> re-learn on next miss.

## Success criteria

- `edgarpack query NVDA fcf --period lfy` returns the FCF value with a `[learned:alias]` indicator, or goes through the deterministic path if the alias resolution was enough.
- `edgarpack query <COMPANY> <NOVEL_METRIC> --period ltm` for a company that uses a non-standard GAAP tag returns the value with a `[learned:fuzzy]` or `[learned:llm]` badge, verified against the prior year.
- A second run of the same query hits the cache, no LLM call, same output.
- `edgarpack query <COMPANY> <UNKNOWN> --period ltm` returns a clear `MetricNotFound` error with suggestions, not a silent `N/A`.
- `edgarpack query NVDA revenue,fcf --period ltm --strict` either returns both values (because alias-only) or rejects fcf if it was learned.
- All existing tests pass unchanged.
- `edgarpack learned list` shows any mappings accumulated during the run.

## Out of scope (v2+)

- Layer B (KPI extraction from MD&A and segment tables).
- Cross-company triangulation (`--require-triangulated N`).
- A `learned promote` command that emits a METRIC_MAP PR diff.
- Embedding-based concept matching.
- Pre-warming the registry during `build`.
