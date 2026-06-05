# Trail 6: Find the KPIs a company discloses

Time: about 12 minutes.

Run:

```bash
edgarpack which FIG
```

`query` answers a named question such as "what was Figma revenue last year?" `which` answers a different question: "what company-specific operating metrics has Figma disclosed in its filings?"

That second question needs built packs. The SEC companyfacts API is not enough, because many operating KPIs live in MD&A prose, tables, and registration filing sections.

## Try it

First make sure you have packs:

```bash
edgarpack build FIG --form 10-K --last 3 --with-chunks --out ./packs
```

Then run discovery:

```bash
edgarpack which FIG
```

Look for metric slugs in the left column and period labels across the row. Those slugs are the names you can try in later `query` calls.

Run it again:

```bash
edgarpack which FIG
```

The second run should mostly replay cached discovery rows. If you want to force a new scan, use:

```bash
edgarpack which FIG --no-cache
```

Use `--no-cache` sparingly. It can rerun the model pass for each filing.

## The command reads packs

For SEC filers, `_cmd_which()` resolves the company to a CIK and asks the pack registry for local packs. If none are registered, the command points the user back to `edgarpack build`.

The command does not fetch fresh filings from the SEC. You decide the filing universe by building packs first.

Eligible packs include 10-K, 10-Q, 20-F, and registration forms. Other forms can still exist in the registry, but they are not the main target for this scan.

## Discovery is cached by filing

For each eligible pack, `_discover_pack()` checks whether discovery has already completed for that CIK, accession, discovery version, and pack fingerprint. If it has, the cached rows replay. If a prior scan found no qualifying KPIs, the empty result is cached too.

That empty sentinel matters. Without it, every `which` call would pay to rediscover that a filing had nothing useful.

When the cache misses, EdgarPack loads the pack manifest, selects filing sections, passes the useful text through the KPI discovery extractor, and stores accepted rows in the learned registry. It also stores candidate windows and rejections so a later debug pass can see what happened.

## Slugs are meant to stay stable

Companies change words. A metric called "Paid Users" in one filing might become "Paid Seats" later.

The discovery pass receives existing slugs for the company. That gives the extractor a chance to reuse the same slug instead of creating a new one for every wording change. In the aggregate view, the latest display name wins, and older names can appear as aliases.

The point is not to hide naming drift. It is to keep `edgarpack query FIG paid_seats` from breaking just because the company changed a label in a later filing.

## Catalog KPIs are separate

Some metrics are part of the known KPI catalog, such as ARR or net revenue retention. Those rows do not come from the free-form discovery pass.

`which` can also read already-cached catalog hits from the learned registry. A catalog KPI appears only if the company has previously produced a cached row for that metric. This keeps the output tied to actual disclosures, not a wish list of metrics EdgarPack knows in theory.

`--only discovered` hides catalog rows. `--only catalog` does the reverse. The default shows both, with discovered company-specific rows first.

## Query can use discovered rows

Discovery also feeds later queries. Once a row is cached, `financials()` can resolve a company-specific slug through `lookup_company_kpi()`.

If you run:

```bash
edgarpack query FIG paid_seats --period lfy
```

the normal metric map will not know `paid_seats`. The query path can still find it if `which` already wrote the row to the company KPI cache.

For discovered KPIs, LTM degrades to LFY. EdgarPack records that as a diagnostic because it is not doing a real three-filing LTM calculation over free-form KPI rows.

## In the code

- `edgarpack/cli.py:902` registers `which`; `_cmd_which()` starts at `edgarpack/cli.py:3618`.
- `edgarpack/cli.py:3646` routes SSE and HKEX companies to the China-specific `which` path.
- `edgarpack/cli.py:3663` loads the pack registry for SEC filers.
- `edgarpack/query/kpi_discover.py:45` filters eligible pack forms.
- `edgarpack/query/kpi_discover.py:299` discovers or replays one pack.
- `edgarpack/query/kpi_discover.py:369` through `edgarpack/query/kpi_discover.py:383` replay completed cached runs.
- `edgarpack/query/kpi_discover.py:385` through `edgarpack/query/kpi_discover.py:391` pass existing slugs into the extractor.
- `edgarpack/query/kpi_discover.py:412` through `edgarpack/query/kpi_discover.py:454` cache empty runs.
- `edgarpack/query/kpi_extract.py:1873` runs staged discovery for one pack.
- `edgarpack/query/kpi_discover.py:552` reads cached catalog hits.
- `edgarpack/query/kpi_discover.py:706` through `edgarpack/query/kpi_discover.py:799` aggregates rows by slug.
- `edgarpack/query/kpi_discover.py:820` looks up a cached company KPI for later `query` calls.
