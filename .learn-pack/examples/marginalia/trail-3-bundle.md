# Trail 3: The Bundle: What Ships to the Agent

**Time**: ~6 minutes
**Prerequisite**: Trail 0 (steps 9-10)

*This trail is outlined. The full version will open a real bundle directory and walk through each file, explaining what it contains and why.*

---

## Planned sections

**The 7 files**: `original.md`, `final.md`, `changes.json`, `annotations.json`, `changes.patch`, `provenance.json`, `summary_for_agent.md`. What each contains, who reads it, why it exists.

**summary_for_agent.md in detail**: the primary agent-facing artifact. Structured as: changes summary, feedback by priority (IMPORTANT annotations first, then regular, then stale), general notes. This is what the agent actually parses.

**provenance.json**: session metadata, artifact hashes, timing, version markers. Exists so you can verify bundle integrity and trace when a review happened.

**changes.json schema**: bundle format 3.0. Token-level changes with IDs, types, offsets, location metadata. Plus semantic changes (paragraph-level structural diffs).

**Try it**: finalize a review session, then `ls` the bundle directory and `cat` each file. Read `summary_for_agent.md` and compare it to what you actually typed.

---

## Key code paths

- `src/lib/utils/bundle.js:generateBundle()` (line 421)
- `src/lib/utils/bundle.js:generateSummaryMarkdown()` (line 294)
- `src/lib/utils/bundle.js:generateProvenanceJson()` (line 210)
- `src/lib/utils/bundle.js:generateChangesJson()` (line 121)
- `src/routes/review/+page.svelte:handleDone()` (around line 910)
