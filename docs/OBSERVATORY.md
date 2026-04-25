# Filing Observatory

The observatory answers one question: what actually changed between filings?

It is not a byte-level diff. SEC filings change mechanically every year: dates roll forward, tables move, signatures change, table-of-contents links get new anchors. EdgarPack filters that noise and compares disclosure prose at the paragraph level. What remains is the part a human should read: risk-factor rewrites, business-description changes, new regulatory language, deleted sections, and meaningful shifts in how a company talks about itself.

If you are new to EdgarPack, read [`GETTING_STARTED.md`](GETTING_STARTED.md) first. Use this page when you already have packs built and want the details of `diff`, static HTML reports, and registration timelines.

If you are working from this repo and `edgarpack` is not on your PATH, prefix any command here with `uv run`.

## Fast path

Build enough filings first:

```bash
edgarpack build NVDA --form 10-K --last 3
```

Then triage the latest pair:

```bash
edgarpack diff --ticker NVDA --form 10-K
```

When you want to read the changed paragraphs, write the static report:

```bash
edgarpack diff --ticker NVDA --form 10-K --format html --out ./reports/nvda-10k.html
```

Open `./reports/nvda-10k.html` in a browser. It is a local, script-free HTML file. It includes:

- filing provenance: company, form, accession, filing date
- a changed-section rail
- old/new paragraph rows
- collapsed unchanged context
- token-level highlights for modified paragraphs
- SEC source links
- local pack-file links
- reproduce command

## Pair diffs

`--ticker` accepts a ticker, CIK, or company name. EdgarPack finds the latest two local packs for the form and compares them.

```bash
# Summary: section counts and overall intensity
edgarpack diff --ticker NVDA --form 10-K

# Full terminal output: paragraph-level old/new text
edgarpack diff --ticker "NVIDIA" --form 10-K --format full

# JSON: machine-readable downstream input
edgarpack diff --ticker NVDA --form 10-K --format json

# HTML: best human reading surface
edgarpack diff --ticker NVDA --form 10-K --format html --out ./reports/nvda-10k.html
```

If you already know the exact pack directories or accessions:

```bash
edgarpack diff \
  --before ./packs/0001045810/0001045810-24-000029 \
  --after ./packs/0001045810/0001045810-25-000023 \
  --format html \
  --out ./reports/nvda-pair.html
```

Use explicit `--before` / `--after` when you are reviewing a specific amendment pair, not just the latest two filings.

## Registration timelines

S-1 work is a filing-chain problem. A company may file an S-1, several S-1/As, then a 424B prospectus. Reading every draft from scratch is wasteful. The registration timeline builds one pair report per transition and an index page that points you to the highest-change steps.

```bash
edgarpack build "Cerebras Systems" --form S-1 --last 2

edgarpack timeline \
  --series registration \
  --cik 0002021728 \
  --packs ./packs \
  --format html \
  --out ./reports/cerebras-s1
```

The output directory contains:

```text
reports/cerebras-s1/
├── index.html
├── pair-001.html
├── pair-002.html
└── ...
```

Start at `index.html`. It lists each transition, section counts, and overall intensity. Click into the pair reports when a transition looks material.

For ordinary periodic filings, section timelines still work:

```bash
edgarpack timeline --ticker NVDA --section 10k_parti_item1a_risk_factors
```

HTML output is currently for `--series registration`; annual section timelines stay in terminal/JSON-style output.

## What gets filtered

**Suppressed entirely:**

- financial statement sections, where number changes are expected
- signature blocks

**Filtered at paragraph level:**

- table-of-contents links
- anchor-only paragraphs
- cross-reference boilerplate such as "See Item 7..."

**Marked as mechanical and hidden:**

- date rollovers
- fiscal-year rollovers
- page-number changes
- paragraph pairs where the only differences are mechanical tokens

**Kept but damped:**

- exhibit-index changes, because exhibit movement can matter but usually should not dominate the report

The goal is not to hide information. The goal is to stop mechanical churn from burying the disclosure changes.

## How section matching works

The engine matches sections in three passes:

1. Exact section ID: `10k_parti_item1a_risk_factors` to `10k_parti_item1a_risk_factors`.
2. Reduced section key: strip form/part prefixes so moved sections can still pair.
3. Add/remove classification: anything still unmatched is genuinely new or removed.

Within matched sections, paragraphs align with a deterministic mix of exact fingerprints and fuzzy Jaccard matching. Modified paragraphs are scored by changed-word weight, not raw line count, so a three-word date update does not look as important as a full rewritten risk paragraph.

## Reading the report

Use the section rail as triage. High-intensity sections are not automatically "important"; they are sections that changed a lot after noise filtering. MD&A often changes heavily because the underlying fiscal year changed. Risk factors, business description, legal proceedings, liquidity, and regulatory sections are usually more interesting.

For every paragraph row, check the evidence line:

- old accession and paragraph position
- new accession and paragraph position
- section ID
- source links
- optional chunk ID when chunks exist

If a row has no chunk ID, that does not invalidate it. It means the pack did not have chunk coverage for that paragraph. The accession, section, paragraph index, and offsets still anchor the evidence.

## API

The API exposes the same core model:

```text
GET /api/v1/observatory/companies/{ticker}/diff?form_type=10-K&detail=full
```

- `detail=full`: includes paragraph deltas with old/new text.
- `detail=sections`: section-level stats only.

The API is a wrapper over the same deterministic diff engine. It is not a separate summarization layer.

## Caching

Diff results are cached on disk under `~/.edgarpack/diff_cache/`. The cache key comes from both pack manifests plus a diff-cache version string. If the pack contents or diff behavior change, old cache entries are ignored. Corrupted cache files are recomputed.

## Module map

- `edgarpack/diff/text_diff.py`: paragraph splitting, TOC filtering, fingerprinting, fuzzy alignment, boilerplate detection.
- `edgarpack/diff/section_diff.py`: section matching, intensity scoring, suppression, output assembly, caching.
- `edgarpack/diff/report_models.py`: report data contract for HTML output.
- `edgarpack/diff/report_builder.py`: converts a pair of packs into an evidence-linked report model.
- `edgarpack/diff/html_report.py`: static HTML rendering and safe-link handling.
- `edgarpack/diff/timeline.py`: annual section timelines and registration-chain discovery.
- `edgarpack/api/observatory/routes.py`: API endpoints.

## Known limitations

- MD&A often changes heavily for legitimate year-specific reasons. High intensity there is expected, not automatically a red flag.
- Sectionizer quality controls report quality. If a pack has garbled section IDs, rebuild after parser fixes rather than hiding it in the renderer.
- There is no LLM semantic ranking inside sections. All paragraph changes in a section are presented evenly. That is intentional for now: the report is evidence, not generated interpretation.
