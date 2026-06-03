# Trail 3: Turn `ltm` Into The Right Filings

Time: about 14 minutes.

Most query mistakes are period mistakes. The metric can be right and the concept
can be right, but the value is still wrong if the period selector grabs the
wrong filing window.

This trail follows:

```bash
edgarpack query NVDA revenue --period ltm
```

## The Visual

```
all companyfacts values for Revenue
  -> remove segment breakouts where consolidated facts exist
  -> split annual and quarterly candidates
  -> pick the latest cumulative quarter
  -> find latest full fiscal year
  -> find matching prior-year cumulative quarter
  -> compute MRP + LFY - MRP_prior
  -> return DerivedValue with all three component citations
```

## `select_period()` Is A Router

`financials()` passes one metric, one concept, and one period string into
`select_period()`. The router lives at `edgarpack/query/periods.py:1160`.
It accepts scalar selectors like `lfy`, `mrq`, `mrp`, `ltm`, `ltm-N`, and series
selectors like `annual:N` and `quarterly:N`. The CLI parses comma-separated
period lists before it calls `financials()`; that parser is
`parse_period_spec()` at `edgarpack/query/periods.py:1323`.

For `ltm`, the path is:

```text
select_period()
  -> select_ltm()
    -> _select_ltm_like(years_back=0)
```

`ltm-1` and `ltm-N` use the same helper with a shifted anchor year. See
`edgarpack/query/periods.py:976`, `edgarpack/query/periods.py:1012`,
`edgarpack/query/periods.py:1039`, and `edgarpack/query/periods.py:535`.

## First, Pull The Candidate Facts

The selector starts by pulling every reported value for the concept with
`_extract_values()` at `edgarpack/query/periods.py:176`. That function walks the
companyfacts taxonomy and unit buckets, then returns raw SEC fact dicts.

Before those facts are used, they pass through `_filter_segment_entries()` at
`edgarpack/query/periods.py:138`.

The problem is simple: SEC companyfacts can hold consolidated revenue and
segment revenue in the same concept list. If you ask for revenue, you want the
total company value, not the gaming segment or cloud segment.

The filter groups facts by filing context:

```text
accession + fiscal year + fiscal period + start date + end date
```

When several facts share that context, a fact with an SEC `frame` wins. If no
frame exists, the largest absolute value wins. That fallback is not magic; it is
the practical rule that consolidated totals are usually larger than segment
pieces.

## Then, Separate Annual And Quarterly Values

Duration metrics like revenue need both annual and quarterly values. Instant
metrics like cash or total assets do not; `ltm` for those routes to the most
recent period instead of fake four-quarter math.

For duration metrics, `_select_ltm_like()` builds a quarterly candidate list and
sorts it by recency. The recency key uses period end, quarter length, fiscal
year, and filed date. The picker then chooses the cumulative quarter when a
filing reports both a three-month standalone value and a year-to-date value. The
cumulative picker starts at `edgarpack/query/periods.py:430`.

This is the critical distinction:

| Filing row | Example | Use for LTM? |
| --- | --- | --- |
| standalone quarter | Q3 revenue for only three months | no |
| cumulative quarter | Q3 year-to-date revenue for nine months | yes |
| annual | FY revenue from the 10-K | yes |

LTM math needs cumulative values because the formula subtracts one cumulative
window from another.

## The Formula Is Only Safe With Three Components

For a Q3 anchor:

```text
MRP       = current fiscal year Q3 cumulative revenue
LFY       = latest full fiscal year revenue
MRP_prior = prior fiscal year Q3 cumulative revenue

LTM = MRP + LFY - MRP_prior
```

`_assert_ltm_invariant()` at `edgarpack/query/periods.py:493` enforces the
component shape. A non-null LTM derived value must carry the component citations
that explain the number. If a component is missing, the code records a diagnostic
or degrades to a reported value according to the selector path. It does not
create an uncited LTM scalar.

Derived arithmetic uses the shared formula evaluator in
`edgarpack/query/formula.py:10` for named formula shapes elsewhere in the query
layer. The LTM path is more specific because it needs date-window semantics, not
just arithmetic.

## S-1 Pseudo-Periods Are Separate

Registration filings do not behave like mature public-company 10-K/10-Q history.
S-1 snapshot periods are guarded with `is_snapshot_pseudo_period()` at
`edgarpack/query/periods.py:1383` and handled by the S-1 path in
`edgarpack/query/s1_financials.py`.

That separation matters. Do not let S-1 snapshot facts leak into ordinary LTM
math. They are sourced differently, often extracted from prose or tables, and may
carry pro-forma assumptions.

## The Failure Modes To Watch

| Symptom | Likely cause | First file to inspect |
| --- | --- | --- |
| LTM equals one quarter | standalone quarter picked instead of cumulative | `edgarpack/query/periods.py` |
| revenue looks like a segment | segment filter failed or concept picked badly | `periods.py`, then `concepts.py` |
| old annual value appears | staleness or fiscal-year alignment guard | `financials.py` |
| S-1 value enters LTM | pseudo-period guard missing | `periods.py`, `s1_financials.py` |
| derived value has no components | invariant regression | `periods.py`, `models.py` |

## What To Run

Use the normal gate, then focused period coverage:

```bash
scripts/symphony_quality_gate.sh
uv run --extra dev --extra china --extra sse mypy edgarpack
uv run pytest tests/test_periods.py tests/test_query_derivations.py tests/test_staleness_multi_period.py -q
```

If you touched live SEC selection behavior, add the live smoke lane from
`docs/TESTING.md`.
