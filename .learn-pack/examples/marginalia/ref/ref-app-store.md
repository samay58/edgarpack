# Reference: The Store (app.js)

`src/lib/stores/app.js`

This is the reactive state layer. Every component reads from these stores. When a store changes, Svelte automatically re-renders any component that subscribes to it. Think of it as the nervous system: all signals pass through here.

---

## Writable stores (you set these directly)

### filename
**Type**: `string`, default `'Untitled'`
**Set by**: `initializeWithContent`, `restoreFromSnapshot`
**Read by**: Header component, snapshot persistence

The display name of the file being reviewed. Extracted from the file path on load.

### filePath
**Type**: `string`, default `''`
**Set by**: `initializeWithContent`, `restoreFromSnapshot`
**Read by**: Bundle generation, snapshot persistence

The full filesystem path. Used when saving the bundle and recording provenance.

### originalContent / editedContent
**Type**: `string`, default `''`
**Set by**: `initializeWithContent` (both identical), `updateContent` (edited only), `restoreFromSnapshot`
**Read by**: Bundle generation (original.md and final.md), `hasChanges` derived store

The raw markdown. `originalContent` never changes after load. `editedContent` updates on every keystroke via the `onChange` callback from the editor. These are the markdown source; the plain text stores below are what gets diffed.

### originalPlainText / editedPlainText
**Type**: `string`, default `''`
**Set by**: `setOriginalPlainText` (both), `updatePlainText` (edited only), `restoreFromSnapshot`
**Read by**: `editedPlainText` is read by autosave snapshots. Neither is read directly by the diff chain (that reads `debouncedEditedPlainText` instead).

The rendered plain text extracted from the Milkdown editor. This is what the user actually sees, stripped of markdown syntax. "**bold**" becomes "bold." Diffing happens on these, not on the raw markdown.

**Why two separate pairs?** Markdown and plain text diverge because markdown formatting characters are invisible to the user. The user reviews plain text, so that is what we diff. But the bundle needs the markdown for `original.md` and `final.md`.

### debouncedEditedPlainText
**Type**: `string`, default `''`
**Set by**: `updatePlainText` (via 120ms debounce), `setOriginalPlainText` (immediate), `restoreFromSnapshot` (immediate), `initializeWithContent` (immediate), `reset` (immediate)
**Read by**: `diffResult`, `resolvedAnnotations`

This is the key performance trick. The expensive derived stores (diff computation, annotation resolution) read from this store instead of `editedPlainText`. It only updates after 120ms of typing silence, so rapid keystrokes batch into a single diff computation.

**Design choice**: we debounce the input to the expensive chain, not the output. The editor store (`editedPlainText`) stays immediate because autosave needs current content and the editor needs to feel responsive. Only the consumers that are expensive get the delayed signal.

### annotations
**Type**: `AnnotationRecord[]`, default `[]`
**Set by**: `addAnnotation`, `updateAnnotation`, `removeAnnotation`, `initializeWithContent`, `restoreFromSnapshot`
**Read by**: `resolvedAnnotations` derived store

The raw saved annotations. Each is a record with an ID, rationale text, and target metadata. This is the source of truth; `resolvedAnnotations` is the resolved/enriched view.

### generalNotes
**Type**: `string`, default `''`
**Set by**: `updateGeneralNotes`
**Read by**: Bundle generation, SessionDrawer, snapshot persistence

Session-level notes that are not attached to any specific change. Included in the bundle output.

### selectedChangeId
**Type**: `string | null`, default `null`
**Set by**: `setSelectedChange`, `clearSelectedChange`
**Read by**: `selectedChange`, `selectedAnnotation`, ChangeRail, Editor (for highlighting)

Which change the user has clicked on. Drives highlighting in the editor and the annotation column state.

### currentLine / startTime
**Type**: `number | null` / `Date`
Bookkeeping. `currentLine` tracks the cursor position for the "near cursor" indicator in the change rail. `startTime` is used to compute session duration in the bundle.

---

## Derived stores (computed automatically)

These recompute whenever their input stores change. Svelte is smart: if the derived function returns the same value, downstream stores do not re-fire.

### diffResult
**Depends on**: `originalPlainText`, `debouncedEditedPlainText`
**Produces**: `DiffResult | null` (changes array, deletion/insertion counts)

The core diff computation. Calls `computeDiff()` from diff.js with the previous snapshot for ID reconciliation. Resets the snapshot when the original text changes (new file loaded).

**Important detail**: passes `previousDiffSnapshot?.changes` and `previousDiffSnapshot?._editedText` to `computeDiff`. This is how change IDs survive across edits. Without this, every keystroke would generate fresh IDs and all annotations would go stale.

### hasChanges
**Depends on**: `originalContent`, `editedContent`
**Produces**: `boolean`

Simple string comparison on the raw markdown. Used by the header to show the "unsaved" indicator and by `handleDone` to decide whether to generate a bundle.

### visibleChanges
**Depends on**: `diffResult`
**Produces**: `Change[]`

Filters `diffResult.changes` through `isVisibleChange()`, which removes whitespace-only changes (where `text.trim().length === 0`). These are changes that actually show up in the UI.

### substantiveChanges
**Depends on**: `visibleChanges`
**Produces**: `Change[]`

Filters out trivial changes (1 word or fewer, punctuation-only) using `isTrivialChange()`. This is what the change rail renders as its main list.

### trivialChanges / trivialChangeCount
**Depends on**: `visibleChanges`
**Produces**: `Change[]` / `number`

The complement of substantiveChanges. Trivial edits are collapsed into the "N minor edits" row at the bottom of the rail.

### changeGroups
**Depends on**: `visibleChanges`
**Produces**: `Change[][]`

Groups adjacent deletion+insertion at the same location into replacement pairs. Used by the editor decorations to render replacements as a single visual unit.

### linesWithChanges
**Depends on**: `visibleChanges`
**Produces**: `Set<number>`

Set of line numbers that have at least one change. Used for cursor-proximity highlighting in the rail.

### changeSummary
**Depends on**: `diffResult`
**Produces**: `string`

Human-readable text like "2 deletions, 3 insertions". Used in the status bar.

### selectedChange
**Depends on**: `visibleChanges`, `selectedChangeId`
**Produces**: `Change | null`

Looks up the full Change object for the selected ID. Returns null if nothing is selected or the ID does not match any visible change.

### resolvedAnnotations
**Depends on**: `annotations`, `diffResult`, `debouncedEditedPlainText`
**Produces**: `ResolvedAnnotation[]`

Runs `resolveAnnotations()` from annotations.js, which matches each saved annotation against the current changes. Each entry gets a status (`active` or `stale`), the matched change (if any), and a reason.

**Design choice**: depends on `debouncedEditedPlainText`, not `editedPlainText`. This means annotation resolution runs at the same cadence as the diff (120ms debounce), not on every keystroke.

### annotationEntries
**Depends on**: `resolvedAnnotations`
**Produces**: `ResolvedAnnotation[]` with `displayIndex` added

Adds sequential 1-based display indices for the UI. "Note 1", "Note 2", etc.

### annotatedChangeIds
**Depends on**: `annotationEntries`
**Produces**: `Set<string>`

Set of change IDs that have an active annotation. Used by the change rail to show the annotation dot indicator.

### selectedAnnotation
**Depends on**: `annotationEntries`, `selectedChangeId`
**Produces**: `ResolvedAnnotation | null`

Finds the annotation entry for the currently selected change. Used by the annotation column to decide whether to show "Add rationale" or "Edit rationale."

---

## The derived store chain (dependency graph)

```
debouncedEditedPlainText ──┐
originalPlainText ─────────┤
                           v
                       diffResult
                           │
              ┌────────────┼────────────────┐
              v            v                v
       visibleChanges   changeSummary   resolvedAnnotations
         │   │   │                          │
         v   v   v                          v
  substantive  trivial  changeGroups  annotationEntries
  Changes      Changes  linesWithChanges    │
                                       ┌────┴────┐
                                       v         v
                                 annotated   selectedAnnotation
                                 ChangeIds
```

---

## Action functions

### initializeWithContent(path, content)
**Called by**: `+page.svelte` on file load

Resets everything. Sets original and edited content to the same value. Clears annotations, notes, selection. Plain text stores are empty until the editor renders and calls `setOriginalPlainText`.

### restoreFromSnapshot(snapshot)
**Called by**: `+page.svelte` on session recovery

Hydrates the full store from a JSON snapshot. Handles two annotation formats: the current `{id, target, rationale}` format and a legacy `{annotation, changeId}` format from earlier versions.

**Design choice**: sets `debouncedEditedPlainText` synchronously (not debounced). Recovery must produce an immediate diff so the UI renders correctly on first frame.

### setOriginalPlainText(text)
**Called by**: Editor.svelte after first render (`onInitialRender`)

Sets all three plaintext stores simultaneously. This is the moment the diff chain becomes active. Before this call, `diffResult` returns null because the inputs are empty.

### updatePlainText(text)
**Called by**: Editor.svelte on every keystroke (`onPlainTextChange`)

The debounce entry point. Sets `editedPlainText` immediately, then schedules `debouncedEditedPlainText` to update after 120ms. If another call comes in before the timer fires, the timer resets. This means rapid typing produces one diff computation per pause, not one per keystroke.

### updateContent(content)
**Called by**: `+page.svelte` when the editor fires `onChange`

Sets `editedContent` (the raw markdown). This is separate from `updatePlainText` because markdown and plain text update at different times via different callbacks.

### addAnnotation(annotation) / updateAnnotation(id, patch) / removeAnnotation(id)
CRUD for the annotations array. `addAnnotation` normalizes the record before storing. `updateAnnotation` merges the patch, including nested target fields. `removeAnnotation` filters by ID.

### setSelectedChange(changeId) / clearSelectedChange()
Selection management. Setting a change ID drives `selectedChange` and `selectedAnnotation` derived stores.

### updateGeneralNotes(notes)
Simple setter for session-level notes.

### reset()
Returns every store to its initial state. Clears the debounce timer and diff snapshot. Called when a new file is loaded after a previous session.
