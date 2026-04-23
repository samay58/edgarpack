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

__all__ = ["extract_toc_sections", "inject_s1_headings"]

_TOC_LINK_RE = re.compile(
    r'<a\s+[^>]*href="#([^"]+)"[^>]*>([^<]+)</a>',
    re.IGNORECASE,
)

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
    # Pure numeric page numbers (1, 23, 178) or roman-numeral page refs.
    if title.isdigit() or _ROMAN_NUMERAL_RE.match(title):
        return False
    return True


def extract_toc_sections(html: str) -> list[tuple[str, str]]:
    """Return [(anchor_id, section_title)] for every distinct TOC-style link.

    One (anchor_id, title) pair per unique anchor; the first occurrence wins
    so repeated body cross-references don't override the TOC mapping.
    """
    seen_anchors: set[str] = set()
    pairs: list[tuple[str, str]] = []
    for anchor, raw_title in _TOC_LINK_RE.findall(html):
        title = _clean_title(raw_title)
        if not _is_section_title(title):
            continue
        if anchor in seen_anchors:
            continue
        seen_anchors.add(anchor)
        pairs.append((anchor, title))
    return pairs


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
        pattern = re.compile(
            rf'(<[a-z][a-z0-9]*\s+[^>]*\bid="{re.escape(anchor)}"[^>]*>)',
            re.IGNORECASE,
        )
        replacement = rf"<h2>{safe_title}</h2>\1"
        result = pattern.sub(replacement, result, count=1)
    return result
