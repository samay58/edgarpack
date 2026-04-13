# Markdown Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clean up generated SEC filing markdown so it reads well for humans and parses reliably for agents.

**Architecture:** Two-part change: (1) structural fixes in the existing `md_render.py` for issues that lose information during HTML-to-markdown conversion (nested lists, colspan, links, spacing), and (2) a new `md_polish.py` post-processing pass with 8 cosmetic cleanup rules that runs after render and before sectionize. All changes are deterministic and idempotent.

**Tech Stack:** Python 3.11+, regex, pytest, no new dependencies.

**Spec:** `docs/superpowers/specs/2026-04-12-markdown-polish-design.md`

---

## File Map

| File | Action | Responsibility |
| --- | --- | --- |
| `edgarpack/parse/md_render.py` | Modify | Fix `_process_lists()`, `_process_tables()`, link rendering, inline spacing |
| `edgarpack/parse/md_polish.py` | Create | 8 polish rules + `polish()` entry point |
| `edgarpack/pack/build.py` | Modify | Wire `polish()` between `render_markdown()` and `sectionize()` |
| `edgarpack/config.py` | Modify | Bump `PARSER_VERSION` from `"0.1.0"` to `"0.2.0"` |
| `tests/test_md_render.py` | Modify | Add tests for structural fixes |
| `tests/test_md_polish.py` | Create | Unit tests for each polish rule + idempotency |

---

### Task 1: Recursive Nested List Support

**Files:**
- Modify: `edgarpack/parse/md_render.py:180-216`
- Modify: `tests/test_md_render.py`

- [ ] **Step 1: Write failing tests for nested lists**

Add to `tests/test_md_render.py` inside `TestRenderMarkdown`:

```python
def test_renders_nested_unordered_list(self) -> None:
    html = "<ul><li>A<ul><li>A1</li><li>A2</li></ul></li><li>B</li></ul>"
    md = render_markdown(html)
    self.assertIn("- A", md)
    self.assertIn("  - A1", md)
    self.assertIn("  - A2", md)
    self.assertIn("- B", md)

def test_renders_nested_ordered_list(self) -> None:
    html = "<ol><li>First<ol><li>Sub 1</li><li>Sub 2</li></ol></li><li>Second</li></ol>"
    md = render_markdown(html)
    self.assertIn("1. First", md)
    self.assertIn("  1. Sub 1", md)
    self.assertIn("  2. Sub 2", md)
    self.assertIn("2. Second", md)

def test_renders_deeply_nested_list(self) -> None:
    html = "<ul><li>L1<ul><li>L2<ul><li>L3</li></ul></li></ul></li></ul>"
    md = render_markdown(html)
    self.assertIn("- L1", md)
    self.assertIn("  - L2", md)
    self.assertIn("    - L3", md)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_md_render.py::TestRenderMarkdown::test_renders_nested_unordered_list tests/test_md_render.py::TestRenderMarkdown::test_renders_nested_ordered_list tests/test_md_render.py::TestRenderMarkdown::test_renders_deeply_nested_list -v`

Expected: FAIL (nested items not indented)

- [ ] **Step 3: Replace `_process_lists()` with recursive implementation**

Replace the `_process_lists` function in `edgarpack/parse/md_render.py` (lines 180-216) with:

```python
def _process_lists(html: str) -> str:
    """Process ul and ol lists, including nested lists."""

    def _render_list(match: re.Match, ordered: bool = False) -> str:
        content = match.group(1)
        return "\n\n" + _render_list_items(content, ordered=ordered, depth=0) + "\n\n"

    # Process outermost lists only; inner lists are handled recursively.
    # We iterate until no more top-level lists remain (nested lists may
    # create new top-level matches after their parent is processed).
    result = html
    prev = None
    while prev != result:
        prev = result
        result = re.sub(
            r"<ul[^>]*>(.*?)</ul>",
            lambda m: _render_list(m, ordered=False),
            result,
            count=1,
            flags=re.DOTALL | re.IGNORECASE,
        )
        result = re.sub(
            r"<ol[^>]*>(.*?)</ol>",
            lambda m: _render_list(m, ordered=True),
            result,
            count=1,
            flags=re.DOTALL | re.IGNORECASE,
        )
    return result


def _render_list_items(html: str, ordered: bool, depth: int) -> str:
    """Recursively render list items with proper indentation."""
    indent = "  " * depth
    lines: list[str] = []
    item_idx = 0

    for li_match in re.finditer(
        r"<li[^>]*>(.*?)</li>", html, re.DOTALL | re.IGNORECASE
    ):
        li_content = li_match.group(1)
        nested_parts: list[str] = []

        # Extract nested lists from the <li> content before processing inline
        def _extract_nested(m: re.Match) -> str:
            nested_parts.append(m.group(0))
            return ""

        li_text = re.sub(
            r"<(ul|ol)[^>]*>.*?</\1>",
            _extract_nested,
            li_content,
            flags=re.DOTALL | re.IGNORECASE,
        )

        li_text = _process_inline(li_text).strip()
        marker = f"{item_idx + 1}." if ordered else "-"
        lines.append(f"{indent}{marker} {li_text}")
        item_idx += 1

        # Render nested lists at depth + 1
        for nested_html in nested_parts:
            nested_ol = nested_html.strip().lower().startswith("<ol")
            inner_match = re.search(
                r"<(?:ul|ol)[^>]*>(.*?)</(?:ul|ol)>",
                nested_html,
                re.DOTALL | re.IGNORECASE,
            )
            if inner_match:
                nested_output = _render_list_items(
                    inner_match.group(1), ordered=nested_ol, depth=depth + 1
                )
                lines.append(nested_output)

    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_md_render.py -v`

Expected: ALL PASS (including the original `test_renders_lists`)

- [ ] **Step 5: Commit**

```bash
git add edgarpack/parse/md_render.py tests/test_md_render.py
git commit -m "fix(parse): support nested lists in markdown rendering

Replaces flat regex-based list extraction with recursive implementation
that properly indents nested <ul>/<ol> items. Handles up to arbitrary
nesting depth with 2-space indentation per level."
```

---

### Task 2: Colspan/Rowspan Table Expansion

**Files:**
- Modify: `edgarpack/parse/md_render.py:219-290`
- Modify: `tests/test_md_render.py`

- [ ] **Step 1: Write failing tests for colspan/rowspan**

Add to `tests/test_md_render.py` inside `TestRenderMarkdown`:

```python
def test_renders_table_with_colspan(self) -> None:
    html = (
        "<table>"
        "<tr><th colspan='2'>Merged Header</th><th>C</th></tr>"
        "<tr><td>A1</td><td>A2</td><td>A3</td></tr>"
        "</table>"
    )
    md = render_markdown(html)
    # The merged header should expand to fill 2 columns
    rows = [line for line in md.strip().split("\n") if line.startswith("|")]
    # Header row should have 3 pipe-separated cells
    header_cells = [c.strip() for c in rows[0].split("|") if c.strip()]
    self.assertEqual(len(header_cells), 3)
    # Data row should also have 3 cells
    data_cells = [c.strip() for c in rows[2].split("|") if c.strip()]
    self.assertEqual(len(data_cells), 3)

def test_renders_table_with_rowspan(self) -> None:
    html = (
        "<table>"
        "<tr><th>Category</th><th>Value</th></tr>"
        "<tr><td rowspan='2'>Assets</td><td>100</td></tr>"
        "<tr><td>200</td></tr>"
        "</table>"
    )
    md = render_markdown(html)
    rows = [line for line in md.strip().split("\n") if line.startswith("|")]
    # Both data rows should have 2 cells each
    for row in rows[2:]:
        cells = [c.strip() for c in row.split("|") if c.strip()]
        self.assertEqual(len(cells), 2)
    # "Assets" should appear in both rows
    self.assertEqual(md.count("Assets"), 2)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_md_render.py::TestRenderMarkdown::test_renders_table_with_colspan tests/test_md_render.py::TestRenderMarkdown::test_renders_table_with_rowspan -v`

Expected: FAIL (colspan/rowspan ignored, column counts wrong)

- [ ] **Step 3: Replace `_process_tables()` with grid-aware implementation**

Replace the `_process_tables` function in `edgarpack/parse/md_render.py` (lines 219-290) with:

```python
def _process_tables(html: str) -> str:
    """Process tables to GFM format with colspan/rowspan support."""

    def _parse_span_attr(tag: str, attr: str) -> int:
        m = re.search(rf'{attr}\s*=\s*["\']?(\d+)', tag, re.IGNORECASE)
        return int(m.group(1)) if m else 1

    def process_table(match: re.Match) -> str:
        content = match.group(1)

        # Build a 2D grid accounting for colspan/rowspan
        grid: list[list[str]] = []
        has_header = False

        for tr_match in re.finditer(
            r"<tr[^>]*>(.*?)</tr>", content, re.DOTALL | re.IGNORECASE
        ):
            tr_content = tr_match.group(1)
            row_idx = len(grid)
            grid.append([])

            # Collect cells (th or td) in order
            cells: list[tuple[str, str, bool]] = []  # (tag, content, is_header)
            for cell_match in re.finditer(
                r"<(th|td)([^>]*)>(.*?)</(?:th|td)>",
                tr_content,
                re.DOTALL | re.IGNORECASE,
            ):
                tag_name = cell_match.group(1).lower()
                tag_attrs = cell_match.group(2)
                cell_text = _strip_tags(cell_match.group(3)).strip()
                cells.append((tag_attrs, cell_text, tag_name == "th"))

            if not cells:
                continue

            is_header_row = any(is_h for _, _, is_h in cells)
            if is_header_row and not has_header:
                has_header = True

            # Place cells into grid, skipping occupied positions (from rowspan)
            col = 0
            for tag_attrs, cell_text, _ in cells:
                # Advance past columns occupied by previous rowspans
                while col < len(grid[row_idx]) and grid[row_idx][col] is not None:
                    col += 1

                colspan = _parse_span_attr(tag_attrs, "colspan")
                rowspan = _parse_span_attr(tag_attrs, "rowspan")

                # Ensure grid row is wide enough
                while len(grid[row_idx]) <= col + colspan - 1:
                    grid[row_idx].append(None)

                # Fill colspan cells
                grid[row_idx][col] = cell_text
                for c in range(1, colspan):
                    grid[row_idx][col + c] = ""

                # Fill rowspan cells in subsequent rows
                for r in range(1, rowspan):
                    target_row = row_idx + r
                    while len(grid) <= target_row:
                        grid.append([])
                    while len(grid[target_row]) <= col + colspan - 1:
                        grid[target_row].append(None)
                    for c in range(colspan):
                        grid[target_row][col + c] = cell_text if c == 0 else ""

                col += colspan

        if not grid:
            return ""

        # Replace None placeholders with empty strings
        max_cols = max(len(row) for row in grid) if grid else 0
        for row in grid:
            for i in range(len(row)):
                if row[i] is None:
                    row[i] = ""
            while len(row) < max_cols:
                row.append("")

        # Render as GFM table
        lines: list[str] = []
        header = grid[0] if grid else [""] * max_cols
        lines.append("| " + " | ".join(_escape_table_cell(c) for c in header) + " |")
        lines.append("| " + " | ".join("---" for _ in range(max_cols)) + " |")
        for row in grid[1:]:
            lines.append("| " + " | ".join(_escape_table_cell(c) for c in row) + " |")

        return "\n\n" + "\n".join(lines) + "\n\n"

    return re.sub(
        r"<table[^>]*>(.*?)</table>",
        process_table,
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_md_render.py -v`

Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add edgarpack/parse/md_render.py tests/test_md_render.py
git commit -m "fix(parse): handle colspan/rowspan in table rendering

Builds a 2D grid from HTML table cells, expanding colspan and rowspan
attributes so GFM tables maintain correct column alignment. Financial
tables with merged headers/categories now render with proper structure."
```

---

### Task 3: Empty/Malformed Link Cleanup

**Files:**
- Modify: `edgarpack/parse/md_render.py:74-80`
- Modify: `tests/test_md_render.py`

- [ ] **Step 1: Write failing tests for bad links**

Add to `tests/test_md_render.py` inside `TestRenderMarkdown`:

```python
def test_unwraps_empty_href_link(self) -> None:
    html = '<a href="">click here</a>'
    md = render_markdown(html)
    self.assertIn("click here", md)
    self.assertNotIn("[click here]()", md)

def test_drops_empty_text_link(self) -> None:
    html = '<a href="https://example.com">   </a>'
    md = render_markdown(html)
    self.assertNotIn("[](", md)
    self.assertNotIn("example.com", md)

def test_unwraps_javascript_link(self) -> None:
    html = '<a href="javascript:void(0)">click</a>'
    md = render_markdown(html)
    self.assertIn("click", md)
    self.assertNotIn("[click]", md)

def test_unwraps_bare_hash_link(self) -> None:
    html = '<a href="#">top</a>'
    md = render_markdown(html)
    self.assertIn("top", md)
    self.assertNotIn("[top](#)", md)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_md_render.py::TestRenderMarkdown::test_unwraps_empty_href_link tests/test_md_render.py::TestRenderMarkdown::test_drops_empty_text_link tests/test_md_render.py::TestRenderMarkdown::test_unwraps_javascript_link tests/test_md_render.py::TestRenderMarkdown::test_unwraps_bare_hash_link -v`

Expected: FAIL

- [ ] **Step 3: Fix link rendering in `render_markdown()` and `_process_inline()`**

Replace the link processing regex in `render_markdown()` (lines 75-80) with:

```python
# Process links
result = re.sub(
    r'<a[^>]*href=["\']([^"\']*)["\'][^>]*>(.*?)</a>',
    lambda m: _render_link(m.group(1), _strip_tags(m.group(2)).strip()),
    result,
    flags=re.DOTALL | re.IGNORECASE,
)
```

Replace the link processing regex in `_process_inline()` (lines 167-172) with:

```python
# Process links
result = re.sub(
    r'<a[^>]*href=["\']([^"\']*)["\'][^>]*>(.*?)</a>',
    lambda m: _render_link(m.group(1), _strip_tags(m.group(2)).strip()),
    result,
    flags=re.DOTALL | re.IGNORECASE,
)
```

Add the `_render_link` helper function after `_strip_tags()`:

```python
def _render_link(href: str, text: str) -> str:
    """Render a link, unwrapping invalid/empty ones to plain text."""
    href = href.strip()
    if not text or text.isspace():
        return ""
    if not href or href == "#" or href.lower().startswith("javascript:"):
        return text
    return f"[{text}]({href})"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_md_render.py -v`

Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add edgarpack/parse/md_render.py tests/test_md_render.py
git commit -m "fix(parse): unwrap empty/malformed links instead of rendering broken markdown

Links with empty href, javascript: href, or bare # are unwrapped to
plain text. Links with empty/whitespace text are dropped entirely."
```

---

### Task 4: Inline Spacing Preservation

**Files:**
- Modify: `edgarpack/parse/md_render.py:82-96`
- Modify: `tests/test_md_render.py`

- [ ] **Step 1: Write failing test for spacing**

Add to `tests/test_md_render.py` inside `TestRenderMarkdown`:

```python
def test_preserves_space_around_bold(self) -> None:
    html = "<p>the <strong>bold</strong> word</p>"
    md = render_markdown(html)
    self.assertIn("the **bold** word", md)
    self.assertNotIn("the**bold**word", md)

def test_preserves_space_around_italic(self) -> None:
    html = "<p>the <em>italic</em> word</p>"
    md = render_markdown(html)
    self.assertIn("the *italic* word", md)
    self.assertNotIn("the*italic*word", md)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_md_render.py::TestRenderMarkdown::test_preserves_space_around_bold tests/test_md_render.py::TestRenderMarkdown::test_preserves_space_around_italic -v`

Expected: May pass or fail depending on how the space injector at line 32 interacts with the strip. Run to determine current behavior.

- [ ] **Step 3: Fix inline formatting to preserve boundary spaces**

In `render_markdown()`, replace the strong/bold processing (lines 83-88) with:

```python
# Process strong/bold
def _render_strong(m: re.Match) -> str:
    inner = _process_inline(m.group(1)).strip()
    if not inner:
        return ""
    return f"**{inner}**"

result = re.sub(
    r"<(?:strong|b)[^>]*>(.*?)</(?:strong|b)>",
    _render_strong,
    result,
    flags=re.DOTALL | re.IGNORECASE,
)
```

Replace the emphasis/italic processing (lines 91-96) with:

```python
# Process emphasis/italic
def _render_em(m: re.Match) -> str:
    inner = _process_inline(m.group(1)).strip()
    if not inner:
        return ""
    return f"*{inner}*"

result = re.sub(
    r"<(?:em|i)[^>]*>(.*?)</(?:em|i)>",
    _render_em,
    result,
    flags=re.DOTALL | re.IGNORECASE,
)
```

The key fix is that the `> <` space injector at line 32 already prevents concatenation. The lambdas now also guard against empty content producing `****` or `**` markers.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_md_render.py -v`

Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add edgarpack/parse/md_render.py tests/test_md_render.py
git commit -m "fix(parse): preserve word-boundary spacing around bold/italic markers

Guard against empty bold/italic content producing bare markers.
Boundary spaces between tags and adjacent text are preserved by
the existing space injector."
```

---

### Task 5: Polish Pass - TOC Spam + Whitespace + Anchors

**Files:**
- Create: `edgarpack/parse/md_polish.py`
- Create: `tests/test_md_polish.py`

- [ ] **Step 1: Write failing tests for TOC spam, whitespace, and anchor cleanup**

Create `tests/test_md_polish.py`:

```python
"""Tests for markdown polish pass."""

import unittest

from edgarpack.parse.md_polish import polish, _strip_toc_spam, _normalize_whitespace, _strip_broken_anchors


class TestStripTocSpam(unittest.TestCase):
    def test_keeps_first_toc_heading(self) -> None:
        md = "##### Table of Contents\n\nContent here"
        result = _strip_toc_spam(md)
        self.assertIn("Table of Contents", result)

    def test_removes_subsequent_toc_headings(self) -> None:
        md = "##### Table of Contents\n\nContent\n\n##### Table of Contents\n\nMore"
        result = _strip_toc_spam(md)
        self.assertEqual(result.count("Table of Contents"), 1)
        self.assertIn("More", result)

    def test_removes_italic_wrapped_toc(self) -> None:
        md = "##### Table of Contents\n\nContent\n\n*##### Table of Contents*\n\nMore"
        result = _strip_toc_spam(md)
        self.assertEqual(result.count("Table of Contents"), 1)

    def test_removes_index_headings(self) -> None:
        md = "## INDEX\n\nContent\n\n## INDEX\n\nMore"
        result = _strip_toc_spam(md)
        self.assertEqual(result.count("INDEX"), 1)

    def test_no_toc_headings_unchanged(self) -> None:
        md = "## Business\n\nContent\n\n## Risk Factors\n\nMore"
        result = _strip_toc_spam(md)
        self.assertEqual(result, md)


class TestNormalizeWhitespace(unittest.TestCase):
    def test_collapses_triple_blank_lines(self) -> None:
        md = "Para 1\n\n\n\nPara 2"
        result = _normalize_whitespace(md)
        self.assertNotIn("\n\n\n", result)
        self.assertIn("\n\n", result)

    def test_blank_line_before_heading(self) -> None:
        md = "Some text\n## Heading"
        result = _normalize_whitespace(md)
        self.assertIn("\n\n## Heading", result)

    def test_strips_trailing_whitespace(self) -> None:
        md = "Line with trailing   \nNext line"
        result = _normalize_whitespace(md)
        # Should strip trailing spaces (not a 2-space intentional break here - 3 spaces)
        self.assertNotIn("   \n", result)

    def test_preserves_intentional_line_break(self) -> None:
        md = "Soft break  \nNext line"
        result = _normalize_whitespace(md)
        self.assertIn("  \n", result)

    def test_strips_leading_trailing_blank_lines(self) -> None:
        md = "\n\n\nContent\n\n\n"
        result = _normalize_whitespace(md)
        self.assertFalse(result.startswith("\n"))
        self.assertFalse(result.endswith("\n\n"))


class TestStripBrokenAnchors(unittest.TestCase):
    def test_strips_fragment_only_link(self) -> None:
        md = "See [Risk Factors](#toc890989_3) for details"
        result = _strip_broken_anchors(md)
        self.assertIn("See Risk Factors for details", result)
        self.assertNotIn("#toc", result)

    def test_preserves_full_url_links(self) -> None:
        md = "Visit [SEC](https://sec.gov) for filings"
        result = _strip_broken_anchors(md)
        self.assertIn("[SEC](https://sec.gov)", result)

    def test_preserves_toc_section_anchors(self) -> None:
        md = "##### Table of Contents\n\n[Item 1](#item1)\n[Item 2](#item2)\n\n## Item 1"
        result = _strip_broken_anchors(md)
        # Links within the TOC section should be preserved
        self.assertIn("[Item 1](#item1)", result)


class TestPolish(unittest.TestCase):
    def test_idempotent(self) -> None:
        md = "##### Table of Contents\n\nContent\n\n##### Table of Contents\n\nMore\n\n\n\n## Section"
        once = polish(md)
        twice = polish(once)
        self.assertEqual(once, twice)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_md_polish.py -v`

Expected: FAIL (module does not exist)

- [ ] **Step 3: Create `edgarpack/parse/md_polish.py` with first 3 rules**

Create `edgarpack/parse/md_polish.py`:

```python
"""Post-processing polish pass for generated markdown.

Runs after md_render and before sectionize. Each rule is a standalone
function (str -> str). All rules are idempotent and deterministic.
"""

import re


def polish(md: str) -> str:
    """Apply all polish rules in sequence."""
    md = _strip_toc_spam(md)
    md = _strip_broken_anchors(md)
    md = _normalize_whitespace(md)
    return md


def _strip_toc_spam(md: str) -> str:
    """Keep the first Table of Contents / INDEX heading, remove all repeats."""
    # Match headings like: ##### Table of Contents, *##### Table of Contents*,
    # ## INDEX (case-insensitive, with optional bold/italic wrapping)
    pattern = re.compile(
        r"^\*{0,2}#{1,6}\s+\*{0,2}\s*(?:Table of Contents|INDEX)\s*\*{0,2}\s*\*{0,2}\s*$",
        re.MULTILINE | re.IGNORECASE,
    )

    matches = list(pattern.finditer(md))
    if len(matches) <= 1:
        return md

    # Remove all matches after the first, including surrounding blank lines
    # Work backwards to preserve character positions
    result = md
    for m in reversed(matches[1:]):
        start = m.start()
        end = m.end()
        # Expand to consume surrounding blank lines
        while start > 0 and result[start - 1] == "\n":
            start -= 1
        while end < len(result) and result[end] == "\n":
            end += 1
        result = result[:start] + "\n" if start > 0 else "" + result[end:]

    return result


def _strip_broken_anchors(md: str) -> str:
    """Strip fragment-only links, preserving those in the TOC section."""
    lines = md.split("\n")
    in_toc = False
    past_toc = False
    result_lines: list[str] = []

    toc_heading = re.compile(
        r"^#{1,6}\s+(?:Table of Contents|INDEX)", re.IGNORECASE
    )
    any_heading = re.compile(r"^#{1,6}\s+")
    fragment_link = re.compile(r"\[([^\]]+)\]\(#[^)]+\)")

    for line in lines:
        if not past_toc and toc_heading.match(line):
            in_toc = True
            result_lines.append(line)
            continue

        if in_toc and any_heading.match(line) and not toc_heading.match(line):
            in_toc = False
            past_toc = True

        if in_toc:
            # Preserve fragment links inside TOC
            result_lines.append(line)
        else:
            # Strip fragment-only links outside TOC
            result_lines.append(fragment_link.sub(r"\1", line))

    return "\n".join(result_lines)


def _normalize_whitespace(md: str) -> str:
    """Normalize blank lines, trailing whitespace, and heading spacing."""
    # Normalize line endings
    md = md.replace("\r\n", "\n").replace("\r", "\n")

    # Collapse 3+ blank lines to 1 blank line
    md = re.sub(r"\n{3,}", "\n\n", md)

    # Ensure blank line before headings
    md = re.sub(r"([^\n])\n(#{1,6}\s)", r"\1\n\n\2", md)

    # Clean trailing whitespace per line (preserve 2-space intentional breaks)
    lines = md.split("\n")
    cleaned: list[str] = []
    for line in lines:
        stripped = line.rstrip()
        if line.rstrip(" ") != line and line.endswith("  ") and len(line) - len(line.rstrip()) == 2:
            # Exactly 2 trailing spaces = intentional line break
            cleaned.append(stripped + "  ")
        else:
            cleaned.append(stripped)

    md = "\n".join(cleaned)

    # Strip leading/trailing blank lines
    md = md.strip()

    return md
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_md_polish.py -v`

Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add edgarpack/parse/md_polish.py tests/test_md_polish.py
git commit -m "feat(parse): add md_polish pass with TOC spam, anchor, and whitespace rules

New post-processing module with three initial rules:
- Strip repeated Table of Contents / INDEX page-break headings
- Remove broken fragment-only links (except within TOC section)
- Normalize whitespace (collapse blanks, ensure heading spacing)"
```

---

### Task 6: Polish Pass - Bold De-noising

**Files:**
- Modify: `edgarpack/parse/md_polish.py`
- Modify: `tests/test_md_polish.py`

- [ ] **Step 1: Write failing tests for bold de-noising**

Add to `tests/test_md_polish.py`:

```python
from edgarpack.parse.md_polish import _strip_bold_noise


class TestStripBoldNoise(unittest.TestCase):
    def test_strips_all_bold_paragraph(self) -> None:
        md = "**This entire paragraph is bold and should not be.**"
        result = _strip_bold_noise(md)
        self.assertEqual(result, "This entire paragraph is bold and should not be.")

    def test_strips_bold_dollar_amount(self) -> None:
        md = "Revenue was **$1,234** million"
        result = _strip_bold_noise(md)
        self.assertIn("$1,234", result)
        self.assertNotIn("**$1,234**", result)

    def test_strips_bold_negative_parens(self) -> None:
        md = "Loss of **(1,234)**"
        result = _strip_bold_noise(md)
        self.assertIn("(1,234)", result)
        self.assertNotIn("**(1,234)**", result)

    def test_strips_bold_percentage(self) -> None:
        md = "Growth of **12.5%** year over year"
        result = _strip_bold_noise(md)
        self.assertNotIn("**12.5%**", result)

    def test_preserves_partial_bold_in_sentence(self) -> None:
        md = "The company **expanded operations** to new markets"
        result = _strip_bold_noise(md)
        self.assertIn("**expanded operations**", result)

    def test_strips_bold_standalone_number(self) -> None:
        md = "Total was **42,000** units"
        result = _strip_bold_noise(md)
        self.assertNotIn("**42,000**", result)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_md_polish.py::TestStripBoldNoise -v`

Expected: FAIL (function does not exist)

- [ ] **Step 3: Add `_strip_bold_noise()` to `md_polish.py`**

Add the function to `edgarpack/parse/md_polish.py` and wire it into `polish()`:

```python
def _strip_bold_noise(md: str) -> str:
    """Remove bold formatting from content where it adds no emphasis."""
    # Rule 1: All-bold paragraphs - if a paragraph is entirely wrapped in **...**,
    # the bold is decorative, not emphatic.
    md = re.sub(
        r"(?m)^(\*\*)((?:(?!\*\*).)+)\1$",
        r"\2",
        md,
    )

    # Rule 2: Bold dollar amounts like **$1,234** or **$1,234.56**
    md = re.sub(r"\*\*(\$[\d,]+(?:\.\d+)?)\*\*", r"\1", md)

    # Rule 3: Bold parenthetical negatives like **(1,234)** or **($1,234)**
    md = re.sub(r"\*\*(\(?\$?[\d,]+(?:\.\d+)?\)?)\*\*", r"\1", md)

    # Rule 4: Bold standalone numbers like **42,000** or **12.5%**
    md = re.sub(r"\*\*([\d,]+(?:\.\d+)?%?)\*\*", r"\1", md)

    return md
```

Update `polish()` to include the new rule (after `_strip_toc_spam`, before `_strip_broken_anchors`):

```python
def polish(md: str) -> str:
    """Apply all polish rules in sequence."""
    md = _strip_toc_spam(md)
    md = _strip_bold_noise(md)
    md = _strip_broken_anchors(md)
    md = _normalize_whitespace(md)
    return md
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_md_polish.py -v`

Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add edgarpack/parse/md_polish.py tests/test_md_polish.py
git commit -m "feat(parse): add bold de-noising rule to polish pass

Strips bold markers from all-bold paragraphs, dollar amounts,
parenthetical negatives, standalone numbers, and percentages.
Preserves partial emphasis within sentences."
```

---

### Task 7: Polish Pass - Bullet-Table Recovery + Empty-Column Simplification

**Files:**
- Modify: `edgarpack/parse/md_polish.py`
- Modify: `tests/test_md_polish.py`

- [ ] **Step 1: Write failing tests for bullet-table and empty-column rules**

Add to `tests/test_md_polish.py`:

```python
from edgarpack.parse.md_polish import _recover_bullet_tables, _simplify_empty_columns


class TestRecoverBulletTables(unittest.TestCase):
    def test_converts_bullet_table_to_list(self) -> None:
        md = (
            "| | \u2022 | | First item |\n"
            "| --- | --- | --- | --- |\n"
            "| | \u2022 | | Second item |\n"
        )
        result = _recover_bullet_tables(md)
        self.assertIn("- First item", result)
        self.assertIn("- Second item", result)
        self.assertNotIn("|", result)

    def test_ignores_normal_tables(self) -> None:
        md = (
            "| Name | Value |\n"
            "| --- | --- |\n"
            "| Alpha | 100 |\n"
        )
        result = _recover_bullet_tables(md)
        self.assertIn("|", result)
        self.assertIn("Alpha", result)

    def test_converts_dash_bullet_table(self) -> None:
        md = (
            "| - | Item one |\n"
            "| --- | --- |\n"
            "| - | Item two |\n"
        )
        result = _recover_bullet_tables(md)
        self.assertIn("- Item one", result)
        self.assertIn("- Item two", result)


class TestSimplifyEmptyColumns(unittest.TestCase):
    def test_removes_all_empty_columns(self) -> None:
        md = (
            "| | Name | | Value | |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| | Alpha | | 100 | |\n"
        )
        result = _simplify_empty_columns(md)
        lines = [l for l in result.strip().split("\n") if l.startswith("|")]
        # Should only have Name and Value columns
        for line in lines:
            if "---" in line:
                continue
            cells = [c.strip() for c in line.split("|") if c.strip()]
            self.assertLessEqual(len(cells), 2)

    def test_converts_single_column_to_text(self) -> None:
        md = (
            "| | Content here | |\n"
            "| --- | --- | --- |\n"
            "| | More content | |\n"
        )
        result = _simplify_empty_columns(md)
        self.assertIn("Content here", result)
        self.assertIn("More content", result)
        # Should not have pipe table structure
        self.assertNotIn("| --- |", result)

    def test_no_empty_columns_unchanged(self) -> None:
        md = (
            "| A | B |\n"
            "| --- | --- |\n"
            "| 1 | 2 |\n"
        )
        result = _simplify_empty_columns(md)
        self.assertEqual(result, md)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_md_polish.py::TestRecoverBulletTables tests/test_md_polish.py::TestSimplifyEmptyColumns -v`

Expected: FAIL

- [ ] **Step 3: Add both rules to `md_polish.py`**

Add to `edgarpack/parse/md_polish.py`:

```python
_BULLET_CHARS = {"\u2022", "\u25cb", "\u25aa", "\u25e6", "*", "-", "\u2023", "\u25b8"}


def _parse_md_table(text: str) -> tuple[list[list[str]], int, int] | None:
    """Parse a GFM markdown table into rows of cells. Returns (rows, start, end) or None."""
    lines = text.split("\n")
    table_lines: list[int] = []
    in_table = False

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            if not in_table:
                in_table = True
            table_lines.append(i)
        elif in_table:
            break

    if len(table_lines) < 2:
        return None

    rows: list[list[str]] = []
    for idx in table_lines:
        line = lines[idx]
        cells = [c.strip() for c in line.split("|")]
        # Split produces empty strings at start/end from leading/trailing pipes
        cells = cells[1:-1] if len(cells) >= 2 else cells
        rows.append(cells)

    return rows, table_lines[0], table_lines[-1]


def _recover_bullet_tables(md: str) -> str:
    """Convert tables that represent bullet lists back to markdown lists."""
    # Find all tables in the markdown
    table_pattern = re.compile(
        r"((?:^\|.*\|\s*$\n?)+)",
        re.MULTILINE,
    )

    def _try_recover(match: re.Match) -> str:
        table_text = match.group(1)
        lines = [l for l in table_text.strip().split("\n") if l.strip()]
        if len(lines) < 2:
            return table_text

        # Parse rows, skip separator
        data_rows: list[list[str]] = []
        for line in lines:
            cells = [c.strip() for c in line.split("|")]
            cells = cells[1:-1] if len(cells) >= 2 else cells
            # Skip separator rows
            if all(re.match(r"^-+$", c.strip()) for c in cells if c.strip()):
                continue
            data_rows.append(cells)

        if not data_rows:
            return table_text

        # Check if any column is a bullet column (all cells are bullet chars or empty)
        num_cols = max(len(r) for r in data_rows)
        bullet_col = -1
        content_col = -1

        for col_idx in range(num_cols):
            col_vals = [r[col_idx].strip() if col_idx < len(r) else "" for r in data_rows]
            non_empty = [v for v in col_vals if v]
            if non_empty and all(v in _BULLET_CHARS for v in non_empty):
                bullet_col = col_idx
                break

        if bullet_col == -1:
            return table_text

        # Find the content column (first non-empty, non-bullet column)
        for col_idx in range(num_cols):
            if col_idx == bullet_col:
                continue
            col_vals = [r[col_idx].strip() if col_idx < len(r) else "" for r in data_rows]
            if any(v for v in col_vals):
                content_col = col_idx
                break

        if content_col == -1:
            return table_text

        # Convert to list
        items: list[str] = []
        for row in data_rows:
            content = row[content_col].strip() if content_col < len(row) else ""
            if content:
                items.append(f"- {content}")

        return "\n".join(items) + "\n"

    return table_pattern.sub(_try_recover, md)


def _simplify_empty_columns(md: str) -> str:
    """Remove entirely empty columns from tables; collapse to text if <=1 column remains."""
    table_pattern = re.compile(
        r"((?:^\|.*\|\s*$\n?)+)",
        re.MULTILINE,
    )

    def _try_simplify(match: re.Match) -> str:
        table_text = match.group(1)
        lines = [l for l in table_text.strip().split("\n") if l.strip()]
        if len(lines) < 2:
            return table_text

        # Parse all rows
        all_rows: list[list[str]] = []
        separator_indices: list[int] = []
        for i, line in enumerate(lines):
            cells = [c.strip() for c in line.split("|")]
            cells = cells[1:-1] if len(cells) >= 2 else cells
            if all(re.match(r"^-+$", c.strip()) for c in cells if c.strip()):
                separator_indices.append(i)
            all_rows.append(cells)

        if not all_rows:
            return table_text

        num_cols = max(len(r) for r in all_rows)

        # Identify empty columns (all cells empty or whitespace, excluding separator)
        non_sep_rows = [r for i, r in enumerate(all_rows) if i not in separator_indices]
        empty_cols: set[int] = set()
        for col_idx in range(num_cols):
            col_vals = [r[col_idx].strip() if col_idx < len(r) else "" for r in non_sep_rows]
            if all(v == "" for v in col_vals):
                empty_cols.add(col_idx)

        if not empty_cols:
            return table_text

        # Filter out empty columns
        kept_cols = [i for i in range(num_cols) if i not in empty_cols]

        if len(kept_cols) <= 1:
            # Collapse to plain text
            text_lines: list[str] = []
            for i, row in enumerate(all_rows):
                if i in separator_indices:
                    continue
                content = " ".join(row[c].strip() for c in kept_cols if c < len(row)).strip()
                if content:
                    text_lines.append(content)
            return "\n".join(text_lines) + "\n"

        # Rebuild table with kept columns only
        rebuilt: list[str] = []
        for i, row in enumerate(all_rows):
            cells = [row[c] if c < len(row) else "" for c in kept_cols]
            if i in separator_indices:
                rebuilt.append("| " + " | ".join("---" for _ in kept_cols) + " |")
            else:
                rebuilt.append("| " + " | ".join(c for c in cells) + " |")

        return "\n".join(rebuilt) + "\n"

    return table_pattern.sub(_try_simplify, md)
```

Wire into `polish()`:

```python
def polish(md: str) -> str:
    """Apply all polish rules in sequence."""
    md = _strip_toc_spam(md)
    md = _strip_bold_noise(md)
    md = _recover_bullet_tables(md)
    md = _simplify_empty_columns(md)
    md = _strip_broken_anchors(md)
    md = _normalize_whitespace(md)
    return md
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_md_polish.py -v`

Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add edgarpack/parse/md_polish.py tests/test_md_polish.py
git commit -m "feat(parse): add bullet-table recovery and empty-column simplification

Two new polish rules:
- Detect tables with a bullet-character column and convert back to lists
- Remove columns where every cell is empty; collapse to text if <=1 col"
```

---

### Task 8: Polish Pass - Heading Normalization

**Files:**
- Modify: `edgarpack/parse/md_polish.py`
- Modify: `tests/test_md_polish.py`

- [ ] **Step 1: Write failing tests for heading normalization**

Add to `tests/test_md_polish.py`:

```python
from edgarpack.parse.md_polish import _normalize_headings


class TestNormalizeHeadings(unittest.TestCase):
    def test_shifts_h1_to_h2(self) -> None:
        md = "# PART I\n\nContent"
        result = _normalize_headings(md)
        self.assertIn("## PART I", result)
        self.assertNotIn("# PART I", result)

    def test_maintains_relative_levels(self) -> None:
        md = "# PART I\n\n## ITEM 1\n\n### Sub-section\n\nContent"
        result = _normalize_headings(md)
        self.assertIn("## PART I", result)
        self.assertIn("### ITEM 1", result)
        self.assertIn("#### Sub-section", result)

    def test_clamps_level_skips(self) -> None:
        md = "## PART I\n\n##### Deep heading\n\nContent"
        result = _normalize_headings(md)
        lines = result.split("\n")
        heading_lines = [l for l in lines if l.startswith("#")]
        # Second heading should be at most 1 level deeper than first
        first_level = len(heading_lines[0].split(" ")[0])
        second_level = len(heading_lines[1].split(" ")[0])
        self.assertLessEqual(second_level, first_level + 1)

    def test_already_normalized_unchanged(self) -> None:
        md = "## PART I\n\n### ITEM 1\n\n#### Details\n\nContent"
        result = _normalize_headings(md)
        self.assertEqual(result, md)

    def test_no_headings_unchanged(self) -> None:
        md = "Just some text\n\nMore text"
        result = _normalize_headings(md)
        self.assertEqual(result, md)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_md_polish.py::TestNormalizeHeadings -v`

Expected: FAIL

- [ ] **Step 3: Add `_normalize_headings()` to `md_polish.py`**

Add to `edgarpack/parse/md_polish.py`:

```python
def _normalize_headings(md: str) -> str:
    """Normalize heading levels: minimum becomes ##, no level skips."""
    heading_re = re.compile(r"^(#{1,6})\s+(.*)", re.MULTILINE)

    matches = list(heading_re.finditer(md))
    if not matches:
        return md

    # Find the minimum heading level in the document
    min_level = min(len(m.group(1)) for m in matches)

    # Target: minimum level should be 2 (##), reserving # for filing title
    shift = 2 - min_level

    if shift == 0:
        # Still need to check for level skips
        pass

    # Rebuild with shifted levels and no skips
    lines = md.split("\n")
    prev_level = 1  # virtual parent level (the # title added by pack builder)
    result_lines: list[str] = []

    for line in lines:
        m = heading_re.match(line)
        if m:
            raw_level = len(m.group(1))
            shifted = raw_level + shift
            # Clamp to valid range
            shifted = max(2, min(6, shifted))
            # No skipping: at most 1 deeper than previous heading
            if shifted > prev_level + 1:
                shifted = prev_level + 1
            shifted = min(shifted, 6)
            prev_level = shifted
            result_lines.append(f"{'#' * shifted} {m.group(2)}")
        else:
            result_lines.append(line)

    return "\n".join(result_lines)
```

Wire into `polish()` (after `_simplify_empty_columns`, before `_strip_broken_anchors`):

```python
def polish(md: str) -> str:
    """Apply all polish rules in sequence."""
    md = _strip_toc_spam(md)
    md = _strip_bold_noise(md)
    md = _recover_bullet_tables(md)
    md = _simplify_empty_columns(md)
    md = _normalize_headings(md)
    md = _strip_broken_anchors(md)
    md = _normalize_whitespace(md)
    return md
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_md_polish.py -v`

Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add edgarpack/parse/md_polish.py tests/test_md_polish.py
git commit -m "feat(parse): add heading level normalization to polish pass

Shifts minimum heading level to ## (reserving # for filing title).
Clamps level jumps so headings never skip more than 1 level deeper
than the previous heading."
```

---

### Task 9: Polish Pass - Complex Table Simplification

**Files:**
- Modify: `edgarpack/parse/md_polish.py`
- Modify: `tests/test_md_polish.py`

- [ ] **Step 1: Write failing tests for complex table simplification**

Add to `tests/test_md_polish.py`:

```python
from edgarpack.parse.md_polish import _simplify_complex_tables


class TestSimplifyComplexTables(unittest.TestCase):
    def test_leaves_simple_table_alone(self) -> None:
        md = (
            "| Metric | Q1 | Q2 |\n"
            "| --- | --- | --- |\n"
            "| Revenue | 100 | 200 |\n"
        )
        result = _simplify_complex_tables(md)
        self.assertIn("| Metric |", result)

    def test_converts_wide_table_to_block(self) -> None:
        # 8 columns = complex
        header = "| Category | Sub | 2025 Q1 | 2025 Q2 | 2024 Q1 | 2024 Q2 | 2023 Q1 | 2023 Q2 |"
        sep = "| --- | --- | --- | --- | --- | --- | --- | --- |"
        row1 = "| Revenue | Product | 100 | 200 | 80 | 150 | 60 | 120 |"
        md = f"{header}\n{sep}\n{row1}\n"
        result = _simplify_complex_tables(md)
        # Should be converted to blockquote format
        self.assertIn(">", result)
        self.assertNotIn("| --- |", result)

    def test_converts_long_row_table_to_block(self) -> None:
        # Fewer columns but content makes rows > 120 chars
        header = "| Description | Amount | Notes |"
        sep = "| --- | --- | --- |"
        long_row = "| " + "A" * 50 + " | " + "B" * 50 + " | " + "C" * 50 + " |"
        md = f"{header}\n{sep}\n{long_row}\n"
        result = _simplify_complex_tables(md)
        self.assertIn(">", result)

    def test_preserves_content_in_block_format(self) -> None:
        header = "| A | B | C | D | E | F | G |"
        sep = "| --- | --- | --- | --- | --- | --- | --- |"
        row = "| Revenue | 100 | 200 | 300 | 400 | 500 | 600 |"
        md = f"{header}\n{sep}\n{row}\n"
        result = _simplify_complex_tables(md)
        self.assertIn("Revenue", result)
        self.assertIn("100", result)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_md_polish.py::TestSimplifyComplexTables -v`

Expected: FAIL

- [ ] **Step 3: Add `_simplify_complex_tables()` to `md_polish.py`**

Add to `edgarpack/parse/md_polish.py`:

```python
_MAX_SIMPLE_COLS = 6
_MAX_ROW_WIDTH = 120


def _simplify_complex_tables(md: str) -> str:
    """Convert wide/complex GFM tables to indented blockquote format."""
    table_pattern = re.compile(
        r"((?:^\|.*\|\s*$\n?)+)",
        re.MULTILINE,
    )

    def _try_simplify(match: re.Match) -> str:
        table_text = match.group(1)
        lines = [l for l in table_text.strip().split("\n") if l.strip()]
        if len(lines) < 2:
            return table_text

        # Parse rows
        parsed_rows: list[list[str]] = []
        sep_idx: int | None = None
        for i, line in enumerate(lines):
            cells = [c.strip() for c in line.split("|")]
            cells = cells[1:-1] if len(cells) >= 2 else cells
            if all(re.match(r"^-+$", c.strip()) for c in cells if c.strip()):
                sep_idx = i
                continue
            parsed_rows.append(cells)

        if not parsed_rows:
            return table_text

        num_cols = max(len(r) for r in parsed_rows)
        max_row_len = max(len(l) for l in lines)

        # Check if this table is complex
        is_complex = num_cols > _MAX_SIMPLE_COLS or max_row_len > _MAX_ROW_WIDTH

        if not is_complex:
            return table_text

        # Convert to blockquote format
        header_row = parsed_rows[0] if parsed_rows else []
        data_rows = parsed_rows[1:] if len(parsed_rows) > 1 else parsed_rows

        output: list[str] = []

        # Caption from header: join non-empty header cells
        caption_parts = [c for c in header_row if c]
        if caption_parts:
            # Use first non-empty header cell as caption if it looks like a label
            # Otherwise join all headers as column identifiers
            if len(caption_parts) <= 3:
                output.append(f"> **{' / '.join(caption_parts)}**")
            else:
                # Multiple column headers: show as period header line
                output.append(f"> **{caption_parts[0]}**")
                output.append(">")
                output.append("> " + " / ".join(caption_parts[1:]))
            output.append(">")

        # Data rows: first cell is label, rest are values separated by /
        for row in data_rows:
            padded = row + [""] * (num_cols - len(row))
            label = padded[0] if padded else ""
            values = [v for v in padded[1:] if v]

            if not label and not values:
                continue

            if label and values:
                # Determine indentation from leading whitespace in label
                stripped_label = label.lstrip()
                indent_spaces = len(label) - len(stripped_label)
                indent = "  " * min(indent_spaces // 2, 3) if indent_spaces else ""

                value_str = " / ".join(values)
                # Calculate dot-leader length
                leader_target = max(40 - len(indent) - len(stripped_label), 3)
                leader = "." * leader_target
                output.append(f"> {indent}{stripped_label} {leader} {value_str}")
            elif label:
                output.append(f"> {label}")
            else:
                output.append(f"> {' / '.join(values)}")

        return "\n".join(output) + "\n"

    return table_pattern.sub(_try_simplify, md)
```

Wire into `polish()` (after `_simplify_empty_columns`, before `_normalize_headings`):

```python
def polish(md: str) -> str:
    """Apply all polish rules in sequence."""
    md = _strip_toc_spam(md)
    md = _strip_bold_noise(md)
    md = _recover_bullet_tables(md)
    md = _simplify_empty_columns(md)
    md = _simplify_complex_tables(md)
    md = _normalize_headings(md)
    md = _strip_broken_anchors(md)
    md = _normalize_whitespace(md)
    return md
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_md_polish.py -v`

Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add edgarpack/parse/md_polish.py tests/test_md_polish.py
git commit -m "feat(parse): add complex table simplification to polish pass

Tables with >6 columns or >120-char rows are converted to an indented
blockquote format with dot-leaders connecting labels to values. Simple
tables are left as standard GFM pipe tables."
```

---

### Task 10: Wire Polish Into Pipeline + Version Bump

**Files:**
- Modify: `edgarpack/pack/build.py:46-52`
- Modify: `edgarpack/config.py:18`

- [ ] **Step 1: Add `polish` import and call in `build.py`**

In `edgarpack/pack/build.py`, add the import (after the existing parse imports around line 14):

```python
from ..parse.md_polish import polish
```

In the `_process_html_files` function (line 46-52), add the polish call after `render_markdown`:

```python
def _process_html_files(html_files: list[tuple[str, bytes]], base_url: str) -> str:
    """Run the parse pipeline and return a single markdown string."""
    combined_html = "\n".join(_decode_html_blob(content) for _, content in html_files)
    html_stripped = strip_ixbrl(combined_html)
    html_cleaned = clean_html(html_stripped)
    html_semantic = reduce_to_semantic(html_cleaned, base_url=base_url)
    md = render_markdown(html_semantic)
    return polish(md)
```

- [ ] **Step 2b: Add filing title to `build_pack()`**

In `build_pack()`, after the markdown is generated and before it's written (between the current steps 4 and 5, around line 137-140), prepend the filing title:

```python
    # Step 4: Process HTML to markdown
    base_url = f"{SEC_ARCHIVES_BASE}/{meta.cik}/{meta.accession_nodash}/"
    markdown = _process_html_files(html_files, base_url=base_url)

    # Step 4b: Prepend filing title
    filing_title = f"# {meta.company_name} | {meta.form_type} | Filed {meta.filing_date.isoformat()}"
    markdown = f"{filing_title}\n\n{markdown}"
```

- [ ] **Step 2: Bump `PARSER_VERSION` in `config.py`**

In `edgarpack/config.py`, change line 18:

```python
PARSER_VERSION = "0.2.0"
```

- [ ] **Step 3: Run existing test suite to check for regressions**

Run: `.venv/bin/python -m pytest tests/ -x -v`

Expected: ALL PASS. If any test fails, inspect whether it's a test that asserts on exact markdown output (it may need updating to reflect the polished output). Fix test expectations, not the polish rules.

- [ ] **Step 4: Commit**

```bash
git add edgarpack/pack/build.py edgarpack/config.py
git commit -m "feat(pack): wire polish pass into build pipeline, bump parser to 0.2.0

The polish() function now runs after render_markdown() and before
sectionize() in _process_html_files(). Parser version bumped from
0.1.0 to 0.2.0 to reflect changed output for existing filings."
```

---

### Task 11: Integration Tests + Idempotency

**Files:**
- Modify: `tests/test_md_polish.py`

- [ ] **Step 1: Add integration and idempotency tests**

Add to `tests/test_md_polish.py`:

```python
class TestPolishIntegration(unittest.TestCase):
    def test_idempotent_on_realistic_input(self) -> None:
        """polish(polish(md)) == polish(md) for realistic SEC content."""
        md = (
            "##### Table of Contents\n\n"
            "[Item 1](#item1)\n\n"
            "##### Table of Contents\n\n"
            "# PART I\n\n"
            "## ITEM 1. BUSINESS\n\n"
            "**$1,234** million in revenue.\n\n"
            "See [Risk Factors](#toc123) for details.\n\n"
            "| | \u2022 | | Risk one |\n"
            "| --- | --- | --- | --- |\n"
            "| | \u2022 | | Risk two |\n\n"
            "| | Name | | Value | |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| | Alpha | | 100 | |\n\n"
            "##### Table of Contents\n\n"
            "## ITEM 1A. RISK FACTORS\n\n"
            "**This entire paragraph is bold and should not be.**\n\n"
            "\n\n\n\n"
            "More content here.\n"
        )
        once = polish(md)
        twice = polish(once)
        self.assertEqual(once, twice)

    def test_all_rules_applied(self) -> None:
        """Verify each rule fires on combined realistic input."""
        md = (
            "##### Table of Contents\n\n"
            "##### Table of Contents\n\n"
            "# PART I\n\n"
            "**$500** revenue\n\n"
            "See [details](#anchor123)\n\n"
            "| | \u2022 | | Item A |\n"
            "| --- | --- | --- | --- |\n\n"
            "| | Data | |\n"
            "| --- | --- | --- |\n\n"
            "\n\n\n\n"
        )
        result = polish(md)
        # TOC spam removed
        self.assertEqual(result.count("Table of Contents"), 1)
        # Bold stripped from dollar amount
        self.assertNotIn("**$500**", result)
        self.assertIn("$500", result)
        # Anchor stripped
        self.assertNotIn("#anchor123", result)
        self.assertIn("details", result)
        # Bullet table recovered
        self.assertIn("- Item A", result)
        # Whitespace normalized (no triple blank lines)
        self.assertNotIn("\n\n\n", result)
        # Heading shifted to ##
        self.assertIn("## PART I", result)
        self.assertNotIn("# PART I", result)

    def test_preserves_normal_content(self) -> None:
        """Clean markdown should pass through unchanged (except heading shift)."""
        md = (
            "## Section Title\n\n"
            "Normal paragraph with **emphasis** on a word.\n\n"
            "| Name | Value |\n"
            "| --- | --- |\n"
            "| Alpha | 100 |\n\n"
            "- List item one\n"
            "- List item two\n"
        )
        result = polish(md)
        self.assertIn("**emphasis**", result)
        self.assertIn("| Name | Value |", result)
        self.assertIn("- List item one", result)
```

- [ ] **Step 2: Run all tests**

Run: `.venv/bin/python -m pytest tests/test_md_polish.py tests/test_md_render.py -v`

Expected: ALL PASS

- [ ] **Step 3: Run full test suite for final regression check**

Run: `.venv/bin/python -m pytest tests/ -x -v`

Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_md_polish.py
git commit -m "test(parse): add integration and idempotency tests for polish pass

Tests verify all rules fire on combined input, idempotency holds,
and clean content passes through without corruption."
```

---

## Summary

| Task | Description | Estimated Steps |
| --- | --- | --- |
| 1 | Recursive nested lists | 5 |
| 2 | Colspan/rowspan table expansion | 5 |
| 3 | Empty/malformed link cleanup | 5 |
| 4 | Inline spacing preservation | 5 |
| 5 | Polish: TOC spam + whitespace + anchors | 5 |
| 6 | Polish: Bold de-noising | 5 |
| 7 | Polish: Bullet-table + empty-column | 5 |
| 8 | Polish: Heading normalization | 5 |
| 9 | Polish: Complex table simplification | 5 |
| 10 | Wire into pipeline + version bump | 4 |
| 11 | Integration + idempotency tests | 4 |
| **Total** | | **53 steps** |
