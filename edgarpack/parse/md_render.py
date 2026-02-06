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
    # Process the HTML step by step with regex replacements.
    #
    # Important: SEC filings often use lots of block-level tags (<div>, <tr>, etc.)
    # without meaningful whitespace between them. Before stripping unknown tags we
    # insert minimal separators so visible text doesn't get concatenated.

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
    """Process ul and ol lists."""
    result = html

    # Process unordered lists
    def process_ul(match: re.Match) -> str:
        content = match.group(1)
        items = re.findall(r"<li[^>]*>(.*?)</li>", content, re.DOTALL | re.IGNORECASE)
        if not items:
            return ""
        lines = [f"- {_process_inline(item).strip()}" for item in items]
        return "\n\n" + "\n".join(lines) + "\n\n"

    result = re.sub(
        r"<ul[^>]*>(.*?)</ul>",
        process_ul,
        result,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # Process ordered lists
    def process_ol(match: re.Match) -> str:
        content = match.group(1)
        items = re.findall(r"<li[^>]*>(.*?)</li>", content, re.DOTALL | re.IGNORECASE)
        if not items:
            return ""
        lines = [f"{i + 1}. {_process_inline(item).strip()}" for i, item in enumerate(items)]
        return "\n\n" + "\n".join(lines) + "\n\n"

    result = re.sub(
        r"<ol[^>]*>(.*?)</ol>",
        process_ol,
        result,
        flags=re.DOTALL | re.IGNORECASE,
    )

    return result


def _process_tables(html: str) -> str:
    """Process tables to GFM format."""
    def process_table(match: re.Match) -> str:
        content = match.group(1)

        rows: list[list[str]] = []
        has_header = False

        # Find all rows
        for tr_match in re.finditer(r"<tr[^>]*>(.*?)</tr>", content, re.DOTALL | re.IGNORECASE):
            tr_content = tr_match.group(1)
            cells: list[str] = []
            is_header_row = False

            # Find header cells
            for th_match in re.finditer(r"<th[^>]*>(.*?)</th>", tr_content, re.DOTALL | re.IGNORECASE):
                cells.append(_strip_tags(th_match.group(1)).strip())
                is_header_row = True

            # Find data cells (if no header cells found)
            if not cells:
                for td_match in re.finditer(r"<td[^>]*>(.*?)</td>", tr_content, re.DOTALL | re.IGNORECASE):
                    cells.append(_strip_tags(td_match.group(1)).strip())

            if cells:
                rows.append(cells)
                if is_header_row and not has_header:
                    has_header = True

        if not rows:
            return ""

        # Determine column count
        max_cols = max(len(row) for row in rows)

        # Pad rows
        for row in rows:
            while len(row) < max_cols:
                row.append("")

        # Build markdown table
        lines: list[str] = []

        # Header row
        header = rows[0] if rows else [""] * max_cols
        lines.append("| " + " | ".join(_escape_table_cell(c) for c in header) + " |")

        # Separator
        lines.append("| " + " | ".join("---" for _ in range(max_cols)) + " |")

        # Body rows
        start_idx = 1 if len(rows) > 1 else 0
        for row in rows[start_idx:]:
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
