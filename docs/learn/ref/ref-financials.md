# Reference: query/financials.py

`edgarpack/query/financials.py` (2,395 lines)

The top-level query orchestrator for single-company metric queries. Wraps everything: ticker resolution, companyfacts fetch, concept resolution, period selection, derived-metric computation, staleness guards, the low-debt sanity check, and the fact_id enrichment pass. Called from the CLI's `_cmd_query` and from `query/comps.py` for multi-company comparisons.

Trails that walk this module: [Trail 0](../trail-0-full-loop.md) (full loop), [Trail 4](../trail-4-citation-anchors.md) (fact_id enrichment).

---

## Public functions

### financials(company, metrics, period, force)

`edgarpack/query/financials.py:664`. Run a financial metrics query for one company.

**Parameters:**

- `company` (str): ticker (e.g. `"NVDA"`) or CIK (e.g. `"1045810"`).
- `metrics` (str | list[str] | None): comma-separated string, explicit list, or `None` for all metrics in `ALL_METRICS`.
- `period` (str): one of `"lfy"`, `"mrq"`, `"mrp"`, `"ltm"`, `"ltm-1"`, `"annual:N"`, `"quarterly:N"`. Default `"lfy"`.
- `force` (bool): bypass cache on all underlying fetches.

**Returns:** `QueryResult` with `.metrics` populated.

**Flow:**

1. `resolve_ticker(company, force=force)` -> `(cik, company_name)`.
2. `fetch_company_facts(cik, force=force)` -> XBRL facts blob.
3. `_build_doc_map(cik, force=force)` -> `{accession: primary_document}` for URL building later.
4. Normalize `metrics` into a concrete list.
5. For each metric, look up `METRIC_MAP[metric]`:
   - If derived (formula-based like EBITDA or gross margin): call `_compute_derived`.
   - Otherwise: call `resolve_concept` to find the best GAAP tag, then `select_period` to pick the value.
   - Apply staleness guard via `_is_stale`.
   - Apply scope warnings via `get_scope_warning`.
6. Run `_check_low_debt` as a post-resolution audit.
7. Build a `QueryResult`.
8. Run the fact_id enrichment pass: `_collect_accessions` -> `_fetch_fact_id_maps` -> `_enrich_fact_ids`.
9. Return the result.

---

## Private helpers

### _staleness_limit(period) / _is_stale(cited, period)

`edgarpack/query/financials.py:30, 38`. Rejects values whose fiscal year is too far behind the current calendar year.

The limit is looked up in `_STALENESS_YEARS` (line 26):

```python
_STALENESS_YEARS: dict[str, int] = {"ltm-1": 3}
_STALENESS_DEFAULT = 2
```

Default is 2 years (anything older than `current_year - 2` is rejected). `ltm-1` gets 3 years because it intentionally looks one year back. Series queries (`annual:N`, `quarterly:N`) skip the check entirely by returning `999`, since the caller explicitly asked for history.

A stale value becomes `None` in the final `QueryResult.metrics`.

### _build_doc_map(cik, force)

`edgarpack/query/financials.py:184`. Fetches the submissions JSON and builds `{accession: primary_document}` for every filing in `filings.recent`. On failure (network, HTTP, malformed JSON), returns an empty dict and logs a warning. The empty-dict fallback means downstream fact_id lookups degrade gracefully: `anchor_url` falls back to `document_url` when no primary document is available.

### _fetch_fact_id_maps(cik, doc_map, accessions)

`edgarpack/query/financials.py:208`. For each accession in the set, fetches the filing's primary HTML once (cached), parses the inline XBRL via `parse_fact_ids_from_html`, and returns `{accession: {(concept, value): fact_id}}`. Runs fetches in parallel via `asyncio.gather`. Per-accession failures are logged but don't abort the enrichment.

### _collect_accessions(result) / _enrich_fact_ids(result, maps)

`edgarpack/query/financials.py:244, 123`. Walk the `QueryResult` and gather every accession, or walk again and write fact_ids back into `CitedValue.fact_id` fields. Both functions handle scalar, list, and `DerivedValue` (with components) shapes via `isinstance` dispatch.

### _compute_derived(facts, metric, meta, company, cik, period, doc_map, cache, in_progress)

`edgarpack/query/financials.py:1448`. Compute a derived metric (EBITDA, margins, ratios) from its components.

**Cycle protection**: `in_progress` is a set of metric names currently being resolved. If a metric depends on itself transitively, the recursive call sees it in `in_progress`, caches `None`, and returns. This prevents infinite recursion for any formula that contains a loop (shouldn't happen in `METRIC_MAP`, but defensive).

**Cross-year validation**: all components must share the same fiscal year. Checked at line 403. Rejects the derivation if components came from different years, since combining them would produce a number that doesn't represent any real period.

**Staleness propagation**: if any component is stale, the whole derivation is rejected (`None`).

**Unit determination**: `_derived_unit` at line 483 decides the unit for the result. Ratio metrics (gross_margin, operating_margin, roe, current_ratio, etc.) return `"pure"`. Additive/subtractive metrics inherit the first component's unit.

### _eval_formula(formula, components)

`edgarpack/query/financials.py:1622`. A small arithmetic evaluator for formulas stored in `MetricMeta.formula`. Supports two shapes:

- 3 tokens: `"a op b"` where op is `+`, `-`, `*`, `/`. Division by zero returns `None`.
- 5 tokens: `"a op1 b op2 c"` where both ops are `+` or `-`. Used for `ebitda = operating_income + depreciation_amortization` style formulas (actually 3 tokens) and more complex chains.

Any formula shape not matching returns `None`. Returning `None` lets the caller distinguish "formula evaluated to zero" from "formula was invalid or had missing inputs".

### _check_low_debt(result_metrics, facts, company_name, cik, period, doc_map)

`edgarpack/query/financials.py:1172`. Post-resolution sanity check. If the query returned a `total_debt` value and it's less than 2% of `total_liabilities` for the same period, attach a warning pointing out that the value may be missing captive finance or financial-services subsidiary debt.

This is the Ford case: companies that stop tagging consolidated debt in standard XBRL while total liabilities stay correctly reported. The check resolves `total_liabilities` itself (calls `resolve_concept` + `select_period` inline) rather than relying on whether the user asked for it.

---

## Invariants

- **Every metric is resolved through `METRIC_MAP`.** Unknown metric names return `None` in the result dict with no warning. Callers that need to distinguish "metric not supported" from "metric had no value" check `METRIC_MAP` first.
- **Staleness rejection is silent.** A stale value becomes `None`. No warning is attached because the warning would live on a nonexistent value. The user sees a missing metric and the absent row is the signal.
- **Scope warnings are additive.** A non-stale value with a scope warning returns the value with a warning in `.warnings`. The value is still usable; the warning is advisory.
- **Derived metric components share fiscal year.** Enforced at line 403. Cross-year components produce `None`.
- **Fact ID enrichment is best-effort.** If the fetch or parse fails, `fact_id` stays empty and `anchor_url` falls back to `document_url` or `filing_url`. The query still returns.
- **Batched I/O.** Enrichment fetches are batched at the filing level (one per unique accession), not per value. This keeps the call count proportional to the number of distinct source filings, not the number of metrics.

---

## What this module does not do

- **It does not render citations.** `QueryResult` is a data model; formatting happens in `query/render.py:_render_query_table` or in the various JSON dumpers on the model.
- **It does not compare companies.** That's `query/comps.py`, which calls `financials` N times in parallel and assembles a multi-company table.
- **It does not know about the XBRL Viewer or SEC URL formats.** URL building is on the `CitedValue` model, not here. This module only enriches `fact_id`; the URL construction happens at property-access time.
- **It does not enforce unit coherence across metrics in the result.** Each metric's unit is whatever its concept reports. A result with revenue in USD and stock_compensation in shares is returned as-is; consumers validate coherence if they care.
