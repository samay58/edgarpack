"""Render semantic HTML to CommonMark markdown."""

import re
from html import unescape


def render_markdown(html: str) -> str:
    """Convert semantic HTML to CommonMark markdown.

    Args:
        html: Semantic HTML (should be pre-processed by semantic_html.py)

    Returns:
        CommonMark-compliant markdown string
    """
    # Order matters. We render block structures first (tables/headings/pre/lists),
    # then inline tags (links/strong/em/code), then paragraphs and remaining tags.
    # Reordering these passes can re-wrap table content or collapse section text.
    #
    # SEC filings often use dense block tags (<div>, <tr>, etc.) with no spacing.
    # Before stripping unknown tags we insert minimal separators to avoid text joins.

    result = html

    # First, extract body content if present
    body_match = re.search(r"<body[^>]*>(.*?)</body>", result, re.DOTALL | re.IGNORECASE)
    if body_match:
        result = body_match.group(1)

    # Prevent word concatenation when tags are later stripped.
    # (Use space, not newline, to avoid injecting hard line breaks in inline contexts.)
    result = re.sub(r">\s*<", "> <", result)

    # Process tables first (complex structure)
    result = _process_tables(result)

    # Process headings
    for level in range(1, 7):
        pattern = rf"<h{level}[^>]*>(.*?)</h{level}>"
        result = re.sub(
            pattern,
            lambda m: f"\n\n{'#' * level} {_strip_tags(m.group(1)).strip()}\n\n",
            result,
            flags=re.DOTALL | re.IGNORECASE,
        )

    # Process code blocks (pre) before inline code
    result = re.sub(
        r"<pre[^>]*>(.*?)</pre>",
        lambda m: f"\n\n```\n{unescape(_strip_tags(m.group(1)))}\n```\n\n",
        result,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # Process inline code
    result = re.sub(
        r"<code[^>]*>(.*?)</code>",
        lambda m: f"`{_strip_tags(m.group(1)).strip()}`",
        result,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # Process blockquotes
    result = re.sub(
        r"<blockquote[^>]*>(.*?)</blockquote>",
        lambda m: _format_blockquote(_strip_tags(m.group(1)).strip()),
        result,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # Process lists
    result = _process_lists(result)

    # Process links
    result = re.sub(
        r'<a[^>]*href=["\']([^"\']*)["\'][^>]*>(.*?)</a>',
        lambda m: f"[{_strip_tags(m.group(2)).strip()}]({m.group(1)})",
        result,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # Process strong/bold
    result = re.sub(
        r"<(?:strong|b)[^>]*>(.*?)</(?:strong|b)>",
        lambda m: f"**{_process_inline(m.group(1)).strip()}**",
        result,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # Process emphasis/italic
    result = re.sub(
        r"<(?:em|i)[^>]*>(.*?)</(?:em|i)>",
        lambda m: f"*{_process_inline(m.group(1)).strip()}*",
        result,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # Process paragraphs
    result = re.sub(
        r"<p[^>]*>(.*?)</p>",
        lambda m: f"\n\n{_process_inline(m.group(1)).strip()}\n\n",
        result,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # Process line breaks
    result = re.sub(r"<br\s*/?>", "  \n", result, flags=re.IGNORECASE)

    # Process horizontal rules
    result = re.sub(r"<hr\s*/?>", "\n\n---\n\n", result, flags=re.IGNORECASE)

    # Add separators for common block-level tags that we don't explicitly render.
    # This helps preserve paragraph/section boundaries before we strip remaining tags.
    result = re.sub(
        r"</(?:div|section|article|main|header|footer|nav|tr|td|th|tbody|thead|tfoot|dl|dt|dd)\s*>",
        "\n",
        result,
        flags=re.IGNORECASE,
    )

    # Strip remaining tags (divs, spans, etc.)
    result = re.sub(r"<[^>]+>", "", result)

    # Unescape HTML entities
    result = unescape(result)

    # Normalize output
    result = _normalize_output(result)

    return result


def _strip_tags(html: str) -> str:
    """Remove all HTML tags, keeping text content."""
    return re.sub(r"<[^>]+>", "", html)


def _process_inline(html: str) -> str:
    """Process inline elements within text."""
    result = html

    # Process nested strong
    result = re.sub(
        r"<(?:strong|b)[^>]*>(.*?)</(?:strong|b)>",
        lambda m: f"**{m.group(1).strip()}**",
        result,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # Process nested emphasis
    result = re.sub(
        r"<(?:em|i)[^>]*>(.*?)</(?:em|i)>",
        lambda m: f"*{m.group(1).strip()}*",
        result,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # Process nested code
    result = re.sub(
        r"<code[^>]*>(.*?)</code>",
        lambda m: f"`{m.group(1).strip()}`",
        result,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # Process links
    result = re.sub(
        r'<a[^>]*href=["\']([^"\']*)["\'][^>]*>(.*?)</a>',
        lambda m: f"[{_strip_tags(m.group(2)).strip()}]({m.group(1)})",
        result,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # Strip remaining tags
    result = re.sub(r"<[^>]+>", "", result)

    return result


def _process_lists(html: str) -> str:
    """Process ul and ol lists, including nested lists."""

    # Process innermost lists first (no nested <ul>/<ol> inside them),
    # then work outward.  Each pass converts one layer of list tags into
    # indented markdown lines, shrinking the depth until no list tags remain.
    result = html
    prev = None
    while prev != result:
        prev = result
        result = re.sub(
            r"<ul[^>]*>((?:(?!<ul|<ol).)*?)</ul>",
            lambda m: _render_list_items(m.group(1), ordered=False, depth=0),
            result,
            flags=re.DOTALL | re.IGNORECASE,
        )
        result = re.sub(
            r"<ol[^>]*>((?:(?!<ul|<ol).)*?)</ol>",
            lambda m: _render_list_items(m.group(1), ordered=True, depth=0),
            result,
            flags=re.DOTALL | re.IGNORECASE,
        )
    return result


def _render_list_items(html: str, ordered: bool, depth: int) -> str:
    """Render a flat list of <li> items at the given indentation depth.

    When called bottom-up by _process_lists, nested lists have already been
    converted to indented lines and are embedded as plain text inside the
    <li> content, so no recursive descent is needed here.
    """
    indent = "  " * depth
    lines: list[str] = []
    item_idx = 0

    for li_match in re.finditer(
        r"<li[^>]*>(.*?)</li>", html, re.DOTALL | re.IGNORECASE
    ):
        li_content = li_match.group(1)
        li_text = _process_inline(li_content).strip()
        marker = f"{item_idx + 1}." if ordered else "-"

        # Split on embedded newlines so already-rendered nested lines get
        # the right indentation prefix.
        sub_lines = li_text.splitlines()
        if sub_lines:
            lines.append(f"{indent}{marker} {sub_lines[0]}")
            for sub in sub_lines[1:]:
                if sub.strip():
                    lines.append(f"{indent}  {sub}")
        else:
            lines.append(f"{indent}{marker} ")
        item_idx += 1

    return "\n\n" + "\n".join(lines) + "\n\n" if lines else ""


def _process_tables(html: str) -> str:
    """Process tables to GFM format with colspan/rowspan support."""

    def _parse_span_attr(tag: str, attr: str) -> int:
        m = re.search(rf'{attr}\s*=\s*["\']?(\d+)', tag, re.IGNORECASE)
        return int(m.group(1)) if m else 1

    def process_table(match: re.Match) -> str:
        content = match.group(1)

        # Build a 2D grid accounting for colspan/rowspan
        grid: list[list[str]] = []

        row_idx = -1
        for tr_match in re.finditer(
            r"<tr[^>]*>(.*?)</tr>", content, re.DOTALL | re.IGNORECASE
        ):
            tr_content = tr_match.group(1)
            row_idx += 1
            # Rowspan pre-fill may have already created this row; only append if needed
            while len(grid) <= row_idx:
                grid.append([])

            # Collect cells (th or td) in document order
            cells: list[tuple[str, str]] = []  # (tag_attrs, text)
            for cell_match in re.finditer(
                r"<(th|td)([^>]*)>(.*?)</(?:th|td)>",
                tr_content,
                re.DOTALL | re.IGNORECASE,
            ):
                tag_attrs = cell_match.group(2)
                cell_text = _strip_tags(cell_match.group(3)).strip()
                cells.append((tag_attrs, cell_text))

            if not cells:
                continue

            # Place cells into grid, skipping occupied positions (from rowspan)
            col = 0
            for tag_attrs, cell_text in cells:
                # Advance past columns occupied by previous rowspans
                while col < len(grid[row_idx]) and grid[row_idx][col] is not None:
                    col += 1

                colspan = _parse_span_attr(tag_attrs, "colspan")
                rowspan = _parse_span_attr(tag_attrs, "rowspan")

                # Ensure grid row is wide enough
                while len(grid[row_idx]) <= col + colspan - 1:
                    grid[row_idx].append(None)

                # Fill colspan cells (repeat text so expanded columns are non-empty)
                grid[row_idx][col] = cell_text
                for c in range(1, colspan):
                    grid[row_idx][col + c] = cell_text

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

        # Replace None placeholders with empty strings and pad rows
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


def _format_blockquote(text: str) -> str:
    """Format text as a blockquote."""
    lines = text.strip().split("\n")
    quoted = "\n".join(f"> {line}" for line in lines)
    return f"\n\n{quoted}\n\n"


def _escape_table_cell(text: str) -> str:
    """Escape text for use in a table cell."""
    text = text.replace("|", "\\|")
    text = text.replace("\n", " ")
    return text.strip()


def _normalize_output(md: str) -> str:
    """Normalize markdown output.

    - Single blank line between blocks
    - No trailing whitespace
    - No leading/trailing blank lines
    """
    # Normalize line endings
    md = md.replace("\r\n", "\n").replace("\r", "\n")

    # Collapse multiple blank lines to single
    md = re.sub(r"\n{3,}", "\n\n", md)

    # Remove trailing whitespace from lines (except intentional breaks)
    lines = md.split("\n")
    cleaned_lines = []
    for line in lines:
        if line.endswith("  "):
            # Preserve intentional line break (two trailing spaces)
            cleaned_lines.append(line.rstrip() + "  ")
        else:
            cleaned_lines.append(line.rstrip())

    md = "\n".join(cleaned_lines)

    # Remove leading/trailing blank lines
    md = md.strip()

    return md
