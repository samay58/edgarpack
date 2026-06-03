# Learn EdgarPack

Read this when you want to change the code without guessing.

User docs explain how to run the product. This pack explains where the work
happens in the repo. It is intentionally plain: command, code path, evidence,
output.

## The Short Map

```
CLI command
  |
  +-- query / comps / compare
  |     resolve company -> fetch or load facts -> pick metric -> pick period
  |     -> attach citation records -> render table/json
  |
  +-- build
  |     resolve filing -> fetch primary document -> clean HTML -> markdown
  |     -> section files -> optional chunks/facts -> manifest hashes
  |
  +-- which
  |     read built packs -> scan disclosed KPIs -> cache company KPI rows
  |     -> later query can reuse those rows without another scan
  |
  +-- diff / timeline
  |     compare local packs -> anchor changed paragraphs -> static HTML report
  |
  +-- distill
        read one existing pack -> extract cited rows -> write a small bundle
        -> check that every row points back to evidence
```

The rule under all of it: do not produce an unsupported claim. Numbers and
findings travel with citation data. Gaps stay gaps.

## Where To Start

| If you need to change... | Read first | Then read |
| --- | --- | --- |
| a single-company query | [Trail 0](trail-0-full-loop.md) | [ref-financials](ref/ref-financials.md), [ref-query-models](ref/ref-query-models.md) |
| period math or LTM | [Trail 3](trail-3-period-selection.md) | [ref-periods](ref/ref-periods.md), `tests/test_periods.py` |
| filing pack output | [Trail 1](trail-1-build-a-pack.md) | [ref-pack-build](ref/ref-pack-build.md), [ref-sectionize](ref/ref-sectionize.md) |
| citation links | [Trail 4](trail-4-citation-anchors.md) | [ref-query-models](ref/ref-query-models.md), `tests/test_query_links.py` |
| multi-company tables | [Trail 5](trail-5-compare-companies.md) | `edgarpack/compare.py`, `edgarpack/query/comps.py` |
| discovered KPIs | [Trail 6](trail-6-which-kpi-discovery.md) | `edgarpack/query/kpi_discover.py`, `tests/test_kpi_discover.py` |
| S-1 or pre-IPO filings | [Trail 7](trail-7-s1-pre-ipo.md) | [ref-s1-financials](ref/ref-s1-financials.md), [docs/S1.md](../S1.md) |
| filing redlines | [Trail 8](trail-8-static-diff-report.md) | [ref-diff-reports](ref/ref-diff-reports.md) |
| small cited research bundles | [Trail 9](trail-9-distill-bundle.md) | [ref-distill](ref/ref-distill.md), [docs/DISTILL.md](../DISTILL.md) |

## The Product Surfaces

| Surface | Command | Source of truth | Output |
| --- | --- | --- | --- |
| cited metric query | `edgarpack query NVDA revenue --period ltm` | SEC companyfacts or pack-local China facts | table/json with citation records |
| filing pack | `edgarpack build NVDA --form 10-K --with-chunks` | SEC archive primary filing | `filing.full.md`, `sections/`, `manifest.json`, optional chunks |
| KPI discovery | `edgarpack which FIG` | built packs for the company | disclosed KPI matrix plus cached rows |
| company comparison | `edgarpack compare NVDA BIDU BABA --metrics revenue --currency usd` | SEC facts plus HKEX/SSE pack facts | side-by-side table with native and USD context |
| filing diff | `edgarpack diff --format html ...` | two local packs | static HTML with paragraph anchors |
| registration timeline | `edgarpack timeline ...` | local S-1 / S-1/A / 424B packs | index plus pair reports |
| distill bundle | `edgarpack distill run lime-s1 --pack packs/...` | one existing pack | small cited bundle under `reports/<slug>/` |
| China Lens API | `edgarpack api` | China storage service and fixtures/imports | evidence search, pack jobs, citation resolution |

China Lens is not fully documented in this pack yet. The current learn pack
shows where query routing touches HKEX/SSE facts, then leaves the larger China
service in `docs/china-lens/` and `docs/TESTING.md`.

## What Changed Since The Old Pack

- `query` rendering moved out of the CLI into `edgarpack/query/render.py`.
- formula evaluation is shared by SEC and S-1 paths in `edgarpack/query/formula.py`.
- `distill` is now a first-class command for producing small cited bundles from
  existing packs.
- China Lens has its own service, storage, API routes, and golden test lanes.
- The quality gate now expects the repo wrapper plus strict mypy:

```bash
scripts/symphony_quality_gate.sh
uv run --extra dev --extra china --extra sse mypy edgarpack
```

For HKEX, SSE, China Lens, citation, FX, or diff work, also use the lane named in
[`docs/TESTING.md`](../TESTING.md).

## Visual Mental Model

```
                 primary filing HTML
                         |
                         v
                build creates a pack
                         |
        +----------------+----------------+
        |                                 |
        v                                 v
   query can cite                    diff can anchor
   values and formulas               paragraph changes
        |
        v
   distill can shrink one pack into rows
   where each row points to evidence
```

The pack is the shared object. Query does not need a pack for ordinary SEC
companyfacts metrics, but everything that reads text, sections, disclosed KPIs,
diffs, timelines, and distill bundles depends on built packs.

## References

Use refs when you already know which module you are changing.

- [SEC client](ref/ref-sec-client.md): request pacing, retry, cache use.
- [cache](ref/ref-cache.md): SHA256 disk cache and atomic writes.
- [pack build](ref/ref-pack-build.md): pack orchestration and artifact order.
- [sectionize](ref/ref-sectionize.md): form-aware section IDs.
- [financials](ref/ref-financials.md): single-company query orchestration.
- [periods](ref/ref-periods.md): LFY, MRQ, LTM, series selectors.
- [query models](ref/ref-query-models.md): citation and calculation contract.
- [identity](ref/ref-identity.md): SEC, HKEX, SSE, and private-company routing.
- [layer zero](ref/ref-query-layer-zero.md): aliases, presets, suggestions.
- [S-1 financials](ref/ref-s1-financials.md): registration filing extraction.
- [diff reports](ref/ref-diff-reports.md): static report model and HTML output.
- [distill](ref/ref-distill.md): cited bundle rows and validation.

## Current Omissions

The omissions are deliberate, not forgotten.

- `edgarpack/china/`: large enough for its own learn pack. Use
  `docs/china-lens/IMPLEMENTATION_TRACKER.md` and `docs/TESTING.md` today.
- `edgarpack/api/`: mostly route wiring over China Lens service objects.
- `edgarpack/site/`: static rendering over built packs.
- `edgarpack/harvest/`: batch planning over `build_pack`.
- `edgarpack/index/` and `edgarpack/insights/`: useful layers over packs, not the
  first path to learn.

When code changes, update the trail or ref in the same commit. A stale learn
pack is worse than no learn pack because it teaches the wrong path.
