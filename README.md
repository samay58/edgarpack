<p align="center">
  <img src="docs/assets/edgarpack-cover.png" alt="EdgarPack: a 10-K rendered as geological strata being excavated" width="800">
</p>

# EdgarPack

SEC filings turned into clean markdown packs and cited financial queries, one command at a time.

## The problem

Public filings are the best primary source for public-company research. 10-Ks and 10-Qs carry the actual numbers, the actual risk factors, the actual management discussion. They're also a pain to work with programmatically. Raw HTML is noisy, inline XBRL tags break most parsers, section boundaries drift between filers, and the tools that do handle this well hand you an answer and hide the source.

I built EdgarPack because I do financial research daily and wanted three things the existing tools didn't give me: clean section-level artifacts I could diff, deterministic output so downstream caches stay valid, and citations on every number that point back to the exact line in the exact filing. The last part is the one that really matters. If I pull an ARR figure out of a 10-K, I want the URL that took me there, not a promise that a model got it right.

## What you get

A handful of commands cover most of the research loop. The four below are the ones I reach for daily; the full surface is in the [Commands](#commands) section.

**Query one metric from one company:**

```bash
edgarpack query NVDA revenue,net_income --period ltm
# ticker, CIK, or company name all work:
edgarpack query "NVIDIA" revenue,net_income --period ltm
edgarpack query "apple inc" revenue --period lfy
```

Each value carries a citation reference and a reproducible formula. Revenue for LTM is computed from the most recent 10-Q plus the last 10-K minus the prior-year 10-Q, and the output tells you which three filings it used.

**Compare companies side by side:**

```bash
edgarpack comps NVDA AMD INTC -m revenue,net_income,ebitda --period ltm
```

A comps table with inline citations by default. Drop `--citations off` if you want the clean table for a screenshot.

**Cross-market comparison (USD-normalized):**

```bash
edgarpack compare NVDA BIDU BABA --metrics revenue,gross_margin --period lfy
```

`compare` handles SEC + HKEX filers in one table, converts non-USD amounts via the bundled FX file, and leaves a footnote with the original reporting currency for each column.

**List the KPIs a company actually discloses:**

```bash
edgarpack which FIG
edgarpack which "Figma"
```

`which` walks every pack you have built for a company, pulls the qualitative metrics out of MD&A (paid seats, ARR, NRR, etc.), and shows a metric-by-period matrix so you know what you can query before asking. Run `edgarpack build` first for the filings you care about.

**Build a filing pack:**

```bash
edgarpack build NVDA --form 10-K
# CIK and company names work too:
edgarpack build 0001045810 --form 10-K
edgarpack build "NVIDIA" --form 10-K
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

- `lfy`, `lfy-N`: last fiscal year (and N years back)
- `mrq`, `mrq-N`: most recent quarter (standalone 3-month); `mrq-N` returns the same fiscal quarter N years back
- `mrp`: most recent reported period
- `ltm`, `ltm-N`: trailing twelve months (and N years back; `ltm-1` is the prior year's TTM window)
- `annual:N`: last N fiscal years
- `quarterly:N`: last N quarters

Pass a CSV to `--period` on `query` to render a metrics x periods grid:

```bash
edgarpack query NVDA revenue,net_income,gross_margin --period lfy,lfy-1,lfy-2
edgarpack query NVDA --preset perf --period ltm,ltm-1,ltm-2
```

`--preset perf` expands to a curated analyst panel
(`revenue`, `revenue_growth_yoy`, `revenue_cagr_3y`, margins, `r_and_d_intensity`, `sga_intensity`, `fcf_margin`).
Columns follow the `--period` order exactly, so put newest first if you want
the newest period on the LEFT.

Full query model, JSON formats, derived metric catalog (including CAGR),
and citation semantics in [`docs/QUERY.md`](docs/QUERY.md).

## Commands

```bash
# Build & browse (all accept ticker / CIK / company name)
edgarpack build NVDA --form 10-K                              # build one filing pack
edgarpack list "NVIDIA" --form 10-K --limit 5                 # recent filings
edgarpack company-llms AAPL --out ./packs                     # llms.txt index
edgarpack site --packs ./packs --out ./site                   # static site generator
edgarpack which FIG                                           # MD&A KPIs a company discloses

# Query & compare
edgarpack query NVDA revenue,net_income --period ltm          # single company, cited values
edgarpack comps NVDA AMD INTC -m revenue,ebitda --period ltm  # SEC-to-SEC comps table
edgarpack compare NVDA BIDU BABA -m revenue --currency usd    # cross-market (SEC + HKEX), USD-normalized

# Bulk harvest & search
edgarpack harvest --universe universe.toml --refresh          # bulk-download from a spec file
edgarpack index --packs ./packs --incremental                 # build the search index
edgarpack search "export controls" --topic risk:export        # full-text search across packs

# Observatory
edgarpack diff --ticker NVDA --form 10-K                      # compare latest two filings
edgarpack timeline --ticker "NVIDIA" --section 10k_parti_item1a   # --ticker also accepts names

# Maintenance
edgarpack learned list                                        # inspect self-heal concept mappings
edgarpack cache                                               # cache stats or --clear
edgarpack api --port 8000                                     # China Lens API server
```

## Filing Observatory

The observatory answers "what actually changed?" across filings. Not byte-level diffs. Paragraph-level language diffs, with the noise stripped out so the signal is readable.

Running `edgarpack diff` on NVIDIA's FY2024 vs FY2025 10-K surfaces things like: the company changed its self-description from "full-stack computing infrastructure company" to "data center scale AI infrastructure company." The China export controls section was rewritten from a chronological narrative about specific chip restrictions to a blunt statement that they "are unable to create and deliver a competitive product" under current rules. The cryptocurrency risk factor was deleted entirely. None of these show up in the financial data. They show up in the prose, and the diff engine finds them.

What gets filtered out: table-of-contents links, date/fiscal-year rollovers, cross-reference sentences ("See Item 7 for discussion..."), financial statement tables, signature blocks. These all change mechanically every year and obscure the real changes. The diff engine detects and suppresses them so the output is the 15-20 sections that actually matter, not the 60+ sections that technically differ.

```bash
edgarpack diff --ticker NVDA --form 10-K --format full
```

The API lives at `/api/v1/observatory/...`. See [`docs/OBSERVATORY.md`](docs/OBSERVATORY.md) for the full data model and [`web/`](web/) for the Next.js frontend.

## China Lens

A parallel pipeline for HKEX and CNINFO filings. Same citation shape as the SEC path, different source format. HKEX-listed tickers (like `0700.HK`, `BIDU`, `BABA`, `9988.HK`) are first-class in `query`, `comps`, and `compare`: when the resolver routes a company to HKEX, queries read from the pack's `facts.json` instead of SEC companyfacts, and currencies normalize through `data/fx_rates.csv` when you pass `--currency usd`. The extractor uses regex pattern matching against the prospectus sections first and falls back to a Claude API pass for tagged-but-unmatched metrics. A FastAPI workspace (`edgarpack api`) exposes the Evidence Explorer on top of the same data. See [`docs/china-lens/IMPLEMENTATION_TRACKER.md`](docs/china-lens/IMPLEMENTATION_TRACKER.md) for the current status and the [HKEX section of docs/QUERY.md](docs/QUERY.md#hkex-path) for query-layer details.

## Development

```bash
uv pip install -e ".[dev]"
ruff check .
ruff format --check .
uv run pytest tests/
```

The parser and pack layout are versioned (`PARSER_VERSION`, `SCHEMA_VERSION` in `edgarpack/config.py`) so downstream caches know when to invalidate. `PARSER_VERSION` was bumped to `0.2.0` with the addition of the polish pass and structural rendering fixes. Tests include a determinism check that rebuilds a pack byte-for-byte. Changes to HTML cleaning, section detection, or chunking will usually require regenerating fixtures.

Network tests that hit real SEC endpoints are gated on `EDGARPACK_USER_AGENT` being set. See [`docs/TESTING.md`](docs/TESTING.md) for the offline and live lanes.
