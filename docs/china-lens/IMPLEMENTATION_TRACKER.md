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

## Next Implementation Steps
1. Wire persistent storage (PostgreSQL + object store) behind service interfaces.
2. Replace fixture extraction with real PDF extraction/OCR pipeline.
3. Integrate frontend `web/` with API and implement Evidence Explorer interactions.
4. Add end-to-end tests for generate-pack, verify-citation, and bounded ask workflows.
