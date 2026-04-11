# Trail 0: From `edgarpack query NVDA revenue` to a cited number

**Time**: ~18 minutes
**Prereq**: none. Start here.
**Covers**: `cli.py`, `query/financials.py`, `sec/tickers.py`, `sec/xbrl.py`, `query/concepts.py`, `query/periods.py`, `query/models.py`

This trail walks the most common EdgarPack command end to end. Every load-bearing module in the query path shows up at least once. By the end you should know what happens in the 500 milliseconds between pressing Enter and seeing the table.

---

## 1. You run the command

```bash
edgarpack query NVDA revenue --period ltm
```

`edgarpack` is an installed console script. The packaging metadata points it at `edgarpack.cli:app`. The `app` function is a thin wrapper that calls `main()` inside a try/except for `KeyboardInterrupt`, then raises `SystemExit` with whatever `main()` returned.

**Code**: `edgarpack/cli.py:18` (`app`), `edgarpack/cli.py:27` (`main`)

---

## 2. The CLI parses your args

`main()` builds an `argparse.ArgumentParser` with one subparser per subcommand. The `query` subparser lives at `edgarpack/cli.py:129`. Your arguments map like this:

- `NVDA` -> positional `company`
- `revenue` -> positional `metrics` (optional, comma-separated)
- `--period ltm` -> `args.period`
- defaults fill in `--format=table`, `--citations=inline`, `--show-links=primary`

After parsing, `main()` dispatches on `args.cmd`. The `query` branch calls `_cmd_query(args)` at `edgarpack/cli.py:757`.

`_cmd_query` defines an inner `_run()` coroutine, imports `financials` lazily (keeps startup fast for commands that don't need it), and calls `asyncio.run(_run())` at line 789. From here, the CLI is just a shell around one coroutine.

**Code**: `edgarpack/cli.py:757` (`_cmd_query`)

---

## 3. Resolve the ticker

The first thing `financials()` does is turn `"NVDA"` into a CIK. Tickers don't matter to SEC; accessions and company facts are keyed by CIK.

```python
cik, company_name = await resolve_ticker(company, force=force)
```

`resolve_ticker` at `edgarpack/sec/tickers.py:59` is straightforward:

1. Strip whitespace.
2. If the string is all digits, treat it as a CIK. Normalize it (zero-pad to 10 digits) and try to find a matching company name in the ticker map. Otherwise return `f"CIK {cik}"`.
3. Otherwise uppercase and look up in the ticker map. Raise `ValueError` if unknown.

The ticker map itself comes from `https://www.sec.gov/files/company_tickers.json`, cached on disk for 24 hours. The first time you run a query, EdgarPack fetches this file. Subsequent queries read from the cache.

`"NVDA"` resolves to `("0001045810", "NVIDIA CORP")`.

**Code**: `edgarpack/sec/tickers.py:59` (`resolve_ticker`), `edgarpack/sec/tickers.py:20` (`_fetch_ticker_map`)

---

## 4. Fetch company facts

Next, `financials()` fetches the full XBRL facts blob for this CIK.

```python
facts_data = await fetch_company_facts(cik, force=force)
facts = facts_data.get("facts", {})
```

`fetch_company_facts` at `edgarpack/sec/xbrl.py:11` hits `https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json`. Cache TTL is 24 hours. Returns an empty dict if the fetch fails (not every company has XBRL data). The response is a large JSON blob keyed by taxonomy (`us-gaap`, `ifrs-full`, `dei`) and then by concept name. Every concept holds a list of filed values tagged with accession, fiscal year, fiscal period, period start and end, and form type.

For NVIDIA, `facts["us-gaap"]["Revenues"]` is a block with `units: {"USD": [...]}` containing every revenue value NVIDIA has ever reported to the SEC, across every 10-K, 10-Q, and amendment.

**Code**: `edgarpack/sec/xbrl.py:11` (`fetch_company_facts`)

---

## 5. Build the doc_map

Before picking values, `financials()` fetches one more thing: a mapping of accession number to primary document filename.

```python
doc_map = await _build_doc_map(cik, force=force)
```

`_build_doc_map` at `edgarpack/query/financials.py:46` calls `fetch_submissions(cik)` (submissions JSON from `/submissions/CIK{cik}.json`) and builds a dict `{accession: primaryDocument}` from the `filings.recent` block. The primary document is the filename like `nvda-20250126.htm`, the thing the SEC viewer URLs point at.

This is why `doc_map` is built up front: the citation anchor URLs in the final output need the primary document filename, and fetching submissions once beats fetching it per-citation. Submission errors are caught and turned into an empty dict plus a warning, and the downstream code gracefully falls back to a less-specific URL.

**Code**: `edgarpack/query/financials.py:46` (`_build_doc_map`)

---

## 6. Normalize the metric list

`"revenue"` is a comma-separated string from argparse. `financials()` at `edgarpack/query/financials.py:174` branches on how you passed metrics:

- `None` -> use `ALL_METRICS`
- string -> split on comma
- list -> cast to list

You get `metric_list = ["revenue"]`. It then iterates. For each metric it looks up `METRIC_MAP[metric]` to get a `MetricMeta` describing how to resolve that metric.

**Code**: `edgarpack/query/financials.py:174`, `edgarpack/query/concepts.py:28` (`METRIC_MAP`)

---

## 7. Resolve the concept

`"revenue"` is an EdgarPack metric name. It is not a GAAP concept. GAAP has several closely-related concepts that companies use interchangeably: `Revenues`, `SalesRevenueNet`, `RevenueFromContractWithCustomerExcludingAssessedTax`, and so on. EdgarPack keeps a priority-ordered tuple for each metric at `edgarpack/query/concepts.py:29-40`:

```python
"revenue": MetricMeta(
    concepts=(
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueGoodsNet",
        "SalesRevenueServicesNet",
    ),
    duration=True,
    ifrs_concepts=("Revenue", "RevenueFromContractsWithCustomers"),
),
```

`resolve_concept` at `edgarpack/query/concepts.py:468` picks the best concept for this company:

1. Walks the metric's concept tuple in order against `facts["us-gaap"]`.
2. For each concept present, scores it by `(max_annual_fy, max_any_fy)`. The most recent annual fiscal year wins, breaking ties by the most recent quarterly report.
3. If no us-gaap concept scores above `(0, 0)`, tries `ifrs-full` as fallback using `ifrs_concepts` first, then the shared concept list.
4. Returns `(concept_name, taxonomy)` or `None`.

For NVIDIA, `"Revenues"` is present and reported through their most recent fiscal year, so the result is `("Revenues", "us-gaap")`. The priority ordering matters. Some companies report both `Revenues` and `SalesRevenueNet` with different values; the first one listed is the canonical one.

**Code**: `edgarpack/query/concepts.py:468` (`resolve_concept`), `edgarpack/query/concepts.py:440` (`_find_best_concept`)

---

## 8. Select the period

Now the interesting part. `financials()` calls:

```python
value = select_period(
    facts, concept, metric, meta, company_name, cik, period,
    taxonomy=taxonomy, doc_map=doc_map,
)
```

`select_period` at `edgarpack/query/periods.py:901` is a router. It lowercases `period` and dispatches to one of seven concrete selectors:

- `"lfy"` -> `select_lfy` (last full fiscal year)
- `"mrq"` -> `select_mrq` (most recent quarter)
- `"mrp"` -> `select_mrp` (most recent period, any)
- `"ltm"` -> `select_ltm` (trailing twelve months)
- `"ltm-1"` -> `select_ltm_minus_1` (trailing twelve months one fiscal year ago)
- `"annual:N"` -> `select_annual_series`
- `"quarterly:N"` -> `select_quarterly_series`

`--period ltm` lands in `select_ltm`. LTM math is subtle enough that it has its own trail ([trail-3](trail-3-period-selection.md)). For this walk, know three things:

1. LTM returns a `DerivedValue`, not a plain `CitedValue`. Derived means the number was computed from components.
2. For `ltm` the formula is `MRP + LFY - MRP_prior`:
   - **MRP** = most recent quarterly cumulative revenue (e.g. the nine-month year-to-date figure from the latest 10-Q)
   - **LFY** = prior fiscal year annual revenue (from the latest 10-K)
   - **MRP_prior** = same fiscal-period-length window one fiscal year earlier
3. Each component carries its own filing provenance. The `DerivedValue.components` dict keeps all three `CitedValue`s, so the citation can say exactly which three filings produced the LTM number.

`select_period` returns a `DerivedValue` if LTM succeeded, or `None` if any component was missing.

**Code**: `edgarpack/query/periods.py:901` (`select_period`)

---

## 9. Staleness and scope warnings

Back in `financials()`, there are two guards applied to whatever `select_period` returned.

**Staleness** (`edgarpack/query/financials.py:38`, `_is_stale`): if the value's fiscal year is more than a configured limit behind the current year, reject it. For `ltm` the limit is 2 years; for `ltm-1` it's 3. Series queries (`annual:N`, `quarterly:N`) skip the check entirely because the caller explicitly asked for history.

**Scope warnings** (`edgarpack/query/concepts.py:561`, `get_scope_warning`): some GAAP concepts are broader or narrower than the metric name implies. For example `CostOfGoodsAndServicesSold` can be broader than `CostOfRevenue` for companies with significant service revenue. If the resolved concept matches one of the watchlist entries in `CONCEPT_SCOPE_WARNINGS`, a warning string gets appended to the `CitedValue.warnings` list. The number is still returned; the reader is just told to check.

For NVIDIA revenue, neither guard fires. The value sails through.

**Code**: `edgarpack/query/financials.py:38` (`_is_stale`), `edgarpack/query/concepts.py:524` (`CONCEPT_SCOPE_WARNINGS`)

---

## 10. The low-debt sanity check

After the metrics loop, `financials()` calls `_check_low_debt` at line 244. This is a post-resolution audit: if you asked for `total_debt` and it resolved to a value less than 2% of the same period's `total_liabilities`, attach a warning that captive finance or financial-services subsidiary debt may be missing (e.g. Ford, which stopped tagging consolidated debt in standard XBRL while total liabilities stayed correct).

This is the kind of check you only add after you've been burned. Don't silently paper over discrepancies; flag them.

**Code**: `edgarpack/query/financials.py:258` (`_check_low_debt`)

---

## 11. Enrich fact IDs

Almost done. `financials()` builds a `QueryResult` at line 246 and then does one more async pass to enrich every `CitedValue` with a stable XBRL fact ID.

```python
accessions = _collect_accessions(result)
if accessions and doc_map:
    fact_id_maps = await _fetch_fact_id_maps(cik, doc_map, accessions)
    _enrich_fact_ids(result, fact_id_maps)
```

`_collect_accessions` at `edgarpack/query/financials.py:106` walks the result and gathers every unique accession (including the components inside each `DerivedValue`). `_fetch_fact_id_maps` at line 70 fetches each filing's primary HTML once (cached), and parses the inline XBRL for `(concept, value) -> fact_id` mappings. `_enrich_fact_ids` at line 123 walks the result again and looks up the fact ID for each cited value, writing it into `cited.fact_id`.

Why do this at the end instead of inline? Because it turns N fetches (one per cited value) into K fetches (one per unique filing). For an LTM query, K=3. The fact ID is what turns `anchor_url` from a text-fragment URL into a stable browser-clickable deep link to the exact span of HTML containing that number.

[Trail 4](trail-4-citation-anchors.md) walks this pass in detail.

**Code**: `edgarpack/query/financials.py:70` (`_fetch_fact_id_maps`), `edgarpack/query/financials.py:123` (`_enrich_fact_ids`)

---

## 12. Render the table

Back in `_cmd_query` at `edgarpack/cli.py:785`, the result gets formatted:

```python
print(_render_query_table(result, args))
```

`_render_query_table` at `edgarpack/cli.py:553` is a long formatting routine. It builds a table, computes column widths from the terminal size, handles the `--citations` flag (inline / footer / off) and the `--show-links` flag (primary / all / none), and renders per-metric citation lines under or beside each value. The important thing to know: every number shown in the table came from a `CitedValue` or `DerivedValue`, and every one of those carries its full provenance. The formatter decides what to show; the data model decides what is available.

For our query, the table looks like:

```
NVIDIA CORP - Financial Metrics (period: LTM)

Metric     Value     Citation
--------   -------   ---------------------------------------------
Revenue    $130.0B   NVIDIA CORP 10-Q (Q3FY2025), filed 2024-11-20
                     NVIDIA CORP 10-K (FY2024), filed 2024-02-21
                     NVIDIA CORP 10-Q (Q3FY2024), filed 2023-11-21
```

Three filings for one number. That's the LTM formula, made visible.

`_cmd_query` returns `0`, `asyncio.run` returns, `main` returns, `app` raises `SystemExit(0)`, the shell prompt comes back.

**Code**: `edgarpack/cli.py:553` (`_render_query_table`), `edgarpack/cli.py:785` (dispatch)

---

## Recap

The query path has four load-bearing files: `cli.py` dispatches, `financials.py` orchestrates, `concepts.py` maps metric names to GAAP concepts, and `periods.py` picks the right filings and does the math. Everything else (the ticker map, the doc map, the fact ID enrichment) is scaffolding that keeps the citations honest. The design choice that shapes all of it is that citations live in the data model, not in formatting. Every number is a `CitedValue` or `DerivedValue` from the moment it comes back from `select_period`, carrying its accession and filing date forward through every layer. The table formatter is the last thing to touch the data; by then the citations are already baked in.

If you want to modify the query path with confidence, start in `financials.py:financials`. The function is 100 lines and it names every other file you need to read. Everything under it either maps names to concepts (`concepts.py`), picks windows of time (`periods.py`), or makes the result citable (`models.py`).
