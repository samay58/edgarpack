# 10-K Section Normalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Bead:** `edgarpack-5ee`

**Goal:** Tighten 10-K section extraction so the NVIDIA 2025 to 2026 static diff report has canonical section IDs and readable section titles instead of duplicate item-title variants.

**Architecture:** Fix section identity at pack construction/sectionization time, not in the HTML report renderer. `diff_filings()` and `build_pair_report()` should receive clean section manifests and continue to operate on evidence-linked local pack files.

**Tech Stack:** Python 3.11+, existing sectionizer/report code, pytest fixtures. No new dependencies.

---

## Safety Rules

- Work in a dedicated git worktree.
- Do not add renderer-only title hacks that hide bad manifest data.
- Do not mutate committed packs during ordinary report generation.
- Preserve existing S-1, 10-Q, 8-K, and HKEX behavior unless tests prove a shared helper needs adjustment.
- Use fixtures or small pack excerpts for regression tests; do not depend on live SEC downloads in default tests.
- Commit after each green task.
- Push before declaring work complete.

## File Map

- Modify: `edgarpack/parse/sectionize.py` - canonicalize 10-K item titles and reject cross-reference fragments before section IDs are minted.
- Modify: `edgarpack/diff/section_diff.py` only if display-title cleanup must mirror sectionizer behavior for existing packs.
- Modify: `tests/test_sectionize.py` or add a focused sectionizer regression test file.
- Modify: `tests/test_diff_report.py` only for report-level regression coverage against cleaned manifest input.

## Task 0: Baseline And Artifact Capture

- [ ] **Step 1: Create a worktree and run focused baseline**

```bash
git worktree add /tmp/edgarpack-10k-section-normalization -b fix/10k-section-normalization main
cd /tmp/edgarpack-10k-section-normalization
uv pip install -e ".[dev,china]"
uv run pytest tests/test_diff.py tests/test_diff_report.py -q
```

- [ ] **Step 2: Capture the noisy NVIDIA case**

Generate or inspect the local NVDA 2025 to 2026 10-K report/manifest using existing local packs. Record the duplicate or garbled section IDs/titles in the commit message or test name so reviewers can see the before/after.

## Task 1: Sectionizer Regression

- [ ] Add a failing fixture-backed test with the minimal NVIDIA-style markdown/html-derived heading sequence that currently produces duplicate or sentence-like 10-K item sections.
- [ ] Assert canonical outputs for standard 10-K item sections, especially `Item 1A. Risk Factors`, `Item 7. Management's Discussion and Analysis`, and any specific duplicated section found in the NVDA 2026 pack.
- [ ] Assert cross-reference sentences such as `See Item 1A. Risk Factors for additional information...` do not mint new sections.
- [ ] Verify:

```bash
uv run pytest tests/test_sectionize.py -q
```

## Task 2: Normalize Before IDs Are Minted

- [ ] Tighten `sectionize.py` title cleanup and item-match validation so canonical 10-K sections use stable item IDs and titles before `section_id()` is called.
- [ ] Prefer known canonical item titles when the detected title is too short, sentence-like, too long, or contains cross-reference phrases.
- [ ] Keep a conservative fallback for unknown item numbers: `Item N` is better than a cross-reference fragment.
- [ ] Verify:

```bash
uv run pytest tests/test_sectionize.py -q
```

## Task 3: Diff/Report Regression

- [ ] Add report or diff coverage proving cleaned manifests produce one coherent rail row per canonical 10-K section.
- [ ] If existing committed packs remain noisy until rebuilt, make the test target freshly sectionized fixture output rather than editing generated packs by hand.
- [ ] Verify:

```bash
uv run pytest tests/test_diff.py tests/test_diff_report.py -q
```

## Task 4: Manual Local Smoke

- [ ] Rebuild or regenerate the NVDA 2026 pack only in a temp output directory, then generate the static diff report against NVDA 2025.
- [ ] Confirm the report rail uses coherent section titles and the local/SEC evidence links still point to source files.
- [ ] Do not commit regenerated large packs unless explicitly needed and reviewed.

Suggested smoke:

```bash
EDGARPACK_CACHE_DIR=/tmp/edgarpack-10k-normalize-cache uv run edgarpack diff --ticker NVDA --form 10-K --format html --out /tmp/nvda-10k-report.html
```

## Task 5: Full Gate

- [ ] Run focused and broad checks:

```bash
uv run pytest tests/test_sectionize.py tests/test_diff.py tests/test_diff_report.py -q
uv run ruff check edgarpack/parse/sectionize.py edgarpack/diff/section_diff.py tests/test_sectionize.py tests/test_diff.py tests/test_diff_report.py
EDGARPACK_CACHE_DIR=/tmp/edgarpack-10k-normalize-full ./.venv/bin/python -m pytest -q
```

- [ ] Commit and push:

```bash
git add edgarpack/parse/sectionize.py edgarpack/diff/section_diff.py tests/test_sectionize.py tests/test_diff.py tests/test_diff_report.py
git commit -m "fix(parse): normalize 10-K section identities for diff reports"
git pull --rebase
bd sync
git push
```

## Acceptance Checklist

- [ ] NVIDIA 2025 to 2026 10-K comparison uses canonical section IDs without duplicate item-title variants.
- [ ] Static diff report rail shows coherent section titles.
- [ ] Report evidence links still point to SEC source URLs and local pack files.
- [ ] Default tests remain offline-safe.
- [ ] No renderer-only workaround hides bad section data.
