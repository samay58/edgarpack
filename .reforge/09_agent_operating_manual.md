# Agent Operating Manual

## Purpose

EdgarPack is a citation-first filing compiler and CLI. It is not a generic finance chatbot.

## Current Rebuild Decision

- The approved path is a full clean rewrite in parallel, not an in-place refactor.
- vNext lives in `edgarpack_next` and is exposed as `edgarpack-next`.
- The current `edgarpack` package is evidence and parity reference, not the vNext base layer.
- The first slice is SEC 10-K/10-Q/S-1, deterministic pack artifacts, cited analyst metrics, simple derived metrics, S-1 selected-financial-data extraction, CLI, and minimal API.
- Out of scope for the first slice: web UI, China Lens findings, HKEX/SSE/CNINFO, `llms.txt` generation, OCR/vector/auth, and learned/self-healing promotion.

## Commands

Use these from repo root:

```bash
bd ready
bd show <id>
./.venv/bin/edgarpack --help
EDGARPACK_CACHE_DIR=/tmp/edgarpack-cache ./.venv/bin/python -m pytest -q
./.venv/bin/ruff check .
./.venv/bin/ruff format --check .
```

Notes:

- In sandboxed agent runs, set `EDGARPACK_CACHE_DIR=/tmp/edgarpack-cache`.
- Tests that hit SEC need network access and `EDGARPACK_USER_AGENT`.
- Mypy is not currently green; do not claim it as a gate without scoping.
- Do not touch `uv.lock` unless dependency changes are intentional; it is dirty in this checkout.

## vNext Command Grammar

- `edgarpack-next filings AAPL --form 10-K`
- `edgarpack-next pack AAPL --form 10-K --last 3`
- `edgarpack-next cite AAPL revenue --period lfy`
- `edgarpack-next audit packs/AAPL/2024-10K`
- Later: `compare`, `trace`, corpus search.

Rules:

- Prefer clear evidence verbs over inherited internal names.
- Do not add old-command compatibility aliases in slice one.
- Add aliases only after the new grammar is stable, tested, and explicitly approved.

## Directory Conventions

- vNext models: `edgarpack_next/models.py`.
- vNext source adapters: `edgarpack_next/sec/`.
- vNext artifacts: `edgarpack_next/artifacts/`.
- vNext metrics: `edgarpack_next/metrics/`.
- vNext use cases: `edgarpack_next/core/`.
- vNext command adapter: `edgarpack_next/cli.py`.
- vNext API wrapper: `edgarpack_next/api.py`.
- Old implementation reference: `edgarpack/`.
- Reforge decisions: `.reforge/`.
- Superpowers spec/plan: `docs/superpowers/specs/` and `docs/superpowers/plans/`.

## How To Add A Feature

1. Read the relevant docs/learn trail or ref.
2. Inspect Beads with `bd show`.
3. Write or identify a failing test.
4. For vNext, add the failing `tests/vnext` test before implementation.
5. Make the smallest change that satisfies the vNext contract.
6. Run focused vNext tests, ruff, and scoped mypy before broad checks.

## What Not To Do

- Do not generate supported findings without chunk citations.
- Do not auto-regenerate golden values from current CLI output.
- Do not let old orchestrators, renderers, sectionizers, web demo flows, or China Lens services become vNext dependencies.
- Do not treat parked web/China Lens work as active product scope without user confirmation.
- Do not touch `uv.lock` unless dependency changes are intentional.
- Do not trust `docs/BACKLOG.md` without checking current README/tracker/code.
- Do not publish `unverified_cited` values unless the command/API option explicitly opts into experimental search.

## Known Pitfalls

- `uv.lock` is currently dirty in this checkout; treat it as user-owned unless the task is dependency work.
- `docs/BACKLOG.md` has stale SSE status.
- Running pytest without writable cache can fail on learned-registry SQLite.
- Running pytest without network can fail on SEC DNS in tests that call live resolution.
- Web sample data contains hardcoded demo claims; do not extend that pattern.

## Definition Of Done

- Behavior is backed by tests or fixture evidence.
- Findings cite evidence chunk IDs.
- vNext public values are `cited`, `derived`, `missing`, `unsupported`, or explicit `unverified_cited`.
- vNext focused tests, ruff, scoped mypy, and live SEC smoke pass or are explicitly blocked with evidence.
- Bead status and push requirements should be followed unless a user instruction constrains writes outside the requested scope.
