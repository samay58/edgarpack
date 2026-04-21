# China Lens Extraction Quality + Multi-Year YoY Design

Date: 2026-04-15
Beads: edgarpack-483, edgarpack-ws7, edgarpack-ej1
Umbrella: edgarpack-2yg (closes when above + 3yv land)

## Why this exists

The China AI labs vertical slice ships FY24-only facts for MiniMax and Zhipu with one row-label fix still outstanding on MiniMax. Three gaps block the "compare AI labs on growth, R&D intensity, and revenue-per-employee" story that the cluster was built for. This spec addresses those three gaps as one pass because they live in the same three files and share a test harness.

Scope: bugs/features `edgarpack-483`, `edgarpack-ws7`, `edgarpack-ej1`. Out of scope: Tencent / Meituan ingestion (`edgarpack-3yv`, closed 2026-04-20; followup `edgarpack-sfi` covers the annual-report shape work that's needed first).

## What we are shipping

Three thin slices, landed in order as three commits:

1. **MiniMax label continuation fix (`edgarpack-483`)**. Regex preprocessor that joins a label line to its amount line when the label wraps. Unlocks `rd_expense` and `operating_cash_flow` for MiniMax.
2. **Headcount extraction (`edgarpack-ws7`)**. New canonical metric `headcount` with a non-currency unit. HKEX: scan non-financial sections. SEC: try the `dei:EntityNumberOfEmployees` XBRL concept first, fall back to a 10-K text scan. Compare renderer skips FX and formats as an integer.
3. **Multi-year extraction + YoY derivations (`edgarpack-ej1`)**. Extract every disclosed year column, not just FY24. Add `period_offset` to the derivation engine so formulas can reference prior-year values. Wire `revenue_growth_yoy`, `gross_margin_trend`, `r_and_d_intensity`, `revenue_per_employee`. Compare renders growth as signed percent.

The umbrella issue `edgarpack-2yg` stays open pending 3yv.

## Design

### Slice 1: MiniMax label continuation

File: `edgarpack/hk/extract.py`.

Problem: MiniMax prospectus renders some rows across two lines:

```
Research and development
expenses /H1118/H1118 ... (10,560) ... (70,002)
```

Current regex in `_extract_metric_from_section` matches line N against a label prefix, then parses amounts on the same line. Line N has no digits; it discards the row.

Approach: a targeted preprocessor `_merge_wrapped_labels(lines)` that runs once per section before the per-label loop. Rule: when line N, after `_strip_filler`, starts with a known label prefix and contains no digits outside filler, and line N+1 begins with a lowercase word or another filler token, concatenate line N+1 onto line N and elide the orphan. The preprocessor considers only the `_PROSE_LABELS` catalog already defined in the module, so it cannot create false merges for unrelated rows.

The preprocessor is unit-testable on synthetic fixture strings. It runs before `_find_fy_col` / `_count_years` so column detection sees the merged form.

Why not multi-line regex: `re.DOTALL` on each label pattern would require every label to handle `\s+\n\s+` and risks consuming downstream rows. A single preprocessor pass is easier to reason about and easier to reject when we get a real false-merge report.

### Slice 2: Headcount extraction

Canonical metric registration:

- `edgarpack/query/metric_map.py`: add `"headcount"` to `CANONICAL_METRICS`. Add `METRIC_MAP["US-GAAP"]["headcount"] = ["EntityNumberOfEmployees", "NumberOfEmployees"]`, `METRIC_MAP["IFRS"]["headcount"] = []`, `METRIC_MAP["HKFRS"]["headcount"] = []`, `METRIC_MAP["CAS"]["headcount"] = []`.

HKEX path (`edgarpack/hk/extract.py`):

- New helper `extract_headcount_from_pack(pack_dir)` that walks all section files (not just `_FINANCIAL_SECTIONS`), applies regex `(\d[\d,]*)\s+(?:full[\s-]time\s+)?employees` case-insensitively, and returns the first match whose integer value is between 50 and 5,000,000.
- On extraction: emit one `HKFact(metric="headcount", unit="headcount", section_id=<section>, extraction_method="regex", matched_label=<phrase>)` with value in raw integer form (no multiplier scaling).
- Fails gracefully with `None` when no section matches. No LLM fallback in this pass.

SEC path (`edgarpack/query/financials.py` / `layer_zero.py`):

- On lookup, `resolve_concept("headcount", facts)` returns `("EntityNumberOfEmployees", "dei")` when present in company-facts.
- When XBRL returns no value, invoke a text-scan helper (`edgarpack/sec/headcount_text.py`, new module) that fetches the primary 10-K document via `fetch_file` and applies the same regex + 50–5,000,000 bounds. Cached per accession.
- Caveat documented in code: headcount is a point-in-time disclosure attributed to the fiscal year end; no time-series guarantees across filings.

Compare renderer (`edgarpack/compare.py`):

- When a column's unit is `"headcount"`, skip FX conversion, format as thousands-separated integer (`32,000`), and omit the currency suffix.

Bounds (50 to 5,000,000) are enforced at extraction time. Out-of-range values are discarded with a `logger.warning`, not stored, so downstream does not see corrupt data.

### Slice 3: Multi-year extraction + YoY derivations

Extraction (`edgarpack/hk/extract.py`):

- Rename the single-year call in `extract_with_regex` to a per-year loop. `_find_fy_col(text, year)` and `_count_years(text)` stay as-is; the loop iterates `years = re.findall(r"\b(20\d\d)\b", text[:500])` and calls `_extract_metric_from_section` once per year column index. Each successful extract produces one `HKFact` tagged with the period.
- `HKFact` gains a `fiscal_year: int` field. `extract_facts_from_pack` writes one entry per fiscal year into `facts[concept][units][currency]`, following the existing SEC-facts shape: `{"start": "<fy>-01-01", "end": "<fy>-12-31", "val": value, "fy": fy, "fp": "FY", ...}`.
- Filings that disclose fewer than 3 years are handled naturally; the loop runs once per detected year.

Query path (`edgarpack/query/financials.py::_query_hkex_pack`):

- Verify the existing function calls `select_period` on the facts list; if it hardcodes single-period, extend it to take `period` and route through `select_period` so `"lfy"` returns the most-recent year and `"annual:3"` returns the full list.
- Back-compat: `select_period("lfy", facts_list)` already picks the max-`fy` entry on the SEC path. Re-use that helper.

Derivation engine (`edgarpack/query/concepts.py`, `financials.py::_compute_derived`):

- Extend `MetricMeta.components` from `list[str]` to `list[str | tuple[str, int]]`. Bare-string components keep `period_offset=0`. Tuple form `("revenue", -1)` means "same metric, prior fiscal year". `_compute_derived` passes the offset to `select_period` (which today ignores offset; add a `period_offset` kwarg that shifts the selected fiscal year).
- Wire four derivations:
  - `revenue_growth_yoy`: components `[("revenue", 0), ("revenue", -1)]`, formula `(a/b) - 1`.
  - `gross_margin_trend`: components `[("gross_margin", 0), ("gross_margin", -1)]`, formula `a - b`.
  - `r_and_d_intensity`: components `[("rd_expense", 0), ("revenue", 0)]`, formula `a / b`.
  - `revenue_per_employee`: components `[("revenue", 0), ("headcount", 0)]`, formula `a / b`.
- Missing prior-year component: `_compute_derived` already returns `None` when any component resolves to `None`; the `Diagnostic` emitted names the missing period so the user sees "revenue FY2023 not found" rather than a silent gap.

Compare renderer:

- Growth-type metrics (detected by canonical-metric name suffix `_yoy`, `_trend`, or presence in a small explicit set) render as signed integer percent: `+50%`, `-12%`. Values with `abs < 0.10` render with one decimal (`+4.2%`) so magnitude is visible.
- Ratios (`r_and_d_intensity`, `gross_margin`) render as unsigned percent.
- Efficiency (`revenue_per_employee`) renders as FX-normalized currency integer per employee.

### Fixture strategy

- Regenerate `tests/fixtures/china_packs/minimax_2024/` and `zhipu_2024/` in place via `scripts/build_hk_fixture_packs.py` plus `extract_facts_from_pack`. Pack dir names stay the same (the `_2024` suffix marks most-recent FY, not data scope). `facts.json` grows to include FY22, FY23, FY24 entries per concept.
- Extend `tests/eval/china_golden.yaml` with new rows: MiniMax FY22/FY23 revenue, Zhipu FY22/FY23 revenue, both companies' FY24 headcount, revenue_growth_yoy for both at FY24, r_and_d_intensity at FY24, revenue_per_employee at FY24. Values cross-checked against prospectus tables.
- Add focused unit tests:
  - `tests/test_hk_label_merge.py`: preprocessor behavior on synthetic wrapped-label strings, including a negative case where merging would be wrong.
  - `tests/test_hk_headcount.py`: HKEX regex extractor on MiniMax and Zhipu fixtures, bounds enforcement on an out-of-range synthetic.
  - `tests/test_query_derivations.py`: each of the four new derived metrics computed against a fabricated facts list covering 3 fiscal years. Missing-prior-year case returns `None` with a matching diagnostic.

## Contracts

CLI, after the cluster lands:

```
edgarpack query minimax revenue,revenue_growth_yoy,r_and_d_intensity,headcount,revenue_per_employee --period lfy
edgarpack compare minimax zhipu BIDU GOOGL --metrics revenue,headcount,revenue_per_employee,revenue_growth_yoy
edgarpack query minimax revenue --period annual:3   # returns FY22, FY23, FY24
```

Existing single-metric queries stay green. `edgarpack query NVDA` still routes through SEC (thanks to the n8e regression fix).

## Risks and how we handle them

- **Label preprocessor false-merges.** Mitigated by scoping merges to the `_PROSE_LABELS` catalog and requiring line N to contain no digits outside filler. The negative-case unit test guards the regression surface.
- **SEC text-scan flakiness for headcount.** Companies phrase employee counts inconsistently. The regex is simple on purpose; when it misses, `headcount` resolves to `None` and downstream shows `n/a`. We do not fall through to LLM.
- **YoY divide-by-zero or sign flip.** `_compute_derived` checks components before division. For gross-margin metrics defined on losses, `gross_margin_trend` can be negative; the renderer handles signs.
- **Fixture regeneration drifts numbers.** The existing golden harness is the canary. If a value changes unexpectedly, the test fails and we investigate before committing.
- **Multi-period query path needs retrofit.** The ej1 slice flags verification as an explicit step; if `_query_hkex_pack` does not already route through `select_period`, add it within ej1.

## Done when

- `edgarpack compare minimax zhipu BIDU GOOGL --metrics revenue,rd_expense,operating_cash_flow,headcount,revenue_growth_yoy,r_and_d_intensity,revenue_per_employee` returns a non-`n/a` value for each (metric, company) cell where the source filing discloses the data.
- The golden harness passes with the expanded rows.
- Three commits land in order: `fix(hk): merge wrapped labels for MiniMax extraction`, `feat(query): canonical headcount metric with HKEX + SEC paths`, `feat(query): multi-year HKEX extraction + YoY derivations`.
- `ruff check` + `ruff format --check` clean. Full test suite green.

## Out of scope (deferred)

- Tencent (0700.HK) and Meituan (3690.HK) HKEX ingestion (`edgarpack-3yv`, closed 2026-04-20; blocked on `edgarpack-sfi` for annual-report shape support in the HK pipeline).
- LLM fallback for prior-year gaps.
- EBITDA, operating_margin, cash_burn derivations beyond the four listed.
- Quarterly series for HKEX packs.
