# Reference: The Diff Engine (diff.js)

`src/lib/utils/diff.js`

This module computes the difference between two plain text strings and produces a list of Change objects with stable IDs. It is the algorithmic heart of Marginalia.

---

## Data types

### Change

```javascript
{
  id: "c_1a2b3c",           // Stable identifier (survives across edits)
  type: "deletion",          // "deletion" or "insertion"
  text: "very important",    // The actual changed text
  editedOffset: 142,         // Character position in the edited document
  location: { line: 7, col: 12 }  // Line/column in the edited document
}
```

**Why `editedOffset`?** Decorations (highlights) are placed in the edited document, not the original. Even deletions need a position in the edited document (they show at the point where text was removed).

### DiffResult

```javascript
{
  changes: Change[],     // All non-equal changes
  deletions: 3,          // Count of deletion changes
  insertions: 2,         // Count of insertion changes
  _originalText: "...",  // Snapshot for decoration verification
  _editedText: "..."     // Snapshot for decoration verification
}
```

The `_originalText` and `_editedText` fields are attached so the editor can verify that its decorations match the current diff. If the editor's text has diverged from the diff's snapshot, decorations are skipped to avoid misplacement.

---

## The main pipeline

### computeDiff(original, edited, previousChanges?, previousEditedText?)

**Purpose**: produce a DiffResult from two strings.

**Inputs**:
- `original` (string): the baseline text
- `edited` (string): the current text
- `previousChanges` (Change[]): changes from the last diff (for ID reconciliation)
- `previousEditedText` (string): the edited text from the last diff (for context anchors)

**Returns**: `DiffResult`

**How it works**, step by step:

1. Call `computeTextDiffs(original, edited)` to get raw diff operations.
2. Walk the diff operations. For each deletion or insertion, create a Change object with a fresh ID from `generateChangeId`.
3. Track `editedOffset` as you go. Insertions advance the offset (they exist in the edited text). Deletions do not (deleted text is not in the edited text). Equal segments advance the offset.
4. Pass the new changes through `reconcileChangeIds` to inherit IDs from the previous snapshot where possible.
5. Return the result with text snapshots attached.

**Design choice**: the previous changes and previous text are optional. On first diff (or after loading a new file), they are empty, and every change gets a fresh ID. On subsequent diffs, IDs are preserved for changes that match.

---

## Token compression

The diff algorithm operates on tokens (words), not individual characters. This produces cleaner, more readable diffs. "important" becoming "critical" shows as one swap, not a character-by-character mess.

### tokenizeForDiff(text)

**Purpose**: split text into meaningful editorial units.

**Pattern**: `/\s+|[\p{L}\p{N}][\p{L}\p{N}@._:/&+''-]*|[^\s]/gu`

This matches three kinds of tokens:
- `\s+` : whitespace runs (spaces, newlines, tabs)
- `[\p{L}\p{N}][\p{L}\p{N}@._:/&+''-]*` : words starting with a letter or digit, optionally followed by more letters/digits and common word-interior punctuation (dots, colons, slashes, hyphens, apostrophes)
- `[^\s]` : any remaining non-whitespace character (standalone punctuation)

**Design choice**: whitespace is kept as explicit tokens (not collapsed) because spacing changes should appear in the diff. The word pattern allows characters like `.` and `/` inside tokens so URLs and file paths stay as single tokens.

### encodeTokenText(text, tokenMap, tokenArray)

**Purpose**: compress tokens into single Unicode characters so diff-match-patch can operate on them efficiently.

**How it works**: builds a bidirectional mapping. Each unique token gets assigned a character code starting from 0. "Hello" might become `\u0000`, "world" becomes `\u0001`, " " becomes `\u0002`. The original text "Hello world" becomes three characters: `\u0000\u0002\u0001`.

**The overflow guard**: if there are more than 65,535 unique tokens (`MAX_TOKEN_ALPHABET`), encoding returns `null` and the system falls back to raw character diffing. This is extremely rare (it would require a 65K-word vocabulary in a single document).

**Returns**: the encoded string, or `null` if the alphabet overflowed.

### decodeTokenText(compressed, tokenArray)

**Purpose**: reverse the encoding. Takes the compressed string and the token array, returns the original text.

### computeTextDiffs(original, edited)

**Purpose**: produce raw diff operations using the token compression trick.

**How it works**:
1. Try to encode both texts into the token alphabet.
2. If both succeed: run `dmp.diff_main` on the encoded strings, then decode the results back.
3. If either fails (alphabet overflow): fall back to `dmp.diff_main` on the raw strings.
4. In both cases: run `dmp.diff_cleanupSemantic` and `dmp.diff_cleanupSemanticLossless` to merge trivial adjacent diffs into cleaner operations.

**Returns**: an array of `[operation, text]` tuples where operation is -1 (delete), 0 (equal), or 1 (insert).

---

## ID reconciliation

This is the most important subsystem for annotation stability. When you type and the diff recomputes, the "same" change might appear at a different offset with slightly different text. Without reconciliation, it would get a new ID, and any annotation targeting the old ID would go stale.

### reconcileChangeIds(nextChanges, previousChanges, editedText, previousEditedText)

**Purpose**: match new changes to previous changes and inherit their IDs.

**Inputs**:
- `nextChanges`: the freshly computed changes (with fresh IDs from `generateChangeId`)
- `previousChanges`: changes from the last diff
- `editedText`: the current edited text (for building context anchors)
- `previousEditedText`: the previous edited text (for building context anchors)

**How it works**:

1. Bucket previous changes by type (deletion/insertion). A deletion can only match a deletion.

2. For each new change, score it against all unmatched previous changes of the same type:
   ```
   score = textSimilarity * 0.74          // How similar is the text?
         + anchorSimilarity * 0.26         // How similar is the surrounding context?
         - distance * 0.00015              // Penalty for being far from original position
   ```

3. The best-scoring previous change wins, but only if `textSimilarity >= 0.34`. Below that threshold, the text is too different to be "the same change."

4. Mark the matched previous change as used (each previous ID can only be inherited once).

5. If no match passes the threshold, the change keeps its fresh ID.

**Design choices**:

- **0.74 text weight, 0.26 anchor weight**: text content is the strongest signal. But when two changes have identical text (e.g., you deleted "the" in two places), the surrounding context breaks the tie.

- **0.34 minimum similarity**: low enough that a change like "important" -> "very important" (substring relationship) still matches. High enough that "apples" and "oranges" do not.

- **0.00015 distance weight**: very small. Position shift matters, but much less than text content. If the change text is clearly the same, it should match even if it moved 1000 characters.

- **One-to-one matching**: `usedPreviousIds` prevents two new changes from claiming the same old ID. First match wins (in document order).

### generateChangeId(type, text, offset)

**Purpose**: create a deterministic ID for a new change.

**How it works**: hashes `type|offset|text.length|text` with a simple bit-rotation hash, then encodes as base-36.

**Design choice**: deterministic, not random. The same change at the same position always gets the same ID. This means that if reconciliation fails and later succeeds (because the user undid an edit), the ID comes back naturally.

### textSimilarity(a, b)

**Purpose**: Sorensen-Dice coefficient on character bigrams.

**How it works**:
1. Normalize both strings (lowercase, collapse whitespace).
2. If one contains the other: return length ratio.
3. Build bigram multisets for both. ("hello" -> {"he":1, "el":1, "ll":1, "lo":1})
4. Compute: `2 * intersection / (leftCount + rightCount)`

**Returns**: 0.0 (completely different) to 1.0 (identical).

### buildContextAnchor(text, offset, radius?)

**Purpose**: capture 32 characters before and after a change position.

**Returns**: `{ before: string, after: string }` (normalized).

Used by reconciliation to distinguish changes with identical text but different positions.

### anchorSimilarity(left, right)

**Purpose**: compare two context anchors using `textSimilarity` on the before and after segments.

---

## Grouping and utilities

### groupChanges(changes)

**Purpose**: find replacement pairs (a deletion immediately followed by an insertion at the same line and column).

**How it works**: walks through changes in order. If a deletion and the next insertion share the same `location.line` and `location.col`, they are grouped as a pair. The editor uses these to render deletion+insertion as a single visual replacement.

**Returns**: `Change[][]` where each inner array is either a single change or a [deletion, insertion] pair.

### getLinesWithChanges(changes)

**Purpose**: compute which lines have changes, including multi-line changes.

**Returns**: `Set<number>` of 1-based line numbers.

For a change on line 7 that spans 3 newlines, the set includes 7, 8, 9, and 10.

### summarizeChanges(diffResult)

**Purpose**: human-readable summary text.

**Returns**: string like `"2 deletions, 3 insertions"` or `"No changes"`.

### offsetToLocation(text, offset)

**Purpose**: convert a character offset to line/column numbers.

**How it works**: walks character by character from the start, counting newlines. Line is 1-based, column is 0-based.

Used when constructing Change objects to attach a human-readable location.
