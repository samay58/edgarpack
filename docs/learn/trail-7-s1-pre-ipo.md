# Trail 7: How `edgarpack query CRBRS revenue` works for a company that has never filed a 10-K

**Time**: ~14 minutes
**Prereq**: [trail-0-full-loop.md](trail-0-full-loop.md). This trail assumes you already know the periodic-filer query path and only walks the pre-IPO branches.
**Covers**: `edgarpack/cli.py`, `edgarpack/parse/s1_headings.py`, `edgarpack/pack/build.py` (registration branch), `edgarpack/sec/submissions.py:is_registration_form`, `edgarpack/query/financials.py` (S-1 augmentation pass), `edgarpack/query/s1_financials.py`, `edgarpack/diff/timeline.py:build_registration_timeline`, `edgarpack/query/kpi_discover.py:extract_s1_metrics_from_pack`

A pre-IPO filer breaks two assumptions trail-0 leaned on. The companyfacts API returns nothing because XBRL companyfacts is fed by 10-K / 10-Q / 20-F filings. The S-1 HTML often has no real headings, so `sectionize` has nothing to anchor on. The fix is split across the build path and the query path, with a third user-facing surface for redline review. You run `edgarpack query CRBRS revenue` and a number comes back. This trail walks why.

---

## 1. The form-family gate

Every fork in this trail asks the same question: is the form registration-class? The answer lives in one helper that all the other modules import.

```python
# edgarpack/sec/submissions.py:101
def is_registration_form(form_type: str) -> bool:
    if not form_type:
        return False
    normalized = normalize_form_type(form_type)
    return normalized in REGISTRATION_FORMS
```

The covered family is S-1, S-1/A, F-1, F-1/A, 424B1-5, and FWP. One predicate, used in five places: `pack/build.py` to swap parse modes, `query/periods.py` to keep S-1 facts out of LTM math, `query/s1_financials.py` to find the latest registration pack, `diff/timeline.py` to assemble the redline chain, and `query/kpi_discover.py` to choose between MD&A scan and S-1 metrics extraction. If you ever change what counts as registration-class, this is the only line to touch.

**Code**: `edgarpack/sec/submissions.py:101` (`is_registration_form`)

---

## 2. Build time: synthetic headings get injected before sectionize

You ran `edgarpack build` on the S-1 earlier. That run took a different parse path than a 10-K because `is_registration_form` returned True. The pack builder added one step before the standard pipeline.

```python
# edgarpack/pack/build.py:74
preserve = is_registration_form(form_type)
if preserve:
    html_stripped = inject_s1_headings(html_stripped)
html_cleaned = (
    clean_html(html_stripped, preserve_images=preserve)
    if preserve
    else clean_html(html_stripped)
)
```

The order matters. `clean_html` strips most attributes, including `id=`. If you injected headings after that pass, the anchor ids would already be gone.

`inject_s1_headings` reads the document's table of contents and rewrites the body. Cerebras-era S-1 HTML uses absolute-positioned divs and inline `<font>` tags instead of `<h1>` / `<h2>`. Section titles in the body are split across multiple `<font>` elements at the same point size as the surrounding prose. A heading detector that looks at font size or weight finds nothing.

```python
# edgarpack/parse/s1_headings.py:88
def inject_s1_headings(html: str) -> str:
    pairs = extract_toc_sections(html)
    if not pairs:
        return html

    result = html
    for anchor, title in pairs:
        safe_title = _html_mod.escape(title, quote=False)
        pattern = re.compile(
            rf'(<[a-z][a-z0-9]*\s+[^>]*\bid="{re.escape(anchor)}"[^>]*>)',
            re.IGNORECASE,
        )
        replacement = rf"<h2>{safe_title}</h2>\1"
        result = pattern.sub(replacement, result, count=1)
    return result
```

The TOC has `<a href="#anchor_id">Section Title</a>`. The body has `<div id="anchor_id">`. The injector pairs them and emits an `<h2>` immediately before each body container. From `sectionize`'s perspective the document now has explicit headings.

`extract_toc_sections` is the cleaning pass. It throws away leader-dot fragments ("Section .......... 12"), self-links to the TOC ("Table of Contents", "Index"), pagination markers ("Page", "Next"), and pure page numbers. The first occurrence of each anchor wins, so body cross-references that point back to a section don't override the TOC's title for that section.

The function is a no-op on filings that have no TOC links or no matching ids. That's why pack/build.py calls it unconditionally for any registration form without checking whether the specific filing needs it.

**Code**: `edgarpack/pack/build.py:74` (the registration branch in `_process_html_files_for_form`), `edgarpack/parse/s1_headings.py:88` (`inject_s1_headings`), `edgarpack/parse/s1_headings.py:69` (`extract_toc_sections`)

---

## 3. You run `edgarpack query CRBRS revenue`

The CLI handler is the same `_cmd_query` from trail-0. Identity resolves through `universe.toml` and falls through to `financials()`. From the resolver's view, CRBRS is just another ticker. The split happens deeper, inside `financials()`.

The first half of `financials()` runs unchanged from trail-0: companyfacts fetch, concept resolution, period selection, citation enrichment. For a pre-IPO filer, every cell it tries to fill comes back as None, because companyfacts is empty and the periodic-filer paths can't produce values.

```python
# edgarpack/query/financials.py:703
# Pre-IPO fallback: if any requested metric still has no value, try
# pulling it from cached S-1 snapshots for this CIK.
resolved_requested = [
    resolve_alias((m or "").strip().lower()) for m in _requested_metrics_list(metrics)
]
any_empty = any(result.metrics.get(m) is None for m in resolved_requested)
if any_empty or period == "pro-forma":
    from .s1_financials import augment_with_s1_snapshot

    root = Path(pack_root) if pack_root is not None else Path("./packs")
    result = await augment_with_s1_snapshot(
        result=result, cik=cik,
        metrics=list(result.metrics.keys()),
        period=period, pack_root=root,
        company=company_name, form_type="S-1",
    )
```

Two details to notice. The empty-cell check normalizes the user's requested metric names through `resolve_alias` before reading `result.metrics`. The result dict is keyed on the alias-normalized slug, so a caller passing `metrics=["Revenue"]` against a 10-K filer would still trigger this branch unless you alias-normalized first. That would do an unnecessary disk walk on every periodic query.

The other detail: the augmentation also fires when the user explicitly asks for `period == "pro-forma"`. That period is S-1-only. There's no XBRL fact for "pro-forma revenue assuming the offering closed." The user is signaling they want the S-1 path even if the cell happened to fill from somewhere else.

**Code**: `edgarpack/query/financials.py:703-730` (the augmentation gate inside `financials()`)

---

## 4. The S-1 snapshot extractor: cached or lazy

`augment_with_s1_snapshot` is the entry point for everything S-1-financial. Its job is to fill `result.metrics` cells that are still None.

```python
# edgarpack/query/s1_financials.py:567
facts = snapshots_for_cik(cik, pack_root=pack_root)

if not facts:
    latest_pack = _find_latest_registration_pack(cik, pack_root)
    if latest_pack is not None:
        extract_result = await extract_or_load_snapshot(latest_pack)
        ...
        facts = extract_result.facts
```

Three paths nest here. If any registration pack for this CIK already has a cached `s1_financials.json`, those facts get used directly. If none does, the function locates the most recent registration-class pack by filing date and lazily extracts a snapshot from it. If extraction can't run (no API key), the function injects placeholder `CitedValue` rows with `source="no_api_key"` so the CLI can print a helpful hint instead of leaving the user with bare N/A cells.

`extract_or_load_snapshot` itself is the cache layer:

```python
# edgarpack/query/s1_financials.py:321
async def extract_or_load_snapshot(pack_dir: Path, *, force: bool = False) -> SnapshotResult:
    pack_dir = Path(pack_dir)
    accession = _read_manifest_accession(pack_dir)
    source_hash = source_sha256_for_pack(pack_dir)
    cache_path = pack_dir / _CACHE_FILENAME

    if not force and cache_path.exists():
        try:
            cached = SnapshotResult.from_json(cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            cached = None
        if (
            cached is not None
            and cached.schema_version == SCHEMA_VERSION
            and cached.source_sha256 == source_hash
        ):
            return cached
```

The cache is keyed on schema version and a SHA256 of the first 50KB of `filing.full.md`. If you rebuild the pack and the markdown changes, the hash mismatches and the next query re-extracts. The schema-version check covers code changes to the snapshot format itself: bump `SCHEMA_VERSION` and every existing cache becomes stale automatically.

The "first 50KB" cap matters for cost. The Selected Financial Data section is always near the top of an S-1. Hashing the entire 4MB markdown file would be a big disk read on every cache check, and the hash would change for unrelated edits to the back of the document.

**Code**: `edgarpack/query/s1_financials.py:321` (`extract_or_load_snapshot`), `edgarpack/query/s1_financials.py:549` (`augment_with_s1_snapshot`)

---

## 5. Finding and prompting the right section

When the cache misses, `extract_or_load_snapshot` reads `filing.full.md`, locates the Selected Financial Data section, and prompts Haiku 4.5.

```python
# edgarpack/query/s1_financials.py:135
def find_financial_data_section(markdown: str) -> str | None:
    if not markdown:
        return None
    match = _FINDATA_RE.search(markdown)
    if not match:
        return None
    start = match.start()
    rest = markdown[start:]
    next_heading = re.search(r"\n\#{1,2}\s+\S", rest[1:])
    if next_heading is not None:
        end = 1 + next_heading.start()
        rest = rest[:end]
    return rest[:_SECTION_CAP_CHARS]
```

The regex matches five canonical phrasings: "Selected Consolidated Financial Data", "Summary Consolidated Financial Data", "Selected Financial Data", "Summary Financial Data", "Selected Historical Financial Data". The match is case-insensitive and anchored at H1-H3. The walker stops at the next H1 or H2 heading so adjacent sections (Use of Proceeds, MD&A) don't bleed in. The 50KB cap is a final safety net for filings whose TOC absorbs body text.

If `find_financial_data_section` returns None, the snapshot is cached with `extraction_status="no_financial_data_found"` and zero facts. The cache write happens unconditionally. A future query reading that cache sees the empty result and skips the LLM call.

The prompt itself is fixed in `s1_financials.py:163-201`. Two rules in it carry the most weight: scaling is the model's responsibility ("if the filing says '78,287' and the preamble says 'in thousands' then value_cents = 78,287 * 1000 * 100 = 7,828,700,000"), and pro-forma rows must mark themselves with `is_pro_forma=true` and quote the assumption verbatim. The downstream `pick_snapshot_fact` function uses the pro-forma flag to route facts to the right cells.

**Code**: `edgarpack/query/s1_financials.py:135` (`find_financial_data_section`), `edgarpack/query/s1_financials.py:163-201` (the prompt template)

---

## 6. From SnapshotFact to CitedValue

The model returns a JSON array. `parse_llm_response` validates each row, drops anything missing required keys or pointing at an out-of-set metric slug, and produces `SnapshotFact` records. Each fact carries the accession, the fiscal year, the period end, the metric slug, an integer `value_cents` in the reporting currency's smallest unit, the currency code, and two booleans: `is_audited` and `is_pro_forma`.

The CitedValue conversion is where the source provenance gets stamped.

```python
# edgarpack/query/s1_financials.py:427
def snapshot_fact_to_cited_value(...) -> CitedValue:
    unit, divisor = _UNIT_FOR_METRIC[fact.metric]
    if fact.currency != "USD":
        unit = unit.replace("USD", fact.currency)
    value = fact.value_cents / divisor if divisor else fact.value_cents
    source = "s1_pro_forma" if fact.is_pro_forma else "s1_snapshot"
    ...
    return CitedValue(
        ..., source=source, reporting_currency=fact.currency,
        is_pro_forma=fact.is_pro_forma,
        pro_forma_note=fact.pro_forma_note,
    )
```

The `source` field is the contract that propagates upward. Every renderer that touches CitedValue can ask "where did this number come from?" and get one of `sec`, `s1_snapshot`, `s1_pro_forma`, `hkex`, or `private`. The CLI table renderer reads it to attach an `[S-1, accn-short]` marker to S-1-sourced cells, and `[S-1 pro-forma, accn-short] *` to pro-forma cells with a footnote pointing at `pro_forma_note`. Same number, different provenance, marked clearly.

`pick_snapshot_fact` is what handles `--period`. For `lfy` or `mrp` it returns the most recent audited non-pro-forma fact. For `lfy-N` it walks back N years. For `pro-forma` it returns the most recent pro-forma fact and nothing else. This is why `--period=pro-forma` can succeed even when audited cells are also available: pick_snapshot_fact filters to pro-forma rows first.

**Code**: `edgarpack/query/s1_financials.py:252` (`parse_llm_response`), `edgarpack/query/s1_financials.py:427` (`snapshot_fact_to_cited_value`), `edgarpack/query/s1_financials.py:468` (`pick_snapshot_fact`)

---

## 7. The registration-form guard in periods.py

Trail-3 covered period selection in detail. The S-1 work added one tightening worth knowing about, because the failure mode without it is silent.

```python
# edgarpack/query/periods.py:267
def _is_annual(v: dict[str, Any]) -> bool:
    form = str(v.get("form", "")).upper()
    if is_registration_form(form):
        return False
    return str(v.get("fp", "")).upper() == "FY" or form in ("10-K", "10-K/A", "20-F", "20-F/A")
```

The same guard fires in `_is_quarter_form_type` (line 283). If a company files a 10-K and then later files an S-1 (a follow-on offering, for example), companyfacts contains both. Without the guard, `_annual_history` would treat S-1-reported figures as annual data points alongside 10-K rows. The S-1 numbers would slip into LTM and lfy-N math even though they aren't audited annual facts. The guard says: registration forms never count as annual or quarterly for period-selection purposes. They go through the snapshot path or not at all.

**Code**: `edgarpack/query/periods.py:267` (`_is_annual`), `edgarpack/query/periods.py:281` (`_is_quarter_form_type`)

---

## 8. The redline timeline: a different user surface

The other thing pre-IPO research wants is a redline. Companies file S-1, then S-1/A as the SEC asks for revisions, then 424B at pricing. Each amendment changes specific sections. `edgarpack timeline --series registration --cik <cik>` walks that chain.

```python
# edgarpack/cli.py:2327
def _render_registration_timeline(args: Any) -> int:
    from .diff.section_diff import diff_filings
    from .diff.timeline import build_registration_timeline
    from .query.kpi_discover import extract_s1_metrics_from_pack
    ...
    entries = build_registration_timeline(pack_root=pack_root, cik=args.cik)
```

`build_registration_timeline` walks `pack_root` looking for manifest.json files, filters to registration forms whose CIK matches, and sorts by filing date ascending so the redline goes oldest-to-newest.

```python
# edgarpack/diff/timeline.py:148
target = normalize_cik(cik)
entries: list[RegistrationTimelineEntry] = []
for manifest_path in Path(pack_root).rglob("manifest.json"):
    ...
    filing_cik = str(filing.get("cik", "")).strip()
    if not filing_cik or normalize_cik(filing_cik) != target:
        continue
```

The strict CIK check matters. The walker looks at every pack under the root, not just packs known to be for this filer. Manifests with a missing or empty CIK are skipped rather than silently included, which prevents a malformed pack from leaking another company's filings into the timeline.

After the timeline is built, the CLI prints a one-shot S-1 metrics summary for the latest filing (framing claims, use of proceeds, dilution, lockup, principal holders) by calling `kpi_discover.extract_s1_metrics_from_pack`. That's the same path trail-6 covers for `edgarpack which`. Then it diffs each consecutive pair with `diff_filings(detail="sections")` and prints overall change intensity plus the top-5 most interesting changed sections. The intensity score, change classification, and interest-score logic are derived layers; trail-7 stops at the surface they expose.

**Code**: `edgarpack/cli.py:2327` (`_render_registration_timeline`), `edgarpack/diff/timeline.py:136` (`build_registration_timeline`), `edgarpack/query/kpi_discover.py:837` (`extract_s1_metrics_from_pack`)

---

## 9. The handoff

The query path returns to `_cmd_query`, which then renders. From the CLI's point of view nothing about the render changed: the S-1 and pro-forma rows are CitedValues in `result.metrics` like everything else. The renderer attaches the `[S-1, ...]` markers because of the `source` field, and emits a one-line API-key hint when any CitedValue has `source="no_api_key"`.

```python
# edgarpack/cli.py:1992
scan_sources = [result] if len(periods) == 1 else list(results_by_period.values())
missing_key = any(
    getattr(v, "source", "") == "no_api_key"
    for r in scan_sources
    for v in (r.metrics or {}).values()
    if v is not None
)
if missing_key:
    print(_render_query_no_api_key_hint(), file=sys.stderr)
```

This works correctly across multi-period queries (`--period lfy,pro-forma`) because the scan walks every period's result, not just the first.

**Code**: `edgarpack/cli.py:1988-2000` (the no-api-key hint emission)

---

## Try it

You need `ANTHROPIC_API_KEY` exported and a built S-1 pack. The repo's universe ships with Cerebras (`CRBRS`).

1. Build a registration-class pack: `edgarpack build CRBRS --form S-1 --out ./packs` (one-time; the snapshot is cached after the first query).
2. Query a metric: `edgarpack query CRBRS revenue`. The first run does a Haiku call and writes `s1_financials.json` next to the pack's `manifest.json`. The second run reads from that cache.
3. Ask for the pro-forma figure explicitly: `edgarpack query CRBRS revenue --period=pro-forma`. Same data file, different `pick_snapshot_fact` branch.
4. Walk the redline: `edgarpack timeline --series registration --cik 0002021728 --packs ./packs`. Needs at least one S-1 amendment in `./packs` to print pair diffs.
5. Open the cache: `cat packs/CRBRS/<accession>/s1_financials.json`. Look at the `extraction_status` and the `facts` array. Compare against the filing's Selected Financial Data table.
6. Force a re-extraction: delete the cache file and re-run the query. The second pass re-prompts Haiku.

---

## Recap

The pre-IPO path is a tightly scoped fork. Build time runs `inject_s1_headings` so `sectionize` can find sections, gated by `is_registration_form`. Query time falls through the periodic path until every requested cell is None, then `augment_with_s1_snapshot` either reads cached `s1_financials.json` files or does one Haiku call against the most recent registration pack, caches the result with a SHA256 invalidation key, and writes `CitedValue` rows tagged `s1_snapshot` or `s1_pro_forma`. The `is_registration_form` guard in `periods.py` keeps S-1 facts out of LTM math the rest of the time. The redline timeline is a separate user-facing command that diffs consecutive S-1 / S-1/A / 424B packs and surfaces the latest filing's S-1 metrics bundle from `kpi_discover`. One predicate (`is_registration_form`), one extractor (`s1_financials.py`), one source tag (`source="s1_*"` on CitedValue), and the rest of the system stays unchanged.

---

## Check your understanding

- The augmentation gate in `financials()` reads `result.metrics` after running `resolve_alias` on the requested metric names. What goes wrong if you read it before alias normalization? Why is that worse than just being slow?

- `extract_or_load_snapshot` hashes the first 50KB of `filing.full.md` for cache invalidation. What kinds of edits to the source filing would silently bypass cache invalidation, and is that acceptable?

- A company files a 10-K and later files an S-1 for a follow-on. Without the `is_registration_form` guard in `_is_annual`, what specific number does `--period lfy` return? What about `--period ltm`?

- `inject_s1_headings` is a no-op for filings with no TOC links. Why does `pack/build.py` call it unconditionally for registration forms instead of detecting "this S-1 actually has font-size headings already"?
