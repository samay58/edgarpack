# EdgarPack

SEC filings turned into clean markdown packs and cited financial queries, one command at a time.

## The problem

Public filings are the best primary source for public-company research. 10-Ks and 10-Qs carry the actual numbers, the actual risk factors, the actual management discussion. They're also a pain to work with programmatically. Raw HTML is noisy, inline XBRL tags break most parsers, section boundaries drift between filers, and the tools that do handle this well hand you an answer and hide the source.

I built EdgarPack because I do financial research daily and wanted three things the existing tools didn't give me: clean section-level artifacts I could diff, deterministic output so downstream caches stay valid, and citations on every number that point back to the exact line in the exact filing. The last part is the one that really matters. If I pull an ARR figure out of a 10-K, I want the URL that took me there, not a promise that a model got it right.

## What you get

Three commands cover most of it.

**Query one metric from one company:**

```bash
edgarpack query NVDA revenue,net_income --period ltm
```

Each value carries a citation reference and a reproducible formula. Revenue for LTM is computed from the most recent 10-Q plus the last 10-K minus the prior-year 10-Q, and the output tells you which three filings it used.

**Compare companies side by side:**

```bash
edgarpack comps NVDA AMD INTC -m revenue,net_income,ebitda --period ltm
```

A comps table with inline citations by default. Drop `--citations off` if you want the clean table for a screenshot.

**Build a filing pack:**

```bash
edgarpack build --cik 0001045810 --form 10-K
```

One full-filing markdown file, one file per detected section, a manifest with hashes and offsets, optional chunk and XBRL artifacts. The output runs through a polish pass that strips TOC page-break spam, recovers bullet lists trapped in tables, normalizes heading levels, and simplifies wide financial tables into a readable blockquote format. Deterministic. Rebuild produces the same bytes.

## Install

```bash
pip install edgarpack
# or editable for local dev
uv pip install -e ".[dev]"
```

SEC requires a User-Agent on every request in the format `Name email@example.com`. Set it before running anything:

```bash
export EDGARPACK_USER_AGENT="Your Name your.email@example.com"
```

Optional cache location:

```bash
export EDGARPACK_CACHE_DIR="$HOME/.edgarpack/cache"
```

If `EDGARPACK_USER_AGENT` is missing, the first network call fails with an actionable error. Requests are rate-limited to 10 per second and cached on disk to keep repeated runs polite.

## Output layout

Each filing gets a title line at the top of `filing.full.md` (`# Company Name | Form Type | Filed YYYY-MM-DD`) followed by the polished markdown. Sections are split into individual files under `sections/`.

```text
packs/
└── 0001045810/
    └── 0001045810-25-000001/
        ├── filing.full.md
        ├── llms.txt
        ├── manifest.json
        ├── sections/
        │   ├── 10k_parti_item1_business.md
        │   ├── 10k_parti_item1a_risk_factors.md
        │   └── ...
        └── optional/
            ├── chunks.ndjson
            └── xbrl.json
```

## Period vocabulary

- `lfy`: last fiscal year
- `mrq`: most recent quarter (standalone three-month value for duration metrics)
- `mrp`: most recent reported period
- `ltm`: trailing twelve months
- `ltm-1`: prior-year trailing twelve months (same formula, fiscal-year-shifted anchor)
- `annual:N`: last N fiscal years
- `quarterly:N`: last N quarters

Full query model, JSON formats, and citation semantics in [`docs/QUERY.md`](docs/QUERY.md).

## Commands

```bash
# Build & browse
edgarpack build --cik 0001045810 --form 10-K                  # build one filing pack
edgarpack list --cik 0001045810 --form 10-K --limit 5         # recent filings
edgarpack company-llms --cik 0001045810 --out ./packs         # llms.txt index for a CIK
edgarpack site --packs ./packs --out ./site                   # static site generator

# Query & compare
edgarpack query NVDA revenue,net_income --period ltm          # single company, cited values
edgarpack comps NVDA AMD INTC -m revenue,ebitda --period ltm  # side-by-side comparison

# Bulk harvest & search
edgarpack harvest --universe universe.toml --refresh          # bulk-download from a spec file
edgarpack index --packs ./packs --incremental                 # build the search index
edgarpack search "export controls" --topic risk:export        # full-text search across packs

# Observatory
edgarpack diff --ticker NVDA --form 10-K                      # compare latest two filings
edgarpack timeline --ticker NVDA --section 10k_parti_item1a   # one section over time

# Maintenance
edgarpack learned list                                        # inspect self-heal concept mappings
edgarpack cache                                               # cache stats or --clear
edgarpack api --port 8000                                     # China Lens API server
```

## Filing Observatory

The `diff`, `timeline`, and `search` commands power the Filing Observatory, a web view that stitches packs together into side-by-side diffs, section histories, and cross-corpus search. Change intensity is similarity-weighted so rewrites rank above mechanical rollovers (date rollovers, page refs, numeric-only boilerplate). Every diff and timeline result is disk-cached by manifest hash pair so warm queries return in single-digit milliseconds.

The API lives at `/api/v1/observatory/...`. See [`docs/OBSERVATORY.md`](docs/OBSERVATORY.md) for the full data model and [`web/`](web/) for the Next.js frontend.

## China Lens (experimental)

An in-progress parallel pipeline for Chinese filings (CNINFO, SSE prospectuses). Different source format, same citation-backed output shape. See [`docs/china-lens/`](docs/china-lens/) for the current state. Not wired into the main CLI yet and living on a feature branch.

## Development

```bash
uv pip install -e ".[dev]"
ruff check .
ruff format --check .
uv run pytest tests/
```

The parser and pack layout are versioned (`PARSER_VERSION`, `SCHEMA_VERSION` in `edgarpack/config.py`) so downstream caches know when to invalidate. `PARSER_VERSION` was bumped to `0.2.0` with the addition of the polish pass and structural rendering fixes. Tests include a determinism check that rebuilds a pack byte-for-byte. Changes to HTML cleaning, section detection, or chunking will usually require regenerating fixtures.

Network tests that hit real SEC endpoints are gated on `EDGARPACK_USER_AGENT` being set. See [`docs/TESTING.md`](docs/TESTING.md) for the offline and live lanes.
