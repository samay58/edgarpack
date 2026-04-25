# Reforge Inventory

Assessment date: 2026-04-24
Mode: Reforge Assessment
Allowed write scope for this pass: `.reforge/` only

## Project Root And Git State

- Project root: `/Users/samaydhawan/Projects/active/edgarpack` (`git rev-parse --show-toplevel`).
- Shell `pwd` resolves through `/Users/samaydhawan/edgarpack`; use the git root above for repo-relative references.
- Branch: `main`.
- Existing `.reforge/`: absent before this assessment.
- Pre-existing dirty worktree: `uv.lock` was already modified before assessment (`git status --short` showed ` M uv.lock`). This pass did not intentionally touch it.
- Recent commits show active CLI/query work, including `feat: pre-IPO / S-1 filer support`.

## Repo Instructions

- `AGENTS.md:7` says China Lens must produce citation-backed Packs from primary documents and must not ship uncited claim-generation flows.
- `AGENTS.md:11-16` asks for small diffs, fixtures, tests after code changes, no invented facts, finding evidence chunk IDs, and keyboard/reduced-motion support.
- `AGENTS.md:20-25` names `bd` as the issue tracker. Read-only Beads inspection was performed; no bead status was changed because the user requested `.reforge/` artifacts only.

## Stack

- Primary package: Python project `edgarpack`, version `0.1.0`, Python `>=3.11` (`pyproject.toml:1-23`).
- CLI entry point: `edgarpack = "edgarpack.cli:app"` (`pyproject.toml:50-51`).
- Package manager / runner in docs: `uv` (`README.md:227-234`, `docs/TESTING.md:13-17`).
- Core dependencies: `pydantic`, `tiktoken` (`pyproject.toml:20-23`).
- Optional surfaces:
  - `china`: FastAPI, uvicorn, httpx, psycopg, pypdf, pyyaml (`pyproject.toml:25-33`).
  - `sse`: pymupdf4llm, pypinyin, httpx (`pyproject.toml:34-38`).
  - `vlm`: anthropic (`pyproject.toml:39`).
- Web app: Next.js/React workspace under `web/`, with `next`, `react`, `react-dom`, TypeScript, ESLint (`web/package.json`).

## Public Interfaces

CLI help from `./.venv/bin/edgarpack --help` exposes:

- Pack/build: `build`, `doctor`, `company-llms`, `list`, `cache`, `site`, `harvest`.
- Query/analysis: `query`, `comps`, `compare`, `which`, `learned`.
- Observatory/search: `diff`, `timeline`, `search`, `index`.
- China/SSE: `api`, `build-sse`, `translate-sse`.

Docs align with the same surface:

- Primary daily workflow: `query`, `comps`, `compare`, `which`, `build` (`README.md:36-85`).
- Full command block includes harvest/search/observatory/SSE/API (`README.md:153-186`).
- China Lens status says CLI is primary; HKEX query and SSE build/translate are live, while FastAPI/Evidence Explorer is parked (`docs/china-lens/IMPLEMENTATION_TRACKER.md:5-7`).

## Main Directories

- `edgarpack/sec/`: SEC client, cache, submissions, archives, XBRL, ticker resolution.
- `edgarpack/parse/`: iXBRL strip, HTML cleanup, markdown render/polish, sectionization.
- `edgarpack/pack/`: pack builder, manifest, chunks, assets, llms.txt, doctor.
- `edgarpack/query/`: citation models, concepts, periods, financials, comps, KPI discovery/extraction, learned registry.
- `edgarpack/diff/`: paragraph/section diff and filing timelines.
- `edgarpack/index/`, `edgarpack/insights/`: search and analytical layers over packs.
- `edgarpack/hk/`: HKEX pack adapter and fact extraction.
- `edgarpack/sse/`: SSE PDF acquisition and Chinese sectionization.
- `edgarpack/china/`: China Lens API domain service, acquisition, extraction, QA, storage, translation, synthesis.
- `edgarpack/api/`: FastAPI routes for China Lens and observatory.
- `web/`: parked Next.js Evidence Explorer / Observatory UI.
- `tests/`: broad pytest suite, including SEC/query, pack, diff, HKEX, S-1, SSE, China API, and fixtures.
- `docs/learn/`: generated learning pack for core CLI lifecycle.
- `docs/superpowers/`: specs/plans from prior implementation sessions.
- `packs/`, `test-packs/`, `test_packs/`, `site*`: committed/generated pack and site artifacts used by demos/tests.

## Data, Fixtures, Generated Artifacts

- Standard SEC pack layout: `filing.full.md`, `llms.txt`, `manifest.json`, `sections/*.md`, optional chunks/XBRL (`README.md:109-127`).
- Manifest carries source, filing metadata, sections, hashes, warnings, token totals, reporting currency, accounting standard (`edgarpack/pack/manifest.py:78-91`).
- Manifest generation hashes section content and uses a stable timestamp derived from filing date for determinism (`edgarpack/pack/manifest.py:131-154`).
- HKEX golden fixtures are committed under `tests/fixtures/china_packs/` for MiniMax and Zhipu (`tests/fixtures/china_packs/README.md:1-13`).
- China golden harness requires hand verification against filing PDFs and forbids auto-regenerating values from current CLI output (`tests/eval/README.md:26-52`).
- Benchmarks commit raw/stripped/clean artifacts for NVDA, AAPL, TSLA so compression claims can be re-counted without rerunning (`docs/BENCHMARKS.md:3-17`).

## Existing Tests And Quality Gates

- Pytest config defines live/slow flags and an autouse LTM citation-contract harness (`tests/conftest.py:11-43`, `tests/conftest.py:55-98`).
- Testing docs define:
  - Fast local regression: `uv run ruff check .` and `uv run pytest -q` (`docs/TESTING.md:25-41`).
  - Live SEC smoke and expanded live SEC lanes (`docs/TESTING.md:43-84`).
  - China golden harness for HKEX extraction/query/currency (`docs/TESTING.md:86-104`).
  - Manual CLI audit checks for citations, LTM components, compare footers, and JSON citation fields (`docs/TESTING.md:106-130`).

Commands run in this assessment:

| Command | Result |
| --- | --- |
| `git status --short` | ` M uv.lock` pre-existing dirty file |
| `bd ready` | 2 ready P3 issues: HKEX annual-report shape; empty discovered-KPI series rendering |
| `bd show edgarpack-sfi` | Confirms HKEX annual reports are unsupported by current IPO-prospectus-shaped pipeline |
| `bd show edgarpack-t2h` | Confirms CLI renders an empty discovered-KPI series poorly |
| `./.venv/bin/edgarpack --help` | Passed; command surface listed above |
| `./.venv/bin/python -m pytest -q` | Failed under sandbox: 72 failures from unwritable learned-registry DB and blocked SEC DNS |
| `EDGARPACK_CACHE_DIR=/tmp/edgarpack-cache ./.venv/bin/python -m pytest -q` | Failed under sandbox: 6 failures, all SEC-network dependent |
| same pytest command with network approval | Passed: `1301 passed, 50 skipped, 12 xfailed in 34.27s` |
| `./.venv/bin/ruff check .` | Passed |
| `./.venv/bin/ruff format --check .` | Passed: `245 files already formatted` |
| `./.venv/bin/mypy .` | Failed: `1293 errors in 136 files`; aligns with parked "strict mypy baseline restoration" noted in `docs/china-lens/IMPLEMENTATION_TRACKER.md:121-123` |

## Files Or Areas That Look Parked, Duplicated, Or Experimental

- `web/` and `edgarpack/api/` are still present, but project docs explicitly mark Evidence Explorer / FastAPI as parked (`docs/china-lens/IMPLEMENTATION_TRACKER.md:5-7`, `docs/china-lens/IMPLEMENTATION_TRACKER.md:112-123`).
- `web/lib/sample-data.ts` contains demo Tencent claims and citations detached from committed source PDFs (`web/lib/sample-data.ts:36-146`). This conflicts with the repo-level "Do not invent facts" posture if the web surface is revived without replacing demo data with fixtures.
- `edgarpack/china/service.py` seeds mock CNINFO URLs and hardcoded evidence chunks by default (`edgarpack/china/service.py:86-189`). Useful for local demos, not a source-of-truth production path.
- `docs/BACKLOG.md` says the SSE prospectus pipeline is parked on a branch (`docs/BACKLOG.md:7-15`), but README, CLI help, implementation tracker, and code show `build-sse` / `translate-sse` are now on main (`README.md:178-181`, `docs/china-lens/IMPLEMENTATION_TRACKER.md:27-41`, `edgarpack/pack/build.py:329-460`). Treat `docs/BACKLOG.md` as stale.
- `edgarpack/cli.py` is 3005 lines; `query/financials.py`, `query/kpi_extract.py`, and `query/periods.py` are also large. Prior `docs/learn/manifest.yml:141-147` calls `periods.py` and `financials.py` load-bearing, which supports targeted extraction only where a user story needs it.
