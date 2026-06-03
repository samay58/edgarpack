---
tracker:
  kind: linear
  api_key: $LINEAR_API_KEY
  project_slug: "edgarpack"
  active_states:
    - Ready
    - In Progress
    - Rework
  terminal_states:
    - Done
    - Closed
    - Cancelled
    - Canceled
    - Duplicate
polling:
  interval_ms: 10000
workspace:
  root: $SYMPHONY_WORKSPACE_ROOT
  hooks:
    after_create: |
      git clone --depth 1 https://github.com/samay58/edgarpack.git .
      uv sync --extra dev --extra china --extra sse
agent:
  max_concurrent_agents: 1
  max_turns: 20
codex:
  command: codex --config shell_environment_policy.inherit=all app-server
  approval_policy: never
  thread_sandbox: workspace-write
  turn_sandbox_policy:
    type: workspaceWrite
---
# EdgarPack Symphony Workflow

> Optional and not required. This is the Symphony + Linear unattended-orchestration contract.
> The default day-to-day workflow is the lightweight one in `AGENTS.md`; you do not need Linear
> or Symphony for normal work. Retained for reference if you opt into running that system.

You are working on Linear issue `{{ issue.identifier }}`.

Title: {{ issue.title }}
State: {{ issue.state }}
Labels: {{ issue.labels }}
URL: {{ issue.url }}

Description:
{% if issue.description %}
{{ issue.description }}
{% else %}
No description provided.
{% endif %}

## Operating Contract

This is an unattended Symphony session. Work only inside the issue workspace. Do not
touch paths outside this repository copy.

Linear is canonical. If the issue references an old `bd` bead, preserve that ID in the
branch name, PR title/body, and workpad notes, but do not update `bd`.

Use exactly one persistent Linear comment named:

```md
## Codex Workpad
```

Keep that comment updated in place with plan, acceptance criteria, validation, notes,
and blockers. Do not create extra progress comments.

## Status Routing

- `Ready`: move the issue to `In Progress`, create or update the workpad, then start.
- `In Progress`: continue from the existing workpad and current workspace state.
- `Rework`: re-read issue, PR feedback, and workpad; produce a revised plan before edits.
- `Human Review`: do not code. The previous run already reached handoff.
- `Done`, `Closed`, `Cancelled`, `Canceled`, `Duplicate`: do nothing.

## Execution Flow

1. Inspect the current repo state, branch, HEAD, and issue state.
2. Create or update the workpad with:
   - environment stamp: `host:/abs/workspace/path@shortsha`
   - plan checklist
   - acceptance criteria copied from the issue
   - validation checklist
   - notes and blockers
3. Reproduce or characterize the current failure before changing code when the issue is
   a bug or regression.
4. Pull/rebase from `origin/main` before editing.
5. Make the smallest coherent change that satisfies the issue.
6. Keep generated findings citation-backed. Any research or claim-generation output must
   point to primary-source evidence chunk IDs.
7. Run validation:
   - Always run the issue-specific tests.
   - For routine code changes, run `scripts/symphony_quality_gate.sh`.
   - For HKEX, SSE/CNINFO, citation, FX, or China Lens work, also run the relevant
     China golden-harness and citation tests listed in `docs/TESTING.md`.
8. Commit with a concise message.
9. Push the branch and open or update a GitHub PR.
10. Add the `symphony` label to the PR when available.
11. Link the PR on the Linear issue.
12. Update the workpad with final validation results and remaining risks.
13. Move the Linear issue to `Human Review`.

## Blockers

Only stop early for a true external blocker: missing auth, missing required secrets, or a
required tool that is not installed and cannot be installed in-session.

If blocked, update the workpad with:

- what is missing
- why it blocks acceptance
- exact human action needed

Then move the issue to `Human Review`.

## Hard Stops

- Do not merge PRs.
- Do not move issues to `Done`.
- Do not expand scope when a follow-up issue is the right answer.
- Do not ship uncited claims or invented facts.
