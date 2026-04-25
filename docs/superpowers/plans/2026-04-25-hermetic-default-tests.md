# Hermetic Default Tests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Bead:** `edgarpack-4et`

**Goal:** Make the default pytest lane deterministic with a fresh cache and no SEC/network access.

**Architecture:** Keep live SEC coverage in the existing opt-in `--run-live-sec` lane. Default tests must use fixtures, mocks, or pure unit coverage. Do not weaken CLI error behavior to make tests pass; replace tests that accidentally rely on DNS with explicit mocked resolver behavior.

**Tech Stack:** Python 3.11+, pytest, unittest.mock, existing fixtures. No new dependencies.

---

## Safety Rules

- Work in a dedicated git worktree.
- Do not change production SEC fetching semantics unless a test exposes a real bug.
- Do not remove live coverage; move it behind live markers when fixture-backed coverage is not equivalent.
- Keep default test data local and deterministic.
- Write the failing hermetic test or reproduce the existing failure before each fix.
- Commit after each green task.
- Push before declaring work complete.

## File Map

- Modify: `tests/test_cli_build_range.py` - mock CLI company label resolution in build-range tests.
- Modify: `tests/test_cli_query_currency.py` - remove DNS dependency from unknown-company behavior.
- Modify: `tests/test_compare.py` - replace SEC subprocess assumptions with mocked/unit-level compare behavior where possible.
- Modify: `tests/test_query_derivations.py` or live-smoke tests - move/replace the live NVDA derivation fallback.
- Modify: `docs/TESTING.md` only if the live/default lane split needs clarification.

## Task 0: Baseline And Failure Capture

- [ ] **Step 1: Create a worktree from current `main` and install dev extras**

```bash
git worktree add /tmp/edgarpack-hermetic-tests -b fix/hermetic-default-tests main
cd /tmp/edgarpack-hermetic-tests
uv pip install -e ".[dev,china]"
```

- [ ] **Step 2: Reproduce the default-suite network leaks**

```bash
EDGARPACK_CACHE_DIR=/tmp/edgarpack-hermetic-baseline ./.venv/bin/python -m pytest -q
```

Expected baseline failures are the known network-dependent tests: two build-range CLI tests, one unknown-company query subprocess test, two compare subprocess tests, and one query-derivation fallback test. If different tests fail, investigate before editing.

## Task 1: Build-Range CLI Tests

- [ ] Patch `tests/test_cli_build_range.py` so tests that monkeypatch `_cik_from_company_args` also monkeypatch `_resolve_cli_company`.
- [ ] Preserve assertions that `build_pack` / `build_pack_range` receive the expected CIK, form, and range arguments.
- [ ] Verify:

```bash
EDGARPACK_CACHE_DIR=/tmp/edgarpack-hermetic-build ./.venv/bin/python -m pytest tests/test_cli_build_range.py -q
```

## Task 2: Unknown Company CLI Behavior

- [ ] Replace the default subprocess path in `tests/test_cli_query_currency.py` with a fixture-backed or monkeypatched route that proves unknown companies return the intended user-facing error without DNS.
- [ ] If a true live SEC unknown-company smoke is still useful, move it to the live lane and guard it with existing `--run-live-sec` behavior.
- [ ] Verify:

```bash
EDGARPACK_CACHE_DIR=/tmp/edgarpack-hermetic-query ./.venv/bin/python -m pytest tests/test_cli_query_currency.py -q
```

## Task 3: Compare Defaults Without Live SEC

- [ ] Replace `compare minimax ZZZZZZ` subprocess coverage with a mocked resolver/gather test that proves unknown SEC-shaped input exits with code 2 and a useful message.
- [ ] Replace `compare NVDA AMD` mismatched fiscal-year subprocess coverage with pure renderer/header coverage using local `CompanyColumn`/period data, or with mocked `_gather` responses.
- [ ] Keep HKEX fixture compare subprocess tests unchanged.
- [ ] Verify:

```bash
EDGARPACK_CACHE_DIR=/tmp/edgarpack-hermetic-compare ./.venv/bin/python -m pytest tests/test_compare.py -q
```

## Task 4: Query Derivation Fallback

- [ ] Replace the live `NVDA` fallback in `tests/test_query_derivations.py` with local facts/text-scan fixtures, or move the live case to an opt-in live test.
- [ ] Preserve the behavioral assertion: revenue-per-employee should resolve after the intended text-scan fallback path.
- [ ] Verify:

```bash
EDGARPACK_CACHE_DIR=/tmp/edgarpack-hermetic-derivations ./.venv/bin/python -m pytest tests/test_query_derivations.py -q
```

## Task 5: Full Offline Gate

- [ ] Run the default suite from a fresh cache:

```bash
EDGARPACK_CACHE_DIR=/tmp/edgarpack-hermetic-final ./.venv/bin/python -m pytest -q
```

- [ ] Run targeted lint on touched test/docs files:

```bash
uv run ruff check tests/test_cli_build_range.py tests/test_cli_query_currency.py tests/test_compare.py tests/test_query_derivations.py
```

- [ ] Update `docs/TESTING.md` only if a live-smoke relocation changes the documented commands.
- [ ] Commit and push:

```bash
git add tests docs/TESTING.md
git commit -m "test: make default suite hermetic around SEC access"
git pull --rebase
bd sync
git push
```

## Acceptance Checklist

- [ ] Default pytest passes with a fresh `EDGARPACK_CACHE_DIR` and no live SEC dependency.
- [ ] Live SEC coverage remains opt-in via existing flags.
- [ ] Unknown-company CLI coverage no longer depends on DNS.
- [ ] Default compare/query derivation tests use fixtures or mocks.
- [ ] `docs/TESTING.md` accurately describes default vs live lanes.
