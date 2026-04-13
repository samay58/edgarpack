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


def _strip_broken_anchors(md: str) -> str:
    """Strip fragment-only links outside the TOC section.

    Fragment links like [Risk Factors](#toc890989_3) are replaced with plain
    text (Risk Factors) everywhere except inside the TOC section, where they
    are navigation links and should be preserved.
    """
    toc_span = _find_toc_span(md)

    def _replace(m: re.Match) -> str:
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
    md = _strip_broken_anchors(md)
    md = _normalize_whitespace(md)
    return md
