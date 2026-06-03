# Symphony And Harness Engineering

> Optional and not required. The default workflow is the lightweight one in `AGENTS.md`; Linear
> and Symphony are not needed for normal work. This document is retained for reference if you
> opt into unattended orchestration.

This repo is moving from interactive agent management to issue-level orchestration with
Symphony. The first rollout uses Linear as the canonical tracker and the reference
Elixir implementation as an evaluation runner.

Sources:

- Harness engineering: https://openai.com/index/harness-engineering/
- Symphony announcement: https://openai.com/index/open-source-codex-orchestration-symphony/
- Symphony spec: https://github.com/openai/symphony/blob/main/SPEC.md
- Reference runner: https://github.com/openai/symphony/blob/main/elixir/README.md

## Policy

Linear is canonical for new work. `bd` remains useful as migration history, but agents
must not actively update both Linear and `bd` for the same task. Preserve old bead IDs
inside Linear issue descriptions and PRs when they matter for traceability.

The first Symphony success bar is modest:

- one Linear issue in `Ready`
- one isolated workspace
- one pushed branch
- one PR
- one Linear workpad with validation results
- final issue state `Human Review`

No auto-merge in the first rollout.

## Linear Setup

Create or select a Linear project for EdgarPack. Configure these states:

- `Backlog`
- `Ready`
- `In Progress`
- `Rework`
- `Human Review`
- `Merging`
- `Done`
- `Canceled`

Set the project slug in `WORKFLOW.md`:

```yaml
tracker:
  project_slug: "edgarpack"
```

If the real Linear URL slug differs, update that value before starting Symphony.

Discover Linear IDs without printing secrets:

```bash
export LINEAR_API_KEY="lin_api_..."
python scripts/linear_cutover.py status
```

This prints team, project, and workflow-state IDs. Set the IDs needed by the
cutover:

```bash
export LINEAR_TEAM_ID="<team uuid>"
export LINEAR_PROJECT_ID="<project uuid>"        # optional
export LINEAR_READY_STATE_ID="<Ready state uuid>" # optional but recommended
```

Preview the bead-to-Linear payloads:

```bash
python scripts/linear_cutover.py plan --id edgarpack-5ee
python scripts/linear_cutover.py push --id edgarpack-5ee
```

Create the issues only after the dry-run looks right:

```bash
python scripts/linear_cutover.py push --id edgarpack-5ee --execute
```

For a wider migration:

```bash
python scripts/linear_cutover.py plan --status open --limit 10
python scripts/linear_cutover.py push --status open --limit 10 --execute
```

Each migrated issue includes:

- old bead ID in the title or first line of the description
- original description
- acceptance criteria
- priority
- labels
- links to existing docs or plans

Since `edgarpack-4et` was completed manually as the harness proof, the first real
Symphony-dispatched issue should now be a small Linear seed issue, for example:

```text
[edgarpack-5ee] Improve 10-K pack section normalization for static diff reports
```

Use the existing plan:

```text
docs/superpowers/plans/2026-04-25-10k-section-normalization.md
```

After the migrated Linear issues exist, stop using `bd` as active issue state. Keep it
read-only unless a deliberate migration cleanup task reopens it.

## Local Symphony Run

Install and build the reference runner:

```bash
git clone https://github.com/openai/symphony /tmp/symphony
cd /tmp/symphony/elixir
mise trust
mise install
mise exec -- mix setup
mise exec -- mix build
```

Prepare environment:

```bash
export LINEAR_API_KEY="lin_api_..."
export SYMPHONY_WORKSPACE_ROOT="$HOME/code/edgarpack-symphony-workspaces"
export EDGARPACK_USER_AGENT="Samay Dhawan samay58@gmail.com"
```

Start the runner from the Symphony checkout:

```bash
mise exec -- ./bin/symphony /Users/samaydhawan/Projects/active/edgarpack/WORKFLOW.md \
  --logs-root "$HOME/Library/Logs/edgarpack-symphony" \
  --port 4017
```

Keep `agent.max_concurrent_agents: 1` until the first pilot issue reaches `Human Review`
with a pushed PR and clean validation notes.

## Harness Rules For EdgarPack

The OpenAI harness-engineering lesson that matters here is not more prompting. It is
making the work legible and mechanically checkable.

EdgarPack-specific rules:

- `AGENTS.md` stays short and points to deeper docs.
- `WORKFLOW.md` owns Symphony policy.
- `docs/TESTING.md` owns test lanes.
- `scripts/symphony_quality_gate.sh` owns the default routine gate.
- China Lens claim-generation work must remain citation-backed to primary documents.
- Golden fixtures are preferred over invented examples.
- Follow-up work is filed as Linear issues, not hidden in chat summaries.

## Quality Gates

Routine code changes:

```bash
scripts/symphony_quality_gate.sh
```

HKEX, SSE/CNINFO, FX, citation, or China Lens changes should also run the relevant
targeted lanes from `docs/TESTING.md`, especially:

```bash
uv run pytest tests/test_china_query_hk.py tests/test_china_query_eval.py -q
uv run pytest tests/test_citation_registry.py -q
```

Live SEC tests remain opt-in and require `EDGARPACK_USER_AGENT`.

## Cloud Roadmap

After the local proof works, move Symphony to a persistent cloud devbox. Do not start
with GitHub Actions or a short-lived job runner. Symphony needs durable workspaces,
logs, Codex auth, GitHub auth, Linear auth, caches, and SSH access for inspection.

First cloud target:

- persistent VM/devbox
- attached disk for workspaces and logs
- Tailscale or SSH access
- `codex app-server` authenticated on the host
- `LINEAR_API_KEY`, GitHub auth, and `EDGARPACK_USER_AGENT` configured as host secrets
- log retention for failed runs
- cleanup job for terminal Linear states

Fly can be revisited after the devbox path is stable. If Fly is used, preserve volumes
and stop machines for cost control instead of deleting state.
