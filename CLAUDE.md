# CLAUDE.md

Guidance for coding agents working in this repository.

## Project Summary

EdgarPack converts SEC EDGAR filings (10-K, 10-Q, 8-K) into deterministic markdown packs with section IDs, manifests, and optional chunk/XBRL artifacts.

Core properties:

- Stdlib HTTP stack
- Regex and `html.parser` parsing stack
- Deterministic artifact generation
- Full filing and section-level outputs
- Query layer with citation provenance

## Commands

```bash
# Install (editable + dev deps)
uv pip install -e ".[dev]"

# Tests
python3 -m unittest discover -s tests

# Lint and formatting checks
ruff check .
ruff format --check .

# Build a filing pack
edgarpack build --cik 0001045810 --form 10-K --out ./packs

# Query one company
edgarpack query NVDA revenue,net_income --period ltm

# Run comps
edgarpack comps NVDA AMD INTC --metrics revenue,net_income,ebitda --period ltm
```

## Architecture

### `edgarpack/sec/`

SEC client, cache, submissions, archives, ticker resolution, and companyfacts retrieval.

- `client.py`: async HTTP with rate limiter, retry handling, and per-event-loop singleton client.
- `cache.py`: SHA256-keyed disk cache with atomic writes.

### `edgarpack/parse/`

HTML to markdown pipeline, in order:

1. `ixbrl_strip.py`
2. `html_clean.py`
3. `semantic_html.py`
4. `md_render.py`
5. `sectionize.py`

`sectionize.py` is the highest-complexity parser and includes TOC skipping, table-cell heading detection, inline heading detection, and stable section ID generation.

### `edgarpack/pack/`

Pack assembly and artifact generation.

- `build.py`: orchestrates the end-to-end pipeline.
- `manifest.py`: manifest model and deterministic JSON serialization.
- `chunks.py`: semantic chunking for optional `chunks.ndjson`.

### `edgarpack/query/`

Financial query layer over SEC companyfacts.

- Concept resolution from metric names to GAAP/IFRS tags. `total_debt` includes broader tags (`DebtLongTermAndShortTermCombinedAmount`, `LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities`) for captive-finance companies like Ford.
- Period selection (`lfy`, `mrq`, `mrp`, `ltm`, `ltm-1`, series selectors). LTM-1 for annual-only filers (20-F) returns the prior fiscal year instead of the same year.
- Derived metrics with component-level provenance and recursion guards.
- Data quality guards: staleness rejection (2-year default, 3 for `ltm-1`, disabled for series), segment-vs-consolidated filtering via SEC `frame` field, and concept scope warnings for known mismatches (COGS breadth, lease-inclusive debt, cash-plus-investments).
- `CitedValue` carries an optional `warnings` field. Per-share metrics get a stock split contamination warning when the LTM-derived value differs from the latest annual filing by more than 5x. Scope warnings attach when the resolved concept is broader/narrower than the metric name implies.

### `edgarpack/site/`

Minimal static site generator over pack artifacts.

## Environment Variables

- `EDGARPACK_USER_AGENT`
- `EDGARPACK_CACHE_DIR`
- `EDGARPACK_CACHE_DIR_FALLBACK`

## Current Parsing Notes

- Section detection supports headings inside markdown table cells and inline concatenations such as `PART IItem 1`.
- TOC table skipping handles multi-table TOCs and avoids skipping non-TOC content tables.
- If no sections are detected, `sectionize()` emits a single `unknown_01` section with warnings.

## Public API Contracts

- Query subpackage exports: `comps`, `financials`, `QueryResult`, `CitedValue`, `DerivedValue`.
- Pack subpackage exports: `build_pack`, `PackResult`.
