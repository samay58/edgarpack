# learn-pack design

The "why" behind the package shape. Read this if you're going to modify the skill itself, not if you're just running it.

## What problem this solves

Codebases of any real size accumulate tribal knowledge that doesn't live in the code or in the README. New contributors (human or agent) bounce off the surface for days before they understand the load-bearing files, the dominant lifecycle, the invariants that look optional but aren't. The fix isn't another README. It's a small set of narrative trails that follow concrete actions through the code, plus a function-level reference layer for lookups.

This package generates that material. It does not replace the README or the architecture doc. Those answer "what is this?" Trails answer "what happens when I do X?" Refs answer "what does this function do exactly?"

The pattern was extracted from `marginalia/docs/learn/`, which proved out the shape on a small SvelteKit + Tauri app.

## Design choices and the alternatives we rejected

### Skill + scaffold script, not a full CLI tool

We considered shipping a Python CLI that parses ASTs, builds call graphs, and emits real first-draft prose. Rejected because: the irreducible work of a learn pack is choosing what's worth narrating and writing it in a voice a human will trust. A static analyzer can list functions, but it can't tell you which ones matter or why. The places it could help (call graphs, dependency lists) are fast for an LLM to compute on demand and faster for a human to verify visually.

A pure prompt would have been the opposite mistake: every run reinvents the file structure and there's drift between projects. The scaffold script locks the directory shape and the templates lock the section structure inside each file.

### Two phases with a hard checkpoint

Discovery and fill are two distinct turns of work, separated by user review of the manifest. This was the most important design choice and the easiest one to get wrong.

The failure mode of one-shot generation is well-documented: the agent writes a wall of plausible prose, the user has nothing to react to but the wall, and the slop ships because reviewing it line by line is more work than the user budgeted. By forcing a manifest review in the middle, the user shapes the output before any prose exists. The plan is small enough to read in two minutes; the prose isn't.

### Both a global install and per-repo vendoring

There are two ways to run the skill, for two different needs.

The global install is for cold-start. A self-contained copy lives at `~/.agents/skills/learn-pack/`, with `~/.claude/skills/learn-pack` symlinked to it and a Codex stub at `~/.codex/prompts/learn-pack.md`. This is what makes `learn-pack` available in any repo you open, including one that has never seen the skill before. The global copy carries its own PRINCIPLES, templates, and examples, so it works with no host-repo support at all.

Per-repo vendoring is for customization. The package also lives at `.learn-pack/` inside a host repo that wants to own its copy. Different repos want different principles, different templates, different examples; vendoring lets a fork diverge without touching the global copy, and lets the skill version itself with the host repo's git history. `scripts/install.sh` wires the vendored copy into that repo's `.claude/skills/`, and a Codex run prefers a repo-local `.learn-pack/` over the global copy when both exist.

The honest tradeoff: the global copy is a snapshot. When you improve the in-repo copy, run `scripts/sync-global.sh` to push the change out to `~/.agents/skills/learn-pack/`. Until you do, the two can drift. We accept that over the alternative (global canonical, every repo symlinked back to it) because cold-start must not depend on any one repo being checked out.

### Free-form shape, not preset archetypes

We considered shipping 3-4 archetype templates (CLI tool, library, web app, data pipeline) that the AI would pick from. Rejected because the archetypes always lie about a specific project. The discovery phase is cheap; let the AI invent the shape that fits. Two learn packs ship as worked examples so the AI has something concrete to anchor on: `examples/edgarpack/` is the primary reference (run-first trails over a larger CLI), and `examples/marginalia/` is a smaller pack that proves the shape scales down. They are references, not blueprints.

## What's deliberately not in the package

- **No call graph generation.** A modern agent can read the code faster than a static analyzer can be configured.
- **No language-specific tooling.** The templates and principles work for any language. The scaffold script is bash; the templates are markdown.
- **No frontmatter validation.** If the manifest is malformed, the user finds out at fill time. Validation would catch typos but slow down the iteration loop.
- **No automatic regeneration.** The user runs the skill when they want the pack updated. The trails reference real line numbers and need to be updated when the code moves; we considered a watcher but it would cause more churn than it prevents.

## Cross-tool runtime assumptions

The skill assumes the agent has:

- Read access to any file in the host repo
- Write access to `docs/learn/` in the host repo
- Bash execution for the scaffold script

That's it. No editor APIs, no LSP, no per-tool conveniences. Anything more would couple the skill to one runtime.

Both Claude Code and Codex CLI satisfy this. The install script wires up each one's preferred discovery mechanism (`Skill` tool for Claude Code, prompt file for Codex CLI), but the actual work happens through generic file operations.

## The done bar (for the package itself)

The package is shipped when:

1. `scripts/install.sh` works on macOS and Linux from a fresh repo.
2. Running the skill on a never-touched codebase produces a manifest a human is willing to approve in one round of edits or fewer.
3. Running the skill again on the same codebase updates files in place without clobbering edits.
4. The output for edgarpack passes its own done bar (a reader who has never seen the codebase can read trail-0 and make a confident one-line change).
