# Trail 3: Turn `ltm` into filings

Time: about 14 minutes.

A query can have the right metric and the right accounting concept and still be wrong. Period selection is usually where that happens.

This trail follows the same command as [Trail 0](trail-0-full-loop.md):

```bash
edgarpack query NVDA revenue --period ltm
```

## Try it

Compare three period requests:

```bash
edgarpack query NVDA revenue --period lfy
edgarpack query NVDA revenue --period mrq
edgarpack query NVDA revenue --period ltm --audit
```

`lfy` should read like one annual filing value. `mrq` should read like the most recent quarter. `ltm --audit` should show a calculation with components.

Now ask for a small period grid:

```bash
edgarpack query NVDA revenue --period lfy,lfy-1,lfy-2
```

That output is useful for checking whether the selector is walking fiscal years in the order you expect.

## The path

```text
all reported values for the revenue concept
  -> prefer consolidated facts inside each filing context
  -> split annual and quarterly candidates
  -> pick the latest cumulative quarter
  -> find the latest full fiscal year
  -> find the matching prior-year cumulative quarter
  -> compute MRP + LFY - MRP_prior
  -> return a derived value with component citations
```

`select_period()` routes period strings. It handles scalar selectors like `lfy`, `mrq`, `mrp`, `ltm`, `ltm-N`, and series selectors like `annual:N` and `quarterly:N`. The CLI parses comma-separated period lists before calling `financials()`, so the query function still receives one selector at a time.

For `ltm`, the route is:

```text
select_period()
  -> select_ltm()
  -> _select_ltm_like(years_back=0)
```

`ltm-1` and `ltm-N` use the same helper with a shifted anchor year.

## Segment facts are filtered before period math

SEC companyfacts can put consolidated revenue and segment revenue in the same concept list. EdgarPack groups values by filing context:

```text
accession + fiscal year + fiscal period + start date + end date
```

When a group has more than one value, facts with an SEC `frame` field are kept and unframed duplicates are dropped. If no fact in the group has `frame`, EdgarPack keeps the largest absolute value as a fallback. The fallback is practical, not perfect: consolidated totals are usually larger than segment pieces.

Do not simplify this as "choose the headline number." The code is looking for XBRL `frame` period codes inside matching filing contexts.

## Duration metrics need cumulative quarters

Revenue is a duration metric. It covers a span of time. Cash is an instant metric. It is a balance at one date.

For duration metrics, LTM needs a cumulative quarter. A standalone Q3 value covers three months. A Q3 year-to-date value covers nine months. Only the second form works in this formula:

```text
MRP       = current fiscal year Q3 cumulative revenue
LFY       = latest full fiscal year revenue
MRP_prior = prior fiscal year Q3 cumulative revenue

LTM = MRP + LFY - MRP_prior
```

If the newest available quarter is really a full fiscal year, EdgarPack can return the annual value without doing arithmetic. Otherwise, a real LTM result must carry the three component roles.

## Missing pieces stay missing

`_assert_ltm_invariant()` guards the output shape. A derived LTM value must have the component roles `mrp`, `lfy`, and `mrp_prior`. A plain cited value is allowed only when the anchor is already FY or Q4. Anything else is a bug, because it risks labeling a six-month or nine-month value as twelve months.

If EdgarPack cannot compute the three-part value, it records a diagnostic and returns no scalar for that cell. That is the right failure mode. A neat number with no component proof is worse than an `N/A`.

## S-1 pseudo-periods stay out

Registration filings do not behave like 10-K and 10-Q history. S-1 snapshot values come from a different extractor and may include pro-forma assumptions. EdgarPack keeps those pseudo-periods out of ordinary annual, quarterly, and LTM selection.

That guard matters for follow-on filings too. A company can have normal 10-K history and later file an S-1. Registration-form values should not slip into `lfy` or `ltm` as if they were periodic annual or quarterly facts.

## What to run

For period work:

```bash
scripts/symphony_quality_gate.sh
uv run --extra dev --extra china --extra sse mypy edgarpack
uv run pytest tests/test_periods.py tests/test_query_derivations.py tests/test_staleness_multi_period.py -q
```

If you changed live SEC selection behavior, add the live smoke lane from [docs/TESTING.md](../TESTING.md).

## In the code

- `edgarpack/query/periods.py:1160` is `select_period()`.
- `edgarpack/query/periods.py:1323` parses comma-separated period specs for the CLI.
- `edgarpack/query/periods.py:176` extracts raw values for one concept.
- `edgarpack/query/periods.py:138` filters segment entries by filing context and XBRL `frame`.
- `edgarpack/query/periods.py:430` picks cumulative quarter candidates.
- `edgarpack/query/periods.py:535` is `_select_ltm_like()`.
- `edgarpack/query/periods.py:493` enforces the LTM output shape.
- `edgarpack/query/periods.py:976`, `edgarpack/query/periods.py:1012`, and `edgarpack/query/periods.py:1039` route `ltm`, `ltm-1`, and `ltm-N`.
- `edgarpack/query/periods.py:267` and `edgarpack/query/periods.py:288` keep registration forms out of annual and quarter form checks.
- `edgarpack/query/periods.py:1383` identifies S-1 pseudo-period selectors.
