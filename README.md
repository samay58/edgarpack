<p align="center">
  <img src="docs/assets/edgarpack-cover.png" alt="EdgarPack: a Form 13F rendered as a subway map, one holding circled and threaded to its CUSIP and accession number" width="800">
</p>

# EdgarPack

SEC filings turned into clean markdown packs, cited financial queries, and evidence-linked filing diffs, one command at a time.

## The problem

Public filings are the best primary source for public-company research. 10-Ks and 10-Qs carry the actual numbers, the actual risk factors, the actual management discussion.

They are also a nightmare for LLMs to parse and work with properly.

Why?

1. The HTML is incredibly noisy. Presentational tags, inline styles, table gymnastics, page-break artifacts.
2. XBRL (the taxonomy tagging layer) was designed for an older world. The machine-readable facts get tangled into the visible text and bloat every parse.
3. Most tools that handle this well hand you an answer and hide the building blocks. You cannot diff a section, cite a specific line, or feed the cleaned prose into your own pipeline.

EdgarPack exists to compress a filing down to its substantive pieces and give them back to you as something you can actually work with. Clean section markdown. Deterministic artifacts. Every number cited to the exact accession, concept, and filing URL it came from, so an LLM or a human reviewer can always trace the claim back to primary source.

### By the numbers

Measured against the latest NVDA, AAPL, and TSLA 10-Ks on 2026-04-20, cl100k tokens:

- Raw 10-K HTML is a median of **~595k tokens**. The clean EdgarPack pack is a median of **~102k tokens**. That is an **85.6% reduction**, tight across the three filings (82.9% to 86.1%).
- The raw filings do not fit in any mainstream LLM context window. The clean packs fit in GPT-4 Turbo's 128k window with room for citations and instructions.
- At Claude 3.5 Sonnet input pricing ($3 / 1M tokens): raw costs about $1.79 per call, the pack costs about $0.31 per call. Same filing, ~5.8x cheaper to feed in.
- About a fifth of the win is iXBRL tag stripping. The rest comes from the semantic cleaning, markdown rendering, and polish passes together.

Full methodology, per-filing table, cost breakdown at two providers, and a section on where the win is smaller than you think in [`docs/BENCHMARKS.md`](docs/BENCHMARKS.md). Committed raw artifacts (raw HTML, stripped HTML, clean markdown) under [`benchmarks/artifacts/`](benchmarks/artifacts/) if you want to re-count anything yourself.

I built it because I do financial research daily and wanted three things the existing tools did not give me: clean section-level artifacts I could diff, deterministic output so downstream caches stay valid, and citations on every value that point back to the exact line in the exact filing. The last part is the one that really matters. If I pull an ARR figure out of a 10-K, I want the URL that took me there, not a promise that a model got it right.

## Start here

If this is your first time using EdgarPack, read these in order:

1. [`docs/GETTING_STARTED.md`](docs/GETTING_STARTED.md): the first 15 minutes, from install to your first cited answer.
2. [`docs/WORKFLOWS.md`](docs/WORKFLOWS.md): practical research recipes for public companies, pre-IPO S-1 filers, cross-market comps, KPI discovery, and filing diffs.
3. [`docs/QUERY.md`](docs/QUERY.md): the metric, period, citation, JSON, and derived-value reference.
4. [`docs/OBSERVATORY.md`](docs/OBSERVATORY.md): how to use filing diffs, static HTML reports, and S-1 registration timelines.
5. [`docs/learn/README.md`](docs/learn/README.md): the code walk-through for engineers and agents once you want internals.

If you installed EdgarPack from PyPI, run commands as `edgarpack ...`. If you are working from this repo, run the same commands as `uv run edgarpack ...`. The docs use `edgarpack` for readability, but the repo-local form is often what you want during development.

## What you get

A handful of commands cover most of the research loop. The commands below are the ones I reach for daily; the full user workflows are in [`docs/WORKFLOWS.md`](docs/WORKFLOWS.md).

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

`which` walks every pack you have built for a company, pulls the qualitative metrics out of MD&A (paid customers, ARR, NRR, etc.), and shows a metric-by-period matrix so you know what you can query before asking. Run `edgarpack build` first for the filings you care about.

**Build a filing pack:**

```bash
edgarpack build NVDA --form 10-K
# CIK and company names work too:
edgarpack build 0001045810 --form 10-K
edgarpack build "NVIDIA" --form 10-K
```

One full-filing markdown file, one file per detected section, a manifest with hashes and offsets, optional chunk and XBRL artifacts. The output runs through a polish pass that strips TOC page-break spam, recovers bullet lists trapped in tables, normalizes heading levels, and simplifies wide financial tables into a readable blockquote format. Deterministic. Rebuild produces the same bytes.

**Review what changed between filings:**

```bash
edgarpack diff --ticker NVDA --form 10-K
edgarpack diff --ticker NVDA --form 10-K --format html --out ./reports/nvda-10k.html
```

The text output is fast triage. The HTML report is the thing to open when you want to actually read the changed paragraphs: old text, new text, collapsed context, section rail, SEC links, and local pack links.

**Work with pre-IPO S-1 filers:**

```bash
edgarpack build "Cerebras Systems" --form S-1 --last 2
edgarpack query "Cerebras Systems" revenue,gross_profit,net_income,operating_cash_flow,capex,free_cash_flow --period lfy,lfy-1
edgarpack timeline --series registration --cik 0002021728 --packs ./packs --format html --out ./reports/cerebras-s1
```

S-1 filers usually do not have SEC companyfacts yet. EdgarPack reads the built registration packs instead, extracts selected/summary financial data when the table shape is supported, computes simple S-1-derived metrics like free cash flow, and gives you a registration-timeline redline for the filing chain. `capital_expenditures` works as an alias for `capex`.

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

If you want LLM-assisted extraction for table shapes EdgarPack cannot parse deterministically, install the VLM extra and export an Anthropic key:

```bash
uv pip install -e ".[dev,china,vlm]"
export ANTHROPIC_API_KEY="sk-ant-..."
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
# Build & browse (all accept ticker / CIK / company name; paginate into full history)
edgarpack build NVDA --form 10-K                              # build latest 10-K
edgarpack build META --accession 0001326801-19-000009         # or any historical accession
edgarpack list "NVIDIA" --form 10-K --limit 10                # form-filtered, full history
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
edgarpack diff --ticker NVDA --form 10-K --format html \
  --out ./reports/nvda-10k.html                               # static local HTML report
edgarpack timeline --ticker "NVIDIA" \
  --section 10k_parti_item1a_risk_factors                    # section arc across filings
edgarpack timeline --series registration --cik 0002021728 \
  --packs ./packs --format html --out ./reports/cerebras-s1    # S-1 amendment chain

# SSE (Shanghai Stock Exchange) prospectuses. Requires the [sse] extra.
edgarpack build-sse --url <pdf-url> --stock-code 301536 \
  --company "Unitree Robotics" --filing-date 2026-03-20           # Chinese pack
edgarpack build-sse ... --translate                              # + zh->en; needs EDGARPACK_DEEPINFRA_KEY

# Maintenance
edgarpack learned list                                        # inspect self-heal concept mappings
edgarpack cache                                               # cache stats or --clear
edgarpack api --port 8000                                     # China Lens API server
```

## Historical reach

`build --accession`, `list`, and the downstream `diff` / `timeline` commands reach across a filer's full submission history, not just the recent window.

SEC splits high-volume filers across paginated submission files. For an active filer like META — thousands of Form 4 / 144 notices per year — the "recent" window can cap out in weeks, pushing older 10-Ks out of view. EdgarPack transparently follows the pagination chain when a match isn't in the recent window, so:

```bash
edgarpack build META --accession 0001326801-19-000009   # FY2018 10-K, filed 2019
edgarpack list META --form 10-K --limit 10              # all 10-Ks, not just recent
edgarpack timeline --ticker META \
  --section 10k_parti_item1a_risk_factors              # full risk-factor arc, IPO → today
```

all work the same way on a ten-year-old filing as on last week's. Older pagination files are immutable, so they're cached with a long TTL after first fetch — repeated historical lookups hit disk, not SEC.

## Filing Observatory

The observatory answers "what actually changed?" across filings. Not byte-level diffs. Paragraph-level language diffs, with the noise stripped out so the signal is readable.

Running `edgarpack diff` on NVIDIA's FY2024 vs FY2025 10-K surfaces things like: the company changed its self-description from "full-stack computing infrastructure company" to "data center scale AI infrastructure company." The China export controls section was rewritten from a chronological narrative about specific chip restrictions to a blunt statement that they "are unable to create and deliver a competitive product" under current rules. The cryptocurrency risk factor was deleted entirely. None of these show up in the financial data. They show up in the prose, and the diff engine finds them.

What gets filtered out: table-of-contents links, date/fiscal-year rollovers, cross-reference sentences ("See Item 7 for discussion..."), financial statement tables, signature blocks. These all change mechanically every year and obscure the real changes. The diff engine detects and suppresses them so the output is the 15-20 sections that actually matter, not the 60+ sections that technically differ.

```bash
edgarpack diff --ticker NVDA --form 10-K --format full
edgarpack diff --ticker NVDA --form 10-K --format html --out ./reports/nvda-10k.html
```

See [`docs/OBSERVATORY.md`](docs/OBSERVATORY.md) for the full diff workflow, HTML report output, S-1 registration timelines, and API model.

## China Lens

A parallel pipeline for HKEX, CNINFO, and SSE filings. Same citation shape as the SEC path, different source formats.

**HKEX** tickers (`0700.HK`, `BIDU`, `BABA`, `9988.HK`) are first-class in `query`, `comps`, and `compare`: when the resolver routes a company to HKEX, queries read from the pack's `facts.json` instead of SEC companyfacts, and currencies normalize through `data/fx_rates.csv` when you pass `--currency usd`. The extractor uses regex pattern matching against prospectus sections and falls back to a Claude API pass for tagged-but-unmatched metrics.

**SSE (Shanghai Stock Exchange)** prospectuses are built via `edgarpack build-sse`. The builder converts the PDF via `pymupdf4llm`, detects CSRC STAR Market sections using Chinese numerals (`第一节`, `第二节`, ...), and produces the same `manifest.json` + `sections/*.md` + `llms.txt` pack layout as SEC filings. Add `--translate` (requires `EDGARPACK_DEEPINFRA_KEY`) to run the zh->en translation pipeline, which is section-aware and validated against glossary consistency, literal-token preservation, and numeric fidelity.

A FastAPI workspace (`edgarpack api`) exposes the Evidence Explorer on top of the same data. See [`docs/china-lens/IMPLEMENTATION_TRACKER.md`](docs/china-lens/IMPLEMENTATION_TRACKER.md) for the current status and the [HKEX section of docs/QUERY.md](docs/QUERY.md#hkex-path) for query-layer details.

## Development

```bash
uv pip install -e ".[dev]"
ruff check .
ruff format --check .
uv run pytest tests/
```

The parser and pack layout are versioned (`PARSER_VERSION`, `SCHEMA_VERSION` in `edgarpack/config.py`) so downstream caches know when to invalidate. `PARSER_VERSION` was bumped to `0.2.0` with the addition of the polish pass and structural rendering fixes. Tests include a determinism check that rebuilds a pack byte-for-byte. Changes to HTML cleaning, section detection, or chunking will usually require regenerating fixtures.

Network tests that hit real SEC endpoints are gated on `EDGARPACK_USER_AGENT` being set. See [`docs/TESTING.md`](docs/TESTING.md) for the offline and live lanes.
