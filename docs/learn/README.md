# Learn EdgarPack

This pack is for people who want to understand EdgarPack by running it.

You do not need to read Python to use these trails. Run the commands, look at the files or output they point to, then read the short explanation underneath. If `edgarpack` is not installed on your shell path, prefix the examples with `uv run`:

```bash
uv run edgarpack query NVDA revenue --period ltm
```

EdgarPack turns public filings into two kinds of output:

- clean local filing packs, mostly markdown and section files;
- cited answers to financial questions, usually from SEC companyfacts or pack-local facts.

The cited answer is the product promise. If EdgarPack prints a number, the result carries source data with it. If it cannot find the fact, it should say so. The tool may return a gap. It cannot invent a clean answer.

## A short map

```text
you run a command
  |
  +-- query / comps / compare
  |     resolve the company
  |     fetch or load reported facts
  |     match the metric name
  |     choose the period
  |     attach citations
  |     print a table or JSON
  |
  +-- build
  |     fetch the primary filing
  |     clean the HTML
  |     render markdown
  |     split sections
  |     write manifest hashes
  |
  +-- which
  |     read built packs
  |     find company-specific KPIs
  |     cache rows for later query calls
  |
  +-- diff / timeline
  |     compare two local packs
  |     anchor changed paragraphs
  |     write text, JSON, or static HTML
  |
  +-- distill
        read one pack
        write a smaller bundle of findings, metrics, evidence, and gaps
        check that rows point to evidence
```

The pack is the local filing object. Ordinary SEC metric queries can work without one because the SEC publishes companyfacts separately. Anything that needs filing text, section files, disclosed KPIs, redlines, registration timelines, or distill bundles needs a pack.

## How to use this

Start with [Trail 0](trail-0-full-loop.md). It gives you a few small commands to run, then explains what happened.

```bash
edgarpack query NVDA revenue --period ltm
```

After that, pick the trail closest to the thing you want to learn or change.

| If you care about... | Read first | Then read |
| --- | --- | --- |
| one-company metric queries | [Trail 0](trail-0-full-loop.md) | [ref-financials](ref/ref-financials.md), [ref-query-models](ref/ref-query-models.md) |
| building filing packs | [Trail 1](trail-1-build-a-pack.md) | [ref-pack-build](ref/ref-pack-build.md), [ref-sectionize](ref/ref-sectionize.md) |
| SEC request pacing and cache behavior | [Trail 2](trail-2-rate-limited-fetch.md) | [ref-sec-client](ref/ref-sec-client.md), [ref-cache](ref/ref-cache.md) |
| LTM, LFY, MRQ, and period math | [Trail 3](trail-3-period-selection.md) | [ref-periods](ref/ref-periods.md), `tests/test_periods.py` |
| filing links and citation anchors | [Trail 4](trail-4-citation-anchors.md) | [ref-query-models](ref/ref-query-models.md), `tests/test_query_links.py` |
| side-by-side company tables | [Trail 5](trail-5-compare-companies.md) | `edgarpack/compare.py`, `edgarpack/query/comps.py` |
| company-specific KPI discovery | [Trail 6](trail-6-which-kpi-discovery.md) | `edgarpack/query/kpi_discover.py`, `tests/test_kpi_discover.py` |
| S-1 or other registration filings | [Trail 7](trail-7-s1-pre-ipo.md) | [ref-s1-financials](ref/ref-s1-financials.md), [docs/S1.md](../S1.md) |
| filing redlines | [Trail 8](trail-8-static-diff-report.md) | [ref-diff-reports](ref/ref-diff-reports.md) |
| small cited research bundles | [Trail 9](trail-9-distill-bundle.md) | [ref-distill](ref/ref-distill.md), [docs/DISTILL.md](../DISTILL.md) |

## The command surface

| Surface | Command | Reads from | Writes or prints |
| --- | --- | --- | --- |
| cited metric query | `edgarpack query NVDA revenue --period ltm` | SEC companyfacts, or pack-local China facts | table or JSON with citation records |
| filing pack | `edgarpack build NVDA --form 10-K --with-chunks` | SEC archive primary filing | `filing.full.md`, `sections/`, `manifest.json`, optional chunks |
| KPI discovery | `edgarpack which FIG` | built packs for the company | disclosed KPI matrix and cached rows |
| company comparison | `edgarpack compare NVDA BIDU BABA --metrics revenue --currency usd` | SEC facts plus HKEX/SSE pack facts | side-by-side table with native and USD context |
| filing diff | `edgarpack diff --format html ...` | two local packs | static HTML with paragraph anchors |
| registration timeline | `edgarpack timeline ...` | local S-1 / S-1/A / 424B packs | index plus pair reports |
| distill bundle | `edgarpack distill run lime-s1 --pack packs/...` | one existing pack | small bundle under `reports/<slug>/` |
| China Lens API | `edgarpack api` | China storage service and fixtures/imports | evidence search, pack jobs, citation lookup |

China Lens is larger than this learn pack. These trails show the places where query routing touches HKEX and SSE facts. For the service itself, use `docs/china-lens/` and `docs/TESTING.md`.

## What changed recently

- Query table rendering moved out of CLI-only code into `edgarpack/query/render.py`.
- Formula evaluation is shared by SEC and S-1 paths in `edgarpack/query/formula.py`.
- `distill` is a first-class command for producing small cited bundles from existing packs.
- China Lens has its own service, storage, API routes, and golden test lanes.
- The normal verification pass is:

```bash
scripts/symphony_quality_gate.sh
uv run --extra dev --extra china --extra sse mypy edgarpack
```

For HKEX, SSE, China Lens, citation, FX, or diff work, also run the lane named in [docs/TESTING.md](../TESTING.md).

## References

Use refs after you know which module you are touching.

- [SEC client](ref/ref-sec-client.md): request pacing, retries, and cache use.
- [cache](ref/ref-cache.md): SHA256 disk cache and atomic writes.
- [pack build](ref/ref-pack-build.md): pack orchestration and artifact order.
- [sectionize](ref/ref-sectionize.md): form-aware section IDs.
- [financials](ref/ref-financials.md): one-company query orchestration.
- [periods](ref/ref-periods.md): LFY, MRQ, LTM, and series selectors.
- [query models](ref/ref-query-models.md): citation and calculation contract.
- [identity](ref/ref-identity.md): SEC, HKEX, SSE, and private-company routing.
- [layer zero](ref/ref-query-layer-zero.md): aliases, presets, suggestions.
- [S-1 financials](ref/ref-s1-financials.md): registration filing extraction.
- [diff reports](ref/ref-diff-reports.md): static report model and HTML output.
- [distill](ref/ref-distill.md): bundle rows and validation.

## Current omissions

These are out of scope for this pack:

- `edgarpack/china/`: use `docs/china-lens/IMPLEMENTATION_TRACKER.md` and `docs/TESTING.md`.
- `edgarpack/api/`: mostly route wiring over China Lens service objects.
- `edgarpack/site/`: static rendering over built packs.
- `edgarpack/harvest/`: batch planning over `build_pack`.
- `edgarpack/index/` and `edgarpack/insights/`: useful layers over packs, but not the first path to learn.

When you change behavior, update the trail or ref in the same commit. Stale learning docs are worse than missing docs because they teach the wrong path with confidence.
