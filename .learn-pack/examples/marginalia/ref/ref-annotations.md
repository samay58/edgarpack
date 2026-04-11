# Reference: The Annotation Model (annotations.js)

`src/lib/utils/annotations.js`

This module handles everything about saved rationales: creating them, attaching them to changes, keeping them attached when the document evolves, and detecting when they can no longer be trusted.

---

## Data types

### AnnotationRecord

```javascript
{
  id: "note_m1abc_x7k9f2",     // Stable, never changes after creation
  rationale: "Removed hedging.", // What the user typed
  matchedRule: null,              // Auto-matched WRITING.md rule, if any
  target: { ... },               // AnnotationTarget (see below)
  createdAt: "2026-03-25T...",
  updatedAt: "2026-03-25T..."
}
```

### AnnotationTarget

```javascript
{
  changeId: "c_1a2b3c",        // The diff change this note is attached to
  type: "insertion",             // The change type when the note was created
  excerpt: "critical",           // The change text when the note was created
  line: 14,                      // Line number in the document
  beforeLine: "The problem is",  // The line ABOVE the change
  lineText: "This is critical",  // The line the change is ON
  afterLine: "and needs fixing", // The line BELOW the change
  blockKey: "a_3f8e2a1c"        // Hash of the three context lines
}
```

**Why all this context?** The `changeId` is the primary key for matching. But change IDs can shift (see diff.js reconciliation). When the ID no longer matches, the system uses excerpt similarity plus line context to find the best new match. Three lines of context (before, current, after) are much more reliable than just the excerpt alone because they anchor the annotation to a specific location in the document, not just a piece of text.

**The blockKey** is an FNV-1a hash of the three context lines concatenated. If two changes have the same blockKey, they are in the same region of the document. This is used as a bonus signal during reattachment scoring.

### ResolvedAnnotation

```javascript
{
  annotation: AnnotationRecord,     // The original saved record
  status: "active" | "stale",       // Can we still find this annotation's target?
  change: Change | null,            // The matched change (null if stale)
  target: AnnotationTarget,         // The current target descriptor
  resolvedChangeId: "c_1a2b3c",    // The change we matched to (null if stale)
  reason: null | "reattached" | "ambiguous" | "missing"
}
```

The `reason` field explains how we got here:
- `null`: exact match on changeId. Healthy.
- `"reattached"`: the old changeId was gone, but we found a clearly best new match.
- `"ambiguous"`: multiple candidates scored too close to call. Went stale to be safe.
- `"missing"`: no candidates scored above the minimum threshold at all.

---

## Creating annotations

### createAnnotationId()

**Purpose**: generate a unique ID for a new annotation.

**Returns**: `"note_[timestamp_base36]_[random_6chars]"`

The timestamp prefix makes IDs roughly chronological. The random suffix prevents collisions if two annotations are created in the same millisecond.

### createAnnotationRecord({ change, editedText, rationale, matchedRule?, annotationId?, createdAt?, updatedAt? })

**Purpose**: build a complete AnnotationRecord from a change and a rationale string.

**How it works**:
1. Generates an ID (or uses `annotationId` if provided, for updates).
2. Calls `buildAnnotationTarget(change, editedText)` to capture all the context metadata.
3. Assembles the full record with timestamps.

**Called by**: `+page.svelte` when the user saves a rationale.

### buildAnnotationTarget(change, editedText)

**Purpose**: capture everything needed to find this change again later.

**How it works**:
1. Calls `getLineContext(editedText, change.location.line)` to get the surrounding lines.
2. Assembles the target with changeId, type, excerpt, line context, and blockKey.

**Design choice**: captures context at save time, not at resolution time. This means the target metadata is a snapshot of where the change was when the user annotated it. Later, resolution compares the saved snapshot against current state.

### buildAnnotationTargetFromLines(change, lines)

**Purpose**: same as `buildAnnotationTarget`, but takes a pre-split lines array instead of the full text string.

**Why it exists**: `resolveAnnotations` builds target descriptors for every visible change. Without this variant, it would call `text.split(/\r?\n/)` once per change (splitting a 1000-line document 50 times). This function takes the already-split array, cutting that to one split for the entire resolution pass.

### reanchorAnnotation(annotation, change, editedText)

**Purpose**: manually move an annotation to a different change.

**Called by**: `+page.svelte` when the user clicks "Attach to selected edit" on a stale note.

**How it works**: replaces the annotation's target with a fresh `buildAnnotationTarget` for the new change. Updates the timestamp.

---

## Resolution

This is the most complex part of the system. It runs on every diff recomputation (debounced at 120ms) to figure out which saved annotations still match a visible change and which have gone stale.

### resolveAnnotations(annotations, diffResult, editedText)

**Purpose**: match every saved annotation against the current visible changes.

**Inputs**:
- `annotations` (AnnotationRecord[]): the saved annotations
- `diffResult` (DiffResult | null): the current diff
- `editedText` (string): the current document text

**Returns**: `ResolvedAnnotation[]`

**How it works**:

1. Filter `diffResult.changes` to visible changes only (non-whitespace).
2. Split `editedText` into lines once (optimization).
3. Build a target descriptor for each visible change using `buildAnnotationTargetFromLines`.
4. For each saved annotation:
   a. **Exact match**: look for a change with the same ID as `annotation.target.changeId`. If found, the annotation is active. Done.
   b. **Heuristic reattachment**: if no exact match, score every visible change against the annotation's saved target using `scoreDescriptorMatch`.
   c. Filter to scores that are finite (not -infinity from type mismatch or low excerpt similarity).
   d. Sort by score descending. Take the best and the runner-up.
   e. If best score >= 0.74 AND (best - runner-up) >= 0.12: reattach. The annotation moves to the new change.
   f. Otherwise: mark as stale.

**Design choice**: the margin requirement (0.12) prevents ambiguous reattachment. If two changes score 0.80 and 0.78, neither wins. The annotation goes stale rather than picking the wrong one. This is the "conservative" in "conservative resolution."

### scoreDescriptorMatch(target, descriptor)

**Purpose**: score how well a saved annotation target matches a candidate change's descriptor.

**Inputs**:
- `target`: the annotation's saved target (from when it was created)
- `descriptor`: the candidate change's current target

**Returns**: a score (higher is better), or `-Infinity` if the match is impossible.

**The scoring formula**:

```
score = excerptSimilarity * 0.60      // How similar is the change text?
      + lineTextSimilarity * 0.18      // How similar is the line the change is on?
      + beforeLineSimilarity * 0.08    // How similar is the line above?
      + afterLineSimilarity * 0.08     // How similar is the line below?
      + blockKeyBonus                  // 0.14 if blockKeys match, 0 otherwise
      - linePenalty                    // 0.03 per line of distance, max 4 lines
```

**Hard gates** (return -Infinity immediately):
- Type mismatch: a deletion annotation cannot reattach to an insertion (and vice versa).
- Excerpt similarity below 0.58: the text is too different to be the same change.

**Design choices**:

- **0.60 excerpt weight**: the change text itself is the strongest signal. "Removed 'very important'" should find "very important" even if it moved.
- **0.18 line text weight**: the line the change is on provides strong context but can itself change, so it gets less weight than the excerpt.
- **0.08 each for before/after**: surrounding lines are stable anchors but individually weak.
- **0.14 blockKey bonus**: if the three-line hash matches exactly, the change is in the same region. Strong signal, awarded as a bonus rather than a multiplier.
- **0.03 per line penalty, max 4**: slight preference for changes that haven't moved far, but capped so a change that moved 100 lines can still match if the text is right.

### sortResolvedAnnotations(entries)

**Purpose**: put active annotations before stale ones, ordered by document position.

**How it works**:
1. Active before stale.
2. Within active: sort by `change.editedOffset` (document order).
3. Within stale: sort by `updatedAt` (most recently updated first).

---

## Filtering

### isVisibleChange(change)

**Purpose**: should this change appear in the UI?

**Returns**: `true` if the change has non-whitespace text (`text.trim().length > 0`).

Whitespace-only changes (e.g., adding a newline, changing indentation) are real changes but they clutter the review surface. They are excluded from the visible list but still present in the raw diff and the bundle.

### isTrivialChange(change)

**Purpose**: is this change too small to warrant its own rail entry?

**Returns**: `true` if:
- The text is punctuation-only (matches `/^[\s\p{P}\p{S}]+$/u`)
- OR the text has 1 word or fewer (`text.trim().split(/\s+/).length <= 1`)

Trivial changes are still visible in the editor (green/red highlights) and included in the bundle. They are just collapsed in the change rail into the "N minor edits" summary.

**Design choice**: this is deliberately simple. No semantic analysis, no dictionary lookup. One word or fewer, or punctuation. Easy to predict, easy to explain.

---

## Normalization

### normalizeAnnotationRecord(annotation)

**Purpose**: ensure an annotation record has all required fields with correct types.

**Why it exists**: annotations can come from multiple sources:
- Freshly created in the UI
- Restored from a JSON snapshot (field names might be camelCase or snake_case)
- Migrated from an older schema version

The function normalizes field names (`created_at` -> `createdAt`, `change_id` -> `changeId`), provides defaults for missing fields, and ensures type safety.

**Connected to**: called by `addAnnotation`, `updateAnnotation`, and `restoreFromSnapshot` in the store.

---

## Internal helpers (not exported)

### normalize(text)
Collapse whitespace, trim, lowercase. Used by similarity functions.

### hashText(text)
FNV-1a hash of normalized text, returned as hex prefixed with `a_`. Used to generate blockKeys.

### buildBigrams(text)
Character bigram multiset. Used by `similarity()`.

### similarity(left, right)
Sorensen-Dice coefficient on bigrams. Same algorithm as `textSimilarity` in diff.js (both modules have independent implementations). Returns 0.0 to 1.0.

### clampLineNumber(line, lineCount)
Ensure a line number is within bounds. Handles null, NaN, out-of-range gracefully.

### getLineContext(text, lineNumber)
Split text, extract the line plus before/after lines, compute blockKey. Used by `buildAnnotationTarget`.
