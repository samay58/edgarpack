# Trail 5: How `edgarpack compare AAPL MSFT GOOGL --period lfy` builds a side-by-side table

**Time**: ~12 minutes
**Prereq**: [Trail 0](trail-0-full-loop.md) (you know how a single-company query works)
**Covers**: `edgarpack/cli.py:588`, `edgarpack/compare.py`, `edgarpack/identity.py`, `edgarpack/fx/`, `edgarpack/query/financials.py:financials`

You run `edgarpack compare AAPL MSFT GOOGL --period lfy --currency both`. Three seconds later a table prints with revenue, gross profit, net income, and cash across the three companies, every non-USD number converted, every row carrying a citation. Trail 0 showed you what happens for one ticker. This trail is what happens when you have three and two of them might be on HKEX.

---

## 1. The subparser takes two or more companies

`compare` accepts one or more positional tickers, a comma-separated `--metrics`, a `--period` that defaults to `lfy`, a `--currency` with three modes (`native`, `usd`, `both`), and a `--format` with three modes (`table`, `json`, `markdown`).

```python
p_compare = sub.add_parser("compare", help="Side-by-side comparison of two or more companies")
p_compare.add_argument("companies", nargs="+", ...)
p_compare.add_argument("--metrics", help="Comma-separated metric names")
p_compare.add_argument("--period", default="lfy", ...)
p_compare.add_argument("--currency", choices=["native", "usd", "both"], default="both", ...)
```

`nargs="+"` is what lets you write three tickers in a row. The dispatcher near the top of `main()` intercepts `compare` before the normal subcommand chain so `cmd_compare` runs before anything else is set up.

**Code**: `edgarpack/cli.py:588` (`p_compare = sub.add_parser(...)`), `edgarpack/cli.py:612` (`if args.cmd == "compare"`).

---

## 2. Identity resolution runs twice per input

Before any query fires, `cmd_compare` loads `universe.toml` into an `IdentityIndex` and walks each company name through `resolve()` twice: first as a ticker, then (on `UnknownCompany`) as a company alias.

```python
for name in args.companies:
    try:
        resolve(idx, ticker=name, company=None)
    except UnknownCompany:
        try:
            resolve(idx, ticker=None, company=name)
        except UnknownCompany:
            continue  # fall through to SEC ticker lookup inside _gather
```

The double-try is deliberate: a user who types `GOOG` means the ticker; a user who types `Alphabet` means the alias. `resolve()` doesn't guess which shape a string is; the caller tries both. Unknown inputs don't bail here. They fall through to the SEC ticker lookup inside `_fetch_one`, which is how the `--companies AAPL MSFT NOT_IN_UNIVERSE` case still works.

`AmbiguousCompany` does bail: if two aliases in `universe.toml` resolve to different tickers, the config is broken and the user needs to fix it before any query runs.

**Code**: `edgarpack/compare.py:324-353` (pre-validation loop), `edgarpack/identity.py:110` (`resolve`). Full contract in [`ref/ref-identity.md`](ref/ref-identity.md).

---

## 3. Fan-out is sequential, not parallel

`_gather()` looks like it should be `asyncio.gather(...)` but it isn't:

```python
async def _gather(names: list[str], metrics: str | None, period: str) -> list[CompanyColumn]:
    return await asyncio.gather(*(_fetch_one(n, metrics, period) for n in names))
```

Columns are fetched concurrently, while every SEC HTTP call still flows through the per-event-loop `SECClient` and its no-burst request pacer. That keeps fan-out useful without letting startup bursts punch through the SEC fair-access ceiling.

Each iteration calls `financials()` (same function Trail 0 walks) and flattens the `CitedValue | list[CitedValue]` into one representative cite per metric. When a metric returns a list of three citations (the LTM trio), `_flatten()` keeps just the first.

**Code**: `edgarpack/compare.py:184` (`_gather`), `edgarpack/compare.py:98` (`_fetch_one`), `edgarpack/compare.py:90` (`_flatten`).

---

## 4. Currency conversion picks spot vs. average per metric

`_fetch_one` classifies each returned value and, if the reporting currency isn't USD, converts it.

```python
def _convention_for(metric: str) -> str:
    if metric in _BALANCE_SHEET_METRICS:
        return "spot"
    return "average"
```

Balance-sheet metrics (`total_assets`, `cash_and_equivalents`, `total_debt`, `shares_outstanding_*`) convert at the spot rate on the fiscal-year-end date. Income-statement and cash-flow metrics convert at the average rate over the fiscal year. This is not a stylistic choice. Converting a full-year revenue number at spot produces the wrong answer the moment the rate moves during the year. The distinction is wired through `convention` in `edgarpack.fx.convert`.

Growth metrics (`revenue_growth_yoy`, `gross_margin_trend`) and ratios (`gross_margin`, `r_and_d_intensity`, `fcf_margin`) are dimensionless and bypass conversion. `revenue_per_employee` is a hybrid: native currency divided by a headcount, so it converts at the revenue convention (average). `cv.unit == "headcount"` formats as integer with no currency at all.

A `RateNotFound` or `NotImplementedError` from `fx.convert` downgrades silently: the row prints with only the native value and no USD side. Missing rates are diagnostic, not fatal.

**Code**: `edgarpack/compare.py:44` (`_convention_for`), `edgarpack/compare.py:56` (`_convert_to_usd`), `edgarpack/compare.py:130-168` (per-metric entry build).

---

## 5. The period header flags fiscal-year mismatch

Each column records a `period_label` like `FY2024` pulled from the first sample citation's `fiscal_year`. `_period_header()` dedupes those labels across columns and decides what to print:

```python
if len(unique) == 1:
    return f"Period: {period_request} ({unique[0]})"
pairs = ", ".join(f"{c.ticker}={c.period}" for c in columns)
return f"Period: {period_request}; fiscal years differ: {pairs}"
```

When every column lands on the same fiscal year you get `Period: lfy (FY2024)`. When one company's `lfy` is FY2024 and another's is FY2025 (common for non-calendar fiscal years; Apple's FY ends in September), the header becomes `Period: lfy; fiscal years differ: AAPL=FY2024, MSFT=FY2024, GOOGL=FY2024`. That is the one-line alarm that a naive side-by-side read is wrong.

The footer renders per-column context; company name, resolved period, reporting currency; and then the warnings block pulls `QueryResult.diagnostics` from each column into a flat list prefixed with `  ! TICKER.metric: message`. Most warnings here are LTM-mislabeling ones produced deep inside `periods.py`: if `lfy` returned a 9-month stub, the diagnostic surfaces here so it doesn't silently parade as a full-year value.

**Code**: `edgarpack/compare.py:230` (`_period_header`), `edgarpack/compare.py:243` (`_diagnostics_lines`), `edgarpack/compare.py:256-278` (`_format_table`: header, body, per-column footer, warnings block).

---

## 6. The handoff

The command ends by printing one of three formats: plain-text table (default), JSON (`--format json`), or a Markdown table (`--format markdown`). All three paths go through the same `CompanyColumn` objects and the same `_period_header` logic. Table vs. markdown vs. json is a rendering choice; the table contract is the same.

Identity routing set up here reappears in the `query` and `comps` subcommands. Once you understand the double-try resolution and the SEC-fallback, you understand how every multi-company command on the CLI disambiguates user input. Currency conversion, on the other hand, is currently compare-only. If you add USD conversion to `query` later, you'll import `_convert_to_usd` or its neighbors from `compare.py`; right now compare is where that logic lives.

---

## Recap

`compare` is a fan-out wrapper around the single-company `financials()` call, but the fan-out is where the subtleties live. Identity lookup runs twice per input (ticker, then alias) with an SEC fallback for companies not in `universe.toml`; query fan-out is sequential to keep the SEC rate limiter honest; currency conversion splits balance-sheet (spot) from income-statement (average) with the fiscal-year-end as the reference date; and the period header exists specifically to flag fiscal-year mismatch before the eye can be tricked into comparing different years. The load-bearing files are `edgarpack/compare.py`, `edgarpack/identity.py`, and `edgarpack/fx/convert.py`. The one design choice worth internalizing is that this code refuses to present a multi-company number as comparable when it isn't.
