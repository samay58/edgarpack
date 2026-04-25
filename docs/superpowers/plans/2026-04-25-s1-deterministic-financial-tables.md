# Deterministic S-1 Financial Tables Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Bead:** `edgarpack-5zb`

**Goal:** Extend deterministic S-1 financial extraction so common selected/summary financial tables do not require Anthropic and never fall back to stale older S-1 facts when the newest filing has no recognized facts.

**Architecture:** Keep `extract_or_load_snapshot()` as the public snapshot entry point. Add a small deterministic parser layer before `_call_haiku_extract()`. The parser should handle explicitly labeled year columns and known metrics only; ambiguous rows return no facts and can still fall through to the LLM path when an API key is available.

**Tech Stack:** Python 3.11+, stdlib `re`/`decimal`, pytest fixtures. No new dependencies.

---

## Safety Rules

- Work in a dedicated git worktree.
- Do not invent financial facts. Every expected value must come from a committed fixture or local pack excerpt.
- Do not parse pro-forma or multi-scenario columns unless the year mapping is explicit and the output is marked correctly.
- Do not remove the LLM fallback for unrecognized tables when `ANTHROPIC_API_KEY` is available.
- Do not reintroduce stale fallback from older S-1 snapshots.
- Commit after each green task.
- Push before declaring work complete.

## File Map

- Modify: `edgarpack/query/s1_financials.py` - add deterministic table-shape parsing helpers.
- Modify: `tests/test_s1_financials_extract.py` - fixture matrix for recognized deterministic tables and no-LLM behavior.
- Modify: `tests/test_s1_financials_query_integration.py` - protect latest-filing selection and no-stale-fallback behavior.
- Add fixture excerpt only if needed under `tests/fixtures/`, copied from committed local packs with source accession noted in the fixture header.

## Task 0: Baseline

- [ ] **Step 1: Create a worktree and run focused baseline**

```bash
git worktree add /tmp/edgarpack-s1-deterministic -b fix/s1-deterministic-tables main
cd /tmp/edgarpack-s1-deterministic
uv pip install -e ".[dev,china]"
EDGARPACK_CACHE_DIR=/tmp/edgarpack-s1-baseline ./.venv/bin/python -m pytest tests/test_s1_financials_extract.py tests/test_s1_financials_query_integration.py -q
```

Expected: current S-1 tests pass before expansion. If they fail, fix or report the baseline before adding parser coverage.

## Task 1: Cerebras 2024 Selected Financial Data

- [ ] Add a failing parser test using `tests/fixtures/cerebras_selected_financial_data.md`.
- [ ] Expected facts: revenue, gross profit, operating income/loss, net income/loss, and EPS basic where explicitly present for the table years.
- [ ] Implement markdown table parsing for selected financial data with explicit year headers.
- [ ] Verify:

```bash
EDGARPACK_CACHE_DIR=/tmp/edgarpack-s1-cerebras2024 ./.venv/bin/python -m pytest tests/test_s1_financials_extract.py -q
```

## Task 2: Cerebras 2026 Summary Table Preservation

- [ ] Keep existing deterministic parsing for the Cerebras 2026 two-year summary table.
- [ ] Add assertions that recognized Cerebras 2026 input skips `_call_haiku_extract()` and caches model `deterministic-summary-table` or a documented deterministic successor model string.
- [ ] Verify:

```bash
EDGARPACK_CACHE_DIR=/tmp/edgarpack-s1-cerebras2026 ./.venv/bin/python -m pytest tests/test_s1_financials_extract.py::test_extract_or_load_snapshot_skips_llm_for_summary_table -q
```

## Task 3: Alternate Real S-1 Table Shape

- [ ] Add a fixture excerpt from a real committed local S-1 pack with a selected/summary financial table shape that differs from Cerebras.
- [ ] Use the WhiteFiber S-1 chain under `packs/0002042022/` if its year columns can be mapped unambiguously; otherwise choose another committed S-1 excerpt with explicit year headers.
- [ ] Parser behavior must be conservative: emit only recognized metrics for explicitly mapped historical year columns, skip pro-forma/multicolumn rows, and return no facts for ambiguous rows.
- [ ] Verify:

```bash
EDGARPACK_CACHE_DIR=/tmp/edgarpack-s1-altshape ./.venv/bin/python -m pytest tests/test_s1_financials_extract.py -q
```

## Task 4: Latest Filing And No-Stale-Fallback

- [ ] Strengthen integration tests so `--period lfy` chooses the latest S-1 facts when the newest filing parses.
- [ ] Preserve the regression where newest extraction with zero facts returns missing/N/A rather than older S-1 facts.
- [ ] Verify:

```bash
EDGARPACK_CACHE_DIR=/tmp/edgarpack-s1-query ./.venv/bin/python -m pytest tests/test_s1_financials_query_integration.py -q
```

## Task 5: Full Gate

- [ ] Run focused and full quality gates:

```bash
EDGARPACK_CACHE_DIR=/tmp/edgarpack-s1-final ./.venv/bin/python -m pytest tests/test_s1_financials_extract.py tests/test_s1_financials_query_integration.py -q
uv run ruff check edgarpack/query/s1_financials.py tests/test_s1_financials_extract.py tests/test_s1_financials_query_integration.py
EDGARPACK_CACHE_DIR=/tmp/edgarpack-s1-full ./.venv/bin/python -m pytest -q
```

- [ ] Commit and push:

```bash
git add edgarpack/query/s1_financials.py tests/test_s1_financials_extract.py tests/test_s1_financials_query_integration.py tests/fixtures
git commit -m "fix(query): harden deterministic S-1 financial tables"
git pull --rebase
bd sync
git push
```

## Acceptance Checklist

- [ ] Cerebras 2024 selected table parses without Anthropic.
- [ ] Cerebras 2026 summary table still parses without Anthropic.
- [ ] One alternate real S-1 table shape is covered by fixture.
- [ ] Recognized rows emit revenue, gross profit, operating income/loss, net income/loss, and EPS basic where explicitly present.
- [ ] Newest-empty extraction does not fall back to stale older S-1 values.
