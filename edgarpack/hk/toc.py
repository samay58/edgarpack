"""Table-of-contents parsing and page slicing for HKEX annual reports.

The build path locates each disclosed statement by reading the annual report's
own table of contents rather than a hardcoded page map. Two shapes appear in
real filings: the printed page number leads the title (Tencent, BYD) or trails
it (Meituan). Printed page numbers do not equal pypdf page indices, so each
entry's index is recovered by anchor search: look for the entry's own title
text in a narrow window around the naive index and take the nearest match.
Verified offsets across FY2025 filings of Tencent, Meituan, BYD, Anta and HSBC
were 0, +1 and -1.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


class HKSectioningError(ValueError):  # noqa: N818
    """The financial statements could not be located from the TOC.

    Raised when neither per-statement TOC entries nor a coarse
    financial-statements chapter yield locatable statements. Naming what was
    found is deliberate: a garbled (image-only) filing must fail loudly, never
    silently produce a pack with no statements and no explanation.
    """


@dataclass(frozen=True)
class TocEntry:
    title: str
    printed_page: int


@dataclass(frozen=True)
class Section:
    section_id: str | None
    title: str
    start_index: int
    end_index: int
    text: str


# Section ids that carry the financial statements. Mirrors the financial set in
# hk/extract.py; kept local so the has-statements check does not depend on a
# private name from a module this packet does not own.
_FINANCIAL_SECTION_IDS: frozenset[str] = frozenset(
    {
        "hkex_income_statement",
        "hkex_balance_sheet",
        "hkex_cash_flow",
        "hkex_comprehensive_income",
        "hkex_equity_changes",
    }
)

_LEAD_RE = re.compile(r"^\s*(\d{1,3})\s+(.+?)\s*$")
_TRAIL_RE = re.compile(r"^\s*(.+?)\s+(\d{1,3})\s*$")
# First run of CJK characters on a bilingual TOC line (BYD): the English title
# ends where the Chinese begins.
_CJK_RE = re.compile(r"[　-鿿＀-￯]")
# Trailing words that leave a title grammatically open, so the next unnumbered
# line is its continuation (Anta wraps "Consolidated Statement of" onto a
# second line).
_CONTINUATION_CONNECTORS = frozenset(
    {"of", "and", "the", "to", "for", "in", "or", "on", "with", "a", "an", "&"}
)


def _has_alpha_word(text: str) -> bool:
    return bool(re.search(r"[A-Za-z]{2,}", text))


def _english_title(title: str) -> str:
    match = _CJK_RE.search(title)
    if match:
        title = title[: match.start()]
    return re.sub(r"\s+", " ", title).strip()


def _norm(text: str) -> str:
    """Alphanumeric-only upper-case form for heading comparison.

    Collapses whitespace, curly quotes and punctuation so "CHAIRMAN 'S
    STATEMENT" matches "CHAIRMAN'S STATEMENT", while keeping "Balance Sheet"
    distinct from "Consolidated Balance Sheet" (so BYD's PRC parent-company
    statements never collide with the consolidated ones).
    """
    return re.sub(r"[^A-Za-z0-9]", "", text).upper()


def _is_continuation(prev: TocEntry, title: str) -> bool:
    if not _has_alpha_word(title):
        return False
    words = title.split()
    # A continuation is a short wrapped title fragment, not a body paragraph.
    if len(words) > 6 or title.rstrip().endswith("."):
        return False
    if title[0].islower():
        return True
    prev_words = prev.title.split()
    if not prev_words:
        return False
    prev_last = re.sub(r"[^A-Za-z&]", "", prev_words[-1]).lower()
    return prev_last in _CONTINUATION_CONNECTORS or prev.title.rstrip().endswith(",")


def parse_toc(text: str) -> list[TocEntry]:
    """Parse a TOC page's raw text into (title, printed_page) entries."""
    lines = text.split("\n")
    lead_hits = trail_hits = 0
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        lead = _LEAD_RE.match(stripped)
        if lead and _has_alpha_word(lead.group(2)):
            lead_hits += 1
        trail = _TRAIL_RE.match(stripped)
        if trail and _has_alpha_word(trail.group(1)):
            trail_hits += 1
    leading = lead_hits >= trail_hits

    entries: list[TocEntry] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if leading:
            match = _LEAD_RE.match(stripped)
            title_group, page_group = (2, 1)
        else:
            match = _TRAIL_RE.match(stripped)
            title_group, page_group = (1, 2)
        if match and _has_alpha_word(match.group(title_group)):
            entries.append(
                TocEntry(_english_title(match.group(title_group)), int(match.group(page_group)))
            )
            continue
        # No page number on this line: fold it into the previous entry's title
        # when it reads as a wrapped continuation.
        fragment = _english_title(stripped)
        if entries and _is_continuation(entries[-1], fragment):
            prev = entries[-1]
            entries[-1] = TocEntry(f"{prev.title} {fragment}".strip(), prev.printed_page)
    return entries


def find_toc_page_indices(
    page_texts: list[str], *, max_scan: int = 15, min_entries: int = 5
) -> list[int]:
    """Locate the TOC page: the earliest page yielding the most parsed entries."""
    best_index = -1
    best_count = 0
    for i in range(min(max_scan, len(page_texts))):
        count = len(parse_toc(page_texts[i]))
        if count > best_count:
            best_index, best_count = i, count
    if best_count >= min_entries:
        return [best_index]
    return []


def resolve_entry_index(entry: TocEntry, page_texts: list[str], *, window: int = 3) -> int | None:
    """Recover the 0-based pypdf index for a TOC entry by anchor search.

    Searches indices nearest to the naive index first, matching the entry's
    full normalized title against each page's text. Returns None when the title
    text cannot be found in the window (e.g. an image-only, garbled statement
    page), so the caller drops the entry rather than slicing at a wrong page.
    """
    target = _norm(entry.title)
    if not target:
        return None
    naive = entry.printed_page
    order = [naive]
    for delta in range(1, window + 1):
        order.append(naive - delta)
        order.append(naive + delta)
    for index in order:
        if 0 <= index < len(page_texts) and target in _norm(page_texts[index]):
            return index
    return None


def _slice_text(page_texts: list[str], start: int, end: int) -> str:
    return "\n".join(page_texts[start:end])


def _coarse_financial_fallback(
    entries: list[TocEntry],
    page_texts: list[str],
    norm_map: dict[str, str],
) -> list[Section]:
    """Locate statements inside a single 'Financial statements' chapter.

    HSBC groups every statement under one chapter with no per-statement TOC
    entry. Find that chapter's page range and scan it for statement headings
    from the keyword map. Returns [] when no chapter is found or no headings
    surface, leaving the caller to fail loudly.
    """
    chapter_pos = None
    for i, entry in enumerate(entries):
        norm_title = _norm(entry.title)
        if "FINANCIALSTATEMENTS" in norm_title and "NOTES" not in norm_title:
            chapter_pos = i
            break
    if chapter_pos is None:
        return []

    chapter = entries[chapter_pos]
    start = resolve_entry_index(chapter, page_texts)
    if start is None:
        start = chapter.printed_page
    if not (0 <= start < len(page_texts)):
        return []
    end = len(page_texts)
    if chapter_pos + 1 < len(entries):
        nxt = entries[chapter_pos + 1]
        nxt_index = resolve_entry_index(nxt, page_texts)
        end = nxt_index if nxt_index is not None else min(nxt.printed_page, len(page_texts))
    end = max(end, start + 1)

    found: list[tuple[str, int]] = []
    seen: set[str] = set()
    for index in range(start, min(end, len(page_texts))):
        for line in page_texts[index].split("\n"):
            sid = norm_map.get(_norm(line))
            if sid in _FINANCIAL_SECTION_IDS and sid not in seen:
                seen.add(sid)
                found.append((sid, index))
    found.sort(key=lambda pair: pair[1])
    sections: list[Section] = []
    for i, (sid, page_index) in enumerate(found):
        section_end = found[i + 1][1] if i + 1 < len(found) else end
        sections.append(
            Section(
                section_id=sid,
                title=sid,
                start_index=page_index,
                end_index=section_end,
                text=_slice_text(page_texts, page_index, section_end),
            )
        )
    return sections


def slice_sections(
    page_texts: list[str],
    section_map: dict[str, str],
    *,
    toc_page_indices: list[int] | None = None,
) -> list[Section]:
    """Slice a report's pages into sections at its TOC boundaries.

    Only entries whose title maps through ``section_map`` become sections;
    unmapped entries (cover pages, definitions, BYD's parent-only statements)
    are skipped but still bound the ranges of their neighbours. Raises
    HKSectioningError when no financial statements can be located.
    """
    if toc_page_indices is None:
        toc_page_indices = find_toc_page_indices(page_texts)
    if not toc_page_indices:
        raise HKSectioningError(
            "No table-of-contents page found in the first pages of the filing; "
            "cannot locate section boundaries."
        )
    toc_text = "\n".join(page_texts[i] for i in toc_page_indices)
    entries = parse_toc(toc_text)

    resolved: list[tuple[TocEntry, int]] = []
    for entry in entries:
        index = resolve_entry_index(entry, page_texts)
        if index is not None:
            resolved.append((entry, index))
    resolved.sort(key=lambda pair: pair[1])

    norm_map = {_norm(key): value for key, value in section_map.items()}

    sections: list[Section] = []
    for i, (entry, start) in enumerate(resolved):
        end = resolved[i + 1][1] if i + 1 < len(resolved) else len(page_texts)
        end = max(end, start + 1)
        section_id = norm_map.get(_norm(entry.title))
        if section_id is None:
            continue
        sections.append(
            Section(
                section_id=section_id,
                title=entry.title,
                start_index=start,
                end_index=end,
                text=_slice_text(page_texts, start, end),
            )
        )

    if not any(section.section_id in _FINANCIAL_SECTION_IDS for section in sections):
        fallback = _coarse_financial_fallback(entries, page_texts, norm_map)
        if not fallback:
            found_titles = [entry.title for entry, _ in resolved] or [e.title for e in entries]
            raise HKSectioningError(
                "No financial statements could be located from the TOC or a "
                "coarse financial-statements chapter. Titles found: "
                f"{found_titles[:20]}. The filing is likely image-only/garbled; "
                "OCR is out of scope for this build path."
            )
        sections.extend(fallback)
        sections.sort(key=lambda section: section.start_index)

    return sections
