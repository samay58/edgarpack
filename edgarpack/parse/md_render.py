"""Render semantic HTML to CommonMark markdown."""

import re
from html import unescape

_IMG_TAG_RE = re.compile(r"<img\b[^>]*?/?>", re.IGNORECASE)
# Quote-tolerant attribute extractors: SEC HTML uses double, single, or
# occasionally unquoted attributes. Each pattern returns the value via
# whichever alternation branch matches.
_SRC_RE = re.compile(
    r"""src\s*=\s*(?:"([^"]+)"|'([^']+)'|([^\s>"']+))""",
    re.IGNORECASE,
)
_ALT_RE = re.compile(
    r"""alt\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>"']*))""",
    re.IGNORECASE,
)


def _first_group(m: re.Match[str] | None) -> str:
    """Return the first non-empty capture group, or '' when no match."""
    if not m:
        return ""
    return next((g for g in m.groups() if g), "")


def _rewrite_images(text: str, asset_map: dict[str, str]) -> str:
    def _sub(m: re.Match[str]) -> str:
        tag = m.group(0)
        src = _first_group(_SRC_RE.search(tag))
        if not src:
            return ""
        alt = _first_group(_ALT_RE.search(tag)).strip()
        local = asset_map.get(src) or asset_map.get(src.split("/")[-1])
        if not local:
            return ""
        caption = f"\n\n*{alt}*\n" if alt else ""
        return f"![{alt}]({local}){caption}"

    return _IMG_TAG_RE.sub(_sub, text)


def render_markdown(html: str, *, asset_map: dict[str, str] | None = None) -> str:
    """Convert semantic HTML to CommonMark markdown.

    Args:
        html: Semantic HTML (should be pre-processed by semantic_html.py)
        asset_map: Optional mapping of original <img src> values to local
            relative paths (e.g. {"fig-1.png": "assets/fig-1.png"}). When
            provided, matching <img> tags are rewritten to ![alt](local)
            syntax with an italic caption line. When omitted, surviving
            <img> tags are dropped by the catch-all HTML strip.

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
        lambda m: _render_link(m.group(1), _strip_tags(m.group(2)).strip()),
        result,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # Process strong/bold
    def _render_strong(m: re.Match[str]) -> str:
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

    # Process emphasis/italic
    def _render_em(m: re.Match[str]) -> str:
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

    # Rewrite <img> tags to markdown before stripping remaining HTML.
    if asset_map:
        result = _rewrite_images(result, asset_map)

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


def _render_link(href: str, text: str) -> str:
    href = href.strip()
    if not text or text.isspace():
        return ""
    if not href or href == "#" or href.lower().startswith("javascript:"):
        return text
    return f"[{text}]({href})"


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
        lambda m: _render_link(m.group(1), _strip_tags(m.group(2)).strip()),
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
        def _render_ul(match: re.Match[str]) -> str:
            return _render_list_items(match.group(1), ordered=False, depth=0)

        result = re.sub(
            r"<ul[^>]*>((?:(?!<ul|<ol).)*?)</ul>",
            _render_ul,
            result,
            flags=re.DOTALL | re.IGNORECASE,
        )

        def _render_ol(match: re.Match[str]) -> str:
            return _render_list_items(match.group(1), ordered=True, depth=0)

        result = re.sub(
            r"<ol[^>]*>((?:(?!<ul|<ol).)*?)</ol>",
            _render_ol,
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

    for li_match in re.finditer(r"<li[^>]*>(.*?)</li>", html, re.DOTALL | re.IGNORECASE):
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
        if not m:
            return 1
        return max(1, int(m.group(1)))

    def process_table(match: re.Match[str]) -> str:
        content = match.group(1)

        # Build a 2D grid accounting for colspan/rowspan
        grid: list[list[str | None]] = []

        row_idx = -1
        for tr_match in re.finditer(r"<tr[^>]*>(.*?)</tr>", content, re.DOTALL | re.IGNORECASE):
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
        render_grid: list[list[str]] = []
        for row in grid:
            while len(row) < max_cols:
                row.append(None)
            render_grid.append([cell or "" for cell in row])

        # Render as GFM table
        lines: list[str] = []
        header = render_grid[0] if render_grid else [""] * max_cols
        lines.append("| " + " | ".join(_escape_table_cell(c) for c in header) + " |")
        lines.append("| " + " | ".join("---" for _ in range(max_cols)) + " |")
        for render_row in render_grid[1:]:
            lines.append("| " + " | ".join(_escape_table_cell(c) for c in render_row) + " |")

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
