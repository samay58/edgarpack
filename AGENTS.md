# Agent Instructions

Linear is the canonical work tracker for new agent work in this repo. `bd` is legacy
migration/reference state only; do not update both systems for the same task. If an old
bead ID appears in a Linear issue, preserve it in comments, branch names, and PR text.

## Mission

China Lens should produce citation-backed Packs from primary documents. Do not ship
uncited claim-generation flows.

## Working Rules

- Keep diffs small and reviewable.
- Run tests after code changes and report the result.
- Avoid new dependencies unless they materially simplify the system.
- Use fixtures for examples and tests. Do not invent facts.
- Every generated finding must point to evidence chunk IDs.
- Preserve keyboard access and reduced-motion support in UI work.
- Treat repository-local docs, plans, scripts, and tests as the system of record for
  agent behavior.

## Linear

- Work only from Linear issues in `Ready`, `In Progress`, or `Rework`.
- Move a claimed `Ready` issue to `In Progress` before editing code.
- Keep exactly one persistent Linear workpad comment named `## Codex Workpad`.
- File follow-up Linear issues for unfinished or out-of-scope work.
- Stop at `Human Review` after pushing a branch and opening/updating a PR. Do not merge.

## Symphony

The repo-owned orchestration contract is `WORKFLOW.md`. The operational runbook is
`docs/SYMPHONY.md`.

For routine code changes, run:

```bash
scripts/symphony_quality_gate.sh
```

Run narrower or broader gates when the issue demands it, especially China golden-harness
checks for HKEX, SSE/CNINFO, citation, FX, or claim-generation work.

## Session Completion

Work is not complete until the branch is pushed and the Linear issue has a concise
handoff with test results, PR link, and remaining risks.

Required closeout:

1. File follow-up Linear issues for unfinished work.
2. Run quality gates when code changed.
3. Push the branch and open/update the PR.
4. Move the issue to `Human Review`.
5. Hand off with test results and remaining work.

Never stop with local-only commits. Resolve push failures and retry until the branch is
up to date with `origin`.

## learn-pack

Run `/learn-pack` or invoke the learn-pack skill to regenerate `docs/learn/`. See
`.learn-pack/SKILL.md`.
