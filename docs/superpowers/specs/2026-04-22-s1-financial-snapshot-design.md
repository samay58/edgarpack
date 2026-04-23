# S-1 Financial Snapshot for `edgarpack query`

**Date:** 2026-04-22
**Branch:** `feat/new-filer-s1-support` (ships with the rest of pre-IPO work)
**Blocks:** Cerebras demo completeness, merge to main
**Related:** `2026-04-22-new-filer-s1-support-design.md`, `2026-04-22-s1-html-parser-design.md`

## Product framing

`edgarpack query "Cerebras Systems" revenue` currently resolves the CIK and returns `Revenue: N/A`. The user's next move is to grep the filing or pivot to `edgarpack which`. That is a dead-end for the most common analyst question on a pre-IPO filer.

This spec makes `query` return real financial figures for S-1 filers, labeled clearly as S-1-sourced so no one mistakes them for 10-K output:

```
$ edgarpack query "Cerebras Systems" revenue
Cerebras Systems Inc. (CIK 0002021728)

FY2024 Revenue: $78.3M  [S-1 snapshot, 0001628280-24-041596]
FY2025 Revenue: $151.6M [S-1 snapshot, 0001628280-26-025762]
```

Once Cerebras files its first 10-K, that 10-K line replaces the S-1 line for the overlapping period automatically, and users see the transition in their own terminal. The S-1 line stays visible for years the 10-K doesn't yet cover.

## Constraints

1. **No regression** on existing 10-K / 10-Q / 20-F query paths. The Task 8 `is_registration_form` guard in `periods.py` stays untouched; that guard controls periodic selectors only.
2. **No parallel subsystem**. One new module, integrated into the existing `financials()` function as a fallback branch.
3. **Reuse existing Anthropic integration** from `edgarpack/pack/assets.py` (VLM descriptions). Same SDK, same opt-in extra, same sha256-keyed cache pattern.
4. **Cache aggressively**. Each extraction is a Haiku call (~2-3 seconds, ~$0.003). Results cache to disk and survive restarts.
5. **Fail soft**. Missing API key, network errors, or LLM parse failures return `N/A` with an actionable message, never crash `query`.

## Architecture spine

One new module: `edgarpack/query/s1_financials.py` (~180 LOC).

Public surface, three functions:

- `extract_or_load_snapshot(pack_dir: Path, force: bool = False) -> SnapshotResult`
- `snapshots_for_cik(cik: str, pack_root: Path) -> list[SnapshotFact]`
- `query_s1_fact(cik: str, metric: str, period: str, pack_root: Path) -> SnapshotFact | None`

One new data shape:

```python
@dataclass(frozen=True)
class SnapshotFact:
    accession: str
    fiscal_year: int
    period_end: str        # YYYY-MM-DD
    metric: str            # canonical METRIC_MAP slug
    value_cents: int       # integer cents in native currency
    currency: str          # ISO 4217, "USD" for Cerebras
    is_audited: bool
    is_pro_forma: bool
    pro_forma_note: str | None  # e.g. "assumes IPO price $32.50, midpoint"
    extracted_at: str      # ISO 8601
```

Facts persist per-pack as `<pack_dir>/s1_financials.json`. Storing per-pack keeps the cache inspectable, lets `--force` target specific filings, and avoids schema migration on the registry SQLite.

## Data flow

```
edgarpack query Cerebras revenue
        |
        v
query/financials.py::financials()
        |
        +-- fetch_company_facts(cik)     <-- empty for pre-IPO
        |
        +-- select via periods.py         <-- empty: is_registration_form guards
        |
        +-- NEW: if result is empty AND CIK has registration-class packs:
        |         call query_s1_fact(cik, metric, period, pack_root)
        |
        v
query/s1_financials.py::query_s1_fact()
        |
        +-- find most recent registration pack for CIK (prefer 424B > S-1/A > S-1)
        |
        +-- extract_or_load_snapshot(pack_dir):
        |     - return cached s1_financials.json if present and not force
        |     - else: read filing.full.md, call Haiku, cache, return
        |
        v
        SnapshotFact (or None if no match)
        |
        v
financials() wraps it as a QueryResult row with `source="s1_snapshot"`
and passes through to the existing table/JSON renderers.
```

## LLM extraction

Single Haiku 4.5 call per pack, prompt pinned to a strict JSON schema.

Input: the "Selected Financial Data" or "Summary Consolidated Financial Data" section of the filing markdown (typically ~5-10KB of dense tables). If that section is not detected, fall back to the first 50KB of the pack markdown so we still capture the prospectus-summary numbers.

Prompt skeleton:

```
You are extracting historical and pro-forma financial figures from an SEC S-1 filing.

From the text below, return ONLY a JSON array. Each element is one fact:

{
  "fiscal_year": 2024,
  "period_end": "2024-12-31",
  "metric": "revenue" | "gross_profit" | "operating_income_loss" | "net_income_loss"
          | "cash_and_equivalents" | "total_assets" | "stockholders_equity"
          | "shares_outstanding_basic" | "eps_basic",
  "value_cents": 78287000000,       # integer cents in NATIVE CURRENCY
  "currency": "USD",                # ISO 4217
  "is_audited": true,
  "is_pro_forma": false,
  "pro_forma_note": null
}

RULES:
- Do not fabricate. Only emit facts the filing explicitly states.
- Negative values (losses) use negative integers.
- If a row is pro-forma or assumes a specific IPO price, set is_pro_forma=true
  and record the assumption verbatim in pro_forma_note.
- If a row is unaudited (interim stub, MD&A forward looking), set is_audited=false.
- Skip any figure you are less than 90% confident about.

TEXT:
<up to 50KB of filing markdown>
```

LLM response → JSON parse → dataclass validation → disk cache.

Cache key: `sha256(pack_dir/filing.full.md)` (first 50KB). Rebuild triggers re-extraction automatically when the markdown changes.

## Integration into `query`

Minimal change to `edgarpack/query/financials.py`. The existing function already returns a result object; we add one fallback branch near the tail.

Current tail (simplified):
```python
cik, company_name = await resolve_filer_or_name(company, force=force)
facts_data = await fetch_company_facts(cik, force=force)
result = build_query_result_from_facts(facts_data, metrics, period, ...)
return result
```

New tail:
```python
cik, company_name = await resolve_filer_or_name(company, force=force)
facts_data = await fetch_company_facts(cik, force=force)
result = build_query_result_from_facts(facts_data, metrics, period, ...)

# Pre-IPO fallback: if every requested metric came back empty, check for
# a registration-class pack. 10-K data wins when both exist, so this only
# fires when periodic data is genuinely absent.
if result.all_metrics_empty():
    from .s1_financials import augment_with_s1_snapshot
    result = await augment_with_s1_snapshot(
        result, cik=cik, metrics=metrics, period=period, pack_root=out_dir
    )
return result
```

`augment_with_s1_snapshot` fills any still-empty metric cells with `SnapshotFact` rows, tagged with source="s1_snapshot" and the accession. Cells that 10-K or 10-Q populated remain untouched.

Precedence (10-K > S-1) is enforced by this cascade: if `build_query_result_from_facts` already filled a cell, `augment_with_s1_snapshot` sees it as non-empty and skips.

## Period selector behavior

No new keyword. The existing selectors adapt:

- `--period lfy` (default): most recent AUDITED historical year in the S-1. For Cerebras 2026 S-1, that's FY2025. Pro-forma rows are never returned from `lfy` unless the user asks for them.
- `--period lfy-1`: prior audited year. For Cerebras, FY2024.
- `--period lfy-2`: two years prior. May be missing if the S-1 only audits 2 years.
- `--period mrp` (most recent period): if the S-1 has a stub / interim period, return that; otherwise same as `lfy`.
- `--period ltm`, `--period mrq`: return `N/A` with note "`ltm` / `mrq` are not defined for pre-IPO filers; use `lfy` or `mrp`." Existing `periods.py` guards already do this; we preserve them.
- `--period pro-forma`: new explicit keyword. Returns pro-forma rows (only ones with `pro_forma_note`). No silent mixing with historical.

`periods.py` gains one function `is_registration_pseudo_period(period)` returning True for selectors we map against S-1 snapshot data. `parse_period_spec` is unchanged.

## Output labeling

Table renderer appends a citation marker per S-1-sourced cell:

```
                                FY2024          FY2025
Revenue              $78.3M  [S-1, 24-041596]  $151.6M  [S-1, 26-025762]
Net loss           $(259.2M) [S-1, 24-041596]  $(344.0M) [S-1, 26-025762]
Cash & equiv         $209.9M [S-1, 24-041596]  $1,243.1M [S-1, 26-025762]*

* Pro-forma at midpoint IPO price $32.50
```

- Accessions shortened to year-suffix form (`24-041596`) in table output; JSON keeps the full `0001628280-24-041596`.
- Pro-forma values carry `*` with a footnote holding the assumption.
- When an S-1 row would be overwritten by 10-K data for the same period, the S-1 row is dropped entirely. No two-line rendering.

JSON renderer adds `source` and `accession` fields per datapoint:
```json
{
  "value_cents": 78287000000,
  "currency": "USD",
  "period": "FY2024",
  "source": "s1_snapshot",
  "accession": "0001628280-24-041596",
  "is_audited": true,
  "is_pro_forma": false
}
```

## Pro-forma handling

Pro-forma rows are ingested and stored alongside historical, but NOT returned by default period selectors. A user has to ask for them explicitly:

```
edgarpack query Cerebras cash_and_equivalents --period pro-forma
```

This keeps `query Cerebras revenue` deterministic (no dependency on assumed IPO price) while making the pro-forma data accessible when the user wants to see the post-offering cash figure.

## Metrics in v1

All nine:

| Slug | S-1 table label examples |
|---|---|
| `revenue` | "Total revenue", "Revenue" |
| `gross_profit` | "Gross profit", "Total revenue less Total cost of revenue" |
| `operating_income_loss` | "Operating loss", "Income from operations" |
| `net_income_loss` | "Net loss", "Net income (loss)" |
| `cash_and_equivalents` | "Cash and cash equivalents" |
| `total_assets` | "Total assets" |
| `stockholders_equity` | "Total stockholders' equity (deficit)" |
| `shares_outstanding_basic` | "Weighted-average shares outstanding, basic" |
| `eps_basic` | "Net loss per share, basic" |

Each maps to the existing `METRIC_MAP` slug in `edgarpack/query/metric_map.py`. We do not invent new slugs; we extend the snapshot extractor to populate existing ones.

## Error handling

**No API key**: first extraction returns `N/A` per-metric; a single line prints once per `query` invocation:

```
Note: S-1 financial extraction requires ANTHROPIC_API_KEY. Install with
`pip install edgarpack[vlm]` and export your key. Disclosures available
via `edgarpack which`.
```

**LLM returns invalid JSON** (rare with strict prompt): log warning, return `N/A`, cache an empty result with `extraction_status: "llm_parse_failed"` so we do not retry on every query. `--force` resets.

**Network error / rate limit**: transient; return `N/A` without writing a cache file so the next `query` retries.

**Section not found**: if the filing has no "Selected Financial Data" AND the first 50KB has no numeric rows the LLM recognizes, cache `extraction_status: "no_financial_data_found"` and return `N/A`. Happens for filings that were empty placeholders (rare but possible).

## Storage schema

`<pack_dir>/s1_financials.json`:

```json
{
  "schema_version": 1,
  "accession": "0001628280-26-025762",
  "extracted_at": "2026-04-22T18:14:00Z",
  "extraction_status": "ok",
  "source_sha256": "abc123...",     // of filing.full.md[:50000]
  "model": "claude-haiku-4-5-20251001",
  "facts": [ {SnapshotFact dict}, {...} ]
}
```

Cache invalidation: the source_sha256 field lets callers detect when the underlying markdown changed (re-harvest, parser upgrade). `extract_or_load_snapshot(force=True)` bypasses the cache unconditionally.

## Kill-list

Items NOT in v1 (from user decisions + engineering boundaries):

- **FX conversion / USD normalization for non-USD filers**. F-1 filers get native-currency output with a `currency` field. v2 can add FX.
- **Segment and geographic revenue breakdowns**. Those live in disclosure extractors (Task 11), not in `query`.
- **Dual-path iXBRL / LLM extractor**. LLM-only in v1; one path, one prompt, one cache.
- **New custom metrics beyond the 9 listed**. Custom disclosures (`compute_hours_delivered`, `customer_concentration`) stay in `kpi_discover` / `which`.
- **Retroactive cache invalidation** on existing packs. Users rebuild with `--force` if they want to re-extract.
- **LLM-assisted period reconciliation across S-1 drafts**. If the 2024 S-1 reports FY2023 revenue as $X and the 2026 S-1 reports it as $Y (restated), we surface both per-accession; we do not try to reconcile.

## File-change map

| File | Change | Approx LOC |
|---|---|---|
| `edgarpack/query/s1_financials.py` | NEW: SnapshotFact, LLM prompt, extract_or_load_snapshot, query_s1_fact, augment_with_s1_snapshot | +220 |
| `edgarpack/query/financials.py` | Fallback branch at tail, result "all empty" detector | +25 |
| `edgarpack/query/periods.py` | Register `pro-forma` pseudo-period, `is_registration_pseudo_period` | +15 |
| `edgarpack/query/metric_map.py` | Ensure all 9 slugs present; add `stockholders_equity`, `eps_basic` if missing | +10 |
| `edgarpack/query/formatting.py` | Inline S-1 citation marker, pro-forma `*` + footnote | +30 |
| `edgarpack/cli.py` | JSON output adds source/accession/is_audited/is_pro_forma fields | +8 |
| `tests/test_s1_financials_extract.py` | NEW: LLM mocked, parse valid / invalid JSON, cache hit/miss | +120 |
| `tests/test_s1_financials_query_integration.py` | NEW: end-to-end `financials()` with S-1 fallback, 10-K precedence, pro-forma period | +140 |
| `tests/test_s1_financials_formatting.py` | NEW: citation markers, pro-forma footnote, JSON shape | +60 |
| `tests/fixtures/cerebras_selected_financial_data.md` | Real slice from Cerebras 2024 S-1 | +80 |
| **Non-test total** | | **~308** |
| **Test total** | | **~400** |

Non-test delta stays under 350 LOC, matching spec constraint. Heavy lifting is the LLM integration (~180 LOC) and formatting (~60 LOC across two files).

## Test plan

**Unit tests (fast, deterministic, mocked LLM)**:

1. Prompt builder includes Selected Financial Data section when present, falls back to pack-head otherwise.
2. JSON parse: valid LLM output → list of SnapshotFact. Invalid JSON → `extraction_status='llm_parse_failed'`.
3. Cache hit: second call with same source_sha256 returns cached facts without hitting LLM.
4. Cache miss on sha256 change: re-invokes LLM.
5. `--force` bypasses cache unconditionally.
6. Metric coverage: all 9 metrics map correctly from LLM output to SnapshotFact.
7. Pro-forma rows: `--period lfy` excludes them; `--period pro-forma` includes only them.
8. Audited-only filter: rows with `is_audited=false` are not returned by `lfy` / `lfy-N`.
9. Currency: non-USD filer returns facts with currency field populated.
10. Error path: missing ANTHROPIC_API_KEY prints helpful note and returns `N/A`.

**Integration tests (mocked SEC + mocked LLM)**:

11. Filer with only S-1 packs: `query Cerebras revenue --period lfy` returns S-1 snapshot cell with accession marker.
12. Filer with both S-1 and 10-K for overlapping FY: 10-K wins; S-1 is dropped from that year's cell.
13. Multi-period grid (`--period lfy,lfy-1,lfy-2`): cells filled from whichever source has data per period.
14. Pro-forma keyword: returns only pro-forma rows.
15. CLI smoke: `edgarpack query "Cerebras Systems" revenue --format json` emits the expected JSON shape including `source` and `accession`.

**Live-SEC smoke (opt-in, slow)**:

16. End-to-end against real Cerebras filings (requires ANTHROPIC_API_KEY in env): extract snapshot from cached pack, assert FY2024 revenue ≥ $70M (gives tolerance for S-1 restatement), assert at least 5 distinct fiscal years worth of facts across both S-1 packs combined.

## Acceptance

The demo command works with realistic output:

```bash
$ edgarpack query "Cerebras Systems" revenue --period lfy,lfy-1
                     FY2025                          FY2024
Revenue              $151.6M  [S-1, 26-025762]       $78.3M  [S-1, 24-041596]

$ edgarpack query "Cerebras Systems" net_income_loss --period lfy
                     FY2025
Net loss           $(344.0M)  [S-1, 26-025762]

$ edgarpack query "Cerebras Systems" revenue --format json
{
  "cik": "0002021728",
  "company": "Cerebras Systems Inc.",
  "rows": [
    {
      "metric": "revenue",
      "period": "FY2025",
      "value_cents": 15155100000000,
      "currency": "USD",
      "source": "s1_snapshot",
      "accession": "0001628280-26-025762",
      "is_audited": true,
      "is_pro_forma": false
    }
  ]
}
```

Full suite ≥ existing 1089 tests still pass. ~50 new tests in the new test files. Ruff check + format clean.

## Open questions deferred to implementation

- Exact section-name pattern for locating "Selected Financial Data" in the markdown. Cerebras uses that header; some filers use "Summary Consolidated Financial Data". Add both patterns, fallback to pack-head.
- Whether pro-forma rows merit their own JSON field or stay commingled with `rows` and filter-on-read. Default: commingled, with `is_pro_forma` as the filter.
- Whether to print the "extraction in progress" notice on first query call (~3s latency). Default: stderr hint once, no progress spinner.

## Ship sequence

1. Branch already open: `feat/new-filer-s1-support`. Continue on it.
2. Write `query/s1_financials.py` with mocked-LLM unit tests first (TDD).
3. Wire `financials()` fallback. Run the existing test suite to confirm no periodic regression.
4. Add formatting + JSON shape tests.
5. Live-SEC smoke against real Cerebras packs (requires `ANTHROPIC_API_KEY`).
6. Verify the three demo commands above render correctly.
7. Commit, push, proceed to merge.
