# Trail 1: The Edit Pipeline

**Time**: ~7 minutes
**Prerequisite**: Trail 0 (at least steps 4-5)

You type a single character. This trail traces every consequence.

---

## The setup

You have a draft open. The editor is rendered. The stores are initialized. Original and edited plain text are identical. The diff result is empty.

Now you press a key.

---

## Step 1: Milkdown catches the keystroke

Milkdown wraps ProseMirror, which models the document as a tree of nodes (paragraphs, headings, list items). When you type, ProseMirror creates a "transaction" that updates the tree.

Milkdown's listener plugin fires `markdownUpdated` with the new markdown string. This is the bridge between ProseMirror's world and ours.

Inside `Editor.svelte:initEditor()`, the listener does three things:

```javascript
// 1. Store the raw markdown
onChange(markdown);

// 2. Extract what the user actually sees (no markdown syntax)
const plainText = getCurrentPlainText();
onPlainTextChange(plainText);

// 3. Queue a decoration refresh (diff highlights in the editor)
diffUpdateTimeout = setTimeout(() => {
  triggerDiffUpdate(editor);
}, 150);  // 150ms debounce for editor decorations
```

Notice: `getCurrentPlainText()` calls `buildTextMap(view.state.doc)`, which walks the ProseMirror document tree and extracts the visible text. This is why we diff plain text, not markdown. The user never sees `**bold**`; they see **bold**. We diff what they see.

**Code**: `src/lib/components/Editor.svelte` lines 232-253

---

## Step 2: The store splits into fast and slow paths

`onPlainTextChange` calls `updatePlainText(text)` in the store. This is where the debounce happens:

```javascript
export function updatePlainText(text) {
  // FAST: the editor store updates immediately.
  // The editor needs this to not feel laggy.
  editedPlainText.set(text);

  // SLOW: the expensive derived chain waits.
  if (debounceTimer) clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => {
    debouncedEditedPlainText.set(text);
  }, 120);
}
```

Why two stores? Because `editedPlainText` is read by the editor and autosave (which need to be current). But `debouncedEditedPlainText` is read by the diff engine and annotation resolver (which are expensive and can lag by 120ms without anyone noticing).

If you type 5 characters in quick succession, `editedPlainText` gets set 5 times, but `debouncedEditedPlainText` only gets set once, after you pause.

**Code**: `src/lib/stores/app.js` lines 357-367

---

## Step 3: The diff engine runs

When `debouncedEditedPlainText` updates, Svelte's reactivity system fires every derived store that depends on it. First up: `diffResult`.

```javascript
export const diffResult = derived(
  [originalPlainText, debouncedEditedPlainText],
  ([$originalText, $editedText]) => {
    // ...
    const next = computeDiff($originalText, $editedText, previousChanges, previousText);
    previousDiffSnapshot = next;
    return next;
  }
);
```

`computeDiff` (in `src/lib/utils/diff.js`) does this:

1. **Tokenize** both texts into words using the pattern `/\s+|[\p{L}\p{N}][\p{L}\p{N}@._:/&+''-]*|[^\s]/gu`. Each word, whitespace run, or punctuation mark becomes one token.

2. **Encode** tokens into single Unicode characters. Token "critical" might become `\u0042`. This collapses the problem from many-character diffing to single-character diffing.

3. **Run diff-match-patch** on the encoded strings. This is a well-known algorithm (Google's library) that finds the minimal set of insertions and deletions.

4. **Decode** back into real text, producing Change objects with type, text, offsets, and location.

5. **Reconcile IDs**. This is the clever part: changes from the previous diff snapshot are matched to new changes using text similarity (bigram scoring) and position anchors. If a change is "the same edit, just shifted," it keeps its old ID. This means annotation targets stay valid across edits.

**Code**: `src/lib/utils/diff.js:computeDiff()`, `tokenize()` (line 4), `reconcileIds()` (around line 149)

---

## Step 4: The derived chain cascades

`diffResult` changing triggers everything downstream:

```
diffResult
  -> visibleChanges     (filter: remove whitespace-only changes)
    -> substantiveChanges  (filter: remove trivial 1-word edits)
    -> trivialChanges      (filter: keep only trivial edits)
    -> trivialChangeCount  (just the count)
    -> changeGroups        (group adjacent insert+delete into replacements)
    -> linesWithChanges    (Set of line numbers that have changes)
  -> resolvedAnnotations   (re-resolve all saved notes against new changes)
    -> annotationEntries   (add display indices)
    -> annotatedChangeIds  (Set of change IDs that have notes)
  -> selectedChange        (look up the currently selected change)
  -> changeSummary         (human-readable summary text)
```

Each arrow is a Svelte `derived` store. Svelte only recomputes a derived store when its input actually changes value. If the diff produces the same changes array, nothing downstream fires.

The `isTrivialChange()` function that splits substantive from trivial:

```javascript
const PUNCTUATION_ONLY = /^[\s\p{P}\p{S}]+$/u;

export function isTrivialChange(change) {
  const trimmed = change.text.trim();
  if (PUNCTUATION_ONLY.test(trimmed)) return true;
  return trimmed.split(/\s+/).length <= 1;
}
```

One word or fewer? Trivial. Punctuation only? Trivial. Everything else is substantive.

**Code**: `src/lib/stores/app.js` (derived stores after `diffResult`), `src/lib/utils/annotations.js:isTrivialChange()` (line 251)

---

## Step 5: The UI updates

The ChangeRail receives `substantiveChanges` and `trivialChanges` as props. It renders each substantive change as a single-line button:

```
+  critical
-  very important
```

Type icons are color-coded: `+` in verdigris green (insertions), `-` in brick red (deletions), `~` for replacements.

If there are trivial changes, a collapsed "N minor edits" row appears at the bottom of the rail. Click to expand.

In the editor, the diff decorations plugin (`milkdown-diff-plugin.js`) reads the diff result and adds CSS classes to the relevant text nodes: `.added` for insertions (green background), `.struck` for deletions (strikethrough with red background).

The 150ms decoration debounce in the editor (step 1) is separate from the 120ms store debounce (step 2). The store debounce fires first, producing the new diff result. Then the editor decoration refresh fires 30ms later, reading that result. This ordering is intentional.

**Code**: `src/lib/components/ChangeRail.svelte` (full component), `src/lib/utils/milkdown-diff-plugin.js` (decoration logic)

---

## Try it

1. Open `src/lib/stores/app.js` and change `DIFF_DEBOUNCE_MS` from `120` to `2000`.
2. Run `pnpm tauri dev` and open a draft.
3. Type several words quickly. Notice the 2-second gap before the change rail updates.
4. Now change it to `0` (no debounce). Type again. It should feel the same for short documents, but on a long document you might feel keystrokes stutter.
5. Set it back to `120`.

The 120ms sweet spot: fast enough that you never notice the delay, slow enough to batch 3-5 keystrokes into one diff computation.

---

## Check your understanding

- Why does `editedPlainText` update immediately but `debouncedEditedPlainText` waits? What would break if both were debounced?
  (Hint: the autosave snapshot reads `editedPlainText`. If it were debounced, a crash during rapid typing could lose the last 120ms of edits.)

- The diff engine tokenizes text into words before diffing. What would happen if it diffed character by character instead?
  (Hint: "important" -> "critical" as a character diff would be a mess of single-character insertions and deletions instead of one clean swap.)

- If you make 10 edits in 50ms, how many times does `computeDiff` run?
  (Answer: once. The debounce timer keeps resetting. It only fires 120ms after the last edit.)

- What is the purpose of change ID reconciliation? Why not just assign fresh IDs every time the diff recomputes?
  (Hint: annotations target changes by ID. If IDs changed on every keystroke, every saved annotation would immediately go stale.)
