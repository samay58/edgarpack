# China Lens Implementation Tracker

This file is the execution reference for the Rogo China Lens MVP inside `edgarpack`.
It records scope decisions, issue mapping, and implementation status to keep agent work aligned.

## Mission
Build a high-trust research workspace that produces investor-grade Packs where each claim has clickable evidence.

## Architecture Decisions
- Extend existing `edgarpack` repository.
- Backend: FastAPI routes over Python domain services.
- Frontend: Next.js workspace shell in `web/`.
- Intake priority: CNINFO connector first.
- Tenancy: single-tenant internal MVP.
- Model strategy: provider-agnostic translation/synthesis adapters.

## Bead Mapping
- Epic: `edgarpack-lb1` - China Lens MVP foundation.
- Child: `edgarpack-lb1.3` - Backend skeleton (in progress).
- Child: `edgarpack-lb1.1` - Frontend shell.
- Child: `edgarpack-lb1.2` - Contracts + QA + docs.

## Contracts Implemented (Backend)
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

## Deterministic QA Rules Implemented
- Findings without citations are marked `unsupported`.
- Numeric claims require numeric token overlap with cited evidence.
- Section coverage states computed from supported citation density.

## Recent Progress (2026-03-11)
- CNINFO sync now supports manifest-driven ingestion via `manifest_path` on `POST /api/v1/connectors/cninfo/sync`.
- Manifest ingestion upserts documents and indexes evidence chunks from:
  - explicit page snippets (`snippets[]`), or
  - local PDF extraction (`local_pdf_path`) using embedded text with OCR-placeholder fallback.
- Added date-window filtering (`start_date`, `end_date`) and optional `clear_existing` reset for deterministic reruns.
- Added input validation path: invalid manifests now return HTTP 400 (instead of silent success).
- China Lens state now sits behind repository/object-store adapters instead of raw in-memory dicts.
- Added durable local backend:
  - JSON-file repository for companies, documents, chunks, packs, jobs, and acquisition events
  - local object-store adapter for source PDFs
- Added environment-based backend selection:
  - `memory` (default)
  - `json` via `EDGARPACK_CHINA_STORAGE_DIR`
  - `postgres` via `EDGARPACK_CHINA_POSTGRES_DSN`
- Added regression coverage:
  - manifest ingestion populates evidence search corpus
  - date-window filtering behavior
  - invalid manifest API handling
  - repository persistence across service restarts
  - local object-store persistence for synced PDFs

## Next Implementation Steps
1. Add live CNINFO fetch + page-image rendering on top of the new persistence/object-store boundary.
2. Add production OCR provider behind the existing extraction fallback path.
3. Add vector retrieval and database-native search on top of the PostgreSQL adapter.
4. Integrate frontend `web/` with API and implement Evidence Explorer interactions.
5. Add end-to-end tests for generate-pack, verify-citation, and bounded ask workflows.
