# Product Intent

## Apparent Product Purpose

EdgarPack turns public company primary filings into deterministic, section-addressable markdown packs and cited financial/query outputs that a human or LLM can trace back to source evidence (`README.md:7-21`, `README.md:34`).

## Primary User

The primary user is a financial researcher or agent doing public-company research from filings, with a strong preference for inspectable evidence over model-generated answers (`README.md:11-21`, `README.md:34`).

## Jobs To Be Done

- Build clean filing packs from SEC filings for reading, diffing, search, and LLM input (`README.md:76-85`, `README.md:109-127`).
- Query cited financial metrics for one company, including derived/LTM metrics with formulas and component citations (`README.md:40-49`, `docs/TESTING.md:122-130`).
- Compare companies across SEC and HKEX sources with currency normalization and source footers (`README.md:51-65`, `README.md:164-167`).
- Discover qualitative KPIs a company actually discloses before asking the query layer for them (`README.md:67-74`).
- Diff filing prose and track disclosure changes without table-of-contents/date/signature noise (`README.md:203-215`, `docs/OBSERVATORY.md`).
- Build Chinese/HKEX/SSE packs while preserving the same citation-first shape (`README.md:217-225`, `docs/china-lens/IMPLEMENTATION_TRACKER.md:13-23`).

## Main Happy Path

1. User runs a CLI command (`build`, `query`, `comps`, `compare`, `which`, `diff`, or `timeline`).
2. Identity resolves ticker/name/CIK to SEC, HKEX, or private source.
3. Build path fetches primary documents, cleans/renders/sectionizes them, writes a deterministic pack with hashes.
4. Query path selects facts/periods/derived formulas and returns `CitedValue` / `DerivedValue` results.
5. Output renders a table/JSON/pack with citations and reproducible links.

This is also the dominant lifecycle captured by `docs/learn/manifest.yml:15-34`.

## Secondary Flows

- Harvest a universe and build/search an index (`README.md:169-172`).
- Generate a static site from packs (`README.md:160-161`).
- Build and optionally translate SSE prospectus packs (`README.md:178-181`).
- Run the parked China Lens API and Evidence Explorer local loop (`docs/TESTING.md:132-171`).

## Current Non-Goals Or Distractions

- General finance chatbot behavior. The project is built around primary-source artifacts and cited outputs, not free-form claim generation (`AGENTS.md:7`, `README.md:21`).
- Production Evidence Explorer / FastAPI workspace while docs say that surface is parked (`docs/china-lens/IMPLEMENTATION_TRACKER.md:5-7`, `docs/china-lens/IMPLEMENTATION_TRACKER.md:112-123`).
- Web demo claims detached from committed evidence fixtures (`web/lib/sample-data.ts:36-146`).
- Strict mypy as a current release gate: the config is strict, but the current run fails with 1293 errors and tracker lists restoration as parked (`pyproject.toml:64-66`, `docs/china-lens/IMPLEMENTATION_TRACKER.md:121-123`).

## Simplest Useful Version

A CLI-only product that can:

- Build deterministic SEC packs from primary filings.
- Query and compare cited financial metrics.
- Preserve LTM/derived calculation provenance.
- Diff filing prose.
- Support HKEX and SSE only where fixture-backed or source-document-backed evidence exists.

The web/API workspace can be revived later as a client of that evidence model, but it should not define the next architecture.

## Evidence Used

- README purpose, command surface, and citation claims: `README.md:7-225`.
- Learn-pack lifecycle: `docs/learn/manifest.yml:15-34`.
- China Lens parked status and live/parked split: `docs/china-lens/IMPLEMENTATION_TRACKER.md:5-23`, `docs/china-lens/IMPLEMENTATION_TRACKER.md:112-123`.
- Repo mission: `AGENTS.md:7-16`.
