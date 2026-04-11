# Trail 3: How `--period ltm` becomes three filings and one formula

**Time**: ~16 minutes
**Prereq**: [Trail 0](trail-0-full-loop.md). You should already know how `financials()` calls `select_period()` and what `CitedValue` / `DerivedValue` look like.
**Covers**: `query/periods.py`, `query/concepts.py` (derived metrics)

This is the subtlest part of the system. LTM looks simple in the README ("trailing twelve months"), but there are eight distinct decisions between a SEC companyfacts blob and a correctly anchored LTM number. Get any of them wrong and the value silently drifts by a quarter, or includes a stock split, or double-counts segment revenue. Most reasoning bugs in financial code live in this module, which is why it's 961 lines long and has its own trail.

---

## 1. `select_period` is a router

Everything starts at `edgarpack/query/periods.py:901`:

```python
period = period.strip().lower()

if period == "lfy":
    return select_lfy(...)
elif period == "mrq":
    return select_mrq(...)
elif period == "mrp":
    return select_mrp(...)
elif period == "ltm":
    return select_ltm(...)
elif period == "ltm-1":
    return select_ltm_minus_1(...)
elif period.startswith("annual:"):
    ...
```

Seven concrete period selectors. For this trail we care about `ltm` and `ltm-1`, both of which delegate to `_select_ltm_like` at `edgarpack/query/periods.py:469`. `ltm` calls it with `years_back=0`, `ltm-1` with `years_back=1`. The latter simply shifts the anchor quarter one fiscal year earlier; the rest of the logic is identical.

---

## 2. Pull all reported values for the concept

The first thing `_select_ltm_like` does is fetch every reported value for this concept, across every unit type, across every filing.

```python
values = _extract_values(facts, concept, taxonomy=taxonomy)
unit = _unit_for_concept(facts, concept, taxonomy=taxonomy)
```

`_extract_values` at `edgarpack/query/periods.py:170` walks `facts[taxonomy][concept]["units"]` and picks the first non-empty unit list in priority order: `USD`, `shares`, `USD/shares`, `pure`, and then whatever else is present. It returns raw SEC value dicts with keys `val`, `start`, `end`, `fy`, `fp`, `form`, `accn`, `filed`.

Then, and this is the important part, it passes the raw list through `_filter_segment_entries` before returning. That function is where the most insidious class of bug gets prevented.

---

## 3. Consolidated vs. segment breakouts

SEC companyfacts includes both **consolidated** numbers and **dimensional/segment** breakouts for the same concept. If you query `Revenues` for a company that reports segment revenue, the facts blob contains entries for total revenue and entries for each segment (data center, gaming, auto). They all have the same concept name. They all live in the same list.

`_filter_segment_entries` at `edgarpack/query/periods.py:132` dedupes them using one rule: **entries with a `frame` field beat entries without**.

```python
by_context: dict[tuple, list] = {}
for v in values:
    key = (v.get("accn", ""), v.get("fy"), v.get("fp", ""), v.get("start", ""), v.get("end", ""))
    by_context.setdefault(key, []).append(v)

for group in by_context.values():
    if len(group) == 1:
        result.append(group[0])
        continue
    framed = [v for v in group if v.get("frame")]
    if framed:
        result.extend(framed)
    else:
        group.sort(key=lambda v: abs(v.get("val") or 0), reverse=True)
        result.append(group[0])
```

The `frame` field is the SEC's marker for consolidated entries: values that appear in the company's official XBRL frame (e.g. `CY2024Q4I`). Segment disclosures don't carry one. When two entries share the same filing context (accession, fiscal year, fiscal period, date span), the framed one is the total and the unframed one is a segment piece.

The fallback branch handles filings that don't have the frame field at all: pick the entry with the largest absolute value, because consolidated totals are larger than segment breakdowns. It's an heuristic rather than a proof, but it's correct for every company this has been tested against.

Without this filter, a query for NVIDIA's revenue might return the data center segment's revenue instead of the total. The user would have no way to know.

---

## 4. Split the values into annual and quarterly tracks

After dedup, `_select_ltm_like` separates the values into two paths. Balance sheet metrics (`meta.duration == False`, things like `total_assets` that are instantaneous rather than for a period) get shunted to `select_mrp` at line 501. For an instant value, LTM is the same as "most recent period". Per-share metrics (`_is_per_share_metric`) get shunted to annual-history handling at line 482 because EPS and similar metrics are not additive across quarters.

For everything else (duration metrics like revenue, operating income, net income) the function builds a quarterly list:

```python
quarterly = [
    v for v in values
    if _is_quarter_form_type(str(v.get("form", "")))
    and _is_quarterly(v)
    and v.get("val") is not None
    and v.get("start")
    and v.get("end")
]
```

Every entry in `quarterly` is tagged as Q1/Q2/Q3/Q4 (`_is_quarterly` at line 267) from a filing form that can carry quarterly data (`_is_quarter_form_type` at line 273, which accepts `10-Q*`, `10-K*`, `20-F*`; 10-Ks can carry Q4 values).

If there are zero quarterlies, the filer is annual-only (common for foreign private issuers filing 20-F). The function falls back to `_annual_history` and returns the (years_back+1)th most recent full-year annual value. No LTM math, just the annual number.

---

## 5. Find the anchor: the newest MRP

Assuming there are quarterlies, the function sorts them by recency and picks the anchor:

```python
quarterly.sort(key=_quarter_recency_key, reverse=True)
newest = quarterly[0]
```

`_quarter_recency_key` at line 396 returns `(period_end, quarter_months, fy_int, filed)`. Sorting reverse gives you the most-recent quarter end first, breaking ties on quarter length (longer cumulative values beat shorter standalone ones), then fiscal year, then filed date.

But "newest" isn't enough. For Q3 of fiscal 2025, SEC companyfacts will contain **both** a 3-month standalone value (~90 days) and a 9-month cumulative value (the year-to-date figure). The cumulative one is what LTM math needs. `_pick_cumulative_quarter` at line 406 walks candidates sharing the same `(fy, fp, end)` and picks the one with the longest duration via `_is_cumulative_quarter` at line 369. That's the MRP: most recent period, cumulative flavor.

```python
newest_mrp = _pick_cumulative_quarter(newest_candidates) or newest
mrp = _pick_anchor_quarter(quarterly, newest_mrp, years_back)
```

For `years_back=0` (`ltm`), `_pick_anchor_quarter` returns `newest_mrp`. For `years_back=1` (`ltm-1`), it scans backward for the same fiscal period one fiscal year earlier. The anchor is now set.

**Code**: `edgarpack/query/periods.py:355-382` (`_is_standalone_quarter` / `_is_cumulative_quarter`), `edgarpack/query/periods.py:406-457` (`_pick_cumulative_quarter` / `_pick_anchor_quarter`)

---

## 6. The MRP=Q4 special case

If the anchor quarter is `Q4` or `FY` and `years_back == 0`, that means we have a full fiscal year's worth of data already. There's no need to do LTM math; the annual value **is** the LTM.

```python
if years_back == 0 and mrp_fp in ("FY", "Q4"):
    annual_mrp = _annual_for_fy(values, mrp_fy)
    if annual_mrp is not None:
        return _value_to_cited(annual_mrp, ...)
    return _value_to_cited(mrp, ...)
```

`_annual_for_fy` at line 459 looks up the best annual entry for that fiscal year. If found, return it directly as a plain `CitedValue` (not `DerivedValue`, because nothing was computed). If not, return the cumulative Q4 entry.

This is the early-exit that handles ~25% of real LTM queries: companies whose last filing was a 10-K rather than a mid-year 10-Q.

---

## 7. The LTM math

For the common case (anchor is Q1, Q2, or Q3), we need three numbers. First is LFY, the prior fiscal year's full-year annual value.

```python
annual = _annual_history(values)
lfy_target_fy = mrp_fy - 1
lfy = next((v for v in annual if int(v.get("fy") or 0) == lfy_target_fy), None)
if lfy is None:
    lfy = next((v for v in annual if int(v.get("fy") or 0) < mrp_fy), None)
```

`_annual_history` at line 324 builds a deduped list of annual entries, one best entry per fiscal year. The "best" rule prefers full-year durations (350-380 days) over stub periods. It also drops stub periods entirely if at least one full-year entry exists in the list, so short first-year and last-year windows don't contaminate the history.

The primary lookup is `mrp_fy - 1`. The fallback walks further back in case the immediate prior year is missing.

Second is MRP_prior, the same fiscal-period-length window one fiscal year earlier than MRP.

```python
prior_year = [
    v for v in quarterly
    if str(v.get("fp", "")).upper() == mrp_fp
    and int(v.get("fy") or 0) == lfy_fy
    and v.get("val") is not None
]
mrp_prior = _pick_cumulative_quarter(prior_year)
```

If the anchor is Q3 FY2025 (9-month cumulative), MRP_prior is Q3 FY2024 (also 9-month cumulative). The same `_pick_cumulative_quarter` function is used to resolve standalone-vs-cumulative ambiguity in the prior year's data. If the prior-year Q-match is missing, the function gives up on LTM and returns the MRP alone.

Then the formula:

```python
mrp_val = float(mrp.get("val") or 0)
lfy_val = float(lfy.get("val") or 0)
prior_val = float(mrp_prior.get("val") or 0)
ltm_val = mrp_val + lfy_val - prior_val
```

LTM revenue at end of Q3 FY2025 = (9-month YTD revenue for FY2025) + (full-year FY2024 revenue) - (9-month YTD revenue for FY2024). The subtraction removes the first three quarters of FY2024, which are covered both by the LFY annual and by MRP_prior. What's left is exactly the four most recent quarters.

---

## 8. Stock split contamination check

For per-share metrics, the function applies a sanity check at lines 612-619:

```python
if _is_per_share_metric(metric) and lfy_cited.value and lfy_cited.value != 0:
    ratio = abs(ltm_val / lfy_cited.value)
    if ratio > 5.0 or ratio < 0.2:
        split_warnings.append(
            f"Possible stock split contamination: LTM-derived value differs "
            f"from annual by {ratio:.1f}x"
        )
```

A 5x divergence between LTM and the prior annual on a per-share metric almost always means a stock split happened inside the LTM window. SEC doesn't always retroactively adjust every reported value, so the math produces a number that's technically correct for the raw data and obviously wrong for the reader. The warning is attached to the result; the number is still returned. Flagging without hiding.

(Per-share metrics actually go through the early-return branch at line 482 and return an annual value directly, so this check is a guard for edge cases where the early return didn't fire.)

---

## 9. Build the DerivedValue

Finally:

```python
return DerivedValue(
    value=ltm_val,
    unit=unit,
    metric=metric,
    concept=concept,
    period_start=lfy_cited.period_start,
    period_end=mrp_cited.period_end,
    fiscal_year=mrp_cited.fiscal_year,
    fiscal_period=fiscal_period_label,
    form_type=mrp_cited.form_type,
    filed=mrp_cited.filed,
    accession=mrp_cited.accession,
    cik=cik,
    company=company,
    taxonomy=taxonomy,
    primary_document=mrp_cited.primary_document,
    derived=True,
    components={"mrp": mrp_cited, "lfy": lfy_cited, "mrp_prior": prior_cited},
    warnings=split_warnings,
)
```

Every component is itself a fully-formed `CitedValue` built via `_value_to_cited` at line 227. The outer `DerivedValue` gets its top-level provenance fields from the MRP (most recent filing), because that's the filing the user will think of as "the source". The components dict preserves all three. Later, when the CLI renders the citation, it walks the components and prints three separate citation lines, one per source filing.

`_value_to_cited` also looks up the `primary_document` for each component from the `doc_map` that was built up front in `financials()`. This is how the deep-link URLs get populated all the way back to the original filings.

---

## 10. Other derived metrics (ebitda, margins, ratios)

LTM is one kind of derived value. There's another kind: metrics that are computed from other metrics regardless of period. EBITDA is `operating_income + depreciation_amortization`. Gross margin is `gross_profit / revenue`. These live in `METRIC_MAP` with `derived=True` and a `formula` string (e.g. `"operating_income + depreciation_amortization"`).

`financials._compute_derived` at `edgarpack/query/financials.py:310` handles these. It recursively resolves each component metric (calling back into `select_period` for non-derived components), combines the component values via `_eval_formula` (line 446, a small arithmetic evaluator that understands `+`, `-`, `*`, `/` and 3- or 5-token formulas), and returns a `DerivedValue` with all components attached.

Two things make this resolver careful:

1. **Cycle protection**: `in_progress: set[str]` catches a metric that references itself transitively. The offending metric is cached as `None` to break the cycle.
2. **Cross-year validation**: all components must share the same fiscal year. If `operating_income` came from FY2024 and `depreciation_amortization` somehow came from FY2023, the derivation is rejected rather than producing a misleading EBITDA.

Both guards are small but prevent an entire class of wrong answers where the right formula gets applied to mismatched inputs.

**Code**: `edgarpack/query/financials.py:310` (`_compute_derived`), `edgarpack/query/financials.py:446` (`_eval_formula`)

---

## Recap

A single `--period ltm` query turns into: extract all reported values, filter segment breakouts by preferring framed entries, split into annual and quarterly tracks, handle per-share and balance-sheet metrics specially, pick the newest cumulative quarterly entry as the MRP anchor, short-circuit to the annual value if the anchor is Q4 or FY, otherwise fetch the prior year's annual and the same-quarter value one year ago, compute `MRP + LFY - MRP_prior`, check for stock-split contamination on per-share metrics, wrap everything in a `DerivedValue` with all three components as `CitedValue` citations. The module is 961 lines because every one of those steps is a place where a naive implementation would produce a number that looks reasonable and is wrong. The invariant that makes everything else possible is that every number carries its filing provenance from the moment it leaves `_value_to_cited`, so even when the math goes sideways you can always trace back to the exact filing that contributed the wrong value.

If you want to modify `periods.py` with confidence: read `_select_ltm_like` end to end before touching anything. Then read `_filter_segment_entries`, `_annual_history`, and `_pick_cumulative_quarter`. Those four functions encode roughly 80% of the financial-reasoning rules. Everything else is helpers.
