# Self-heal v2 (Layer B) — design spec

**Date**: 2026-04-11
**Status**: Approved via grill-me brainstorm
**Scope**: Layer B — industry KPI extraction from pack MD&A and segment sections. Layer 0 and Layer A already shipped in self-heal v1.
**Depends on**: `docs/superpowers/specs/2026-04-11-self-heal-v1-design.md` (v1 is live on main at merge `ab7edf7`).

## Problem

v1 solved concept drift: `METRIC_MAP` misses on real GAAP metrics get recovered via fuzzy match over the company's reported concepts, then an LLM fallback, then a cached learned mapping. That works for anything XBRL-tagged.

It does not cover the class of metrics that management reports in prose and tables but never encodes in XBRL: annual recurring revenue (ARR), net revenue retention (NRR), remaining performance obligations (RPO), daily active users (DAU), gross merchandise volume (GMV), same-store sales, take rate, and so on. These are the headline numbers in every SaaS, marketplace, and consumer company's MD&A, and `edgarpack query CRWD arr --period lfy` currently errors with `MetricNotFound` because "arr" is neither in `METRIC_MAP` nor in the alias map.

Layer B closes that gap by reading the pack's markdown and extracting the value with an LLM scoped to the MD&A and key-metrics sections, verifying the result against the prior filing's value, and caching the outcome per `(cik, accession, metric)`.

## Goals

1. Extract reported KPIs from pack prose when they exist, return them as fully-cited `CitedValue`s with an anchor URL to the exact span.
2. Preserve the v1 trust properties: every Layer B value carries a visible source badge, `--strict` rejects it, the LLM's quote must be a literal substring of the source text, failures produce structured diagnostics rather than silent N/A.
3. Cache per-filing so repeated queries are free. Layer B is latency-heavy on first call (LLM subprocess) and must be zero-cost on subsequent calls.
4. Keep the v2 implementation bounded: one new file, one DB migration, one fallback call site in `financials.py`, and a 25-30 entry KPI catalog.
5. Zero new third-party runtime dependencies. All LLM work stays on the subprocess path Layer A already uses.

## Non-goals (v2)

- **Chunking and retrieval over the full pack** (RAG). The MD&A + key-metrics slice of a typical 10-K fits in one LLM call. Chunking adds complexity we don't need yet.
- **Embedding-based KPI matching**. The hand-curated catalog is bounded and small; embeddings are bloat.
- **Cross-company triangulation**. Needs a bigger dataset than v2 will have.
- **Auto-building packs**. If a pack doesn't exist, Layer B errors cleanly and tells the user to run `edgarpack build`. No surprise builds.
- **Industry-specific catalog filtering** at query time. The `industry` field is recorded on each KPI entry but not used by the selector. It's there for a future `edgarpack learned suggest --industry saas` command that won't ship in v2.
- **`edgarpack learned promote`** to emit catalog PR diffs.

## The resolution ladder (v2)

```
edgarpack query CRWD arr --period lfy
  |
  v
[Layer 0] alias map + unknown-metric guard
  - Alias map has no entry for "arr" (it's canonical, not an alias)
  - Unknown-metric check now sees KPI_CATALOG alongside METRIC_MAP:
    "arr" is in KPI_CATALOG -> accept, don't raise
  |
  v
[METRIC_MAP lookup]
  - "arr" not in METRIC_MAP
  - financials() enters the non-derived branch, resolve_concept returns None
  |
  v
[Layer A] try_learn
  - Builds company concept list from facts blob
  - Fuzzy match over "arr" tokens fails (short-token filter drops "arr")
  - LLM fallback returns null (no GAAP concept represents ARR)
  - Returns None
  |
  v
[Layer B] try_extract_kpi
  1. KPI_CATALOG lookup -> hit: KpiDef(phrases=("annual recurring revenue",
     "ARR", "ending ARR"), unit_hint="USD")
  2. Period -> filing resolution:
       - period="lfy"  -> most recent 10-K
       - period="mrq"  -> most recent 10-Q
       - period="ltm"  -> most recent 10-Q (same as mrq, because LTM is
                          a computed view; Layer B reads point-in-time
                          reports, not computed trailing sums)
  3. PackRegistry.list_packs(cik=CRWD_CIK, form_type="10-K", limit=5)
       returns rows sorted by filing_date DESC. Take [0] for lfy,
       [1] for annual:2, etc. Empty list -> no pack.
  4. If None: return structured error
       "KPI extraction requires a built pack. Run:
          edgarpack build --cik 0001535527 --form 10-K --out ./packs"
  5. Load pack_dir/manifest.json -> list of sections with IDs + paths
  6. Select sections whose IDs match any of:
       - '^10k_parti_item7'    (MD&A)
       - '^10k_parti_item7a'   (market risk / sometimes key metrics)
       - '_segment'            (segment reporting)
       - '_key_metric'
       - '_operating_data'
       - '_key_performance_indicator'
  7. Read the selected section .md files from disk, concat, trim to
     ~15K tokens (stdlib character count / 4 heuristic; no tiktoken
     dependency required here).
  8. Build extraction prompt with KPI phrases + text.
  9. LLM subprocess (codex or claude) with 45s timeout. Parse JSON.
  10. Anti-hallucination: verify response.excerpt is a literal substring
      of the concatenated source text. Reject otherwise.
  11. If confidence is "not_found" or "ambiguous": structured diagnostic,
      nothing cached. Return None.
  12. Build a CitedValue with:
       - source="learned:kpi-llm"
       - value, unit from the response
       - concept=<literal KPI phrase that matched>
       - accession, filing_date, company, cik from the pack's manifest
       - primary_document from manifest
       - fact_id="" (no inline XBRL for prose values)
       - An anchor URL built with a text-fragment selector on the excerpt
  13. Verify via prior-filing cross-check:
       - Find the prior 10-K pack (second-most-recent). If none, mark
         verified=False.
       - Recursively call try_extract_kpi with _verify=False (to prevent
         infinite recursion).
       - Run verify_order_of_magnitude(current_value, prior_value) from
         Layer A.
       - Pass: verified=True, verif_method="prior_filing_crosscheck"
       - Fail or no prior: verified=False
  14. Persist to learned_concepts (now keyed by (cik, accession, metric))
      and return the CitedValue.
```

## Module layout

```
edgarpack/query/
├── self_heal.py                 # v1, unchanged
├── kpi_extract.py               # NEW, ~400 LOC
├── learned_registry.py          # v1, modified (one migration: add accession column)
├── layer_zero.py                # v1, modified (unknown-metric guard also checks KPI_CATALOG)
├── concepts.py                  # v1, re-exports KPI_CATALOG alongside METRIC_ALIASES
└── financials.py                # v1, modified (one new fallback call site after Layer A)
```

New test files:
```
tests/test_kpi_extract.py               # unit tests: catalog, section selection, prompt, parser
tests/test_kpi_extract_integration.py   # end-to-end with mocked LLM + tmp pack
tests/test_learned_registry_migration.py # schema migration test
```

## `kpi_extract.py` — public API

```python
@dataclass(frozen=True)
class KpiDef:
    phrases: tuple[str, ...]        # forms the LLM should search for in prose
    unit_hint: str                  # "USD" | "count" | "percent" | "days" | "pure"
    industry: tuple[str, ...] = ()  # SIC prefixes (empty = all industries)
    description: str = ""           # human-readable

KPI_CATALOG: dict[str, KpiDef] = {
    # ... 25-30 entries, see "KPI catalog" section below
}


def try_extract_kpi(
    metric: str,
    cik: str,
    company: str,
    period: str,
    *,
    registry_path: Path | None = None,
    pack_registry: PackRegistry | None = None,
    _verify: bool = True,
) -> CitedValue | None:
    """Layer B entry point. Extracts a KPI from a pack's MD&A/segment sections.

    Returns a CitedValue with source='learned:kpi-llm' on success, or None
    on any failure (no pack, no catalog entry, LLM unavailable, not found,
    ambiguous, hallucinated excerpt, cache-write failure).

    `_verify=False` is used internally during prior-filing cross-check to
    prevent infinite recursion.
    """
```

Internal helpers (all private, all in the same file):

```python
def _resolve_filing_for_period(cik: str, period: str,
                                registry: PackRegistry) -> PackRecord | None:
    """Given a period selector, find the pack that represents it.

    Period -> form selection:
      lfy / annual:N   -> 10-K (Nth most recent for annual:N, most recent for lfy)
      mrq / quarterly:N -> 10-Q (Nth most recent for quarterly:N)
      mrp / ltm        -> most recent 10-K OR 10-Q by filing_date

    Implementation: call registry.list_packs(cik=cik, form_type=<form>,
    limit=max(5, N)) which returns rows sorted DESC by filing_date. Index
    into the list by period semantics. Returns None if the list is empty
    or the requested index is out of range.
    """

def _select_sections(manifest: dict) -> list[dict]:
    """Return manifest section entries whose IDs match MD&A / key-metrics
    patterns. Empty list if none match (pack may be a 10-Q or malformed)."""

_SECTION_PATTERNS = (
    re.compile(r"^10k_parti_item7"),      # MD&A
    re.compile(r"^10k_parti_item7a"),     # Quant/Qual disclosures about market risk
    re.compile(r"^10q_parti_item2"),      # MD&A for 10-Q
    re.compile(r"_segment"),              # segment reporting anywhere
    re.compile(r"_key_metric"),
    re.compile(r"_operating_data"),
    re.compile(r"_key_performance"),
)

def _read_section_text(pack_dir: Path, section_entries: list[dict]) -> str:
    """Concatenate section markdown from disk. Separator: '\\n\\n--- [id] ---\\n\\n'.
    Caller trims to token budget."""

def _trim_to_budget(text: str, max_chars: int = 60_000) -> str:
    """Rough char->token heuristic: 4 chars/token -> 15K tokens at 60K chars.
    Truncates mid-section with a clear '...[truncated]' marker so the LLM
    knows the boundary."""

def _build_extraction_prompt(metric: str, kpi_def: KpiDef, company: str,
                              filing_form: str, filing_date: str,
                              text: str) -> str:
    """Build the single-shot extraction prompt. See 'LLM prompt' section
    below for the exact template."""

def _extract_via_llm(prompt: str) -> dict | None:
    """Call codex/claude subprocess, parse JSON response, return the dict
    or None on any failure (no backend, timeout, non-zero, malformed)."""

def _verify_excerpt_in_text(excerpt: str, source_text: str) -> bool:
    """Anti-hallucination: excerpt must be a literal substring of source.
    Whitespace normalization applied to both sides before comparison."""

def _build_cited_from_extraction(
    response: dict, metric: str, kpi_def: KpiDef,
    pack_record: PackRecord, company: str, cik: str,
) -> CitedValue:
    """Build a CitedValue with source='learned:kpi-llm'. The anchor_url
    uses a text-fragment selector on the excerpt for deep-linking into
    the filing HTML."""

def _verify_against_prior_filing(
    current_value: float, metric: str, cik: str, company: str,
    current_form_type: str, current_filing_date: str,
    registry: PackRegistry, registry_path: Path | None,
) -> tuple[bool, str]:
    """Returns (verified, verif_method). Looks for the prior filing of the
    same form type, recursively calls try_extract_kpi with _verify=False,
    runs verify_order_of_magnitude on the pair."""
```

## KPI catalog (ships with v2)

Initial catalog of 26 entries covering SaaS, marketplace, retail, fintech, and consumer internet. Every entry was cross-checked against a real 10-K to confirm the phrasing appears verbatim.

```python
KPI_CATALOG = {
    # SaaS / subscription
    "arr":               KpiDef(phrases=("annual recurring revenue", "ARR", "ending ARR", "ARR of approximately"),  unit_hint="USD"),
    "nrr":               KpiDef(phrases=("net revenue retention", "dollar-based net retention", "net dollar retention", "NRR", "NDR"), unit_hint="percent"),
    "grr":               KpiDef(phrases=("gross revenue retention", "GRR", "gross dollar retention"), unit_hint="percent"),
    "rpo":               KpiDef(phrases=("remaining performance obligations", "RPO"), unit_hint="USD"),
    "crpo":              KpiDef(phrases=("current remaining performance obligations", "cRPO", "current RPO"), unit_hint="USD"),
    "billings":          KpiDef(phrases=("billings", "calculated billings"), unit_hint="USD"),
    "subscription_rev":  KpiDef(phrases=("subscription revenue",), unit_hint="USD"),
    "customer_count":    KpiDef(phrases=("total customers", "number of customers", "customers with ARR over"), unit_hint="count"),
    "magic_number":      KpiDef(phrases=("sales efficiency", "magic number"), unit_hint="pure"),

    # Consumer / internet
    "dau":               KpiDef(phrases=("daily active users", "DAU"), unit_hint="count"),
    "mau":               KpiDef(phrases=("monthly active users", "MAU"), unit_hint="count"),
    "qau":               KpiDef(phrases=("quarterly active users", "QAU"), unit_hint="count"),
    "arpu":              KpiDef(phrases=("average revenue per user", "ARPU"), unit_hint="USD"),
    "arppu":             KpiDef(phrases=("average revenue per paying user", "ARPPU"), unit_hint="USD"),
    "paying_users":      KpiDef(phrases=("paying users", "paid users", "paying subscribers"), unit_hint="count"),

    # Marketplace / platform
    "gmv":               KpiDef(phrases=("gross merchandise volume", "GMV", "gross transaction value", "gross booking value"), unit_hint="USD"),
    "gross_bookings":    KpiDef(phrases=("gross bookings",), unit_hint="USD"),
    "take_rate":         KpiDef(phrases=("take rate", "net take rate", "effective take rate"), unit_hint="percent"),
    "transactions":      KpiDef(phrases=("number of transactions", "total transactions", "transactions processed"), unit_hint="count"),

    # Retail / consumer goods
    "same_store_sales":  KpiDef(phrases=("same-store sales", "comparable store sales", "comparable sales", "comps"), unit_hint="percent"),
    "store_count":       KpiDef(phrases=("number of stores", "total stores", "store count"), unit_hint="count"),
    "avg_ticket":        KpiDef(phrases=("average ticket", "average transaction value", "average check"), unit_hint="USD"),

    # Fintech / payments
    "tpv":               KpiDef(phrases=("total payment volume", "TPV", "payment volume"), unit_hint="USD"),
    "active_accounts":   KpiDef(phrases=("active accounts", "active customer accounts"), unit_hint="count"),
    "aum":               KpiDef(phrases=("assets under management", "AUM"), unit_hint="USD"),
    "aua":               KpiDef(phrases=("assets under administration", "AUA"), unit_hint="USD"),
}
```

Adding a KPI after v2 ships is one dict entry plus (optionally) a unit test. No code changes, no migration.

## Registry schema migration

Layer A's `learned_concepts` table currently has `PRIMARY KEY (cik, metric)`. Layer B needs per-filing keying.

```sql
-- Migration (runs automatically at module import when the schema version is old)
ALTER TABLE learned_concepts ADD COLUMN accession TEXT NOT NULL DEFAULT '';

-- The old primary key stays but a new composite unique index does the real work:
CREATE UNIQUE INDEX IF NOT EXISTS idx_learned_cik_accn_metric
    ON learned_concepts(cik, accession, metric);
```

Layer A rows get `accession=''`. `LearnedRegistry.lookup(cik, metric, accession=None)` preserves old behavior. `lookup(cik, metric, accession='0001535527-24-000123')` checks the per-accession row first and falls back to the whole-company row.

To avoid migration landmines, the migration runs inside `_ensure_schema()` via a `PRAGMA user_version` check:

```python
def _ensure_schema(self) -> None:
    conn = self._get_conn()
    conn.executescript(_SCHEMA)
    current_version = conn.execute("PRAGMA user_version").fetchone()[0]
    if current_version < 1:
        conn.execute(
            "ALTER TABLE learned_concepts "
            "ADD COLUMN accession TEXT NOT NULL DEFAULT ''"
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_learned_cik_accn_metric "
            "ON learned_concepts(cik, accession, metric)"
        )
        conn.execute("PRAGMA user_version = 1")
    conn.commit()
```

## LLM extraction prompt

Single prompt, single LLM call per extraction. The prompt is tight (the catalog phrases are injected, the full section text is appended, the response format is strict JSON).

```
You are extracting a reported KPI from SEC filing prose. Be conservative.
Reject ambiguous cases. Never infer or compute; only extract values that
are stated literally.

Company: {company}
Filing: {form_type} filed {filing_date}
Metric: {metric_name}
Metric phrases to search for: {phrases}
Unit hint: {unit_hint}

Rules:
1. Search only the text below. Never use outside knowledge.
2. Only return a value if the text states it in unambiguous prose or a
   labeled table row. Forward-looking targets, ranges, and competitor
   figures do not count.
3. The value's unit must match the hint. If the text reports a different
   unit, normalize or return not_found.
4. The excerpt must be a verbatim substring of the text. No paraphrasing.
5. If multiple candidate values exist (e.g. a historical figure AND a
   current figure), return the most recent as-of the filing date.
6. If you cannot find the value with high confidence, return
   {"confidence": "not_found", ...} or {"confidence": "ambiguous", ...}.

Respond with strict JSON, no prose, no markdown fences:
  {
    "value": <number or null>,
    "unit": "USD" | "count" | "percent" | "days" | "pure" | null,
    "excerpt": "<verbatim substring of the text>",
    "section_id": "<the section ID the excerpt came from>",
    "confidence": "high" | "medium" | "low" | "not_found" | "ambiguous"
  }

TEXT:
{selected_section_markdown}
```

Parsing:
1. `json.loads(stdout)`. If that fails, try to extract a `{...}` substring via regex and re-parse (same salvage pattern as Layer A).
2. Validate shape: must be a dict with `confidence` present.
3. If `confidence in ("not_found", "ambiguous", "low")`: return None, structured diagnostic, no cache.
4. If `confidence in ("high", "medium")`: require `value`, `unit`, `excerpt`, `section_id` to be present and non-empty.
5. Run `_verify_excerpt_in_text(excerpt, source_text)`. Reject if false.
6. Return the parsed dict to the caller.

## Citation shape for Layer B values

The existing `CitedValue` model already has the fields we need. Layer B populates:

- `value`, `unit`, `metric`: from the LLM response.
- `concept`: the literal KPI phrase that matched (e.g. `"annual recurring revenue"`), NOT a GAAP tag. This distinguishes Layer B citations from Layer A in the JSON output.
- `period_start` / `period_end` / `fiscal_year` / `fiscal_period`: from the pack manifest's filing metadata. For KPIs extracted from a 10-K, these are the filing's fiscal year values.
- `form_type`, `filed`, `accession`, `cik`, `company`: from the pack manifest.
- `taxonomy`: `"kpi-prose"` (new sentinel, distinguishes from `"us-gaap"` / `"ifrs-full"`).
- `primary_document`: from the manifest.
- `fact_id`: `""` (empty — no inline XBRL for prose values).
- `warnings`: populated if verification failed.
- `source`: `"learned:kpi-llm"` (or `"learned:kpi-cached"` on registry hit).

The `anchor_url` property on `CitedValue` already falls back to `document_url` when `fact_id` is empty, and `document_url` builds a text-fragment URL (`#:~:text=...`) using `_concept_to_label(self.concept)`. For Layer B we want to anchor on the **excerpt** (which contains the actual number) rather than the concept label (which would match the first mention of the KPI phrase anywhere on the page).

The cleanest way to support this without disturbing v1 semantics is to add one optional field to `CitedValue`:

```python
class CitedValue(BaseModel):
    # ... existing fields ...
    source: str = "hardcoded"      # from v1
    excerpt_text: str = ""         # NEW in v2, Layer B only
```

And update `document_url` to prefer `excerpt_text` when it's set:

```python
    @property
    def document_url(self) -> str | None:
        if not self.primary_document:
            return None
        acc_nodash = self.accession.replace("-", "")
        cik_bare = self.cik.lstrip("0")
        base = f"{SEC_ARCHIVES_BASE}/{cik_bare}/{acc_nodash}/{self.primary_document}"
        if self.excerpt_text:
            # Layer B: anchor on the first ~8 words of the excerpt
            words = self.excerpt_text.split()[:8]
            fragment = quote(" ".join(words))
            return f"{base}#:~:text={fragment}"
        # v1 behavior: anchor on the concept label
        label = _concept_to_label(self.concept)
        return f"{base}#:~:text={quote(label)}"
```

v1 values have `excerpt_text=""` so their `document_url` is unchanged. Layer B values set `excerpt_text` to the LLM's extracted quote and get a tighter anchor. One field, one property branch, minimal blast radius.

## Failure modes

| Condition | Behavior | Cache |
|---|---|---|
| Metric not in `METRIC_MAP` and not in `KPI_CATALOG` | `MetricNotFound` with suggestions from both sets. Exit 2. | n/a |
| Metric in `KPI_CATALOG`, no pack exists for the requested period | Structured N/A: `"KPI extraction requires a built pack. Run: edgarpack build --cik X --form Y --out ./packs"`. | No |
| Pack exists, no matching section | Structured N/A: `"No MD&A, segment, or key-metrics sections found in pack. Pack may be malformed or for a form type without these sections."`. | No |
| LLM backend unavailable (no codex, no claude) | Structured N/A: `"KPI extraction requires an LLM backend. Install codex or claude CLI."`. | No |
| LLM subprocess times out (45s) | Structured N/A: `"LLM extraction timed out after 45s."`. | No |
| LLM returns invalid JSON after salvage | Structured N/A: `"LLM returned malformed response."`. Log response prefix for debugging. | No |
| LLM returns `confidence="not_found"` | Structured N/A: `"{metric} not disclosed in MD&A or segment sections of {form} filed {date}"`. | No |
| LLM returns `confidence="ambiguous"` | Structured N/A: `"Multiple candidate values for {metric}; cannot disambiguate"`. | No |
| LLM returns `confidence="low"` | Same as `not_found`. Low-confidence answers are not worth caching. | No |
| Excerpt is not a substring of source text | Rejected as hallucination. Treat as `not_found`. Log warning. | No |
| Verification passes (prior filing cross-check in order-of-magnitude range) | Return `CitedValue` with `verified=True`, badge `[learned:kpi-llm ✓]`. | Yes, verified=1 |
| Verification fails (prior filing value is >4x off) | Return `CitedValue` with `verified=False`, warning appended, badge `[learned:kpi-llm ⚠]`. | Yes, verified=0 |
| No prior filing available for verification | Return `CitedValue` with `verified=False`, warning `"No prior filing for cross-check"`, badge `[learned:kpi-llm ⚠]`. | Yes, verified=0 |

Every "Structured N/A" appends to the `QueryResult.diagnostics` list (new field, empty by default). The CLI renders diagnostics as a footer when present.

## CLI impact

Minimal. Layer B rides `edgarpack query` via auto-fallback. The only visible changes:

1. **`--strict` now rejects `learned:kpi-llm` too**. Existing code already checks `source != "hardcoded"`; no changes needed.
2. **Badge renders `[learned:kpi-llm ✓]` or `[learned:kpi-llm ⚠]`**. Already handled by the `_source_badge` helper in `_render_query_table`; no changes needed.
3. **Diagnostics footer**. When `QueryResult.diagnostics` is non-empty, render a footer section:
   ```
   Diagnostics:
     arr: KPI extraction requires a built pack. Run: edgarpack build --cik 0001535527 --form 10-K --out ./packs
   ```
4. **`edgarpack learned list --source kpi-llm`**: already works via the `--source` filter; just needs `kpi-llm` added to the choices.
5. **`edgarpack learned show`** prints the new `accession` field when non-empty.

No new subcommands.

## Anti-slop guarantees

1. **Literal-quote firewall**. Every Layer B value carries an `excerpt` field that is a verbatim substring of the source section. The extractor rejects any response whose excerpt fails the substring check. LLMs cannot invent numbers; they can only pick them out of the text you give them.
2. **Confidence gating**. Only `high` and `medium` confidence responses are returned as values. `low`, `not_found`, and `ambiguous` all collapse to structured N/A with reason.
3. **Prior-filing verification**. A KPI value is only `verified=True` if the same KPI from the prior filing's pack is within order-of-magnitude (0.25x–4x). Otherwise the badge shows `⚠`.
4. **Bounded catalog**. 26 entries at ship time. A reader can see every KPI Layer B attempts in one dict literal. No open-ended metric discovery in v2.
5. **Per-filing cache**. Recomputing is rare; every successful extraction is cached per `(cik, accession, metric)`. A query on the same filing runs the LLM exactly once in the lifetime of the registry.
6. **Structured diagnostics over silence**. Every failure path produces a human-readable reason, not a blank N/A. Users can always tell why a value was withheld.
7. **No auto-build**. Layer B refuses to silently fetch and parse filings in the middle of a query. If no pack exists, the error tells the user exactly what to run.
8. **`--strict` passthrough**. Users who need deterministic-only answers can pass `--strict` and Layer B values disappear entirely, just like Layer A values.

## Anti-bloat guardrails

- **One new source file** (`kpi_extract.py`), capped at 500 LOC. If section selection grows non-trivial, split into `_section_selector.py` rather than letting the main file drift.
- **One migration** (add `accession` column, new unique index, bump `PRAGMA user_version`). No new table.
- **No new runtime dependencies**. Catalog is a dict literal, PackRegistry already exists, LLM subprocess is the same path Layer A uses, text-fragment URL builder is ~10 lines.
- **No chunking, no retrieval layer, no embeddings**. Single prompt, single LLM call, section selection is regex patterns.
- **No new CLI command**. Auto-fallback on existing `edgarpack query`.
- **Diagnostic rendering reuses `_wrap_cli_text`**. No new formatting helper.
- **Tests co-locate with tests, not fixtures**. Synthetic manifest + synthetic section files built in `tempfile.TemporaryDirectory()` in each test. No fixture directory.

## Success criteria

1. `edgarpack query CRWD arr --period lfy` returns a CitedValue with source `learned:kpi-llm`, a badge, and an anchor URL pointing at the excerpt. Works against a real built pack and a live LLM backend.
2. Second run of the same query hits the cache. Zero LLM calls. Same value, same badge (`learned:kpi-cached`).
3. `edgarpack query CRWD arr --period lfy` with no pack built returns a structured error pointing at `edgarpack build`. Exit code 2.
4. `edgarpack query CRWD arr --period lfy` with a pack built but no LLM backend returns a structured diagnostic, not a crash.
5. `edgarpack query CRWD revenue,arr --period lfy` returns `revenue` via the hardcoded path with no badge, and `arr` via Layer B with a badge. Mixed paths work in one query.
6. `edgarpack query CRWD arr --period lfy --strict` rejects arr and keeps revenue hardcoded.
7. `edgarpack query CRWD xyzzy --period lfy` raises `MetricNotFound`. Unknown-metric detection covers both `METRIC_MAP` and `KPI_CATALOG`.
8. `edgarpack learned list --source kpi-llm` shows only Layer B rows.
9. A Layer B row created in v2 and a Layer A row created in v1 coexist in the same registry. The migration runs exactly once.
10. The LLM excerpt substring check rejects a hand-forged malicious response (fixture test with a non-substring excerpt).
11. The prior-filing cross-check fires when a second pack exists, and skips when it doesn't.
12. All Layer A tests, all existing tests pass unchanged. Layer A behavior is untouched.
13. The `_select_sections` function returns the expected set of section IDs for a known 10-K manifest fixture.

## Trust properties (summary table)

| Property | Layer A | Layer B |
|---|---|---|
| Citation points to exact filing | Yes (accession + fact_id anchor) | Yes (accession + text-fragment anchor via excerpt) |
| LLM output verified against source | Candidate list is closed; hallucinated concepts are rejected | Excerpt must be substring of source; hallucinated quotes are rejected |
| Value verified against ground truth | Order-of-magnitude vs prior year | Order-of-magnitude vs prior filing via recursive extraction |
| Visible provenance in output | `[learned:fuzzy|llm ✓|⚠]` | `[learned:kpi-llm ✓|⚠]` and `[learned:kpi-cached ✓|⚠]` |
| `--strict` escape hatch | Rejects all learned values | Rejects all learned values (same check) |
| Cache key | `(cik, metric)` | `(cik, accession, metric)` via schema migration |
| Zero cost on fast path | Yes (deterministic resolution first) | Yes (Layer B only runs when Layer A returned None) |

## Open items, deferred

- **Catalog curation tooling**. A `scripts/curate_kpi_catalog.py` that walks existing packs and suggests new catalog entries based on frequency of occurrence would be useful but is not v2.
- **Industry-aware suggestions**. The `industry` field on `KpiDef` is recorded for future use; `edgarpack learned suggest --industry saas` is not shipped.
- **Metric aliases for KPIs**. Layer 0's alias map is GAAP-focused; a future v2.1 might add `METRIC_ALIASES` entries like `"recurring_revenue" -> "arr"`.
- **Tracking catalog performance**. A `hit_count` column already exists from v1; `edgarpack learned stats` that reports extraction success rates per KPI is a future addition.

## Dependencies on v1

All of v1 is load-bearing:
- `METRIC_ALIASES` and `resolve_alias` (Layer 0)
- `LearnedRegistry` (extended via migration)
- `try_learn` (Layer A, runs before Layer B)
- `CitedValue.source` field (set to `learned:kpi-llm` by Layer B)
- `_source_badge` helper in `_render_query_table` (renders Layer B badges)
- `--strict` flag handler (rejects Layer B values automatically)
- `MetricNotFound` exception (raised when neither `METRIC_MAP` nor `KPI_CATALOG` has the name)
- `edgarpack learned` subcommand (lists Layer B rows via `--source` filter)

No v1 code is rewritten. v2 extends v1.
