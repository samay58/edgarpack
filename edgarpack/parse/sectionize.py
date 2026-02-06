"""Split filings into sections based on form-specific patterns."""

import re
from typing import NamedTuple

from pydantic import BaseModel, Field


class Section(BaseModel):
    """A section of a filing."""

    id: str
    title: str
    content: str
    char_start: int
    char_end: int
    warnings: list[str] = Field(default_factory=list)


class SectionMatch(NamedTuple):
    """Internal representation of a section heading match."""

    line_num: int
    char_pos: int
    part: str | None
    item: str
    title: str
    form_type: str


# 10-K/10-Q Item patterns.
#
# Important: In real filings, headings may be prefixed with a page number (e.g. "2 Part I")
# or embedded in tables (e.g. TOC rows like "| Item 1. | Financial Statements | 3 |").
_SEP_CHARS = r"[-–—.,:;]"

ITEM_PATTERN_10K = re.compile(
    rf"^(?:#+\s*)?(?:[.)]\s*)?(?:\d+\s*)?"
    rf"(?:(?:PART\s+(?P<part>[IVX]+)\b\s*{_SEP_CHARS}?\s*)?)"
    rf"ITEM\s*(?P<item>\d+[A-Z]?)\b"
    rf"(?:\s*{_SEP_CHARS}\s*)?"
    rf"(?P<title>.*)$",
    re.IGNORECASE,
)

# 8-K Item patterns (numbered like 1.01, 2.02, etc.)
ITEM_PATTERN_8K = re.compile(
    rf"^(?:#+\s*)?(?:[.)]\s*)?(?:\d+\s*)?ITEM\s+(?P<item>\d+\.\d+)\b"
    rf"(?:\s*{_SEP_CHARS}\s*)?"
    rf"(?P<title>.*)$",
    re.IGNORECASE,
)

# Part-only heading (used to carry Part context forward to subsequent items).
PART_HEADING_PATTERN = re.compile(
    rf"^(?:#+\s*)?(?:[.)]\s*)?(?:\d+\s*)?PART\s+(?P<part>[IVX]+)\b"
    rf"(?:\s*{_SEP_CHARS}\s*(?P<title>.*))?$",
    re.IGNORECASE,
)

# Common section titles that might not have ITEM prefix
TITLED_SECTION_PATTERN = re.compile(
    r"^(?:#+\s*)?(?P<title>"
    r"SIGNATURES?|"
    r"INDEX\s+TO\s+(?:FINANCIAL\s+)?(?:STATEMENTS|EXHIBITS)|"
    r"TABLE\s+OF\s+CONTENTS|"
    r"EXHIBITS?\s+INDEX|"
    r"FINANCIAL\s+STATEMENTS|"
    r"NOTES\s+TO\s+(?:CONSOLIDATED\s+)?FINANCIAL\s+STATEMENTS"
    r")\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def slugify(text: str, max_len: int = 30) -> str:
    """Convert text to a URL-safe slug.

    Args:
        text: Text to convert
        max_len: Maximum length of slug

    Returns:
        Lowercase slug with underscores
    """
    # Lowercase
    text = text.lower()

    # Replace common words
    text = text.replace(" and ", "_")
    text = text.replace("&", "_")

    # Keep only alphanumeric, spaces, and underscores
    text = re.sub(r"[^a-z0-9\s_]", "", text)

    # Replace whitespace with underscore
    text = re.sub(r"\s+", "_", text)

    # Remove leading/trailing underscores
    text = text.strip("_")

    # Collapse multiple underscores
    text = re.sub(r"_+", "_", text)

    # Truncate
    if len(text) > max_len:
        # Try to break at underscore boundary
        if "_" in text[:max_len]:
            text = text[:max_len].rsplit("_", 1)[0]
        else:
            text = text[:max_len]

    return text


def section_id(form: str, part: str | None, item: str, title: str) -> str:
    """Generate a section ID.

    Args:
        form: Form type (10-K, 10-Q, 8-K)
        part: Part number (I, II, etc.) or None
        item: Item number
        title: Section title

    Returns:
        Section ID string
    """
    form_lower = form.lower().replace("-", "")
    slug = slugify(title) if title else ""

    if form in ("10-K", "10-k"):
        parts = ["10k"]
        if part:
            parts.append(f"part{part.lower()}")
        parts.append(f"item{item.lower()}")
        if slug:
            parts.append(slug)
        return "_".join(parts)

    elif form in ("10-Q", "10-q"):
        parts = ["10q"]
        if part:
            parts.append(f"part{part.lower()}")
        parts.append(f"item{item.lower()}")
        if slug:
            parts.append(slug)
        return "_".join(parts)

    elif form in ("8-K", "8-k"):
        item_clean = item.replace(".", "_")
        parts = [f"8k_item_{item_clean}"]
        if slug:
            parts.append(slug)
        return "_".join(filter(None, parts))

    else:
        # Generic fallback
        parts = [form_lower]
        if part:
            parts.append(f"part{part.lower()}")
        if item:
            parts.append(f"item{item.lower()}")
        if slug:
            parts.append(slug)
        return "_".join(filter(None, parts))


def find_sections(markdown: str, form_type: str) -> list[SectionMatch]:
    """Find all section headings in markdown.

    Args:
        markdown: Markdown content
        form_type: Form type for pattern selection

    Returns:
        List of section matches in order
    """
    matches: list[SectionMatch] = []
    lines = markdown.split("\n")

    # Build line-to-char-offset mapping
    char_offsets: list[int] = []
    offset = 0
    for line in lines:
        char_offsets.append(offset)
        offset += len(line) + 1  # +1 for newline

    form_upper = form_type.upper()

    # Track current PART so items without explicit PART still get a stable ID.
    current_part: str | None = None

    # Heuristic: skip the first markdown table after a "Table of Contents" header to
    # avoid splitting on TOC entries (they often include many "Item X." rows).
    toc_armed = False
    in_toc_table = False

    def _is_table_row(s: str) -> bool:
        return s.startswith("|") and s.count("|") >= 2

    def _split_table_cells(row: str) -> list[str]:
        # Split on unescaped pipes. md_render escapes literal pipes in cells as "\|".
        parts = re.split(r"(?<!\\)\|", row)
        if parts and parts[0].strip() == "":
            parts = parts[1:]
        if parts and parts[-1].strip() == "":
            parts = parts[:-1]
        return [p.strip() for p in parts]

    def _clean_title(raw: str) -> str:
        t = re.sub(r"\s+", " ", raw).strip()
        # Fix common flattening artifacts where words get concatenated when HTML tags are stripped.
        t = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", t)
        return t

    def _truncate_title(t: str) -> str:
        if len(t) <= 100:
            return t
        head = t[:100]
        return head.rsplit(" ", 1)[0] if " " in head else head

    for line_num, line in enumerate(lines):
        line_stripped = line.strip()

        if not line_stripped:
            if in_toc_table:
                in_toc_table = False
                toc_armed = False
            continue

        # Arm TOC skipping when we see a TOC header.
        if re.search(r"\btable\s+of\s+contents\b", line_stripped, flags=re.IGNORECASE):
            toc_armed = True

        is_table = _is_table_row(line_stripped)
        if in_toc_table and not is_table:
            in_toc_table = False
            toc_armed = False

        if is_table and toc_armed and not in_toc_table:
            in_toc_table = True

        # If this is a TOC table row, skip item detection to avoid false section starts.
        if in_toc_table and is_table:
            continue

        # Update current_part if we see a PART heading (line or table cell).
        if is_table:
            for cell in _split_table_cells(line_stripped):
                pm = PART_HEADING_PATTERN.match(cell)
                if pm and pm.group("part"):
                    current_part = pm.group("part").upper()
                    break
        else:
            pm = PART_HEADING_PATTERN.match(line_stripped)
            if pm and pm.group("part"):
                current_part = pm.group("part").upper()

        # Identify item headings.
        def _add_item_match(item: str, title: str, part: str | None, char_pos: int) -> None:
            nonlocal matches
            clean_title = _truncate_title(_clean_title(title))
            matches.append(SectionMatch(
                line_num=line_num,
                char_pos=char_pos,
                part=part,
                item=item,
                title=clean_title,
                form_type=form_type,
            ))

        if form_upper == "8-K":
            if is_table:
                cells = _split_table_cells(line_stripped)
                for idx, cell in enumerate(cells):
                    m = ITEM_PATTERN_8K.match(cell)
                    if not m:
                        continue
                    item = m.group("item")
                    title = (m.group("title") or "").strip()
                    if not title and idx + 1 < len(cells):
                        title = cells[idx + 1]
                    _add_item_match(item=item, title=title, part=None, char_pos=char_offsets[line_num])
                    break
            else:
                m = ITEM_PATTERN_8K.match(line_stripped)
                if m and m.group("item"):
                    item = m.group("item")
                    title = (m.group("title") or "").strip()
                    _add_item_match(item=item, title=title, part=None, char_pos=char_offsets[line_num])
                # Inline scan (ordered) for concatenated headings that got flattened into one line.
                # Only consider matches far into the line to avoid duplicating proper headings.
                for m2 in re.finditer(r"ITEM\s+(?P<item>\d+\.\d+)\b", line, flags=re.IGNORECASE):
                    if m2.start() < 20:
                        continue
                    prev = line[m2.start() - 1]
                    if not (prev.islower() or prev.isdigit() or prev in ".:;)|]"):
                        continue
                    tail = line[m2.start():].strip()
                    mm = ITEM_PATTERN_8K.match(tail)
                    title = (mm.group("title") or "").strip() if mm else ""
                    _add_item_match(
                        item=m2.group("item"),
                        title=title,
                        part=None,
                        char_pos=char_offsets[line_num] + m2.start(),
                    )
        else:
            if is_table:
                cells = _split_table_cells(line_stripped)
                for idx, cell in enumerate(cells):
                    m = ITEM_PATTERN_10K.match(cell)
                    if not m or not m.group("item"):
                        continue
                    item = m.group("item")
                    part = (m.group("part") or current_part)
                    if part:
                        part = part.upper()
                        current_part = part
                    title = (m.group("title") or "").strip()
                    if not title and idx + 1 < len(cells):
                        title = cells[idx + 1]
                    _add_item_match(item=item, title=title, part=part, char_pos=char_offsets[line_num])
                    break
            else:
                m = ITEM_PATTERN_10K.match(line_stripped)
                if m and m.group("item"):
                    item = m.group("item")
                    part = (m.group("part") or current_part)
                    if part:
                        part = part.upper()
                        current_part = part
                    title = (m.group("title") or "").strip()
                    _add_item_match(item=item, title=title, part=part, char_pos=char_offsets[line_num])
                # Inline scan (ordered) for concatenated PART/ITEM headings that got flattened.
                events: list[tuple[int, str, re.Match[str]]] = []
                for pm2 in re.finditer(r"PART\s+(?P<part>[IVX]+)\b", line, flags=re.IGNORECASE):
                    if pm2.start() < 20:
                        continue
                    prev = line[pm2.start() - 1]
                    if prev.islower() or prev.isdigit() or prev in ".:;)|]":
                        events.append((pm2.start(), "part", pm2))
                for im2 in re.finditer(r"ITEM\s*(?P<item>\d+[A-Z]?)\b", line, flags=re.IGNORECASE):
                    if im2.start() < 20:
                        continue
                    prev = line[im2.start() - 1]
                    if prev.islower() or prev.isdigit() or prev in ".:;)|]":
                        events.append((im2.start(), "item", im2))

                events.sort(key=lambda e: e[0])
                for start, kind, match in events:
                    if kind == "part":
                        current_part = match.group("part").upper()
                        continue
                    tail = line[start:].strip()
                    mm = ITEM_PATTERN_10K.match(tail)
                    title = (mm.group("title") or "").strip() if mm else ""
                    _add_item_match(
                        item=match.group("item"),
                        title=title,
                        part=current_part,
                        char_pos=char_offsets[line_num] + start,
                    )

        # Also check for titled sections (SIGNATURES, etc.) on their own line.
        if not is_table:
            m = TITLED_SECTION_PATTERN.match(line_stripped)
            if m:
                title = m.group("title")
                _add_item_match(item="other", title=title, part=current_part, char_pos=char_offsets[line_num])

    # Sort and dedupe by char_pos for stability.
    matches.sort(key=lambda m: (m.char_pos, m.line_num))
    deduped: list[SectionMatch] = []
    seen_pos: set[int] = set()
    for m in matches:
        if m.char_pos in seen_pos:
            continue
        seen_pos.add(m.char_pos)
        deduped.append(m)

    return deduped


def sectionize(markdown: str, form_type: str) -> list[Section]:
    """Split markdown into sections based on form-specific patterns.

    Args:
        markdown: Full markdown content
        form_type: Form type (10-K, 10-Q, 8-K)

    Returns:
        List of Section objects
    """
    matches = find_sections(markdown, form_type)

    if not matches:
        # No sections detected - emit single unknown section
        return [Section(
            id="unknown_01",
            title="Unknown Section",
            content=markdown,
            char_start=0,
            char_end=len(markdown),
            warnings=["No section headings detected in document"],
        )]

    sections: list[Section] = []
    total_len = len(markdown)

    # Check for content before first section
    first_match = matches[0]
    if first_match.char_pos > 0:
        preamble = markdown[:first_match.char_pos].strip()
        if preamble and len(preamble) > 100:  # Only if substantial
            sections.append(Section(
                id="unknown_00",
                title="Preamble",
                content=preamble,
                char_start=0,
                char_end=first_match.char_pos,
                warnings=["Content before first detected section"],
            ))

    # Create sections from matches
    for i, match in enumerate(matches):
        # Determine section end
        if i + 1 < len(matches):
            char_end = matches[i + 1].char_pos
        else:
            char_end = total_len

        content = markdown[match.char_pos:char_end].strip()

        sid = section_id(form_type, match.part, match.item, match.title)

        sections.append(Section(
            id=sid,
            title=match.title or f"Item {match.item}",
            content=content,
            char_start=match.char_pos,
            char_end=char_end,
            warnings=[],
        ))

    # Check for duplicate IDs and make unique
    seen_ids: dict[str, int] = {}
    for section in sections:
        if section.id in seen_ids:
            seen_ids[section.id] += 1
            section.id = f"{section.id}_{seen_ids[section.id]}"
            section.warnings.append("Duplicate section ID detected, suffix added")
        else:
            seen_ids[section.id] = 0

    return sections
