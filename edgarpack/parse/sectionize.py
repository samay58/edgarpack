"""Split filings into sections based on form-specific patterns."""

import hashlib
import re
from typing import NamedTuple

from pydantic import BaseModel, Field


class Section(BaseModel):
    id: str
    title: str
    content: str
    char_start: int
    char_end: int
    warnings: list[str] = Field(default_factory=list)


class SectionMatch(NamedTuple):
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

BOLD_HEADING_PATTERN = re.compile(r"\*\*(?P<title>[A-Z0-9][A-Z0-9 &/().,'\-–—]+?)\*\*")

_CANONICAL_ITEM_TITLES = {
    "1": "Business",
    "1A": "Risk Factors",
    "1B": "Unresolved Staff Comments",
    "1C": "Cybersecurity",
    "2": "Properties",
    "3": "Legal Proceedings",
    "4": "Mine Safety Disclosures",
    "5": "Market for Registrant's Common Equity",
    "6": "Reserved",
    "7": "Management's Discussion and Analysis",
    "7A": "Quantitative and Qualitative Disclosures About Market Risk",
    "8": "Financial Statements and Supplementary Data",
    "9": "Changes in and Disagreements with Accountants",
    "9A": "Controls and Procedures",
    "9B": "Other Information",
    "10": "Directors, Executive Officers and Corporate Governance",
    "11": "Executive Compensation",
    "12": "Security Ownership",
    "13": "Certain Relationships and Related Transactions",
    "14": "Principal Accountant Fees and Services",
}


def normalize_form_type_for_sections(form_type: str) -> str:
    """Normalize form type for section detection and IDs.

    - Makes comparison case-insensitive
    - Treats amendments ("/A") as base form for IDs
    """
    if not form_type:
        return ""
    form = form_type.strip().upper().replace(" ", "")
    amended = form.endswith("/A")
    if amended:
        form = form[:-2]
    if form in {"10K", "10-K"}:
        base = "10-K"
    elif form in {"10Q", "10-Q"}:
        base = "10-Q"
    elif form in {"8K", "8-K"}:
        base = "8-K"
    else:
        base = form
    return base


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
    normalized_form = normalize_form_type_for_sections(form)
    form_lower = re.sub(r"[^a-z0-9]+", "", normalized_form.lower())
    slug = slugify(title) if title else ""
    if title and not slug:
        digest = hashlib.sha1(title.strip().lower().encode("utf-8")).hexdigest()[:8]
        slug = f"s{digest}"

    if normalized_form == "10-K":
        parts = ["10k"]
        if part:
            parts.append(f"part{part.lower()}")
        parts.append(f"item{item.lower()}")
        if slug:
            parts.append(slug)
        return "_".join(parts)

    elif normalized_form == "10-Q":
        parts = ["10q"]
        if part:
            parts.append(f"part{part.lower()}")
        parts.append(f"item{item.lower()}")
        if slug:
            parts.append(slug)
        return "_".join(parts)

    elif normalized_form == "8-K":
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
    """Find section headings in markdown while skipping TOC noise.

    Handles headings that appear as plain lines, inline flattened text, or
    markdown table cells. TOC tables are skipped so they do not create sections.
    """
    matches: list[SectionMatch] = []
    lines = markdown.split("\n")

    # Build line-to-char-offset mapping
    char_offsets: list[int] = []
    offset = 0
    for line in lines:
        char_offsets.append(offset)
        offset += len(line) + 1  # +1 for newline

    form_upper = normalize_form_type_for_sections(form_type).upper()
    is_general_form = form_upper not in {"10-K", "10-Q", "8-K"}

    # Track current PART so items without explicit PART still get a stable ID.
    current_part: str | None = None

    # TOC state machine.
    # A TOC heading can be followed by multiple tables (often separated by blank lines),
    # so we keep the TOC armed until we see real non-table content.
    toc_armed = False
    in_toc_table = False
    toc_tables_seen = False

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

    def _normalize_heading_text(text: str) -> str:
        # Keep visible words and remove lightweight markdown/html wrappers.
        normalized = re.sub(r"<[^>]+>", " ", text)
        normalized = re.sub(r"\[(.*?)\]\((?:.*?)\)", r"\1", normalized)
        normalized = re.sub(r"[*_`]+", "", normalized)
        normalized = normalized.replace("&nbsp;", " ")
        return re.sub(r"\s+", " ", normalized).strip()

    def _is_table_separator_row(row: str) -> bool:
        cells = _split_table_cells(row)
        if not cells:
            return False
        return all(re.fullmatch(r":?-{3,}:?", c.replace(" ", "")) for c in cells)

    def _looks_like_toc_row(row: str) -> bool:
        if _is_table_separator_row(row):
            return True
        cells = _split_table_cells(row)
        if not cells:
            return False
        cell_text = _normalize_heading_text(" ".join(cells))
        if not cell_text:
            return False
        has_item_or_part = bool(
            re.search(r"\b(?:item\s+\d+[A-Z]?|part\s+[IVX]+)\b", cell_text, re.I)
        )
        nonempty = [c for c in cells if c.strip()]
        last_cell = _normalize_heading_text(nonempty[-1]) if nonempty else ""
        has_page = bool(re.fullmatch(r"(?:page\s*)?\d{1,4}", last_cell, re.I))
        has_page = has_page or last_cell.upper() == "PAGE"
        has_leader = "..." in row
        return has_item_or_part and (has_page or has_leader)

    def _is_inline_heading_boundary(text: str, start: int) -> bool:
        if start <= 0:
            return False
        prev = text[start - 1]
        if prev.isspace() or prev.islower() or prev.isdigit():
            return True
        if prev in ".:;)|]>*_/":
            return True
        if prev in "IVX":
            tail = text[max(0, start - 16) : start]
            return bool(re.search(r"PART\s+[IVX]+$", tail, flags=re.IGNORECASE))
        return False

    def _extract_part(cell: str) -> str | None:
        cleaned = _normalize_heading_text(cell)
        pm = PART_HEADING_PATTERN.match(cleaned)
        if pm and pm.group("part"):
            return pm.group("part").upper()
        pm2 = re.search(r"\bPART\s+(?P<part>[IVX]+)\b", cleaned, flags=re.IGNORECASE)
        if pm2 and pm2.group("part"):
            return pm2.group("part").upper()
        return None

    def _match_item_in_cell(
        cell: str,
        pattern: re.Pattern[str],
        item_regex: str,
    ) -> re.Match[str] | None:
        cleaned = _normalize_heading_text(cell)
        m = pattern.match(cleaned)
        if m:
            return m
        for im in re.finditer(item_regex, cleaned, flags=re.IGNORECASE):
            tail = cleaned[im.start() :].strip()
            mm = pattern.match(tail)
            if mm:
                return mm
        return None

    def _clean_title(raw: str) -> str:
        t = _normalize_heading_text(raw)
        # Fix common flattening artifacts where words get concatenated when HTML tags are stripped.
        t = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", t)
        # Remove trailing cross-reference boilerplate often concatenated into headings.
        for pattern in (
            r"\s+(?:for|see|refer to|please see|as discussed)\s+"
            r"(?:a\s+)?(?:discussion|details?|information|more|further)\b.*$",
            r"\s+for\s+(?:a\s+)?discussion\s+of\b.*$",
            r"\s*(?:the following|this section|information)(?:\s+(?:discussion|table|report)).*$",
            r"\s*of this annual report.*$",
            r"\s*of (?:our|the) (?:\d{4}\s+)?(?:annual|quarterly) report.*$",
        ):
            t = re.sub(pattern, "", t, flags=re.IGNORECASE)
        return t

    def _truncate_title(t: str) -> str:
        if len(t) <= 100:
            return t
        head = t[:100]
        return head.rsplit(" ", 1)[0] if " " in head else head

    def _canonical_title(item: str) -> str | None:
        return _CANONICAL_ITEM_TITLES.get(item.upper())

    def _content_word_count(title: str) -> int:
        words = re.findall(r"[A-Za-z]{2,}", title)
        stop = {
            "of",
            "the",
            "this",
            "that",
            "for",
            "to",
            "and",
            "our",
            "report",
            "annual",
            "quarterly",
            "form",
            "item",
            "section",
            "information",
            "discussion",
            "see",
            "refer",
        }
        return len([w for w in words if w.lower() not in stop])

    def _starts_with_cross_reference(title: str) -> bool:
        return bool(
            re.match(r"^(?:for|see|refer to|please see|as discussed|information)\b", title, re.I)
        )

    def _normalize_item_title(item: str, title: str) -> str:
        clean_title = _truncate_title(_clean_title(title)).strip()
        if item == "other":
            return clean_title

        canonical = _canonical_title(item)
        needs_fallback = (
            not clean_title
            or _starts_with_cross_reference(clean_title)
            or _content_word_count(clean_title) < 3
        )
        if needs_fallback and canonical:
            return canonical
        return clean_title or canonical or f"Item {item}"

    seen_titles: set[str] = set()

    def _title_key(title: str) -> str:
        return slugify(title, max_len=60)

    def _should_ignore_title(title: str) -> bool:
        upper = title.upper().strip()
        if "TABLE OF CONTENTS" in upper:
            return True
        if upper in {
            "PROSPECTUS",
            "PROSPECTUS SUPPLEMENT",
            "PRELIMINARY PROSPECTUS",
            "FINAL PROSPECTUS",
        }:
            return True
        if upper.startswith("PROSPECTUS DATED"):
            return True
        return False

    def _is_valid_general_heading(title: str, line: str, start: int) -> bool:
        if not title or _should_ignore_title(title):
            return False
        if line[:start].strip():
            return False
        letters = [c for c in title if c.isalpha()]
        if len(letters) < 4:
            return False
        upper_ratio = sum(c.isupper() for c in letters) / len(letters)
        if upper_ratio < 0.8:
            return False
        return True

    def _add_item_match(item: str, title: str, part: str | None, char_pos: int) -> None:
        nonlocal matches
        clean_title = _normalize_item_title(item, title)
        matches.append(
            SectionMatch(
                line_num=line_num,
                char_pos=char_pos,
                part=part,
                item=item,
                title=clean_title,
                form_type=form_type,
            )
        )

    for line_num, line in enumerate(lines):
        line_stripped = line.strip()

        if not line_stripped:
            # Keep TOC state through blank lines so split TOC tables are still ignored.
            continue

        # Arm TOC skipping when we see a TOC header.
        # Some filings use "INDEX" instead of "Table of Contents".
        if re.search(r"\btable\s+of\s+contents\b", line_stripped, flags=re.IGNORECASE) or (
            re.fullmatch(r"\s*INDEX\s*", line_stripped, flags=re.IGNORECASE)
        ):
            toc_armed = True
            in_toc_table = False
            toc_tables_seen = False

        is_table = _is_table_row(line_stripped)

        if toc_armed and is_table:
            if _looks_like_toc_row(line_stripped):
                in_toc_table = True
                toc_tables_seen = True
                continue
            if _is_table_separator_row(line_stripped):
                # Separator rows (| --- | --- |) are part of the TOC table header.
                if toc_tables_seen or not in_toc_table:
                    continue
            # Check for benign TOC table header rows (empty cells, "Page" header).
            cells = _split_table_cells(line_stripped)
            cell_text = " ".join(c.strip() for c in cells).strip()
            is_benign_header = not cell_text or re.fullmatch(
                r"[\s|]*(?:page)?[\s|]*", cell_text, re.IGNORECASE
            )
            if is_benign_header and not toc_tables_seen:
                # Tolerate blank/header rows before the first real TOC row.
                continue
            if in_toc_table:
                # Non-TOC row after TOC rows: the TOC table has ended.
                in_toc_table = False
                toc_armed = False
            elif toc_tables_seen:
                toc_armed = False
        elif toc_armed and not is_table and toc_tables_seen:
            in_toc_table = False
            toc_armed = False
        elif (
            toc_armed
            and not is_table
            and not toc_tables_seen
            and not re.search(
                r"\btable\s+of\s+contents\b|\bINDEX\b", line_stripped, flags=re.IGNORECASE
            )
        ):
            # TOC heading was not followed by TOC-like rows. Do not skip later tables.
            toc_armed = False

        # Update current_part if we see a PART heading (line or table cell).
        if is_table:
            for cell in _split_table_cells(line_stripped):
                part = _extract_part(cell)
                if part:
                    current_part = part
                    break
        else:
            pm = PART_HEADING_PATTERN.match(line_stripped)
            if pm and pm.group("part"):
                current_part = pm.group("part").upper()

        if is_general_form:
            for m in BOLD_HEADING_PATTERN.finditer(line):
                title = (m.group("title") or "").strip()
                if not _is_valid_general_heading(title, line, m.start()):
                    continue
                key = _title_key(title)
                if key in seen_titles:
                    continue
                seen_titles.add(key)
                _add_item_match(
                    item="other",
                    title=title,
                    part=None,
                    char_pos=char_offsets[line_num] + m.start(),
                )

            if line_stripped.startswith("#"):
                title = line_stripped.lstrip("#").strip()
                if _is_valid_general_heading(title, line, line.find("#")):
                    key = _title_key(title)
                    if key not in seen_titles:
                        seen_titles.add(key)
                        _add_item_match(
                            item="other",
                            title=title,
                            part=None,
                            char_pos=char_offsets[line_num],
                        )
            continue

        # Identify item headings.
        if form_upper == "8-K":
            if is_table:
                cells = _split_table_cells(line_stripped)
                for idx, cell in enumerate(cells):
                    m = _match_item_in_cell(cell, ITEM_PATTERN_8K, r"ITEM\s+\d+\.\d+\b")
                    if not m:
                        continue
                    item = m.group("item")
                    title = (m.group("title") or "").strip()
                    if not title and idx + 1 < len(cells):
                        title = cells[idx + 1]
                    _add_item_match(
                        item=item,
                        title=title,
                        part=None,
                        char_pos=char_offsets[line_num],
                    )
                    break
            else:
                m = ITEM_PATTERN_8K.match(line_stripped)
                if m and m.group("item"):
                    item = m.group("item")
                    title = (m.group("title") or "").strip()
                    _add_item_match(
                        item=item,
                        title=title,
                        part=None,
                        char_pos=char_offsets[line_num],
                    )
                # Inline scan (ordered) for concatenated headings that got flattened into one line.
                # Only consider matches far into the line to avoid duplicating proper headings.
                for m2 in re.finditer(r"ITEM\s+(?P<item>\d+\.\d+)\b", line, flags=re.IGNORECASE):
                    if m2.start() < 20:
                        continue
                    if not _is_inline_heading_boundary(line, m2.start()):
                        continue
                    tail = line[m2.start() :].strip()
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
                    m = _match_item_in_cell(cell, ITEM_PATTERN_10K, r"ITEM\s*\d+[A-Z]?\b")
                    if not m or not m.group("item"):
                        continue
                    item = m.group("item")
                    part = m.group("part") or current_part
                    if part:
                        part = part.upper()
                        current_part = part
                    title = (m.group("title") or "").strip()
                    if not title and idx + 1 < len(cells):
                        title = cells[idx + 1]
                    _add_item_match(
                        item=item,
                        title=title,
                        part=part,
                        char_pos=char_offsets[line_num],
                    )
                    break
            else:
                m = ITEM_PATTERN_10K.match(line_stripped)
                if m and m.group("item"):
                    item = m.group("item")
                    part = m.group("part") or current_part
                    if part:
                        part = part.upper()
                        current_part = part
                    title = (m.group("title") or "").strip()
                    _add_item_match(
                        item=item,
                        title=title,
                        part=part,
                        char_pos=char_offsets[line_num],
                    )
                # Inline scan (ordered) for concatenated PART/ITEM headings that got flattened.
                events: list[tuple[int, str, re.Match[str]]] = []
                for pm2 in re.finditer(r"PART\s+(?P<part>[IVX]+)\b", line, flags=re.IGNORECASE):
                    if pm2.start() < 20:
                        continue
                    if _is_inline_heading_boundary(line, pm2.start()):
                        events.append((pm2.start(), "part", pm2))
                for im2 in re.finditer(r"ITEM\s*(?P<item>\d+[A-Z]?)\b", line, flags=re.IGNORECASE):
                    if im2.start() < 20:
                        continue
                    if _is_inline_heading_boundary(line, im2.start()):
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
                if not _should_ignore_title(title):
                    _add_item_match(
                        item="other",
                        title=title,
                        part=current_part,
                        char_pos=char_offsets[line_num],
                    )

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


def _is_toc_stub(content: str) -> bool:
    """Check if section content is just a TOC table row (stub, not real content).

    A TOC stub is a section whose content is entirely or almost entirely table
    rows that look like TOC entries (ITEM/PART text + page number). These appear
    when the sectionizer picks up ITEM headings inside a Table of Contents table
    that the TOC state machine failed to skip.

    Returns False for sections with any meaningful prose, even if short.
    """
    lines = content.split("\n")
    table_lines = 0
    non_table_lines = 0
    total_non_heading_chars = 0

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Table rows and separator rows
        if stripped.startswith("|") and stripped.count("|") >= 2:
            table_lines += 1
            continue
        # Markdown heading that's just the item title (e.g., "Item 1A. Risk Factors")
        clean = re.sub(r"^#+\s*", "", stripped)
        if re.match(r"(?:PART\s+[IVX]+\s*[-–—.:]?\s*)?ITEM\s*\d+[A-Z]?\b", clean, re.I):
            continue
        non_table_lines += 1
        total_non_heading_chars += len(stripped)

    # A TOC stub has table rows and essentially no prose content.
    # If there's any non-table, non-heading text, it's real content.
    if non_table_lines > 0:
        return False
    # Pure table content with no prose: stub if all table lines look like TOC rows.
    return table_lines > 0


def _filter_toc_stubs(sections: list[Section]) -> list[Section]:
    """Remove TOC stub sections, preferring real content when IDs collide.

    When the sectionizer creates both a stub (from a TOC table row) and a real
    section with the same base ID, drop the stub so the real section keeps the
    clean ID. Stubs that don't collide with any real section are also dropped
    since they carry no useful content.
    """
    # Classify each section
    stubs: set[int] = set()
    for i, section in enumerate(sections):
        if section.id == "unknown_00":
            continue
        if _is_toc_stub(section.content):
            stubs.add(i)

    if not stubs:
        return sections

    # Drop stubs outright. By definition they contain TOC table rows only and
    # no prose, so keeping them only pollutes downstream diffs and IDs.
    return [section for i, section in enumerate(sections) if i not in stubs]


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
        return [
            Section(
                id="unknown_01",
                title="Unknown Section",
                content=markdown,
                char_start=0,
                char_end=len(markdown),
                warnings=["No section headings detected in document"],
            )
        ]

    sections: list[Section] = []
    total_len = len(markdown)

    # Check for content before first section
    first_match = matches[0]
    if first_match.char_pos > 0:
        preamble = markdown[: first_match.char_pos].strip()
        if preamble and len(preamble) > 100:  # Only if substantial
            sections.append(
                Section(
                    id="unknown_00",
                    title="Preamble",
                    content=preamble,
                    char_start=0,
                    char_end=first_match.char_pos,
                    warnings=["Content before first detected section"],
                )
            )

    # Create sections from matches
    for i, match in enumerate(matches):
        # Determine section end
        if i + 1 < len(matches):
            char_end = matches[i + 1].char_pos
        else:
            char_end = total_len

        content = markdown[match.char_pos : char_end].strip()

        sid = section_id(form_type, match.part, match.item, match.title)

        sections.append(
            Section(
                id=sid,
                title=match.title or f"Item {match.item}",
                content=content,
                char_start=match.char_pos,
                char_end=char_end,
                warnings=[],
            )
        )

    # Filter out TOC stub sections: sections whose content is just table rows
    # with page numbers and no substantial prose. When a duplicate ID exists,
    # the stub should be dropped so the real content keeps the clean ID.
    sections = _filter_toc_stubs(sections)

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
