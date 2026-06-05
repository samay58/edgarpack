# Trail 7: Query an S-1 company

Time: about 14 minutes.

Run:

```bash
edgarpack query CRBRS revenue
```

A pre-IPO filer breaks the normal periodic-company path. Companyfacts may be empty because there are no 10-K or 10-Q filings yet. The filing HTML may also have weak headings, which makes section-based extraction harder.

EdgarPack handles this in two places:

- build time, where registration packs get better section headings;
- query time, where missing periodic results can be filled from S-1 snapshot extraction.

## Try it

Build a registration pack:

```bash
edgarpack build CRBRS --form S-1 --out ./packs
```

Query normal historical S-1 metrics:

```bash
edgarpack query CRBRS revenue,net_income,operating_cash_flow,capex,free_cash_flow --period lfy,lfy-1
```

Then ask for pro-forma explicitly:

```bash
edgarpack query CRBRS revenue --period pro-forma
```

If S-1 extraction needs an API key and it is missing, the CLI should say that. A useful error is better than a blank result.

After a successful S-1 query, inspect the cache:

```bash
find ./packs -name s1_financials.json -print
```

Open that file and look for `extraction_status`, `source_sha256`, and `facts`.

## One form-family check controls the branch

Registration-class forms are identified by `is_registration_form()`. The family includes S-1, S-1/A, F-1, F-1/A, 424B1-5, and FWP.

That predicate is used across the pack builder, period selection, S-1 financial extraction, registration timelines, and KPI discovery. If the form family changes, update the predicate instead of scattering checks across the repo.

## Build time adds headings before cleanup

For registration forms, `_process_html_files_for_form()` injects headings from the filing table of contents before running normal HTML cleanup.

The order matters. `clean_html()` removes many attributes. S-1 heading injection needs TOC links and matching body `id=` attributes while they still exist.

The injector is conservative. It reads TOC links, keeps the first title per anchor, skips junk like page numbers and "Table of Contents", and inserts an `<h2>` before the matching body element. If a filing has no usable TOC links, it returns the HTML unchanged.

After that, the pack goes through the same markdown render and sectionize path as other filings.

## Query time tries the normal path first

`financials()` starts the same way it does for a mature SEC filer: resolve the company, fetch companyfacts, resolve metrics, select periods, and build a result.

For a pre-IPO filer, requested cells may still be empty. When any requested metric is empty, or when the user explicitly asks for `--period pro-forma`, `financials()` calls `augment_with_s1_snapshot()`.

The empty-cell check uses alias-normalized metric names. That prevents a caller who typed `Revenue` or `rev` from triggering S-1 extraction after the normal SEC path already filled `revenue`.

## The newest registration pack is the source

S-1 augmentation looks for registration packs for the CIK and starts with the newest one. It then calls `extract_or_load_snapshot()` on that pack.

The snapshot cache lives beside the pack as `s1_financials.json`. It is valid only when:

- the cache schema version matches the current extractor;
- the source hash matches the pack's `filing.full.md`;
- the JSON can be parsed into a snapshot result.

When the cache is stale or missing, EdgarPack reads the financial data sections and tries deterministic table extraction. Unsupported shapes can fall back to Haiku when the Anthropic package and API key are available.

If extraction cannot run because the API key is missing, augmentation writes placeholder cited values with `source="no_api_key"`. The CLI then prints a hint instead of leaving the user with unexplained `N/A` cells.

## S-1 facts become cited values

The snapshot extractor produces `SnapshotFact` rows. Each row stores the metric slug, fiscal period, period end, value in cents, currency, accession, audit flag, and pro-forma flag.

`snapshot_fact_to_cited_value()` converts a snapshot fact into the same `CitedValue` model used by periodic queries. The source marker is `s1_snapshot` for audited historical rows and `s1_pro_forma` for pro-forma rows.

`pick_snapshot_fact()` handles period selection inside the snapshot:

- `lfy` and `lfy-N` pick audited annual facts;
- `mrp` picks the most recent audited period;
- `pro-forma` picks the most recent pro-forma fact and ignores audited rows.

The renderer can treat these as normal cited values while still labeling S-1 and pro-forma provenance.

## S-1 values stay out of periodic math

Registration forms are excluded from the ordinary annual and quarterly form checks in `periods.py`. This matters when a company has both periodic filings and a later registration filing.

Without that guard, an S-1 value could look like another annual fact and slip into `lfy` or `ltm`. EdgarPack keeps registration snapshots on their own path.

## The timeline command is a separate surface

Pre-IPO work often needs redlines too. `edgarpack timeline --series registration --cik <cik>` walks local registration packs, sorts them by filing date, and diffs consecutive filings.

When `--format html` is used, the timeline writes an index plus one pair report per transition. [Trail 8](trail-8-static-diff-report.md) covers the report model.

To review amendments, try the timeline after you have more than one registration pack:

```bash
edgarpack timeline --series registration --cik 0002021728 --packs ./packs
```

## In the code

- `edgarpack/sec/submissions.py:101` defines `is_registration_form()`.
- `edgarpack/pack/build.py:91` runs the registration-aware parse path.
- `edgarpack/parse/s1_headings.py:69` extracts TOC section pairs.
- `edgarpack/parse/s1_headings.py:88` injects headings into registration HTML.
- `edgarpack/query/financials.py:1109` through `edgarpack/query/financials.py:1134` run S-1 augmentation after the periodic query path.
- `edgarpack/query/s1_financials.py:1318` starts S-1 result augmentation.
- `edgarpack/query/s1_financials.py:720` loads or extracts the snapshot cache.
- `edgarpack/query/s1_financials.py:146` finds selected or summary financial data sections.
- `edgarpack/query/s1_financials.py:586` builds the LLM extraction prompt when fallback is needed.
- `edgarpack/query/s1_financials.py:641` parses LLM JSON into snapshot facts.
- `edgarpack/query/s1_financials.py:911` converts snapshot facts to cited values.
- `edgarpack/query/s1_financials.py:953` selects a snapshot fact for a requested period.
- `edgarpack/query/periods.py:267` and `edgarpack/query/periods.py:288` exclude registration forms from periodic annual and quarterly checks.
- `edgarpack/cli.py:2851` renders registration timelines.
