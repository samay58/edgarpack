"""Inject semantic section headings into SEC S-1 HTML by reading the TOC.

SEC S-1 filings from Cerebras-era renderers use absolute-positioned divs and
inline <font> tags rather than <h1>/<h2> elements. Body text contains no
large-font section titles; instead the document has a Table of Contents at
the top with `<a href="#anchor_id">Section Title</a>` links, and each body
section carries `id="anchor_id"` on its container div.

This module turns those invisible structural cues into explicit <h2> tags so
the downstream sectionizer can recognize them. Only activated for
registration-class filings from `pack/build.py`.

The alternative (inferring headings from font-size / font-weight) fails on
Cerebras because the largest body font is 12pt and the headings are split
across multiple <font> tags at the same size as surrounding body text.
"""

from __future__ import annotations

import html as _html_mod
import re
from dataclasses import dataclass
from html.parser import HTMLParser

__all__ = ["extract_toc_sections", "inject_s1_headings"]

# Titles that appear as links but are not section headings: TOC self-links,
# pagination markers, generic cross-references.
_TITLE_BLACKLIST = frozenset(
    {
        "table of contents",
        "index",
        "top",
        "back to top",
        "page",
        "next",
        "prev",
        "previous",
    }
)

# Pattern for TOC leader dots ("Section Title .......... 12") that sometimes
# come through as the entire link text.
_LEADER_DOTS_RE = re.compile(r"\s*\.{3,}\s*")
_ROMAN_NUMERAL_RE = re.compile(r"^[ivxlcdm]+$", re.IGNORECASE)
_FINANCIAL_STATEMENT_PAGE_RE = re.compile(r"^[Ff]-\d+$")


@dataclass(frozen=True)
class _TocLink:
    anchor: str
    title: str


class _TocAnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[_TocLink] = []
        self._anchor: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a" or self._anchor is not None:
            return
        attr_dict = {name.lower(): value or "" for name, value in attrs}
        href = attr_dict.get("href", "").strip()
        if not href.startswith("#") or len(href) <= 1:
            return
        self._anchor = href[1:]
        self._text = []

    def handle_data(self, data: str) -> None:
        if self._anchor is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._anchor is None:
            return
        self.links.append(_TocLink(anchor=self._anchor, title="".join(self._text)))
        self._anchor = None
        self._text = []


def _clean_title(title: str) -> str:
    """Normalize a link's text: decode entities, drop leader dots, collapse whitespace."""
    decoded = _html_mod.unescape(title)
    decoded = _LEADER_DOTS_RE.sub(" ", decoded)
    return re.sub(r"\s+", " ", decoded).strip()


def _is_section_title(title: str) -> bool:
    if not title or len(title) < 3:
        return False
    if title.lower() in _TITLE_BLACKLIST:
        return False
    if _FINANCIAL_STATEMENT_PAGE_RE.fullmatch(title):
        return False
    # Pure numeric page numbers (1, 23, 178) or roman-numeral page refs.
    if title.isdigit() or _ROMAN_NUMERAL_RE.match(title):
        return False
    return True


def extract_toc_sections(html: str) -> list[tuple[str, str]]:
    """Return [(anchor_id, section_title)] for every distinct TOC-style link.

    One (anchor_id, title) pair per unique anchor; the first occurrence wins
    so repeated body cross-references don't override the TOC mapping.
    """
    parser = _TocAnchorParser()
    try:
        parser.feed(html)
        parser.close()
    except (AssertionError, UnicodeDecodeError):
        return []

    seen_anchors: set[str] = set()
    pairs: list[tuple[str, str]] = []
    for link in parser.links:
        title = _clean_title(link.title)
        if not _is_section_title(title):
            continue
        if link.anchor in seen_anchors:
            continue
        seen_anchors.add(link.anchor)
        pairs.append((link.anchor, title))
    return pairs


def _target_pattern(anchor: str) -> re.Pattern[str]:
    quoted = re.escape(anchor)
    attr_value = rf'(?:="{quoted}"|=\'{quoted}\'|={quoted})(?=\s|/?>)'
    return re.compile(
        rf"(<[a-z][a-z0-9]*\b(?=[^>]*\b(?:id|name)\s*{attr_value})[^>]*>)",
        re.IGNORECASE,
    )


def _insertion_index_before_target(html: str, target_start: int) -> int:
    prefix = html[:target_start]
    last_p: re.Match[str] | None = None
    for match in re.finditer(r"<p\b[^>]*>", prefix, flags=re.IGNORECASE):
        last_p = match
    if last_p is None:
        return target_start
    last_close = prefix.rfind("</p>")
    if last_close > last_p.start():
        return target_start
    return last_p.start()


def _inject_heading_once(html: str, pattern: re.Pattern[str], heading_html: str) -> str:
    match = pattern.search(html)
    if match is None:
        return html
    insert_at = _insertion_index_before_target(html, match.start(1))
    return html[:insert_at] + heading_html + html[insert_at:]


def inject_s1_headings(html: str) -> str:
    """Return HTML with `<h2>Title</h2>` injected before every TOC-target id.

    A no-op when the document has no TOC links or no matching ids. Safe to
    run on periodic filings as a defensive measure; those typically have
    either zero TOC anchors or such different structure that no replacement
    fires.
    """
    pairs = extract_toc_sections(html)
    if not pairs:
        return html

    result = html
    for anchor, title in pairs:
        # Find the first element carrying id="anchor" and inject <h2> before it.
        # Escaping the title for HTML context so entities like & render safely.
        safe_title = _html_mod.escape(title, quote=False)
        pattern = _target_pattern(anchor)
        result = _inject_heading_once(result, pattern, f"<h2>{safe_title}</h2>")
    return result
