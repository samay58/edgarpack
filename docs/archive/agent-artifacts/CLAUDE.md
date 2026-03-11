# CLAUDE.md

Quick operating notes for coding agents in this repository.

## Priorities

- Preserve deterministic output.
- Keep citation provenance explicit.
- In China Lens flows, do not ship uncited claims.
- Prefer small, reviewable diffs over wide refactors.

## Useful Commands

```bash
uv pip install -e ".[dev]"
uv pip install -e ".[china]"
uv run pytest tests/ -x -v
ruff check .
ruff format --check .

edgarpack build --cik 0001045810 --form 10-K --out ./packs
edgarpack query NVDA revenue --period ltm --audit
edgarpack comps NVDA AMD --metrics revenue,gross_margin --period ltm --audit
edgarpack api --host 127.0.0.1 --port 8000
edgarpack harvest --universe universe.toml --out ./packs
edgarpack diff --ticker NVDA --form 10-K
edgarpack timeline --ticker NVDA --section 10k_parti_item1a_risk_factors --form 10-K
edgarpack index --packs ./packs
edgarpack search "export controls" --topic risk:export_controls --ticker NVDA
```

## Repo Map

- `edgarpack/sec/`: SEC client, caching, submissions, archives, ticker resolution, companyfacts.
- `edgarpack/parse/`: iXBRL stripping, HTML cleanup, markdown rendering, section detection.
- `edgarpack/pack/`: pack assembly, manifests, `llms.txt`, optional chunk/XBRL artifacts.
- `edgarpack/query/`: financial queries, concept resolution, period selection, LTM math, citation models.
- `edgarpack/china/`: China Lens models, service layer, acquisition, extraction, storage adapters, QA.
- `edgarpack/harvest/`: bulk pack download and registry maintenance.
- `edgarpack/diff/`: filing diff and timeline logic.
- `edgarpack/index/`: deterministic topic extraction and search index.
- `edgarpack/insights/`: higher-level disclosure and trend analysis.
- `edgarpack/api/`: FastAPI routes for China Lens and Observatory.

## Important Behaviors

- `sectionize.py` is the highest-risk parser. Be careful around TOC skipping and heading detection.
- Query results must remain auditable. LTM, LTM-1, derived metrics, and warning propagation are easy places to regress.
- China Lens now supports three storage modes:
  - memory
  - local JSON repository + local object store
  - PostgreSQL repository adapter
- Current China Lens retrieval is still Python-side lexical ranking. Database-native retrieval is a follow-up, not done.

## Environment

- `EDGARPACK_USER_AGENT`
- `EDGARPACK_CACHE_DIR`
- `EDGARPACK_CACHE_DIR_FALLBACK`
- `EDGARPACK_CHINA_STORAGE_BACKEND`
- `EDGARPACK_CHINA_STORAGE_DIR`
- `EDGARPACK_CHINA_OBJECT_STORE_DIR`
- `EDGARPACK_CHINA_POSTGRES_DSN`
- `EDGARPACK_CHINA_SEED_FIXTURES`
