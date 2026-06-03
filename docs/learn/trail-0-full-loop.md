# Trail 0: Query One Cited Number

Time: about 12 minutes.

Use this first if you are new to the code. This trail follows one command:

```bash
edgarpack query NVDA revenue --period ltm
```

The goal is not to memorize every helper. The goal is to know the path from a
typed metric to a value that can defend itself.

## The Path

```
cli.py parser
  -> _cmd_query
    -> financials()
      -> company identity
      -> companyfacts or pack-local facts
      -> metric alias and metric map
      -> period selector
      -> citation model
    -> query/render.py
      -> table/json/audit output
```

## The CLI Does The Light Work

The console script points at `edgarpack.cli:app`; `app()` calls `main()` and exits
with the returned status code. `main()` builds the subcommand parser in one
place. The `query` parser is registered with the rest of the command surface,
then the actual work happens in `_cmd_query()`. See `edgarpack/cli.py:330`,
`edgarpack/cli.py:339`, `edgarpack/cli.py:579`, and `edgarpack/cli.py:2225`.

`_cmd_query()` does four useful things before calling the query layer:

- loads `universe.toml` when it exists, so HKEX, SSE, and private companies can
  be caught before the SEC fallback;
- parses `--period`, including comma-separated multi-period grids;
- expands `--preset` and metric aliases;
- imports query-heavy modules lazily, so `edgarpack home` and other light
  commands do not pay query import cost.

That lazy import behavior is intentional and recent. Do not move heavy imports
back to module top-level without checking startup tests.

## `financials()` Is The Main Query Function

The real query entrypoint is `financials()` in `edgarpack/query/financials.py:664`.
It accepts a company, metrics, one period selector, and a cache force flag.
The CLI handles multi-period by calling `financials()` once per parsed selector;
the function itself stays single-period.

The first branch is identity routing. If `universe.toml` resolves the input to
HKEX or SSE, `financials()` returns from the China pack path instead of hitting
SEC companyfacts. If the input looks like a six-digit China A-share code, it
builds a synthetic SSE identity and takes the same local-pack path. See
`edgarpack/query/financials.py:692` through `edgarpack/query/financials.py:741`.

If the company is SEC-backed, the function resolves the input to a CIK and
company name, fetches companyfacts, and builds a primary-document map for later
citation links. See `edgarpack/sec/tickers.py:198`,
`edgarpack/sec/xbrl.py:29`, and `edgarpack/query/financials.py:743` through
`edgarpack/query/financials.py:759`.

## Metrics Get Guarded Before Values Get Picked

Metric input is normalized before any fact is selected. If you pass no metric,
regular SEC companies default to `ALL_METRICS`; registration filers with local
S-1 packs default to the S-1 metric set. If you pass `revenue`, it is put in a
list, run through `resolve_alias()`, and checked against four accepted sources:

- hardcoded `METRIC_MAP` metrics;
- catalog KPIs;
- company-specific KPI rows discovered by `edgarpack which`;
- S-1 snapshot metric slugs.

Unknown metrics raise `MetricNotFound` with suggestions instead of falling
through to a blank `N/A`. See `edgarpack/query/financials.py:761` through
`edgarpack/query/financials.py:803`, `edgarpack/query/concepts.py:66`, and
`edgarpack/query/concepts.py:708`.

For ordinary `revenue`, the metric map supplies candidate GAAP concepts. Concept
resolution picks the best concept this company actually reports. The output is
still not a number; it is a concept choice plus metadata that says whether the
metric is a duration value, an instant value, or a derived value.

## Period Selection Produces The Value

`financials()` calls period selection once it knows the metric and concept.
For `--period ltm`, the selector lives in `edgarpack/query/periods.py`.
`select_period()` dispatches by selector string. `select_ltm()` delegates to
`_select_ltm_like()`, which finds the most recent cumulative quarter, the latest
full fiscal year, and the matching prior-year quarter. See
`edgarpack/query/periods.py:535`, `edgarpack/query/periods.py:976`, and
`edgarpack/query/periods.py:1160`.

The shape is:

```text
LTM = most recent cumulative quarter
    + latest full fiscal year
    - matching cumulative quarter from the prior year
```

That result is a `DerivedValue`, not a raw `CitedValue`, because it is computed
from components. The component map is the proof. If a required component is
missing, the code records a diagnostic instead of inventing a scalar. The model
contract starts in `edgarpack/query/models.py:24` and
`edgarpack/query/models.py:346`.

## Citations Travel With The Data

The citation fields are not formatting sugar. `CitedValue` carries the accession,
CIK, form type, filing date, period dates, concept, taxonomy, source URL, section
fields, accounting standard, reporting currency, and warning list. It also knows
how to build SEC filing, concept-history, and viewer URLs when enough source data
exists. See `edgarpack/query/models.py:24` through
`edgarpack/query/models.py:120`.

After the first result is built, `financials()` enriches fact IDs by fetching the
primary filing HTML for the accessions in the result and parsing inline XBRL
facts. That turns a broad filing link into a tighter fact anchor when the filing
has the needed `fact_id`. See `edgarpack/query/financials.py:208`,
`edgarpack/query/financials.py:261`, and [Trail 4](trail-4-citation-anchors.md).

## Rendering Is Now Its Own File

Old versions of this pack said the query table renderer lived in `cli.py`. It no
longer does. `_cmd_query()` imports `_render_query_table()` from
`edgarpack/query/render.py` for the single-period table path, while multi-period
tables use helpers from `edgarpack/query/comps.py`. See `edgarpack/cli.py:2376`
through `edgarpack/cli.py:2455` and `edgarpack/query/render.py:140`.

That split matters when you are changing output. Query data changes belong in
`financials.py` or the model files. Single-period display changes belong in
`query/render.py`. Multi-period display changes usually belong in
`query/comps.py`.

## What To Remember

There are five files you should hold in your head:

| File | What it owns |
| --- | --- |
| `edgarpack/cli.py` | command parsing, lazy imports, output-mode branching |
| `edgarpack/query/financials.py` | one-company, one-period query orchestration |
| `edgarpack/query/concepts.py` | metric names and concept resolution |
| `edgarpack/query/periods.py` | LFY, MRQ, LTM, and series selection |
| `edgarpack/query/models.py` | citation and calculation data contract |

If you change query behavior, run at least:

```bash
scripts/symphony_quality_gate.sh
uv run --extra dev --extra china --extra sse mypy edgarpack
```

For period math, add the focused period tests named in `docs/TESTING.md`.
