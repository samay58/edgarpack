# Markdown Polish: Clean, Readable Filing Output

**Date**: 2026-04-12
**Status**: Design
**Scope**: `edgarpack/parse/` pipeline improvements + new polish pass

---

## Problem

The generated markdown from SEC filings is functionally correct but messy to read and suboptimal for machine parsing. Specific issues:

- Up to 568 `##### Table of Contents` headings per filing (page-break artifacts)
- Nested lists flattened to a single level (risk factor hierarchies lost)
- Bullet-point content rendered as tables instead of lists
- Financial tables with colspan/rowspan lose column alignment
- Excessive bold formatting on routine content (dollar amounts, item numbers)
- Inconsistent whitespace between sections
- Empty/malformed link syntax
- Wide financial tables (200+ char rows) unreadable in any viewport

The goal: markdown that reads cleanly for humans and parses reliably for agents (RAG retrieval, structured extraction, diff comparison).

---

## Approach: Hybrid (Structural Fixes + Polish Pass)

Two categories of change:

1. **Structural fixes** in existing pipeline stages (md_render.py) for issues where information is lost during HTML-to-markdown conversion. These can't be fixed after the fact.

2. **Polish pass** as a new `md_polish.py` module that runs after md_render and before sectionize. Handles cosmetic cleanup on the raw markdown. Idempotent, testable, on by default.

```
HTML → ixbrl_strip → html_clean → semantic_html → md_render* → md_polish (NEW) → sectionize
                                                       ↑
                                              structural fixes here
```

---

## Part 1: Structural Fixes (md_render.py)

### 1a. Recursive Nested List Support

**Current behavior**: Regex extracts flat `<li>` items. Nested `<ul>`/`<ol>` inside `<li>` gets flattened into sibling items.

**Fix**: Replace `_process_lists()` with a recursive implementation that detects `<ul>`/`<ol>` inside `<li>` and renders with 2-space indentation per nesting level.

**Before**:
```markdown
- Risk Category A
Sub-risk 1
- Sub-risk 2
Risk Category B
```

**After**:
```markdown
- Risk Category A
  - Sub-risk 1
  - Sub-risk 2
- Risk Category B
```

**Implementation**: Parse list items iteratively, tracking depth. When an `<li>` contains a nested `<ul>`/`<ol>`, recurse and indent output by `depth * 2` spaces. Cap nesting at 4 levels (SEC filings rarely go deeper).

### 1b. Colspan/Rowspan Expansion

**Current behavior**: `_process_tables()` ignores colspan and rowspan attributes. Tables with merged cells produce misaligned columns.

**Fix**: When building the table grid from HTML rows:
- `colspan=N`: Duplicate the cell content into N adjacent columns (or use empty cells with a note)
- `rowspan=N`: Carry the cell value down into the next N-1 rows

This preserves the rectangular grid structure that GFM tables require.

**Implementation**: First pass builds a 2D grid accounting for spans. Second pass renders the grid as a pipe table. html_clean.py already preserves colspan/rowspan attributes.

### 1c. Empty/Malformed Link Cleanup

**Current behavior**: `<a href="">text</a>` produces `[text]()` (invalid markdown). `<a href="url"> </a>` produces `[](url)`.

**Fix**:
- If href is empty, `javascript:`, or `#` only: unwrap to plain text
- If link text is empty/whitespace: drop the link entirely
- Apply during link rendering, not as post-processing

### 1d. Inline Spacing Preservation

**Current behavior**: `.strip()` inside bold/italic lambda handlers can remove word-boundary spaces, producing `word**bold**word`.

**Fix**: After applying formatting markers, ensure there's a space between the marker and adjacent word characters. Check the character before/after the `**`/`*` markers.

---

## Part 2: Polish Pass (md_polish.py)

New file: `edgarpack/parse/md_polish.py`

Single entry point: `polish(md: str) -> str`

Each rule is a standalone function `_rule_name(md: str) -> str`. The `polish()` function chains them in order. All rules are idempotent.

### 2a. TOC Page-Break Spam Removal

**Rule**: Keep the first `Table of Contents` or `INDEX` heading. Remove all subsequent headings whose normalized text matches (case-insensitive, ignoring leading `*` or whitespace).

**Pattern**: `r'^#{1,6}\s+\*{0,2}\s*(?:Table of Contents|INDEX)\s*\*{0,2}\s*$'` (multiline)

**Behavior**: First match preserved. All subsequent matches deleted (including the blank lines around them).

### 2b. Whitespace Normalization

**Rules**:
- Collapse 3+ consecutive blank lines to exactly 1 blank line
- Exactly 1 blank line before any heading
- No trailing whitespace on any line (except intentional 2-space line breaks)
- Strip leading/trailing blank lines from the document

This runs last in the chain (after other rules may have created whitespace gaps).

### 2c. Bold De-noising

**Rules** (applied in order):
1. **All-bold paragraphs**: If a paragraph (text between blank lines) consists entirely of bold text (the whole thing is wrapped in `**...**`), strip the markers. If everything is emphasized, nothing is.
2. **Bold dollar amounts**: `**$1,234**` or `**(1,234)**` (parenthetical negatives) in running text: strip bold. Dollar amounts don't need emphasis.
3. **Bold standalone numbers**: `**42,000**` or `**12.5%**` in table cells or running text: strip bold.

**Preserve bold on**: Partial emphasis within a sentence, defined terms, headings, genuinely emphatic phrases. When in doubt, keep the bold.

### 2d. Bullet-Table Recovery

**Detection**: A table where one column consists entirely of bullet characters (`\u2022`, `\u25cb`, `\u25aa`, `\u25e6`, `*`, `-`) or is empty, and another column contains the actual content.

**Conversion**: Replace the table with a markdown unordered list. Each row becomes a `- content` item. Nested bullets (identified by indentation in the content column) get 2-space indentation.

### 2e. Empty-Column Table Simplification

**Rule**: For each table, identify columns where every cell (including header) is empty or whitespace-only. Remove those columns. If the table collapses to 0-1 meaningful columns, convert to plain text (one line per row).

**Threshold**: A column is "empty" if all cells are blank, contain only whitespace, or contain only separator characters (dashes, pipes).

### 2f. Broken Anchor Cleanup

**Rule**: For links where the href is a fragment-only reference (`[text](#something)`), strip the link syntax and keep the plain text. Internal HTML anchors don't survive the conversion pipeline, so these links are always dead.

**Exception**: Preserve fragment links in the Table of Contents section (the first one we kept in 2a), since those might be used by downstream renderers that add their own anchors.

### 2g. Heading Level Normalization

**Rules**:
- Reserve `#` (h1) for the filing title (added by pack builder)
- PART headings: `##`
- ITEM headings: `###`
- Sub-headings within items: `####`
- Never skip levels (no jumping from `##` to `#####`)

**Implementation**: Scan all headings, compute the minimum level present, and shift all levels so the minimum maps to `##`. Then enforce sequential nesting: if a heading is more than 1 level deeper than the previous heading, clamp it.

**Note**: The `#` filing title is added by the pack builder *after* polish runs, so polish normalizes headings to start at `##` without needing to see the title. The sectionize step also runs after polish, so it receives consistently-leveled headings.

### 2h. Complex Table Simplification

**Classification**: A table is complex if:
- More than 6 columns, OR
- Any rendered row exceeds 120 characters, OR
- Header row contains multi-level groupings (detected by colspan in the structural fix stage, or by repeated empty header cells)

**Simple tables** (not complex): Left as standard GFM pipe tables, unchanged.

**Complex tables**: Converted to an indented block format:

```markdown
> **[Table Caption / First Header Row Text]**
>
> [Column Group 1] / [Column Group 2]
>
> [Row Label] .............. [Value 1] / [Value 2]
>   [Sub-row Label] ........ [Value 1] / [Value 2]
>     [Sub-sub-row] ........ [Value 1] / [Value 2]
> [Row Label] .............. [Value 1] / [Value 2]
```

**Conventions**:
- Wrapped in blockquote (`>`) to visually distinguish from prose
- First line bold = table title/caption
- Period-leaders (`.....`) connect row labels to values
- `/` separates values from different time periods
- 2-space indentation indicates row hierarchy (detected from leading whitespace or category groupings in the original table)
- Row labels left-aligned, values right-grouped

**Fallback**: If classification is uncertain or conversion would lose important structure, keep as GFM table.

---

## Part 3: Pipeline Integration

### Wiring (pack/build.py)

```python
# Current flow:
md = render_markdown(html)
sections = sectionize(md, form_type)

# New flow:
md = render_markdown(html)
md = polish(md)             # NEW
sections = sectionize(md, form_type)
```

Polish is always on. No flag.

### Filing Title

The pack builder adds a `#` heading at the top of `filing.full.md`:

```markdown
# NVIDIA Corp | 10-K | Filed 2025-02-26
```

This gives the document a clear identity and uses the `#` level that headings are normalized against.

### Parser Version Bump

The structural fixes in md_render.py change output for existing filings. Bump `PARSER_VERSION` so the manifest reflects the new output. Existing cached packs won't be confused with new ones.

### Determinism

All rules in md_polish.py are deterministic (no randomness, no external state, no LLM calls). Same input always produces same output. The pipeline's determinism guarantee is preserved.

---

## Part 4: Testing Strategy

### Unit Tests (per rule)

Each polish rule gets its own test function with:
- A minimal input that triggers the rule
- Expected output
- An input that should NOT be modified (to verify specificity)

Example:
```python
def test_toc_spam_removal():
    md = "##### Table of Contents\n\nContent\n\n##### Table of Contents\n\nMore content"
    result = _strip_toc_spam(md)
    assert result.count("Table of Contents") == 1
    assert "More content" in result
```

### Integration Tests

- Round-trip a known SEC filing (e.g., NVDA 10-K) through the full pipeline and snapshot the output. Compare against a golden file.
- Verify that sectionize still detects the same sections after polish runs (no section boundary regression).

### Regression Protection

- Run existing 301 test suite after structural fixes to catch breakage.
- Add `test_polish_idempotent()`: verify that `polish(polish(md)) == polish(md)` for a corpus sample.

---

## Files Changed

| File | Change Type | Description |
| --- | --- | --- |
| `edgarpack/parse/md_render.py` | Modified | Nested lists, colspan, empty links, inline spacing |
| `edgarpack/parse/md_polish.py` | New | 8 polish rules + entry point |
| `edgarpack/pack/build.py` | Modified | Wire polish() into pipeline |
| `tests/test_md_polish.py` | New | Unit tests for each polish rule |
| `tests/test_md_render.py` | Modified | Updated expectations for structural fixes |

---

## Out of Scope

- Changing the sectionize module (it receives cleaner input, no changes needed)
- Modifying query, diff, harvest, or index layers
- Changing pack directory structure
- Adding CLI flags for polish (it's always on)
- Image handling (SEC filings rarely have meaningful images)
- Subscript/superscript support (rare in filings, low impact)
