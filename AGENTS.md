# Agent Instructions

Lightweight by design. Work on a branch, keep diffs small, run the gate, commit, push.
There is no mandatory issue tracker and no required PR or orchestration ceremony.

## Mission

EdgarPack and China Lens produce citation-backed packs from primary documents. Every
generated finding must point to evidence chunk IDs. Do not ship uncited claims or invented
facts.

## Working rules

- Keep diffs small and reviewable.
- Run the quality gate after code changes and report the result:
  `scripts/symphony_quality_gate.sh` runs ruff + pytest. Also run mypy strict:
  `uv run --extra dev --extra china --extra sse mypy edgarpack`.
- For HKEX, SSE/CNINFO, citation, FX, or China Lens work, also run the relevant China
  golden lanes listed in `docs/TESTING.md`.
- Avoid new dependencies unless they materially simplify the system.
- Use fixtures for examples and tests. Do not invent facts.
- Preserve keyboard access and reduced-motion support in UI work.
- Treat repo-local docs, plans, scripts, and tests as the system of record for behavior.

## Workflow

Branch off `main`, commit in small steps, and push when the gate is green. Open a PR only if
you want review; otherwise fast-forward `main`. Do not force-push shared branches. Leave a
short note of what changed and the test results (commit messages or a summary are fine).

## Task tracking

Optional. No tracker is required. Use whatever is lightest for the task: `docs/BACKLOG.md`
for genuine outstanding work, clear commit messages, or nothing for small changes.

## Public thread visuals

For public tweet or LinkedIn thread visuals, consult `docs/THREAD_VISUALS.md`. The reference
kit lives at `assets/thread-visual-reference/cerebras-filing-series-2026/` and is the quality
bar for filing-analysis cards.

## Optional: Symphony + Linear orchestration

`WORKFLOW.md` and `docs/SYMPHONY.md` describe an optional unattended orchestration setup
(Linear as the tracker, the Symphony runner). It is not required for normal work and is not
the default. Use it only if you choose to run that system.

## learn-pack

Run `/learn-pack` or the learn-pack skill to regenerate `docs/learn/`. See
`.learn-pack/SKILL.md`.
