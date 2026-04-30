# China Lens Implementation Tracker

Status log for the Chinese-filings pipeline.

## Status (2026-04-27): CLI path active; workspace parked

The CLI is the active product. What is live: the HKEX query path (`query` / `comps` / `compare` route HKEX filers through `facts.json`), the SSE/CNINFO annual-report path (`identify` / `build-sse` / `translate-sse`), English translation with fail-closed validation, and USD-normalized query output with native-currency provenance. What is parked: the Evidence Explorer / FastAPI workspace (`edgarpack api`) and every item in the "Open" list below. The corresponding workspace beads were closed wontfix on 2026-04-20 (`edgarpack-lb1` epic plus `lb1.4`, `lb1.7`, `lb1.11`, `lb1.12`, `lb1.14`, `4o4`, `kax`); see `docs/superpowers/specs/2026-04-20-bead-backlog-trim-design.md`. Reopen those beads only if China Lens becomes a web product surface again.

## Mission

Build a high-trust research workflow that produces investor-grade Packs where each claim has clickable evidence. The active surface is the CLI: HKEX and SSE/CNINFO filings route through primary-source packs, query output stays citation-backed, and translated Chinese filings remain tied to the original source artifacts. The FastAPI workspace exists in the repo but is not the current product surface.

## Architecture at a glance

- **Extraction (HKEX)**: prospectus PDF -> pack markdown -> regex extractor -> Claude API fallback for tagged-but-unmatched metrics -> `facts.json` inside the pack. Source modules: `edgarpack/hk/acquire.py`, `adapter.py`, `extract.py`, `llm_extract.py`.
- **Extraction (SSE/CNINFO)**: annual-report or prospectus PDF -> `pymupdf4llm` markdown conversion -> Chinese section detector (`第X节` with Chinese numerals, canonical annual-report and IPO slugs) -> standard pack layout. Source modules: `edgarpack/china/acquire/cninfo.py`, `edgarpack/sse/client.py`, `pdf_to_md.py`, `sectionize_cn.py`. CLI: `edgarpack identify`, `edgarpack build-sse`.
- **Translation (zh->en, optional)**: section-aware router over a DeepInfra provider. Every translation passes a validator stack (literal token preservation, glossary consistency, markdown table structure fidelity, completion ratio, residual-Han check, romanized-artifact check). Deterministic date/number/percentage/age-range converters short-circuit the LLM for structured cells. Results are cached on disk by provider/model namespace, and long sections are validated/cached in progress batches so interrupted runs can resume from completed batches. Source modules: `edgarpack/china/translate/{router,deepinfra,validators,glossary,numbers,preprocess,cache}.py`. CLI: `edgarpack build-sse --translate` or `edgarpack translate-sse --pack <dir>`. Requires `EDGARPACK_DEEPINFRA_KEY`.
- **Query routing**: `universe.toml` tags HKEX filers; `edgarpack/query/financials.py` routes those CIKs through `facts.json` instead of SEC companyfacts. Same `CitedValue` / `DerivedValue` shapes downstream.
- **Cross-market compare**: `edgarpack/compare.py` handles SEC + HKEX filers in one table, normalizes currencies through `data/fx_rates.csv` with `--currency usd`, and keeps the native-currency value as a footnote.
- **Workspace API**: FastAPI routes under `edgarpack/api/` over Python domain services. Storage adapters pluggable via `EDGARPACK_CHINA_STORAGE_BACKEND` (`memory`, `json`, `postgres`).
- **Intake**: CNINFO connector with manifest-driven ingestion (explicit snippets or local PDF extraction with OCR-fallback markers).
- **Tenancy**: single-tenant internal MVP.
- **Model strategy**: provider-agnostic adapters; Claude for HKEX extraction fallback today.

## Shipped

### Extraction pipeline (SSE/CNINFO)

- `edgarpack identify` resolves known China/HK/company-name cases before SEC fallback so users can see whether a company is public, private, SSE/CNINFO, HKEX, or unknown.
- Raw 6-digit A-share codes can also go straight through `identify`, `build-sse --latest-annual`, `query`, and `which` without a `universe.toml` entry when the stock code is valid.
- `edgarpack build-sse` end-to-end: find the latest annual report when available, download it (or point at a local PDF via `--pdf`), convert to markdown, detect Chinese sections, extract annual metrics, and write a standard pack. Packs land at `packs/sse/<stock_code>/<stock_code>_<filing_date>/` so SEC packs and SSE packs stay out of each other's namespace.
- Canonical Chinese section slugs cover annual-report sections and IPO prospectus sections, with a pinyin fallback for outliers. Chinese numerals (`一` through `二十`) are decoded in place.
- Manifest carries `stock_code`, `exchange=SSE`, document type, source URL/document, reporting currency, and CNINFO acquisition metadata when available. `FilingInfo` is back-compat with SEC manifests (new fields default empty).
- `llms.txt` for SSE packs reflects the Chinese section titles, the original and (if translated) English section lists, and any non-fatal warnings surfaced during section detection.
- Optional `--with-chunks` emits the same `optional/chunks.ndjson` shape used for SEC packs.

### Translation (zh->en, optional)

- Opt-in via `build-sse --translate` or the standalone `translate-sse --pack <dir>` command. Requires `EDGARPACK_DEEPINFRA_KEY`.
- Router dispatches per section type and per paragraph shape (heading vs. flattened catalog vs. markdown table vs. prose). Table cells take a structured path that short-circuits on dates, plain amounts, percentage lists, reporting-period markers, and multi-line structured values.
- Validators run on every translated paragraph. On residual Chinese output the provider gets one bounded repair attempt after strict retry; invalid repairs still fail closed.
- Cache keyed by provider/model namespace + prompt/router/validator strategy fingerprint + normalized source; repeat runs on the same strategy are free and model or strategy changes do not silently reuse stale output.
- Standalone `translate-sse` writes `translation.failures.json` when a section fails closed, with section id, paragraph index, source/target text, excerpts, and validator issues.
- Site builder renders bilingual pages when a translation exists; falls back to Chinese-only when it doesn't.

### Extraction pipeline (HKEX)

- MiniMax and Zhipu prospectus packs under `tests/fixtures/china_packs/` with manifests, section markdown, and extracted `facts.json`.
- Regex extractor in `edgarpack/hk/extract.py` with wrapped-label merging, `/H` filler stripping, and sign-correction for parenthesized negatives (`rd_expense` stored as unsigned magnitude).
- Claude API fallback in `edgarpack/hk/llm_extract.py` with an on-disk cache keyed by accession so repeat runs are free.
- Sanity gate: must-positive metrics (`revenue`, `total_assets`, `total_liabilities`, `cash_and_equivalents`, shares outstanding) reject negative extractions.
- Currency handling: regex layer uses a `_UNIT_PENDING` sentinel; `extract_facts_from_pack` writes the filing's `reporting_currency` from the manifest at assembly time. No mixed-currency facts escape the pipeline.

### Query surface (HKEX)

- `universe.toml` correctly tags BIDU, PDD, BABA, JD, Tencent (`0700.HK`), Meituan (`3690.HK`), Alibaba HK (`9988.HK`), JD HK (`9618.HK`), MiniMax (`00100`), Zhipu (`02513`).
- `financials()` detects HKEX source and reads `facts.json`; same `CitedValue` / `DerivedValue` contract, same period math.
- Operating cash flow, R&D expense, headcount, and the multi-year YoY derivations land on top of the HKEX path.
- HKEX concept names map back to canonical metric names (e.g. OCF concept visible in compare output).
- `edgarpack compare --currency usd` normalizes via `data/fx_rates.csv`; column footer carries the original reporting currency.

### Test coverage

- `tests/test_china_query_hk.py` is a structural smoke suite (ticker-form resolution, metadata flags, multi-metric queries, failure modes).
- `tests/test_china_query_eval.py` drives numeric regression against `tests/eval/china_golden.yaml`.
- `tests/test_china_service.py`, `tests/test_china_api.py`, `tests/test_china_identity.py` cover the workspace API, identity routing, and storage adapters.
- `tests/test_cninfo_latest_annual.py`, `tests/test_china_query_sse.py`, `tests/test_translate_sse_artifacts.py`, `tests/test_table_translation.py`, and `tests/test_deepinfra_translator.py` cover the latest-annual acquisition path, SSE query provenance, translation artifacts, table handling, retry behavior, key validation, and provider/model-scoped caches.

### Workspace API (Evidence Explorer backend)

Contracts live and tested:

- `POST /api/v1/packs`
- `GET /api/v1/packs/{id}`
- `GET /api/v1/packs/{id}/status`
- `POST /api/v1/packs/{id}/cancel`
- `GET /api/v1/companies`
- `GET /api/v1/documents`
- `GET /api/v1/documents/{id}`
- `GET /api/v1/documents/{id}/pages/{n}`
- `POST /api/v1/evidence/search`
- `POST /api/v1/ask`
- `POST /api/v1/citations/resolve`
- `POST /api/v1/connectors/cninfo/sync`

### Deterministic QA rules

- Findings without citations are marked `unsupported`.
- Numeric claims require numeric token overlap with cited evidence.
- Section coverage states computed from supported citation density.

### CNINFO connector

- Manifest-driven ingestion via `manifest_path` on `POST /api/v1/connectors/cninfo/sync`.
- Manifest entries upsert documents and index evidence chunks from explicit `snippets[]` or local PDF extraction (`local_pdf_path`) with OCR-fallback markers.
- Date-window filtering (`start_date`, `end_date`) and `clear_existing` reset for deterministic reruns.
- Invalid manifests return HTTP 400 instead of silent success.

### Storage

- Repository / object-store adapters behind `EDGARPACK_CHINA_STORAGE_BACKEND`.
  - `memory` (default)
  - `json` (durable; `EDGARPACK_CHINA_STORAGE_DIR` + `EDGARPACK_CHINA_OBJECT_STORE_DIR`)
  - `postgres` (`EDGARPACK_CHINA_POSTGRES_DSN`)
- Local object store backs synced PDFs for the CNINFO connector.

### Bead mapping

- Epic: `edgarpack-lb1` -- China Lens MVP foundation.
- `edgarpack-lb1.3` -- Backend skeleton: shipped.
- `edgarpack-lb1.1` -- Frontend shell: shipped (Next.js workspace under `web/`).
- `edgarpack-lb1.2` -- Contracts + QA + docs: shipped for contracts + QA; docs refreshed in this pass.
- `edgarpack-qhn` -- China golden harness: shipped.
- SSE/CNINFO ingestion + translation: shipped (see above).

## Open (parked, see Status above)

These are the tracked-but-not-being-worked items. Each maps to a wontfix-closed bead. Reopen the bead if you pick the work up again.

1. Live CNINFO fetch and page-image rendering on top of the persistence + object-store boundary. The manifest path is in place; the live fetcher is still stubbed. (`edgarpack-lb1.11`)
2. Production OCR provider behind the existing extraction fallback path. Today's local loop uses embedded-text extraction with OCR-fallback markers but no real OCR vendor wired in.
3. Vector retrieval and database-native search on top of the PostgreSQL adapter. (`edgarpack-lb1.12`)
4. Frontend `web/` integration with the full API surface; Evidence Explorer interactions still need plumbing past the first screen. (`edgarpack-4o4`, `edgarpack-kax`)
5. End-to-end tests for generate-pack, verify-citation, and bounded ask workflows.
6. Production hardening: auth, durable async jobs, observability. (`edgarpack-lb1.4`)
7. Web dependency vulnerabilities (`npm audit`). (`edgarpack-lb1.7`)
8. Strict mypy baseline restoration. (`edgarpack-lb1.14`)

## Commands you actually run

These examples use installed-command form (`edgarpack ...`). When running from this repo with `uv run`, prefix XGIMI / China A-share commands with both optional feature groups:

```bash
uv run --extra china --extra sse edgarpack identify xgimi
uv run --extra china --extra sse edgarpack build-sse xgimi --latest-annual --with-chunks
```

`china` enables China Lens/HKEX/CNINFO support. `sse` enables the SSE PDF build and Chinese section tooling. Add `--extra dev` only for tests.

```bash
# HKEX query via the main CLI
edgarpack identify tencent
edgarpack identify laifen
edgarpack query BIDU revenue --period lfy
edgarpack query "tencent" operating_cash_flow --period lfy --currency both

# Cross-market compare with USD normalization
edgarpack compare NVDA BIDU BABA --metrics revenue,gross_margin --currency usd

# SSE / China A-share annual report -> pack (Chinese only)
edgarpack identify xgimi
edgarpack build-sse xgimi --latest-annual --with-chunks

# Manual SSE PDF path still works
edgarpack build-sse --url https://static.sse.com.cn/disclosure/listedinfo/.../prospectus.pdf \
  --stock-code 301536 --company "Unitree Robotics" --filing-date 2026-03-20

# Same filing with zh->en translation
export EDGARPACK_DEEPINFRA_KEY="di-..."
edgarpack build-sse xgimi --latest-annual --with-chunks --translate \
  --translate-model deepseek-ai/DeepSeek-V4-Flash \
  --translate-concurrency 5 \
  --translate-batch-size 25

# Translate an already-built pack
edgarpack translate-sse --pack packs/sse/301536/301536_2026-03-20 \
  --model deepseek-ai/DeepSeek-V4-Flash \
  --concurrency 5 \
  --batch-size 25

# Workspace API for the Evidence Explorer
export EDGARPACK_CHINA_STORAGE_BACKEND=json
export EDGARPACK_CHINA_STORAGE_DIR="$PWD/.local/china-repo"
export EDGARPACK_CHINA_OBJECT_STORE_DIR="$PWD/.local/china-objects"
edgarpack api --host 127.0.0.1 --port 8000
```

Deeper testing recipes (including the golden harness) are in [`docs/TESTING.md`](../TESTING.md). HKEX query-layer details are in the [HKEX Path section of `docs/QUERY.md`](../QUERY.md#hkex-path).
