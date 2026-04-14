# Diff Noise Elimination

Eliminate non-substantive changes from the filing diff engine so output surfaces only purposeful disclosure changes.

## Problem

The NVDA FY2024 vs FY2025 10-K diff reports 64 section deltas at 72.4% overall intensity. The real story is ~15 sections with ~35% intensity. The rest is noise from six sources:

1. **Section ID instability** (38 added + 14 removed): Same content gets different IDs when Part context changes between filings (Part II -> Part IV). The diff engine matches by exact ID only.
2. **TOC link paragraphs** (13 of 37 "modified" in Risk Factors): `[Table of Contents](#hash)` lines flagged as modified because anchor hashes change.
3. **Financial statement sections**: Numbers change every year. Not insight.
4. **Signature blocks**: Date rollovers, officer list changes.
5. **Cross-reference boilerplate**: "See Item 7 for discussion..." sentences where only the item/note number changes.
6. **Strict boilerplate threshold**: Requires 80%+ similarity AND 100% of changed words match a token pattern. Misses date-only changes in paragraphs with lower overall similarity.

## Approach

Hybrid: fix each noise source where it naturally belongs. No new modules.

- TOC link filtering, boilerplate expansion -> `text_diff.py`
- Section fallback matching, section suppression -> `section_diff.py`
- Output formatting -> `section_diff.py` + `cli.py`

## Design

### 1. Section Fallback Matching

**File:** `section_diff.py`, section pairing logic

Three-pass section matching replaces current exact-ID-only matching:

1. **Pass 1 (exact):** Match by full section ID. Same as today.
2. **Pass 2 (item+slug fallback):** For unmatched sections, extract `item{N}_{slug}` from the ID by stripping the form+part prefix (`10k_part{X}_` or `10q_part{X}_`). A regex like `^10[kq]_part[a-z]+_` handles both. Match remaining sections by this reduced key. Only pair unique 1:1 matches (if two sections share the same reduced key, skip both to avoid ambiguity).
3. **Pass 3 (remaining):** Anything still unmatched is genuinely added or removed.

Edge case: Multiple "Item 15" subsections with different suffixes (`_1`, `_2`, etc.) already have unique slugs, so they'll either match exactly in Pass 1 or remain unmatched. The ambiguity guard in Pass 2 handles the rare case where two sections collapse to the same reduced key.

### 2. TOC Link Paragraph Filtering

**File:** `text_diff.py`, before paragraph alignment

Before matching, filter both `before` and `after` paragraph lists. A paragraph is a TOC link if:

- It matches `^\[Table of Contents\]\(#.*\)$` after stripping whitespace
- Or it's a standalone anchor link `^\[.*\]\(#[a-f0-9_]+\)$` with no other substantive text

Filtered paragraphs are removed from both lists entirely. They don't appear in paragraph deltas, counts, or intensity calculations.

Prose paragraphs that mention the table of contents in context are not filtered; the pattern requires the paragraph to be solely a link.

### 3. Expanded Boilerplate Detection

**File:** `text_diff.py`, `_is_boilerplate_change()` and new helpers

#### 3a. Cross-reference pattern detection

New function `_is_cross_reference(text: str) -> bool`. A paragraph is a cross-reference if:

- Starts with "See ", "Refer to ", "For additional information", "For further discussion" (case-insensitive)
- Contains "Item \d+", "Note \d+", or "Part [IVX]+"
- Is under 100 words

If both old and new paragraphs in a matched pair are cross-references, mark the delta as `is_boilerplate=True` regardless of what changed.

#### 3b. Ratio-based boilerplate pass

Current check: 80%+ similarity AND 100% of changed words match `_BOILERPLATE_TOKEN_PATTERN`.

New additional check: If >60% of changed words match the boilerplate token pattern, mark as boilerplate regardless of overall similarity.

The existing strict check stays as a fast path. The new ratio check is a second pass that catches what the first misses (e.g., a date change in a paragraph with 65% overall similarity).

### 4. Section Type Suppression

**File:** `section_diff.py`, output assembly

After computing all section deltas, filter out any delta whose `section_type` is:

- `financial_statement` (Item 8, Item 15 financial schedules)
- `signature`

Suppressed entirely: not in `section_deltas` list, not in CLI output, not in `overall_change_intensity` calculation (excluded from both numerator and denominator).

Not suppressed:

- `exhibit_index` (kept, current 0.15x damping stays)
- `prose` (kept, full weight)

Existing classification logic already tags these types correctly. No changes needed to classification.

### 5. Output Formatting

**Files:** `section_diff.py`, `cli.py`

**Paragraph text display** (`--format full`):

- Show old/new text for modified paragraphs
- If a paragraph exceeds 200 words, truncate to first 200 words + `...`
- Added paragraphs: show new text (capped). Removed: show old text (capped)

**Boilerplate visibility:**

- Paragraphs marked `is_boilerplate=True` are completely invisible in all output formats
- Not in paragraph delta lists, not in added/removed/modified counts
- Section-level counts (`+5 -2 ~37 =19`) only reflect non-boilerplate paragraphs

**Overall intensity:**

- Computed from non-suppressed section types only
- Includes genuinely added and removed sections (real disclosure changes)
- Excludes boilerplate paragraphs within sections

## Testing

### Acceptance test

Re-run the NVDA FY2024 vs FY2025 10-K diff. Expected changes:

| Metric | Before | After |
|---|---|---|
| Section deltas | 64 | ~15-18 |
| Overall intensity | 72.4% | ~30-45% |
| Spurious added/removed | 38+14 | ~2-5 genuinely new/removed |
| Risk Factors modified paragraphs | 37 (13 TOC links) | ~20-24 |

### Unit tests

- **Fallback section matching:** Two manifests with same content under different part prefixes -> matched as modified, not added+removed
- **TOC link filtering:** Paragraph list with TOC links -> links stripped, counts correct
- **Cross-reference detection:** Known patterns ("See Item 7...", "Refer to Note 12...") -> marked boilerplate
- **Ratio-based boilerplate:** Paragraph with 65% similarity but 90% boilerplate tokens -> marked boilerplate
- **Section suppression:** Financial/signature sections absent from output, exhibit indices present

### Regression

Existing test suite (301 tests) must pass unchanged.
