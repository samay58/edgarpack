# Packet: sse-facts

Goal: rebuild the SSE annual-report facts extraction contract so a wrong number can no longer ship under a clean citation. The Phase 0 spike reproduced BYD FY2025 revenue extracted as 80.00 (an ESG coverage ratio) with full provenance; this packet closes every mechanism that produced it.

Files owned: `edgarpack/sse/annual_facts.py`; tests (`tests/test_sse_pack.py`, new test modules fine).
Interface contract: output remains a `facts.json` in the existing shape (concept keys, per-fy points, unit field). Values for correctly-extracted 元-scale key tables must not change. Do not touch `tests/eval/china_golden.yaml` (owned by fx-average).

## Fixes

1. `corner-cell`. `_split_row` (~line 57) does `stripped.strip("|")`, deleting the empty leading cell of SZSE-style headers `||2025年|2024年|增减|2023年|`. Header indices then sit one left of data-row indices, so every value maps to the wrong year (BYD's FY2025 revenue was recorded as fy2024). Preserve empty leading cells so header and data-row indices align. Regression test: a synthetic SZSE table where each year's value must land on its own year.

2. `year-state-leak`. `current_years` (~line 105) never resets at table boundaries, so a following 分季度 quarterly table (whose header carries no years) inherits the annual year map and every quarterly value becomes a bogus annual point. Reset year state when a new table starts (a header row or a table boundary). Regression test: annual table followed by a quarterly table; the quarterly values must produce zero annual points.

3. `key-table-only`. Label matching substring-scans every section, pulling ratio rows (`营业收入` inside `...占营业收入的比例`), parent-company rows (`一、营业收入` in the parent statements), and ESG-table rows into concepts. Restrict extraction to the key-financials table (主要会计数据) in the 第二节 section, and exclude ratio rows and `其中：` breakdown rows. Regression test: a pack whose MD&A carries an ESG row with 营业收入 in the label and a value of 80.00; revenue must not be 80.00.

4. `one-point-per`. Emit at most one point per (concept, fiscal_year). On conflicting candidates, prefer the key table; if the conflict is within equal-priority sources, drop both with a `warnings.warn` naming the concept and year (fail closed). Document order must never decide.

5. `yoy-cross-check`. When the key table carries a 增减/变动 percent column, validate each adjacent-year value pair against it within 1.5 percentage points. A mismatch drops the fact pair with a warning. Regression test: a table whose values imply +3.46% and whose 增减 cell says 3.46 passes; a corrupted value that implies +900% is dropped.

6. `backticks`. pymupdf4llm can render mono-font digits as backtick code spans (`` `2025` ``年), which silently zeroed out one filer's extraction. Strip backticks in cell and label cleaning before year/number parsing. Regression test: a table with backticked years and values extracts normally.

7. `unit-scale`. The extractor hardcodes unit CNY and takes values raw. Detect the 单位 marker near the table: 元 (x1), 千元 (x1e3), 万元 (x1e4), 百万元 (x1e6), and scale values to yuan. A missing or unrecognized marker fails closed: no facts from that table, one warning. 万元 is the common dangerous case (values 10,000x under-scaled today). Regression tests: a 万元 table scales correctly; a table with no 单位 marker yields no facts.

## Done definition

All seven regression tests exist, named recognizably (e.g. `test_corner_cell_header_alignment`), and pass. Existing `test_sse_pack.py` tests still pass (update any that enshrined the old broken behavior, and say so in the report). Full offline suite green.
