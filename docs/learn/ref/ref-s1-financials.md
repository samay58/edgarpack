# Reference: query/s1_financials.py

`edgarpack/query/s1_financials.py` (616 lines)
`edgarpack/parse/s1_headings.py` (111 lines, covered in the [Build-time companion](#build-time-companion-parses1_headingspy) section below)

The pre-IPO snapshot extractor. Companyfacts is empty for filers that have not filed a 10-K / 10-Q / 20-F yet, and Cerebras-era S-1 primary documents carry no embedded iXBRL. The real numbers live in the filing's prose. This module pulls them out with one Haiku 4.5 call per filing, caches the result next to the pack, and feeds them into the existing `financials()` output as `CitedValue` rows tagged `s1_snapshot` or `s1_pro_forma`. See [Trail 7](../trail-7-s1-pre-ipo.md) for the end-to-end story.

Added in commit `b1bad08` (2026-04-25). The contract surface is `augment_with_s1_snapshot` (entry point) and the metric slug set in `METRIC_SLUGS`. Everything else is the cache, the prompt, the parser, and the registration-pack walker that supports those two.

---

## Data types

### `SnapshotFact`

```python
@dataclass(frozen=True)
class SnapshotFact:
    accession: str
    fiscal_year: int
    period_end: str           # ISO YYYY-MM-DD
    metric: str               # member of METRIC_SLUGS
    value_cents: int          # integer in the reporting currency's smallest unit
    currency: str             # ISO 4217
    is_audited: bool
    is_pro_forma: bool
    pro_forma_note: str | None
```

`edgarpack/query/s1_financials.py:39`. One financial figure extracted from one S-1 filing.

`value_cents` is always an integer in the smallest unit of `currency`: cents for USD, öre for SEK, and so on. The model is responsible for the scaling (the prompt at line 178 specifies the rules in detail). Negative values represent losses. Per-share metrics are also expressed in cents-per-share. Share counts are stored as `count * 100` to keep one type rule across the whole struct; consumers divide by the per-metric divisor in `_UNIT_FOR_METRIC`.

`is_audited` and `is_pro_forma` are independent flags. A pro-forma row is by definition unaudited, but an unaudited row is not necessarily pro-forma (interim figures, for example). `pick_snapshot_fact` reads both. `pro_forma_note` is the verbatim assumption text from the filing, surfaced as a footnote in the renderer.

`accession` is the SEC accession number of the filing the fact came from. It propagates into `CitedValue.accession` so the renderer can build the inline marker `[S-1, accn-short]`.

### `SnapshotResult`

```python
@dataclass(frozen=True)
class SnapshotResult:
    schema_version: int
    accession: str
    extracted_at: str         # ISO 8601 UTC
    extraction_status: str    # "ok" | "llm_parse_failed" | "no_financial_data_found" | "no_api_key"
    source_sha256: str
    model: str
    facts: list[SnapshotFact]
```

`edgarpack/query/s1_financials.py:63`. The on-disk cache record. Written to `<pack_dir>/s1_financials.json` after every extraction, including failures.

`schema_version` is the cache invalidation knob for code changes. Bump `SCHEMA_VERSION` (line 297) and every existing cache becomes stale automatically.

`source_sha256` is the cache invalidation knob for source changes: SHA256 of the first 50KB of `<pack_dir>/filing.full.md`. The cap matters because Selected Financial Data is always near the top of an S-1 and hashing the entire file would slow the cache check on every query for unrelated edits.

`extraction_status` is a four-valued enum, not just a success flag. Each value drives different downstream behavior: `ok` returns facts; `no_financial_data_found` and `llm_parse_failed` return zero facts but cache the empty result so the LLM call doesn't repeat; `no_api_key` is the only status that does NOT come from `extract_or_load_snapshot` directly (it's set by `augment_with_s1_snapshot` when the Anthropic import fails) and it triggers placeholder `CitedValue` rows so the CLI can print a helpful hint.

### `METRIC_SLUGS`

```python
METRIC_SLUGS: frozenset[str] = frozenset({
    "revenue", "gross_profit", "operating_income_loss", "net_income_loss",
    "cash_and_equivalents", "total_assets", "stockholders_equity",
    "shares_outstanding_basic", "eps_basic",
})
```

`edgarpack/query/s1_financials.py:24`. The closed set of metrics the S-1 path can fill. Anything outside this set falls through unchanged.

The set must stay in sync with `METRIC_MAP` in `edgarpack/query/metric_map.py`. A slug present here but missing in `metric_map` would extract successfully and then fail to render. The prompt template embeds a sorted list of these slugs at the bottom (`build_extraction_prompt` line 197) so the model can only emit valid metrics.

---

## Functions

### Section detection

#### `find_financial_data_section(markdown: str) -> str | None`

`edgarpack/query/s1_financials.py:135`.

**Purpose**: locate the Selected Financial Data section body in a packed S-1 markdown file.

**Inputs**: `markdown` is the entire `filing.full.md` contents.

**Returns**: the section body capped at 50KB, or `None` if no canonical heading matched.

**How it works**:

1. Searches for one of five canonical heading phrasings (`_FINANCIAL_DATA_HEADINGS`, line 116) at H1 / H2 / H3, case-insensitive. The phrasings cover Cerebras's "Selected Financial Data", Klarna's "SELECTED FINANCIAL DATA", and the three "Summary" / "Historical" / "Consolidated" variants.
2. Anchors at the heading start and walks forward until it finds the next H1 or H2. That endpoint becomes the section boundary so adjacent sections (Use of Proceeds, MD&A) don't bleed in.
3. Truncates to `_SECTION_CAP_CHARS` (50,000) as a final safety net for filings with malformed TOCs that absorb body text into one giant section.

**Design notes**: the regex requires a heading character (`#`) at line start; it intentionally does not match in-prose mentions of "Selected Financial Data". The 50KB cap is also a cost guard: it keeps the prompt well under Haiku's context window even if the boundary detection fails.

### LLM extraction

#### `build_extraction_prompt(section_text: str) -> str`

`edgarpack/query/s1_financials.py:197`. Pure function that fills the prompt template (line 163) with the section text and appends a sorted list of allowed metric slugs. The system prompt (line 156) is separate and constant; together they instruct the model to return ONLY a JSON array, refuse fabrication, and apply the scaling rules verbatim.

#### `_call_haiku_extract(section_text: str) -> str`

`edgarpack/query/s1_financials.py:230`. Awaitable. Constructs the system + user message pair and calls `claude-haiku-4-5-20251001` (`MODEL_ID`, line 226) with `max_tokens=4000`. Concatenates all text content blocks from the response. Raises `RuntimeError` with installation guidance if the `anthropic` package isn't available; that exception is caught by `extract_or_load_snapshot` and turned into `extraction_status="no_api_key"`.

#### `parse_llm_response(raw: str, *, accession: str) -> list[SnapshotFact]`

`edgarpack/query/s1_financials.py:252`.

**Purpose**: turn the model's JSON response into validated `SnapshotFact` records.

**Inputs**:
- `raw` (str): the model's response text, possibly wrapped in `\`\`\`json ... \`\`\`` fences.
- `accession` (str): the filing accession to stamp on every produced fact.

**Returns**: a list of `SnapshotFact`, possibly empty. Raises `ValueError` for unparseable output (empty string, non-JSON, non-array).

**How it works**:

1. Strips code fences via `_strip_code_fences` (line 204). Handles both fenced and un-fenced responses.
2. Parses as JSON. Raises `ValueError` on `json.JSONDecodeError` so callers can mark the extraction failed and cache that fact.
3. Walks each row. Drops any row missing one of the seven `_REQUIRED_KEYS` (line 215) or whose `metric` is not in `METRIC_SLUGS`. Drops any row whose field types can't be coerced.
4. Builds `SnapshotFact` records. The `accession` parameter is stamped on every fact; the model never produces accession numbers itself.

**Design notes**: validation is conservative. Any malformed row is silently dropped rather than raising, because one bad row should not poison the entire extraction. But complete parse failure (the model returned something that wasn't a JSON array) raises so the caller can record `extraction_status="llm_parse_failed"`.

### Cache layer

#### `source_sha256_for_pack(pack_dir: Path) -> str`

`edgarpack/query/s1_financials.py:302`. Returns the SHA256 hex digest of the first 50KB of `<pack_dir>/filing.full.md`. Returns the empty string if the file doesn't exist, which forces a re-extraction on next call (since the cached `source_sha256` will not match).

#### `extract_or_load_snapshot(pack_dir: Path, *, force: bool = False) -> SnapshotResult`

`edgarpack/query/s1_financials.py:321`. Awaitable. The cache-aware extraction entry point.

**Inputs**:
- `pack_dir` (Path): a registration-class pack directory (must contain `manifest.json` and `filing.full.md`).
- `force` (bool, default False): bypass the cache.

**Returns**: a `SnapshotResult` for this pack. Always returns; never raises. The `extraction_status` field tells callers what happened.

**How it works**:

1. Reads the accession from `manifest.json` (`_read_manifest_accession`, line 310). Falls back to the directory name if the manifest is unreadable.
2. Computes the source hash and the cache file path (`<pack_dir>/s1_financials.json`).
3. Cache check: if the cache file exists, parses it. The cache hits only when the parsed `schema_version` AND `source_sha256` both match. Either mismatch invalidates.
4. On miss: reads `filing.full.md`, runs `find_financial_data_section`. If no section, writes a `no_financial_data_found` cache row and returns it.
5. Calls `_call_haiku_extract`. On `RuntimeError` (no api key) returns immediately with `extraction_status="no_api_key"` WITHOUT writing the cache. (The cache is keyed on `source_sha256`, not on api-key state; a no-api-key result should not poison subsequent runs that have a key.)
6. Calls `parse_llm_response`. On `ValueError` records `extraction_status="llm_parse_failed"`, empty facts.
7. Writes the cache file unconditionally for every status except `no_api_key`.

**Design notes**: the function is intentionally idempotent and side-effecting in one direction only. It writes the cache, never reads any file outside `pack_dir`, and never mutates `SnapshotFact` records after construction.

### CitedValue conversion

#### `snapshot_fact_to_cited_value(fact, *, cik, company, form_type, filed, concept) -> CitedValue`

`edgarpack/query/s1_financials.py:427`.

**Purpose**: convert one `SnapshotFact` into a `CitedValue` that the rest of the query path can render.

**How it works**:

1. Looks up the unit and divisor from `_UNIT_FOR_METRIC` (line 399). Monetary metrics divide by 100 to convert cents to dollars; share counts also divide by 100 (we stored `count * 100` to keep a uniform integer type).
2. Substitutes the actual currency code into the unit string when it isn't USD (`"USD"` becomes `"EUR"` for a Klarna fact, for example).
3. Sets `source = "s1_pro_forma" if fact.is_pro_forma else "s1_snapshot"`. This is the contract that propagates upward into rendering.
4. Parses `fact.period_end` as an ISO date, falling back to fiscal-year-end (Dec 31) if the field is malformed.
5. Constructs the `CitedValue` with `is_pro_forma` and `pro_forma_note` fields populated.

**Design notes**: the `concept` argument lets the caller stamp a default GAAP-like concept label (`_DEFAULT_CONCEPTS` map at line 414). This is purely cosmetic; snapshots are not sourced from XBRL tags. It exists so existing renderers that read `CitedValue.concept` see a non-empty string rather than the metric slug.

#### `pick_snapshot_fact(facts, *, metric, period) -> SnapshotFact | None`

`edgarpack/query/s1_financials.py:468`.

**Purpose**: select the single fact that matches a `(metric, period)` request.

**How it works**:

1. Filters `facts` to rows whose `metric` matches.
2. If `period == "pro-forma"`: takes only pro-forma rows, sorts by `(fiscal_year, period_end)` descending, returns the head.
3. Otherwise: takes only audited non-pro-forma rows, sorts the same way.
4. For `period in ("lfy", "mrp")`: returns the head (most recent audited fiscal year).
5. For `period == "lfy-N"`: returns the row at offset N, or None if N is out of range.
6. For any other period: returns None. The S-1 path does not handle quarterly periods, LTM, or anything that requires interim figures.

**Design notes**: pro-forma routing is always strict. A request for `period="pro-forma"` returns a pro-forma row or nothing; it never falls back to audited. A request for `lfy` returns audited or nothing; it never falls back to pro-forma. The renderer's `[S-1 pro-forma, ...]` marker is never wrong about which kind of fact was selected.

### Registration-pack walkers

#### `snapshots_for_cik(cik: str, pack_root: Path) -> list[SnapshotFact]`

`edgarpack/query/s1_financials.py:505`. Walks `pack_root` looking for manifests that match the CIK AND whose `form_type` passes `is_registration_form`. For each match, reads the colocated `s1_financials.json` cache and concatenates the facts. Returns a flat list across all of this CIK's registration packs.

The CIK match is on the raw string (no normalization). Callers normalize before calling. Manifests with no cache file are skipped silently.

#### `_find_latest_registration_pack(cik: str, pack_root: Path) -> Path | None`

`edgarpack/query/s1_financials.py:529`. Same walk as `snapshots_for_cik`, but instead of reading caches, returns the pack directory of the registration filing with the most recent `filing_date`. Used by `augment_with_s1_snapshot` when no caches exist for the CIK and one needs to be built.

#### `augment_with_s1_snapshot(*, result, cik, metrics, period, pack_root, company, form_type, filed) -> result`

`edgarpack/query/s1_financials.py:549`. Awaitable. The single public entry point for the periodic-filer integration in `query/financials.py`.

**Inputs**:
- `result`: the `QueryResult` whose `metrics` dict still has None cells.
- `cik`: the resolved CIK to look up.
- `metrics`: list of metric slugs to attempt (typed as `list[str]`; usually `list(result.metrics.keys())`).
- `period`: a period spec (`lfy`, `lfy-N`, `mrp`, `pro-forma`).
- `pack_root`: where to walk for registration-class packs.
- `company`, `form_type`, `filed`: stamp values for any `CitedValue` rows that get constructed.

**Returns**: the same `result`, possibly with cells filled in. Never raises.

**How it works**:

1. Calls `snapshots_for_cik` first. If any caches already exist, uses them directly.
2. If no caches exist, calls `_find_latest_registration_pack` to find one to build, then `extract_or_load_snapshot`. The result is cached for the next caller.
3. If extraction returns `extraction_status="no_api_key"`, injects placeholder `CitedValue` rows with `source="no_api_key"` for every still-empty metric, then returns. The CLI scans for this source value and prints a hint.
4. For each metric in `metrics`: if the cell is already non-None, skip. Otherwise calls `pick_snapshot_fact` and `snapshot_fact_to_cited_value`, writes the result into `result.metrics[metric]`.

**Design notes**: the function never overwrites a non-None cell. This is what makes the periodic-filer fallback safe: a 10-K filer with a follow-on S-1 filed will get its 10-K cells filled by the normal path, and `augment_with_s1_snapshot` will only fill cells the periodic path couldn't. The `period == "pro-forma"` gate at the call site (`financials.py:718`) is what makes pro-forma queries explicit: without that gate, no cell would be empty for a periodic filer and the snapshot path would never run.

---

## Build-time companion: `parse/s1_headings.py`

The 111-line module that makes S-1 sectionization possible. Lives in `edgarpack/parse/`, called from `pack/build.py:79` for any registration-class form. Out-of-line because it runs at pack build time, not at query time, but it's a hard prerequisite: without synthetic headings, `sectionize` produces a single mega-section and nothing in this ref would have a useful pack to read from.

### `extract_toc_sections(html: str) -> list[tuple[str, str]]`

`edgarpack/parse/s1_headings.py:69`. Walks the HTML for `<a href="#anchor_id">Section Title</a>` patterns and returns `[(anchor_id, cleaned_title)]`. Drops links whose text is in the title blacklist (`"table of contents"`, `"index"`, `"top"`, `"page"`, `"next"`, ...) or matches a pure page number / roman numeral. The first occurrence of each anchor wins; later body cross-references can't override the TOC's title for that anchor.

### `inject_s1_headings(html: str) -> str`

`edgarpack/parse/s1_headings.py:88`. Calls `extract_toc_sections`, then for each `(anchor, title)` finds the first element carrying `id="anchor"` and inserts `<h2>{title}</h2>` immediately before it (regex pattern at line 105). HTML-escapes the title before injection. Uses `count=1` per anchor so the same anchor in the body twice (which shouldn't happen, but does in malformed filings) only gets one heading.

A no-op when there are no TOC links or no matching ids. Safe to call defensively for any registration form.

### Why TOC-driven instead of font-size-driven

The natural alternative is to detect headings by font-size or font-weight inspection. That fails for Cerebras-class S-1s because the body's largest font is 12pt, headings are at the same point size as surrounding prose, and they're split across multiple `<font>` tags so a token-level scan sees fragments. The TOC links and matching `id=` markers are the only structural cue that's reliable across Cerebras, Klarna, and the other modern S-1 renderers.

### Order in the parse pipeline

`pack/build.py:74-79` runs `inject_s1_headings` after `strip_ixbrl` (no iXBRL in S-1s, so no-op anyway) but BEFORE `clean_html`. The order matters: `clean_html` strips most attributes, including `id=`. If injection ran after, the anchors would already be gone and there'd be nothing to match against.

---

## Invariants

- `value_cents` is always an integer in the smallest unit of the row's currency. Per-share metrics use cents-per-share. Share counts use `count * 100`. Enforced by the prompt rules at `s1_financials.py:178` and the type coercion in `parse_llm_response`.
- `SnapshotResult` is written to disk for every extraction outcome except `no_api_key`. A second call with the same source content does not re-prompt the model. Enforced by the cache check in `extract_or_load_snapshot:327`.
- The cache is invalidated on either source content change (SHA256 mismatch on the first 50KB of `filing.full.md`) or schema bump. Enforced by the dual condition at `s1_financials.py:332-336`.
- `pick_snapshot_fact` never falls back across the audited / pro-forma boundary. A `pro-forma` request returns a pro-forma row or nothing; an `lfy` request returns an audited row or nothing. Enforced by the two filter blocks at `s1_financials.py:478-489`.
- `augment_with_s1_snapshot` never overwrites a cell that is already non-None. Enforced by the `if current is not None: continue` guard at line 602.
- Every fact's `accession` is stamped by the caller (`parse_llm_response`), not by the model. The model can hallucinate values; it cannot hallucinate which filing those values came from. Enforced at `s1_financials.py:279`.
- `inject_s1_headings` runs before `clean_html` in the build pipeline; the order cannot be reversed because `clean_html` strips the `id=` attributes the injection relies on. Enforced by the call order in `pack/build.py:74-79`.

---

## What this module does not do

- **It does not render.** Producing the table marker (`[S-1, accn-short]` or `[S-1 pro-forma, accn-short] *`) is the renderer's job, driven off `CitedValue.source`. See `cli.py:1574-1586`.
- **It does not handle quarterly periods.** S-1 facts are annual or pro-forma; `pick_snapshot_fact` returns None for any quarterly period spec. The periodic-filer path covers those, and S-1s rarely include quarterly tables.
- **It does not cross taxonomies.** Every fact assumes US-GAAP-equivalent concepts (the `_DEFAULT_CONCEPTS` map). Foreign filers using IFRS still extract correctly because the metric slugs are taxonomy-neutral, but the `concept` field on the `CitedValue` will be misleading for IFRS callers that read it.
- **It does not deduplicate.** If two registration packs for the same CIK both extract a `revenue` row for fiscal 2024, both end up in the list returned by `snapshots_for_cik`. `pick_snapshot_fact` sorts by `(fiscal_year, period_end)` descending and takes the head, so the most-recently-period-ending row wins; ties resolve by sort stability (insertion order from `rglob`). If you ever need stricter dedup, the change goes here.
- **It does not validate against companyfacts.** A periodic filer with a follow-on S-1 might have both an XBRL-sourced revenue and an S-1-sourced revenue for the same year. `augment_with_s1_snapshot` will not overwrite the XBRL value, but it also will not flag the discrepancy if the S-1 disagrees. That cross-check, if it ever exists, would live in `query/financials.py`, not here.
