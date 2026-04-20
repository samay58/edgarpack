# China Lens Implementation Tracker

Status log for the Chinese-filings pipeline. Written to get a new contributor oriented on what already works, what the current surface looks like, and what is still open.

## Mission

Build a high-trust research workspace that produces investor-grade Packs where each claim has clickable evidence. Two surfaces today: (1) the HKEX extraction path wired into the main `query` / `comps` / `compare` CLI, and (2) the FastAPI workspace exposed via `edgarpack api` for the Evidence Explorer UI.

## Architecture at a glance

- **Extraction (HKEX)**: prospectus PDF -> pack markdown -> regex extractor -> Claude API fallback for tagged-but-unmatched metrics -> `facts.json` inside the pack. Source modules: `edgarpack/hk/acquire.py`, `adapter.py`, `extract.py`, `llm_extract.py`.
- **Query routing**: `universe.toml` tags HKEX filers; `edgarpack/query/financials.py` routes those CIKs through `facts.json` instead of SEC companyfacts. Same `CitedValue` / `DerivedValue` shapes downstream.
- **Cross-market compare**: `edgarpack/compare.py` handles SEC + HKEX filers in one table, normalizes currencies through `data/fx_rates.csv` with `--currency usd`, and keeps the native-currency value as a footnote.
- **Workspace API**: FastAPI routes under `edgarpack/api/` over Python domain services. Storage adapters pluggable via `EDGARPACK_CHINA_STORAGE_BACKEND` (`memory`, `json`, `postgres`).
- **Intake**: CNINFO connector with manifest-driven ingestion (explicit snippets or local PDF extraction with OCR-fallback markers).
- **Tenancy**: single-tenant internal MVP.
- **Model strategy**: provider-agnostic adapters; Claude for HKEX extraction fallback today.

## Shipped

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

## Open

1. Live CNINFO fetch and page-image rendering on top of the new persistence + object-store boundary. The manifest path is in place; the live fetcher is still stubbed.
2. Production OCR provider behind the existing extraction fallback path. Today's local loop uses embedded-text extraction with OCR-fallback markers but no real OCR vendor wired in.
3. Vector retrieval and database-native search on top of the PostgreSQL adapter.
4. Frontend `web/` integration with the full API surface; Evidence Explorer interactions still need plumbing past the first screen.
5. End-to-end tests for generate-pack, verify-citation, and bounded ask workflows.

## Commands you actually run

```bash
# HKEX query via the main CLI
edgarpack query BIDU revenue --period lfy
edgarpack query "tencent" operating_cash_flow --period lfy

# Cross-market compare with USD normalization
edgarpack compare NVDA BIDU BABA --metrics revenue,gross_margin --currency usd

# Workspace API for the Evidence Explorer
export EDGARPACK_CHINA_STORAGE_BACKEND=json
export EDGARPACK_CHINA_STORAGE_DIR="$PWD/.local/china-repo"
export EDGARPACK_CHINA_OBJECT_STORE_DIR="$PWD/.local/china-objects"
edgarpack api --host 127.0.0.1 --port 8000
```

Deeper testing recipes (including the golden harness) are in [`docs/TESTING.md`](../TESTING.md). HKEX query-layer details are in the [HKEX Path section of `docs/QUERY.md`](../QUERY.md#hkex-path).
