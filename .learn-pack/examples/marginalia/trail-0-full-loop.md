# Trail 0: The Full Loop

**Time**: ~18 minutes
**Start here.** This trail walks through an entire Marginalia review session, from the moment a draft file appears to the moment the agent reads your feedback.

---

## 1. The hook fires

You (or your agent) saves a file called `something-draft.md`. Claude Code has a post-write hook installed that watches for this.

The hook is a bash script at `hooks/post-write.sh`. It checks two things:

```
Does the filename end with -draft.md?
Does the file contain <!-- REVIEW -->?
```

If either matches (or if `MARGINALIA_REVIEW_REGEX` is set), the hook enqueues a review request. The key detail: it uses filesystem-based locking (`/tmp/marginalia-review-queue/run.lock`) to guarantee exactly one Marginalia instance runs at a time. If the app is already open, the new request waits in a queue directory.

The hook then launches the Marginalia binary:

```bash
"${MARGINALIA_BIN}" open "${FILE_PATH}" \
  --out "${status_file}" \
  --bundle-dir "${BUNDLE_DIR}" \
  --principles "${PRINCIPLES_PATH}"
```

**What the user sees**: nothing yet. The hook is running silently in the background.

**Code**: `hooks/post-write.sh` (lines 1-50 for config, the `enqueue_request` and `process_queue` functions handle queueing)

---

## 2. Tauri opens and reads the file

The binary is a Tauri app. Tauri is a Rust framework that wraps a web view. Think of it as: Rust handles files and windows, the browser handles the UI.

On startup, the Rust side does three things:

1. Parses CLI arguments into a `CliOptions` struct (file path, bundle dir, principles path, out path).
2. Stores those options in app state so the frontend can fetch them later.
3. Opens the window pointing at `/review`.

The Rust layer is intentionally thin. It exposes five commands to the frontend:

```rust
read_file(path)         // Read any file from disk
write_file(path, content)  // Write any file to disk
save_bundle(...)        // Write a bundle directory atomically
get_home_dir()          // For constructing paths like ~/.marginalia/
get_cli_options()       // The CLI args from step 1
close_window()          // Shut down cleanly
```

All review logic lives in the frontend. Rust is just the file system bridge.

**What the user sees**: the Marginalia window appears.

**Code**: `src-tauri/src/lib.rs` (the entire file is ~185 lines; `parse_cli_options` at line 133, command handlers at lines 22-72)

---

## 3. The store initializes

The frontend loads at `/review`, which mounts `src/routes/review/+page.svelte`. This is the orchestrator. It does not render UI itself; it wires together the components that do.

On mount, it calls `get_cli_options()` via Tauri's invoke bridge to get the file path. Then it reads the file content:

```javascript
const content = await invoke('read_file', { path: cliInitialPath });
initializeWithContent(path, content);
```

`initializeWithContent` (in `src/lib/stores/app.js`) sets up the reactive state:

```javascript
filename.set(name);           // "my-draft.md"
filePath.set(path);           // "/Users/.../my-draft.md"
originalContent.set(content); // The raw markdown
editedContent.set(content);   // Starts identical
originalPlainText.set('');    // Empty until editor renders
editedPlainText.set('');      // Empty until editor renders
debouncedEditedPlainText.set('');
annotations.set([]);          // No rationales yet
```

Notice that the plain text stores are empty. That is because we cannot extract plain text until the Milkdown editor actually renders the markdown into a DOM. This is a key design choice: Marginalia diffs what the user sees (rendered text), not the raw markdown source.

**What the user sees**: the editor appears with the draft content loaded.

**Code**: `src/routes/review/+page.svelte` (onMount init around line 535), `src/lib/stores/app.js:initializeWithContent()` (line 243)

---

## 4. The editor renders and captures plaintext

The Editor component (`src/lib/components/Editor.svelte`) mounts a Milkdown editor. Milkdown is a ProseMirror-based markdown editor; it parses markdown into a document tree and renders it as styled HTML.

After the first render, the editor calls back:

```javascript
onInitialRender(plainText);
```

This fires `setOriginalPlainText(text)` in the store, which sets three stores at once:

```javascript
originalPlainText.set(text);         // The baseline
editedPlainText.set(text);           // Current version (same for now)
debouncedEditedPlainText.set(text);  // The debounced copy (same for now)
```

Now the diff chain can run. Since original and edited are identical, `diffResult` returns an empty changes array. The change rail is empty.

**What the user sees**: the document, ready to edit. No changes shown yet because nothing has changed.

**Code**: `src/lib/components/Editor.svelte:initEditor()` (line 222), `src/lib/stores/app.js:setOriginalPlainText()` (line 348)

---

## 5. You start editing

You change "very important" to "critical." Here is the exact sequence:

1. Milkdown's ProseMirror catches the keystroke and updates the document.
2. The `markdownUpdated` listener fires. It extracts the new plain text.
3. It calls `onPlainTextChange(text)`, which calls `updatePlainText(text)` in the store.

`updatePlainText` does two things:

```javascript
editedPlainText.set(text);  // Immediate. The editor needs this to stay responsive.

// But the expensive stuff waits:
if (debounceTimer) clearTimeout(debounceTimer);
debounceTimer = setTimeout(() => {
  debouncedEditedPlainText.set(text);  // Fires after 120ms of quiet
}, 120);
```

When `debouncedEditedPlainText` finally updates, the derived store chain fires:

```
debouncedEditedPlainText changes
  -> diffResult recomputes (computeDiff with token-level diffing)
    -> visibleChanges filters out whitespace-only changes
      -> substantiveChanges filters out trivial (1-word) edits
      -> trivialChanges collects the trivial ones separately
    -> resolvedAnnotations reruns annotation matching
```

The diff engine (`src/lib/utils/diff.js`) tokenizes both texts into words, encodes them into single characters, runs diff-match-patch on the encoded strings, then decodes back. It also reconciles change IDs against the previous diff snapshot so IDs stay stable across edits.

**What the user sees**: the word "critical" appears with a green highlight. The old text "very important" shows as struck-through. The change rail on the left populates with an entry.

**Code**: `src/lib/stores/app.js:updatePlainText()` (line 357), `src/lib/utils/diff.js:computeDiff()` (main diffing function)

---

## 6. The change rail populates

The ChangeRail component (`src/lib/components/ChangeRail.svelte`) receives two lists:

- `substantiveChanges`: edits with more than one word, or meaning-carrying single words.
- `trivialChanges`: one-word edits, typo fixes, punctuation-only changes.

Substantive changes render as items with a type icon and the actual text:

```
-  very important        (deletion, brick red)
+  critical              (insertion, verdigris green)
```

Trivial changes collapse into an expandable "N minor edits" row at the bottom.

Each item is a button. Clicking one fires `onSelectChange(change, x, y)`, which propagates up to the page orchestrator.

**What the user sees**: the rail shows the edits, color-coded by type. Clicking one highlights it in the editor.

**Code**: `src/lib/components/ChangeRail.svelte` (full component)

---

## 7. You select a change and add a rationale

You click a change in the rail. The orchestrator (`+page.svelte`) calls `selectChange(change)`, which:

1. Sets `selectedChangeId` in the store.
2. Looks up whether an annotation already exists for this change.
3. Scrolls the editor to the change location.
4. On desktop: clears the popover and shows the annotation column.
5. On compact layout: opens the popover near the click position.

You click "Add rationale" and type: "Removed hedging. 'Critical' is more direct."

When you save, `createAnnotationRecord` builds a record:

```javascript
{
  id: "note_m1abc_x7k9f2",
  rationale: "Removed hedging. 'Critical' is more direct.",
  matchedRule: null,
  target: {
    changeId: "d_4",           // The diff change ID
    type: "insertion",
    excerpt: "critical",       // What the change says
    line: 14,                  // Where in the document
    beforeLine: "...",         // Context for reattachment
    lineText: "...",
    afterLine: "...",
    blockKey: "a_3f8e2a1c"    // Hash of surrounding lines
  },
  createdAt: "2026-03-25T...",
  updatedAt: "2026-03-25T..."
}
```

All that target metadata exists for one reason: if you keep editing and the change moves or changes shape, Marginalia needs to figure out whether this annotation still attaches to the same edit.

**What the user sees**: a note badge appears in the editor gutter. The annotation shows in the right column.

**Code**: `src/lib/utils/annotations.js:createAnnotationRecord()` (line 177), `src/lib/utils/annotations.js:buildAnnotationTarget()` (line 152)

---

## 8. Your annotation survives further edits

You keep editing. The text around "critical" shifts. The change ID might not even exist in the next diff computation (IDs are reconciled heuristically, and if the text moves enough, the ID could change).

Every time the diff recomputes, `resolvedAnnotations` runs `resolveAnnotations()`:

```
For each saved annotation:
  1. Look for exact change ID match -> active
  2. If no exact match, score every visible change against the annotation's target:
     - 60% weight: excerpt text similarity (bigram scoring)
     - 18% weight: same-line text similarity
     - 8% weight each: before/after line similarity
     - bonus: matching block key
     - penalty: line distance
  3. If best score >= 0.74 AND margin over runner-up >= 0.12 -> reattach
  4. Otherwise -> stale
```

A stale note is a first-class state: the UI shows it clearly, and the user can reattach it manually or dismiss it. Marginalia never silently moves a note to a different edit.

**What the user sees**: the note badge stays attached to the right edit. If you make radical changes, it might go stale and show a warning.

**Code**: `src/lib/utils/annotations.js:resolveAnnotations()` (line 280), `scoreDescriptorMatch()` (line 252)

---

## 9. You press Escape to finalize

Pressing Escape (or Cmd+Enter) triggers `handleDone()`. This function:

1. Checks whether any changes or annotations exist.
2. If no feedback at all: writes a "no-bundle" status JSON and closes.
3. If there is feedback: computes a fresh diff (in case the debounced one is stale), runs semantic diffing, generates the bundle, saves it via Rust, writes the status JSON, closes the window.

The bundle goes to `~/.marginalia/bundles/[timestamp]_[filename]/` and contains 7 files:

| File | What it is |
|------|-----------|
| `original.md` | The file before edits |
| `final.md` | The file after edits |
| `changes.json` | Machine-readable diff with metadata |
| `annotations.json` | All saved rationales with target info |
| `changes.patch` | Standard unified diff patch |
| `provenance.json` | Session metadata, hashes, timing |
| `summary_for_agent.md` | The primary agent-facing artifact |

**What the user sees**: the window closes.

**Code**: `src/routes/review/+page.svelte:handleDone()` (around line 910), `src/lib/utils/bundle.js:generateBundle()` (line 421)

---

## 10. The agent reads the result

The hook is still waiting (in sync mode) or polling (in async mode). When the status JSON appears, it checks:

- `status: "reviewed"` means a bundle was written.
- `bundle_path` points to the bundle directory.

The hook then emits a response directing the agent to read `summary_for_agent.md`:

```
Marginalia review complete. Read the reviewer's feedback at:
~/.marginalia/bundles/2026-03-25T17-15-42_my-draft/summary_for_agent.md
```

The summary is structured markdown:

```markdown
# Review: my-draft.md
2026-03-25 . 4 min

## Changes
2 deletions, 3 insertions

## Feedback (by priority)
1. Removed hedging. 'Critical' is more direct.
   - "critical"

## General
[Any session-level notes the user typed]
```

The agent reads this, applies the feedback to its next draft, and the loop continues.

**What the user sees**: they are already back in their terminal. The agent is working with the feedback.

**Code**: `hooks/post-write.sh` (the `output_hook_response` function), `src/lib/utils/bundle.js:generateSummaryMarkdown()` (line 294)

---

## Try it

Do an actual review session end-to-end:

1. Run `pnpm tauri dev` (leave it running).
2. In another terminal: `echo '# Test\n\nThis is very important draft content.' > /tmp/test-draft.md`
3. Open it: `open -a Marginalia /tmp/test-draft.md` (or use the file picker in the app).
4. Change "very important" to "critical."
5. Click the change in the rail. Add a rationale: "Tightened language."
6. Press Escape to finalize.
7. Look at what was generated: `ls ~/.marginalia/bundles/ | tail -1` then `cat` the `summary_for_agent.md` in that directory.

You just traced the entire loop yourself.

---

## Check your understanding

- If you edit the document but add zero annotations and no general notes, what happens when you press Escape? (Hint: look at step 9, the "no feedback at all" branch.)

- Why does Marginalia diff plain text instead of raw markdown? What would go wrong if it diffed the markdown source?

- The annotation target stores `beforeLine`, `lineText`, and `afterLine`. Why three lines of context instead of just the line the change is on?

- If the hook is in sync mode and the user takes 20 minutes to review, what happens to the agent? What about async mode?
