# CLAUDE.md

Guidance for coding agents working in this repository.

## Project Summary

EdgarPack converts SEC EDGAR filings (10-K, 10-Q, 8-K) into deterministic markdown packs with section IDs, manifests, and optional chunk/XBRL artifacts.

China Lens extends this repository with a citation-backed research workspace for
Chinese primary filings. In China Lens paths, Evidence Explorer and citation
integrity are the primary product surface.

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

# Install China Lens API extras
uv pip install -e ".[china]"

# Tests
python3 -m pytest tests/ -x -v

# Lint and formatting checks
ruff check .
ruff format --check .

# Build a filing pack
edgarpack build --cik 0001045810 --form 10-K --out ./packs

# Query one company
edgarpack query NVDA revenue,net_income --period ltm

# Run comps
edgarpack comps NVDA AMD INTC --metrics revenue,net_income,ebitda --period ltm

# Run China Lens API
edgarpack api --host 127.0.0.1 --port 8000

# Harvest: bulk-download filing packs for a company universe
edgarpack harvest --universe universe.toml --out ./packs
edgarpack harvest --universe universe.toml --out ./packs --plan       # dry run (still hits SEC for filing lists)
edgarpack harvest --universe universe.toml --out ./packs --refresh --with-chunks

# Diff: compare two filing packs already on disk
edgarpack diff --ticker NVDA --form 10-K                   # latest vs. prior (requires registry)
edgarpack diff --before ./packs/cik/acc1 --after ./packs/cik/acc2

# Timeline: section evolution across filings (requires registry)
edgarpack timeline --ticker NVDA --section 10k_parti_item1a_risk_factors --form 10-K

# Index: build search index from harvested packs (required before search)
edgarpack index --packs ./packs

# Search: full-text search across indexed filing chunks (requires populated search index)
edgarpack search "export controls" --topic risk:export_controls --ticker NVDA
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

- Concept resolution from metric names to GAAP/IFRS tags. `total_debt` prioritizes non-lease debt concepts first, with lease-inclusive tags as fallback for sparse filers.
- Period selection (`lfy`, `mrq`, `mrp`, `ltm`, `ltm-1`, series selectors). LTM-1 for annual-only filers (20-F) returns the prior fiscal year instead of the same year.
- Derived metrics with component-level provenance and recursion guards.
- Data quality guards: staleness rejection (2-year default, 3 for `ltm-1`, disabled for series), segment-vs-consolidated filtering via SEC `frame` field, and concept scope warnings for known mismatches (COGS breadth, lease-inclusive debt, cash-plus-investments).
- `CitedValue` carries an optional `warnings` field. Per-share metrics get a stock split contamination warning when the LTM-derived value differs from the latest annual filing by more than 5x. Scope warnings attach when the resolved concept is broader/narrower than the metric name implies.

### `edgarpack/harvest/`

Bulk filing download pipeline (Filing Observatory).

- `universe.py`: load company list from `universe.toml` with per-company form count overrides.
- `planner.py`: delta plan comparing universe spec against registry state.
- `runner.py`: async batch executor with bounded concurrency and progress reporting.
- `registry.py`: SQLite index of all built packs (`~/.edgarpack/registry.db`) for sub-ms lookups.

### `edgarpack/diff/`

Section-level diff engine for filing comparison.

- `models.py`: `ChangeType`, `ParagraphDelta`, `SectionDelta`, `DiffResult`.
- `section_diff.py`: match sections by stable ID, use SHA256 hashes for instant unchanged detection.
- `text_diff.py`: paragraph-level diff using fingerprinting and Jaccard similarity.
- `timeline.py`: chronological section history across filings.

### `edgarpack/index/`

Topic index and cross-corpus search (syntopic reading primitive).

- `topic_extract.py`: pattern-based topic extraction (risk categories, financial concepts, regulatory refs, industry terms). No LLM required.
- `inverted.py`: SQLite FTS5 inverted index for ranked full-text search + boolean topic queries.
- `catalog.py`: hierarchical topic catalog (risk, financial, regulatory, industry).
- `search.py`: high-level cross-corpus search API with company grouping.

### `edgarpack/insights/`

Analytical layers built on diff engine + topic index.

- `disclosures.py`: new disclosure detection (paragraphs below Jaccard threshold vs. all priors).
- `language_shift.py`: flag sections with abnormally high year-over-year change rates.
- `emerging.py`: topics appearing in more filings this period vs. last.

### `edgarpack/api/observatory/`

FastAPI routes for the Filing Observatory web interface at `/api/v1/observatory/`.

- `GET /companies` - company grid with filing counts
- `GET /companies/{ticker}` - company detail with filing list
- `GET /companies/{ticker}/diff` - latest vs. prior filing diff
- `GET /companies/{ticker}/timeline/{section_id}` - section evolution
- `GET /search` - cross-corpus full-text search
- `GET /stats` - registry and index statistics
- `GET /topics` - topic catalog with counts

### `edgarpack/site/`

Minimal static site generator over pack artifacts.

## Environment Variables

- `EDGARPACK_USER_AGENT`
- `EDGARPACK_CACHE_DIR`
- `EDGARPACK_CACHE_DIR_FALLBACK`

## Current Parsing Notes

- Section detection supports headings inside markdown table cells and inline concatenations such as `PART IItem 1`.
- TOC table skipping handles multi-table TOCs ("Table of Contents" and "INDEX" headings) and avoids skipping non-TOC content tables. TOC stub sections (content is entirely table rows) are filtered before deduplication.
- If no sections are detected, `sectionize()` emits a single `unknown_01` section with warnings.

## Diff Engine Design Notes

- Change intensity is word-weighted: a 200-word rewritten paragraph contributes more than a 3-word boilerplate change. Falls back to paragraph count if word counts are unavailable.
- `ParagraphDelta` carries `old_word_count`/`new_word_count` for traceability.
- Both `section_diff.py` and `timeline.py` use the same `_compute_section_intensity()` function.
- Paragraph matching: exact SHA256 fingerprints first, then greedy Jaccard similarity for fuzzy matches. Threshold = 0.5.

## Insight Pipeline Design Notes

- New disclosure detection filters table-only paragraphs and stores `closest_prior_text` for human verification.
- Language shift detection includes non-unchanged `paragraph_deltas` for drill-down into what changed.
- Emerging topics count by unique filings (accessions), not raw chunks, to prevent verbose filings from inflating counts.
- Topic extraction patterns require risk/threat context for ambiguous terms (competition, regulatory, China) to reduce false positives.

## Public API Contracts

- Query subpackage exports: `comps`, `financials`, `QueryResult`, `CitedValue`, `DerivedValue`.
- Pack subpackage exports: `build_pack`, `PackResult`.
- China Lens package exports domain models in `edgarpack/china/`.
- China Lens FastAPI app factory: `edgarpack.api.create_app`.
- Harvest subpackage exports: `load_universe`, `plan_harvest`, `run_harvest`, `PackRegistry`.
- Diff subpackage exports: `diff_filings`, `diff_paragraphs`, `build_timeline`, `DiffResult`.
- Index subpackage exports: `extract_topics`, `SearchIndex`, `search_corpus`.
- Insights subpackage exports: `detect_new_disclosures`, `detect_language_shifts`, `detect_emerging_topics`.
