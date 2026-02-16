# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

EdgarPack transforms SEC EDGAR filings (10-K, 10-Q, 8-K) into clean, section-addressable markdown packs optimized for LLM consumption. Tagline: "llms.txt for SEC filings." Token reduction is ~3x (300K+ tokens to ~107K), file size ~5-7x (2MB HTML to ~400KB markdown), with deterministic output (same input + version = byte-identical output).

## Commands

```bash
# Install (editable, with dev deps)
uv pip install -e ".[dev]"

# Run all tests
python3 -m unittest discover -s tests

# Run a single test file
python3 -m unittest tests/test_sectionize.py

# Lint + format
ruff check . && ruff format .

# Type check
mypy edgarpack

# Build a filing pack (example: Apple 10-K)
edgarpack build --cik 320193 --form 10-K --out ./packs

# Build with optional artifacts
edgarpack build --cik 320193 --form 10-K --out ./packs --with-chunks --with-xbrl

# Generate static site from packs
edgarpack site --packs ./packs --out ./site

# Query financial metrics (single company)
edgarpack query NVDA revenue,net_income --period lfy
edgarpack query NVDA revenue --format json

# Compare across companies
edgarpack comps NVDA AAPL MSFT --metrics revenue,gross_margin --format table
```

## Architecture

Four-stage pipeline: **SEC → Parse → Pack → Site**

```
SEC API fetch → iXBRL strip → HTML clean → Markdown render → Sectionize → Build pack → Generate site
```

### `edgarpack/sec/` — SEC EDGAR API client
Stdlib-only HTTP client (`urllib`, not requests/aiohttp). Token bucket rate limiter at 10 req/s per SEC rules. Disk cache with SHA256 keys under `~/.edgarpack/cache/`. All async.

### `edgarpack/parse/` — HTML-to-markdown pipeline
Five sequential stages, each a pure function: `ixbrl_strip` → `html_clean` → `semantic_html` → `md_render` → `sectionize`. All regex-based (no DOM parser) by design for portability. The sectionizer is the most complex module (~600 lines) handling form-specific patterns, TOC detection, inline heading extraction, and table cell item detection.

### `edgarpack/pack/` — Pack assembly
Orchestrator in `build.py` wires the pipeline. Outputs: `llms.txt` (entry point), `manifest.json` (metadata + section index + SHA256 hashes), `filing.full.md`, `sections/*.md`, optional `chunks.ndjson` and `xbrl.json`.

### `edgarpack/site/` — Static HTML site generator
Minimal, zero-JS static site. Inline CSS, monospace typography, < 10KB per page. Has its own markdown-to-HTML converter in `build.py` (doesn't depend on external markdown libs).

### `edgarpack/query/` — Financial data queries
Single-company (`financials()`) and multi-company (`comps()`) financial queries against SEC XBRL data. Concept resolver maps normalized metric names (e.g. "revenue") to company-specific GAAP/IFRS tags, scored by recency. Period selectors handle LFY, MRQ, LTM, series. Every value is a `CitedValue` with full provenance: filing URL, XBRL Viewer deep link, and concept API URL. Derived metrics (margins, ratios) are computed from components with cross-year validation.

## Key Design Decisions

- **Stdlib-first**: No requests, no BeautifulSoup, no Click, no Jinja. Only external deps are `pydantic` (validation) and `tiktoken` (token counting). This enables sandboxed/serverless environments.
- **Regex over DOM**: All HTML processing uses regex and `html.parser` streaming. Deterministic and fast, but edge cases exist with deeply nested or malformed HTML.
- **Deterministic output**: Parser version + schema version tracked in manifests. SHA256 hashes on all artifacts.
- **SEC compliance**: Rate limiting, User-Agent header, and aggressive caching are non-negotiable.

## Known Complexity Hotspots

- **`parse/sectionize.py`**: Form-specific section detection has known edge cases. NVIDIA 10-Q failed to detect sections when item headings were embedded in table cells. Table cell detection exists but doesn't cover all patterns. Test thoroughly when modifying.
- **`site/build.py`**: Contains a bespoke markdown-to-HTML converter (~200 lines) using placeholder-based rendering. XSS protection via HTML escaping and `javascript:` URL filtering.

## Environment Variables

- `EDGARPACK_USER_AGENT` — Required by SEC. Format: `"Company Name admin@company.com"`
- `EDGARPACK_CACHE_DIR` — Override cache location (default: `~/.edgarpack/cache`)

## Ruff Config

Line length 100, target Python 3.11+, lint rules: E, F, I, N, W, UP. mypy strict mode enabled.
