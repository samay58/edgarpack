# Session Learnings

## Validated

| Learning | Evidence |
| --- | --- |
| The core CLI/test surface is healthy when run with a writable cache and SEC network access. | Approved command `EDGARPACK_CACHE_DIR=/tmp/edgarpack-cache ./.venv/bin/python -m pytest -q` passed with `1301 passed, 50 skipped, 12 xfailed`; ruff check and format check passed. |
| The repo's mission is citation-first, not claim-generation-first. | `AGENTS.md:7-16`; citation model in `edgarpack/query/models.py`; China QA validators in `edgarpack/china/qa/validators.py:16-137`. |
| The CLI is the current primary product surface. | `docs/china-lens/IMPLEMENTATION_TRACKER.md:5-7`; Bead trim context at `docs/superpowers/specs/2026-04-20-bead-backlog-trim-design.md:3-5`. |
| Deterministic pack artifacts are a real design invariant. | `README.md:76-85`; manifest stable timestamp and hashes in `edgarpack/pack/manifest.py:131-154`; test docs mention determinism checks (`docs/TESTING.md:76-84`). |
| China golden values are intentionally hand-verified, not regenerated from the current system. | `tests/eval/README.md:26-52`. |
| HKEX IPO-prospectus fixtures are validated, while annual-report shape remains open. | `tests/fixtures/china_packs/README.md:7-13`; `bd show edgarpack-sfi`. |

## Plausible

| Learning | Evidence |
| --- | --- |
| The initial assessment favored a hybrid targeted refactor because the existing test suite is healthy; that recommendation is now superseded by the user's explicit clean-rewrite decision. | Full regression and ruff passed, but the user chose a full clean rewrite to cut accidental architecture and AI-generated slop while preserving validated learning. |
| The old implementation should be used as evidence and a source of reviewed leaf utilities, not as the vNext base architecture. | Stable leaves exist in SEC client/cache, URL helpers, HTML cleaning, and token counting; old orchestrators, renderers, sectionizers, web demo flows, and China Lens services are not the target foundation. |
| The vNext API should be a thin client of the evidence model, not a separate fact-generation layer. | User approved a minimal API wrapper that can build/query through the same core contracts, with no web surface in the alpha. |
| A future China Lens revival should start from committed fixtures and QA gates before UI. | AGENTS mission, seed/demo risk, QA validators, and golden harness all point to evidence-first order. |

## Mistakes To Avoid

| Mistake | Evidence |
| --- | --- |
| Treating `docs/BACKLOG.md` as current for SSE. | It says SSE is parked (`docs/BACKLOG.md:7-15`), but current README/tracker/code expose SSE as live. |
| Running pytest in this sandbox without `EDGARPACK_CACHE_DIR=/tmp/...` and network approval. | First run failed on learned-registry SQLite and SEC DNS; approved rerun passed. |
| Shipping web demo data as if it were production evidence. | `web/lib/sample-data.ts:36-146` embeds claims and citations directly; repo instructions forbid invented facts. |
| Refactoring large modules because they are large. | Prior Bead trim closed pure refactors without user stories (`docs/superpowers/specs/2026-04-20-bead-backlog-trim-design.md:20-32`); tests are green. |

## Open Questions

- What old behavior parity checks are hard cutover blockers after vNext passes its own gates?
- Should `compare` and `trace` land immediately after the first slice, or wait until pack/query contracts prove stable?
- Should sample/demo data stay in source at all, or move into fixture files with explicit "demo only" loading?
- Should `docs/BACKLOG.md` be retired in favor of Beads plus implementation tracker?
