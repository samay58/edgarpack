# Learn Marginalia

How the system works, traced through what actually happens.

## The napkin sketch

```
Hook sees draft file
  -> Tauri opens, Rust reads the file from disk
    -> Store loads content, editor renders, plaintext captured
      -> You edit: keystrokes debounce into diffs, rail updates
        -> You annotate: rationale saved with target metadata
          -> You press Escape: bundle written to ~/.marginalia/bundles/
            -> Agent reads summary_for_agent.md
```

That is the entire lifecycle. Everything below fills in the details.

## Visual map

Open [system-map.html](system-map.html) in your browser for an interactive view of the full lifecycle. Each phase expands to show the exact code path.

## Trails

Trails trace a concrete action through the code. Each one starts with something you do and follows the chain of what happens next.

**Start here:**

- [Trail 0: The Full Loop](trail-0-full-loop.md) (~18 min)
  A complete review session from hook trigger to agent handoff. Read this first.

**Then go deeper:**

- [Trail 1: The Edit Pipeline](trail-1-edit-pipeline.md) (~7 min)
  What happens when you type a single character. The debounce chain, diff computation, change rail update.

- [Trail 2: Annotations](trail-2-annotations.md) (~12 min)
  How a rationale survives across edits. Resolution, reattachment, stale detection.

- [Trail 3: The Bundle](trail-3-bundle.md) (~6 min)
  What ships to the agent. Every file in the bundle, what it contains, why.

## Reference

When you need to look up a specific function or store, use the reference docs. These cover every exported function with purpose, inputs, outputs, design choices, and connections.

Trails tell you the story. Reference is the dictionary.

- [ref/ref-app-store.md](ref/ref-app-store.md) -- The reactive state layer. Every store, every derived store, every action function. Start here if you want to understand how data flows.

- [ref/ref-diff-engine.md](ref/ref-diff-engine.md) -- The diff algorithm. Tokenization, encoding, diff-match-patch, ID reconciliation. Start here if you want to understand how changes are detected.

- [ref/ref-annotations.md](ref/ref-annotations.md) -- The annotation model. Creating, resolving, reattaching, stale detection. Start here if you want to understand how rationales survive across edits.

## How to use this

**Before a session**: glance at the napkin sketch or the visual map. Orient yourself to where we will be working.

**During a session**: when something is unclear, ask "walk me through this" and reference the relevant trail.

**After a session**: walk the trail for what we just built. The code references point you to the exact lines.

## Keeping it current

These trails reference actual source files and function names. When the code changes, the trails should be updated in the same commit. If a trail reference is wrong, that is a bug.
