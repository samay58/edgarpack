"""Post-processing polish pass for rendered SEC filing markdown."""

import re

# Matches a heading line that is a Table of Contents or INDEX marker.
# Handles any heading level (#..#), optional bold/italic wrappers, and
# case variations. Examples that match:
#   ##### Table of Contents
#   ## **TABLE OF CONTENTS**
#   # INDEX
#   ### *Index*
_TOC_HEADING_RE = re.compile(
    r"^(#{1,6})\s+(?:\*{1,2}|_{1,2})?(?:table\s+of\s+contents|index)(?:\*{1,2}|_{1,2})?\s*$",
    re.IGNORECASE | re.MULTILINE,
)

# Matches a fragment-only markdown link: [text](#anchor)
# Does NOT match full URLs like https://... or relative paths without leading #.
_FRAGMENT_LINK_RE = re.compile(r"\[([^\]]+)\]\(#[^)]*\)")

# Matches any markdown heading line.
_HEADING_RE = re.compile(r"^#{1,6}\s", re.MULTILINE)


def _strip_toc_spam(md: str) -> str:
    """Keep the first TOC/INDEX heading; remove all subsequent ones.

    Surrounding blank lines around removed headings are also collapsed so
    the removal does not leave double-blank gaps.
    """
    found_first = False
    lines = md.split("\n")
    out: list[str] = []

    i = 0
    while i < len(lines):
        line = lines[i]
        if _TOC_HEADING_RE.match(line):
            if not found_first:
                found_first = True
                out.append(line)
                i += 1
            else:
                # Drop this heading. Also eat any immediately preceding blank
                # line that was already appended, and skip trailing blank lines.
                while out and out[-1] == "":
                    out.pop()
                i += 1
                while i < len(lines) and lines[i] == "":
                    i += 1
        else:
            out.append(line)
            i += 1

    return "\n".join(out)


def _find_toc_span(md: str) -> tuple[int, int] | None:
    """Return (start, end) character offsets of the TOC section body, or None.

    The TOC section begins immediately after the first TOC/INDEX heading line
    and ends at the start of the next non-TOC heading (or EOF).
    """
    m = _TOC_HEADING_RE.search(md)
    if m is None:
        return None

    # Body starts after the heading line (skip the newline that follows it).
    body_start = m.end()
    if body_start < len(md) and md[body_start] == "\n":
        body_start += 1

    # Find the next heading that is NOT a TOC/INDEX heading.
    rest = md[body_start:]
    for hm in _HEADING_RE.finditer(rest):
        pos = hm.start()
        heading_line_end = rest.find("\n", pos)
        heading_line = rest[pos:heading_line_end] if heading_line_end != -1 else rest[pos:]
        if not _TOC_HEADING_RE.match(heading_line):
            return (body_start, body_start + pos)

    return (body_start, len(md))


def _strip_bold_noise(md: str) -> str:
    # Rule 1: All-bold paragraphs
    md = re.sub(r"(?m)^(\*\*)((?:(?!\*\*).)+)\1$", r"\2", md)
    # Rule 2: Bold dollar amounts like **$1,234**
    md = re.sub(r"\*\*(\$[\d,]+(?:\.\d+)?)\*\*", r"\1", md)
    # Rule 3: Bold parenthetical negatives like **(1,234)** or **($1,234)**
    md = re.sub(r"\*\*(\(?\$?[\d,]+(?:\.\d+)?\)?)\*\*", r"\1", md)
    # Rule 4: Bold standalone numbers like **42,000** or **12.5%**
    md = re.sub(r"\*\*([\d,]+(?:\.\d+)?%?)\*\*", r"\1", md)
    return md


_BULLET_CHARS = {"\u2022", "\u25cb", "\u25aa", "\u25e6", "*", "-", "\u2023", "\u25b8"}

# Matches a GFM separator row (e.g. | --- | :---: | --- |)
_TABLE_SEP_RE = re.compile(r"^\|[\s\-:|]+\|[\s\-:|]*$")


def _parse_table_block(lines: list[str]) -> list[list[str]] | None:
    """Parse a sequence of table lines into a list of cell-lists.

    Returns None if the block is not a valid GFM table (no separator row).
    The separator row itself is represented as an empty list so we can
    reconstruct position but is otherwise treated specially by callers.
    """
    if len(lines) < 2:
        return None
    rows: list[list[str]] = []
    sep_found = False
    for line in lines:
        if _TABLE_SEP_RE.match(line.strip()):
            rows.append([])  # sentinel for separator
            sep_found = True
        else:
            # Split on | and strip, dropping empty first/last tokens from leading/trailing |
            parts = line.split("|")
            # Remove empty strings from leading/trailing pipe
            has_border = parts[0].strip() == "" and parts[-1].strip() == ""
            cells = [c.strip() for c in parts[1:-1]] if has_border else [c.strip() for c in parts]
            rows.append(cells)
    return rows if sep_found else None


def _find_table_blocks(md: str) -> list[tuple[int, int]]:
    """Return list of (start_line, end_line) index pairs for each GFM table block.

    A block is a maximal run of consecutive lines that each start with '|'.
    end_line is exclusive.
    """
    lines = md.split("\n")
    blocks: list[tuple[int, int]] = []
    i = 0
    while i < len(lines):
        if lines[i].strip().startswith("|"):
            start = i
            while i < len(lines) and lines[i].strip().startswith("|"):
                i += 1
            blocks.append((start, i))
        else:
            i += 1
    return blocks


def _recover_bullet_tables(md: str) -> str:
    """Convert GFM tables with a bullet-character column into markdown lists.

    When every data cell in exactly one column consists solely of a bullet
    character (and the rest of the table has at most one other content column),
    the table is better represented as a plain list.  We find the bullet column
    and the content column and emit "- <content>" lines.
    """
    lines = md.split("\n")
    blocks = _find_table_blocks(md)
    if not blocks:
        return md

    # Work from last block to first so line indices stay valid.
    for start, end in reversed(blocks):
        block_lines = lines[start:end]
        rows = _parse_table_block(block_lines)
        if rows is None:
            continue

        # Collect data rows (non-separator)
        data_rows = [r for r in rows if r]  # separator rows are []
        if not data_rows:
            continue

        # Determine number of columns from first data row
        ncols = len(data_rows[0])
        if ncols == 0:
            continue

        # Find which column index is the bullet column
        bullet_col = None
        for col in range(ncols):
            if all(col < len(row) and row[col] in _BULLET_CHARS for row in data_rows):
                bullet_col = col
                break

        if bullet_col is None:
            continue  # no bullet column — leave table alone

        # Find the content column: the single non-empty, non-bullet column
        content_col = None
        for col in range(ncols):
            if col == bullet_col:
                continue
            # Check if any cell in this column has content
            if any(col < len(row) and row[col] for row in data_rows):
                if content_col is not None:
                    content_col = None  # more than one content column
                    break
                content_col = col

        if content_col is None:
            continue  # ambiguous or no content — leave table alone

        # Build list lines
        list_lines = [
            f"- {row[content_col]}" if content_col < len(row) else "-" for row in data_rows
        ]

        lines[start:end] = list_lines

    return "\n".join(lines)


def _simplify_empty_columns(md: str) -> str:
    """Remove GFM table columns where every cell (including header) is empty.

    If after removal only 0 or 1 data columns remain, convert the block to
    plain text lines instead of a single-column table.
    """
    lines = md.split("\n")
    blocks = _find_table_blocks(md)
    if not blocks:
        return md

    for start, end in reversed(blocks):
        block_lines = lines[start:end]
        rows = _parse_table_block(block_lines)
        if rows is None:
            continue

        # Identify separator row index and data rows
        sep_idx = next((i for i, r in enumerate(rows) if r == []), None)
        if sep_idx is None:
            continue

        data_rows = [r for r in rows if r != []]
        if not data_rows:
            continue

        ncols = max(len(r) for r in data_rows)

        # Find empty columns (every cell empty across all data rows)
        empty_cols = set()
        for col in range(ncols):
            if all(col >= len(row) or row[col] == "" for row in data_rows):
                empty_cols.add(col)

        if not empty_cols:
            continue  # nothing to remove

        # Build filtered data rows (drop empty columns)
        filtered_rows = [
            [cell for ci, cell in enumerate(row) if ci not in empty_cols] for row in data_rows
        ]

        remaining_cols = ncols - len(empty_cols)

        if remaining_cols <= 1:
            # Convert to plain text
            text_lines: list[str] = []
            for row in filtered_rows:
                text_lines.append(row[0] if row else "")
            lines[start:end] = text_lines
        else:
            # Rebuild as a GFM table
            def _fmt_row(cells: list[str]) -> str:
                return "| " + " | ".join(cells) + " |"

            rebuilt: list[str] = []
            row_iter = iter(data_rows)
            out_iter = iter(filtered_rows)

            # Header row(s) before separator
            header_out: list[str] = []
            for _ in range(sep_idx):
                next(row_iter)
                header_out.append(_fmt_row(next(out_iter)))

            rebuilt.extend(header_out)
            rebuilt.append("| " + " | ".join(["---"] * remaining_cols) + " |")

            # Remaining data rows
            for _ in range(len(data_rows) - sep_idx):
                try:
                    rebuilt.append(_fmt_row(next(out_iter)))
                except StopIteration:
                    break

            lines[start:end] = rebuilt

    return "\n".join(lines)


_MAX_SIMPLE_COLS = 6
_MAX_ROW_WIDTH = 120


def _simplify_complex_tables(md: str) -> str:
    """Convert wide/complex GFM tables to indented blockquote format.

    Tables with more than _MAX_SIMPLE_COLS columns or rows wider than
    _MAX_ROW_WIDTH characters are converted to a blockquote with dot-leaders.
    Simple tables are left as GFM.
    """
    lines = md.split("\n")
    blocks = _find_table_blocks(md)
    if not blocks:
        return md

    result_lines = list(lines)
    # Process blocks in reverse to preserve line indices.
    for start, end in reversed(blocks):
        table_lines = lines[start:end]

        # Parse rows (skip separator rows).
        parsed_rows: list[list[str]] = []
        for tl in table_lines:
            cells = [c.strip() for c in tl.split("|")]
            cells = cells[1:-1] if len(cells) >= 2 else cells
            if cells and all(re.match(r"^-+$", c.strip()) for c in cells if c.strip()):
                continue  # skip separator
            parsed_rows.append(cells)

        if not parsed_rows:
            continue

        num_cols = max(len(r) for r in parsed_rows)
        max_row_len = max(len(tl) for tl in table_lines)

        if num_cols <= _MAX_SIMPLE_COLS and max_row_len <= _MAX_ROW_WIDTH:
            continue  # simple table, leave alone

        # Convert to blockquote format.
        header_row = parsed_rows[0]
        data_rows = parsed_rows[1:] if len(parsed_rows) > 1 else parsed_rows

        output: list[str] = []

        caption_parts = [c for c in header_row if c]
        if caption_parts:
            if len(caption_parts) <= 3:
                output.append(f"> **{' / '.join(caption_parts)}**")
            else:
                output.append(f"> **{caption_parts[0]}**")
                output.append(">")
                output.append("> " + " / ".join(caption_parts[1:]))
            output.append(">")

        for row in data_rows:
            padded = row + [""] * (num_cols - len(row))
            label = padded[0] if padded else ""
            values = [v for v in padded[1:] if v]

            if not label and not values:
                continue

            if label and values:
                stripped_label = label.lstrip()
                indent_spaces = len(label) - len(stripped_label)
                indent = "  " * min(indent_spaces // 2, 3) if indent_spaces else ""
                value_str = " / ".join(values)
                leader_target = max(40 - len(indent) - len(stripped_label), 3)
                leader = "." * leader_target
                output.append(f"> {indent}{stripped_label} {leader} {value_str}")
            elif label:
                output.append(f"> {label}")
            else:
                output.append(f"> {' / '.join(values)}")

        result_lines[start:end] = output

    return "\n".join(result_lines)


def _normalize_headings(md: str) -> str:
    """Normalize heading levels: minimum becomes ##, no level skips."""
    heading_re = re.compile(r"^(#{1,6})\s+(.*)", re.MULTILINE)
    matches = list(heading_re.finditer(md))
    if not matches:
        return md

    min_level = min(len(m.group(1)) for m in matches)
    shift = 2 - min_level  # target: minimum becomes ##

    lines = md.split("\n")
    prev_level = 1  # virtual parent (the # title added later by pack builder)
    result_lines: list[str] = []

    for line in lines:
        m = heading_re.match(line)
        if m:
            raw_level = len(m.group(1))
            shifted = max(2, min(6, raw_level + shift))
            if shifted > prev_level + 1:
                shifted = prev_level + 1
            shifted = min(shifted, 6)
            prev_level = shifted
            result_lines.append(f"{'#' * shifted} {m.group(2)}")
        else:
            result_lines.append(line)

    return "\n".join(result_lines)


def _strip_broken_anchors(md: str) -> str:
    """Strip fragment-only links outside the TOC section.

    Fragment links like [Risk Factors](#toc890989_3) are replaced with plain
    text (Risk Factors) everywhere except inside the TOC section, where they
    are navigation links and should be preserved.
    """
    toc_span = _find_toc_span(md)

    def _replace(m: re.Match[str]) -> str:
        if toc_span is not None:
            toc_start, toc_end = toc_span
            if toc_start <= m.start() < toc_end:
                return m.group(0)  # inside TOC — preserve
        return m.group(1)  # outside TOC — strip to plain text

    return _FRAGMENT_LINK_RE.sub(_replace, md)


def _normalize_whitespace(md: str) -> str:
    """Normalize whitespace in markdown output.

    Rules applied in order:
    1. Strip trailing whitespace on each line, except intentional 2-space
       line breaks (trailing double-space before newline).
    2. Ensure exactly one blank line before any heading.
    3. Collapse 3+ consecutive blank lines to a single blank line.
    4. Strip leading and trailing blank lines from the document.
    """
    # Step 1: strip trailing whitespace, but preserve intentional 2-space breaks.
    # A 2-space break is exactly two trailing spaces — not three or more.
    lines = md.split("\n")
    cleaned: list[str] = []
    for line in lines:
        if line.endswith("  ") and not line.endswith("   "):
            # Intentional soft line break: preserve the two trailing spaces.
            cleaned.append(line.rstrip(" ") + "  ")
        else:
            cleaned.append(line.rstrip())

    md = "\n".join(cleaned)

    # Step 2: ensure exactly one blank line before headings.
    # Replace any run of blank lines (or no blank line) immediately before a
    # heading with exactly one blank line.
    md = re.sub(r"\n{2,}(#{1,6}\s)", r"\n\n\1", md)
    md = re.sub(r"([^\n])\n(#{1,6}\s)", r"\1\n\n\2", md)

    # Step 3: collapse 3+ consecutive blank lines to one blank line.
    md = re.sub(r"\n{3,}", "\n\n", md)

    # Step 4: strip leading/trailing blank lines.
    md = md.strip("\n")

    return md


def polish(md: str) -> str:
    """Apply all polish rules to rendered markdown in sequence."""
    md = _strip_toc_spam(md)
    md = _strip_bold_noise(md)
    md = _recover_bullet_tables(md)
    md = _simplify_empty_columns(md)
    md = _simplify_complex_tables(md)
    md = _normalize_headings(md)
    md = _strip_broken_anchors(md)
    md = _normalize_whitespace(md)
    return md
