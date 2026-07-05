# Phase 2 packet conventions

You are executing one packet of EdgarPack's Phase 2 trust work in an isolated git worktree (cwd = worktree root, based on `streamline/phase2-trust`). Your packet spec is the sibling file named after your track key. Read it fully before touching anything.

## Setup

First command: `git checkout -b phase2/<your-track-key>`. All commits go on that branch; the branch survives worktree cleanup, so commit everything before finishing.

## Method

Per fix, in order: write the failing regression test, watch it fail, implement the minimal fix, watch it pass. Match surrounding code style. No decorative comments; comment only constraints the code cannot show. One commit per coherent fix (or one per packet if the fixes are inseparable).

## Product invariants (breaking any of these fails the packet)

- Citations live in the data model. A value path never returns a bare number.
- A missing fact returns `None` plus a typed diagnostic, never a guess and never a silent N/A.
- Real SEC 404 (no XBRL) maps to `{}` diagnostic-free; network/HTTP failure raises `XBRLFetchError` and surfaces `layer_a_fetch_error`. Never collapse the two.
- `cli.py` never imports the `query` package at module top level (lazy-startup invariant, pinned by `tests/test_cli_lazy_startup.py`).

## Exit bar (all from the worktree root, before your final commit)

```
uv run --extra dev ruff format <files you touched>
uv run --extra dev ruff check .
uv run --extra dev mypy edgarpack
EDGARPACK_CACHE_DIR=/tmp/edgarpack-cache uv run --extra dev --extra china --extra sse pytest -q
```

The full offline suite runs in ~15s and must be green. The first `uv run` in a fresh worktree syncs a venv; that is expected.

## Commits

`fix(scope): imperative subject` plus a body explaining the defect and the fix. End every commit message with exactly:

```
Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
```

Never use an em-dash anywhere: not in commits, code, comments, or docs. Use a period or colon.

## Scope discipline and escalation

Touch only the files your spec lists, plus test files. Respect the function-level ownership notes in your spec; another packet may own a different function in the same file.

If you hit a genuine design decision your spec does not answer, or a fix that requires editing a file outside your scope: STOP that fix, mark it `blocked` in your report with the precise question, and move on. A packet that comes back with a sharp question beats one that guessed.

## Report

Your final message is consumed by an orchestrator through a forced schema: branch, per-fix status (`done` / `partial` / `blocked`), test names added, files touched, suite state, deviations. Report `suite: red` honestly if it is red; a red suite with an explanation beats a fake green.
