# Trail 5: Compare companies

Time: about 10 minutes.

Run:

```bash
edgarpack compare AAPL MSFT GOOGL --period lfy --currency both
```

`compare` is a wrapper around the one-company query path from [Trail 0](trail-0-full-loop.md). It calls `financials()` once per company, flattens each result into a column, and renders the columns together.

The extra work is about comparability: company identity, currency, fiscal years, diagnostics, and citations.

## Try it

Start with two US companies:

```bash
edgarpack compare NVDA AMD --metrics revenue,gross_margin --period lfy
```

Read the first line before you read the values. It tells you which fiscal year each column resolved to.

Now add currency handling:

```bash
edgarpack compare NVDA BIDU BABA --metrics revenue --period lfy --currency both
```

If a company reports in a non-USD currency, the table should keep the native context while also showing the USD-normalized value when rates are available.

Finally, try JSON:

```bash
edgarpack compare NVDA AMD --metrics revenue --period lfy --format json
```

Look for `citations` and `calculations` at the bottom. The comparison table is still built from cited values.

## Input is resolved before fetching

The command accepts two or more companies. Each input can be a ticker, CIK, or company name. If `universe.toml` exists, `compare` tries each name twice: first as a ticker, then as a company alias.

Unknown names in the local universe do not stop the command. They fall through to the SEC lookup inside the query path. Ambiguous local aliases do stop the command, because the config needs to be fixed before EdgarPack can know which company the user meant.

## One column per company

`compare` calls `_gather()`, which runs `_fetch_one()` for every company with `asyncio.gather()`. The fetches can overlap, but SEC traffic still flows through the same per-event-loop client and no-burst rate limiter from [Trail 2](trail-2-rate-limited-fetch.md).

Each `_fetch_one()` call returns a `CompanyColumn`. It keeps:

- the display ticker and company name;
- the resolved period label;
- the reporting currency;
- one representative cited value per metric;
- diagnostics from the underlying query.

If a metric returns a list, `_flatten()` keeps the first value. For LTM, the value itself can still be a derived value with component citations. The comparison table does not show every component in the cell, but the source registry can still record the calculation.

## Currency conversion depends on the metric

For non-USD values, EdgarPack converts with a convention tied to the metric:

- balance-sheet metrics use a spot rate;
- income-statement and cash-flow metrics use an average rate;
- ratios, growth rates, headcount, and pure counts do not convert as currency;
- revenue per employee uses the revenue convention.

If no rate is available, the row keeps the native value. The command does not fail the whole comparison because one FX conversion is missing.

The default `--currency both` prints USD while preserving native context. `--currency native` suppresses USD conversion. `--currency usd` favors the normalized view.

## The period header is a warning label

`lfy` does not always mean the same calendar window across companies. Apple, Microsoft, and Alphabet can all have different fiscal-year ends.

The table header prints the requested selector and the resolved fiscal year. If every column resolves to the same label, it prints a compact header like:

```text
Period: lfy (FY2024)
```

If labels differ, it prints each company’s resolved period:

```text
Period: lfy; fiscal years differ: AAPL=FY2024, MSFT=FY2025, GOOGL=FY2024
```

That line is not decoration. It prevents the reader from treating mismatched fiscal periods as clean comparables.

## Diagnostics and sources follow the columns

Query diagnostics are collected per company and printed in one warnings block. Citation markers are built from the same `CitationRegistry` used elsewhere. JSON and markdown modes use the same columns; only the renderer changes.

## In the code

- `edgarpack/cli.py:947` registers `compare`.
- `edgarpack/compare.py:441` is `cmd_compare()`.
- `edgarpack/compare.py:455` through `edgarpack/compare.py:470` run the local identity pre-check.
- `edgarpack/compare.py:175` fetches columns concurrently.
- `edgarpack/compare.py:58` builds one column by calling `financials()`.
- `edgarpack/compare.py:50` flattens scalar and list results.
- `edgarpack/query/currency.py:58` chooses spot versus average FX convention.
- `edgarpack/query/currency.py:103` converts one cited value to USD when possible.
- `edgarpack/compare.py:283` builds the period header.
- `edgarpack/compare.py:296` renders diagnostics.
- `edgarpack/compare.py:309` renders the default table.
