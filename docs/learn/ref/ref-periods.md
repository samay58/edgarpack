# Reference: query/periods.py

`edgarpack/query/periods.py` (961 lines)

The hairiest module in the codebase. Period selection, LTM math, anchor quarter resolution, segment filtering, inline XBRL fact ID parsing. Most reasoning bugs in financial code live here. [Trail 3](../trail-3-period-selection.md) walks the core LTM path narratively; this ref is the lookup.

---

## Public selectors

Every public selector has the same signature:

```python
def select_X(
    facts: dict[str, Any],
    concept: str,
    metric: str,
    meta: MetricMeta,
    company: str,
    cik: str,
    taxonomy: str = "us-gaap",
    doc_map: dict[str, str] | None = None,
) -> CitedValue | DerivedValue | list[CitedValue] | None:
    ...
```

`select_period` at line 901 is a dispatcher that routes to one of these based on the period string.

### select_lfy

`edgarpack/query/periods.py:647`. Last fiscal year. For duration metrics, picks the most recent entry from `_annual_history`. For balance-sheet (instant) metrics, picks the most recent 10-K/20-F annual instant by `(fiscal_year, end_date)`.

### select_mrq

`edgarpack/query/periods.py:685`. Most recent quarter. For duration metrics, filters to **standalone** ~90-day values (not cumulative YTD) via `_is_standalone_quarter`, sorts by end date, returns the newest. The standalone filter is the whole point. SEC companyfacts has both a 9-month cumulative entry and a 3-month standalone entry for Q3, and a naive "most recent quarterly" would pick the wrong one for anyone wanting a single-quarter value.

### select_mrp

`edgarpack/query/periods.py:734`. Most recent period of any kind. Picks the entry with the latest `filed` date, breaking ties on `end`. Used as the LTM fallback for instant (balance-sheet) metrics and for any metric type where the user just wants the latest number.

### select_ltm

`edgarpack/query/periods.py:760`. Trailing twelve months. Delegates to `_select_ltm_like` with `years_back=0`.

### select_ltm_minus_1

`edgarpack/query/periods.py:790`. LTM shifted one fiscal year back. Delegates to `_select_ltm_like` with `years_back=1`.

### select_annual_series / select_quarterly_series

`edgarpack/query/periods.py:815, 850`. Return a list of `CitedValue`s instead of a single value: the `N` most recent annual or quarterly entries. Used for `--period annual:5` or `--period quarterly:8`. Staleness is not enforced on series results (the caller asked for history).

### select_period

`edgarpack/query/periods.py:901`. The dispatcher. Routes to one of the above based on the normalized `period` string. Raises `ValueError` for unknown selectors.

---

## Core internals

### _extract_values(facts, concept, taxonomy)

`edgarpack/query/periods.py:170`. Pulls the raw value list for a concept from the companyfacts structure, trying unit keys in priority order: `USD`, `shares`, `USD/shares`, `pure`, then any other. Returns the output of `_filter_segment_entries`, which is the de-segmented list.

### _filter_segment_entries(values)

`edgarpack/query/periods.py:132`. Consolidated vs. segment filter. Groups entries by `(accn, fy, fp, start, end)`. For each group:

- If only one entry, keep it.
- If multiple, prefer entries with a `frame` field (consolidated entries in the SEC's XBRL frame carry this; segment disclosures don't).
- If no framed entries exist, pick the largest absolute value (consolidated totals are larger than segment breakdowns).

Without this filter, a query for NVIDIA's revenue would risk returning a segment value (e.g. data center revenue) instead of the total. This is the single most important de-noising step in the whole module.

### _value_to_cited(v, metric, concept, unit, company, cik, taxonomy, doc_map)

`edgarpack/query/periods.py:227`. Convert a raw SEC value dict into a `CitedValue`. Uses `_parse_date` to parse `start`, `end`, `filed`. Looks up `primary_document` from `doc_map` if the accession is present.

### _annual_history(values)

`edgarpack/query/periods.py:324`. Build a deduped annual history: one best entry per fiscal year, sorted newest first.

**Rules:**

- Filter to annual entries via `_is_annual` (fiscal_period == "FY" or form type in 10-K/10-K/A/20-F/20-F/A).
- If any full-year duration (350-380 days) exists across the annual list, drop stub periods (entries with a duration but not within the full-year window). This prevents short stub years from overwhelming a real history.
- Group by fiscal year. For each group, pick the "best" entry via `_best_annual_entry`. Prefer full-year durations, fall back to any annual entry.
- Sort by `_annual_sort_key` (fiscal year, filed date, end date) reversed.

### _pick_cumulative_quarter(values)

`edgarpack/query/periods.py:406`. From a list of quarterly entries, pick the cumulative-YTD one. Uses `_is_cumulative_quarter` (duration > 100 days for Q2-Q4; Q1 cumulative == standalone at ~90 days).

### _pick_anchor_quarter(quarterly, newest_mrp, years_back)

`edgarpack/query/periods.py:419`. The LTM anchor selector. For `years_back=0`, returns `newest_mrp`. For `years_back=1`, scans backward for the same fiscal period (Q1/Q2/Q3/Q4) one fiscal year earlier.

### _select_ltm_like(facts, concept, metric, meta, company, cik, years_back, fiscal_period_label, taxonomy, doc_map)

`edgarpack/query/periods.py:469`. The LTM orchestrator. See [Trail 3](../trail-3-period-selection.md) for a full walkthrough. Summary:

1. If per-share metric: use annual history directly (per-share values are not additive).
2. If instant metric: fall back to `select_mrp`.
3. Otherwise: build the quarterly list, sort by recency, pick the cumulative MRP, compute the anchor via `_pick_anchor_quarter`.
4. If anchor is Q4 or FY and `years_back=0`, short-circuit to the annual value for that fiscal year.
5. Otherwise: pull LFY from `_annual_history`, pull same-period-prior-year from the quarterly list via `_pick_cumulative_quarter`, compute `ltm_val = mrp + lfy - mrp_prior`.
6. Stock split contamination check on per-share metrics (5x divergence triggers a warning).
7. Return a `DerivedValue` with `components = {"mrp", "lfy", "mrp_prior"}`.

---

## Inline XBRL parsing

### parse_fact_ids_from_html(html)

`edgarpack/query/periods.py:67`. Parses inline XBRL HTML and returns `{(concept, value): fact_id}`.

**Strategy**: regex-match every `<ix:nonFraction name="..." id="..." scale="..." sign="...">{text}</ix:nonFraction>`. For each match, extract the concept name (strip taxonomy prefix), the fact ID, the scale, and the sign. Parse the display text via `_parse_display_value` to get the final numeric value. Store `{(concept_short, value): fact_id}`.

The composite key is reliable within a single filing because the same concept at different periods almost always has a different dollar value.

First-occurrence-wins (line 104): if duplicates exist (rare, and typically the result of notes sections repeating values from the financial statements), the financial statement element keeps its ID because it appears first in the HTML.

### _parse_display_value(text, scale, sign)

`edgarpack/query/periods.py:33`. Parse a displayed inline XBRL value:

1. Strip non-breaking spaces, leading/trailing whitespace.
2. Handle parentheses as display-only formatting (negative numbers); the `sign` attribute is the authoritative sign indicator.
3. Strip commas, dollar signs, percent signs.
4. Parse as float.
5. Apply `sign` attribute if `-`.
6. Apply `scale` as power of 10 (XBRL reports numbers in scaled units: `scale="6"` means the displayed number is in millions).

Returns `None` on any parse failure (bad number, empty text, etc.).

### _lookup_fact_id(fact_id_map, concept, val)

`edgarpack/query/periods.py:110`. Look up a fact_id by `(concept, value)`. Strips taxonomy prefix from the concept. Returns empty string if not found. Called from `financials._enrich_fact_ids`.

---

## Classification helpers

- `_is_annual(v)` (line 261): fiscal_period == "FY" or form in annual set.
- `_is_quarterly(v)` (line 267): fiscal_period in Q1/Q2/Q3/Q4.
- `_is_quarter_form_type(form)` (line 273): form is 10-Q* or can carry quarterly data (10-K*, 20-F*).
- `_duration_days(v)` (line 279): days between start and end.
- `_is_full_fiscal_year(v)` (line 292): duration within `[350, 380]` days.
- `_is_standalone_quarter(v)` (line 355): duration <= 100 days.
- `_is_cumulative_quarter(v)` (line 369): Q1 standalone or Q2-Q4 cumulative (>100 days).
- `_is_per_share_metric(metric)` (line 385): metric name contains `"per_share"` or `"eps"`.

Each of these encodes a decision that would be wrong if inverted. Read them as named invariants rather than utility functions.

---

## Invariants

- **Consolidated entries win over segment breakouts**. Enforced by `_filter_segment_entries` and applied in `_extract_values` before any selector sees the data.
- **Cumulative quarterly values are used for LTM math, not standalone quarterly**. Enforced by `_pick_cumulative_quarter` at multiple call sites in `_select_ltm_like`.
- **Standalone quarterly values are used for `select_mrq`**. Enforced by `_is_standalone_quarter` filter in `select_mrq`.
- **Per-share metrics degrade to annual values in LTM**. Enforced in `_select_ltm_like` at line 482 (`if _is_per_share_metric(metric)`).
- **Balance-sheet metrics degrade to `select_mrp` in LTM**. Enforced at line 501 (`if not meta.duration`).
- **Annual history drops stubs when full years exist**. Enforced in `_annual_history` at line 337.
- **Cross-year components break the derivation**. Not enforced here but enforced in `_compute_derived` in `financials.py`.
- **`_parse_display_value` returns `None` on failure, never raises**. Errors become cache misses in the fact_id map, not crashes.

---

## What this module does not do

- **It does not know about metric names, only concepts**. The caller looks up the metric in `METRIC_MAP` and passes the resolved concept in. Periods deal with concept-level data.
- **It does not fetch anything**. Pure function: `(facts, concept, metric, ...) -> CitedValue | DerivedValue | None`. Testable with JSON fixtures.
- **It does not enforce staleness**. Staleness is applied in `financials.financials()` after the selector returns. This lets the selectors be usable in other contexts (series queries, comps) with different staleness rules.
- **It does not build URLs**. URL building is on `CitedValue` / `DerivedValue` properties. This module only produces the values; linkage is the model's job.
- **It does not handle ticker resolution**. Callers pass in a resolved `cik` and `company` name. `resolve_ticker` lives in `sec/tickers.py`.
