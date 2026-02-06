"""Reduce HTML to a simpler, more semantic subset.

EdgarPack's markdown renderer is regex-based and intentionally lightweight.
This module provides a minimal pre-pass that:

- Normalizes common presentational tags (b/i/u -> strong/em)
- Normalizes inline code-like tags to <code>
- Makes links absolute (optional)
- Unwraps unsafe/empty links (javascript:, empty href)

It avoids full DOM parsing dependencies to keep the core pipeline portable.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin


_TAG_RENAMES: dict[str, str] = {
    "b": "strong",
    "i": "em",
    "u": "em",
    "tt": "code",
    "kbd": "code",
    "samp": "code",
    "var": "code",
}

_UNWRAP_TAGS = {
    "s",
    "strike",
    "del",
    "ins",
    "mark",
    "small",
    "big",
    "font",
    "center",
}


def reduce_to_semantic(html: str, base_url: str | None = None) -> str:
    """Reduce cleaned HTML into a smaller semantic subset."""
    result = html

    # Rename presentational tags to semantic equivalents.
    for src, dst in _TAG_RENAMES.items():
        result = re.sub(rf"<\s*{src}\b", f"<{dst}", result, flags=re.IGNORECASE)
        result = re.sub(rf"</\s*{src}\s*>", f"</{dst}>", result, flags=re.IGNORECASE)

    # Unwrap tags we don't want to render explicitly (keep text content).
    for tag in _UNWRAP_TAGS:
        result = re.sub(rf"<\s*{tag}\b[^>]*>", "", result, flags=re.IGNORECASE)
        result = re.sub(rf"</\s*{tag}\s*>", "", result, flags=re.IGNORECASE)

    # Make links absolute if requested.
    if base_url:
        def _abs_href(match: re.Match) -> str:
            href = match.group(1)
            if not href:
                return 'href=""'
            href_stripped = href.strip()
            if href_stripped.startswith(("#", "javascript:", "mailto:")):
                return f'href="{href_stripped}"'
            try:
                return f'href="{urljoin(base_url, href_stripped)}"'
            except Exception:
                return f'href="{href_stripped}"'

        result = re.sub(
            r'href=["\']([^"\']*)["\']',
            _abs_href,
            result,
            flags=re.IGNORECASE,
        )

    # Unwrap empty/javascript links: <a ...>text</a> -> text
    result = re.sub(
        r'<a\b[^>]*href=["\'](?:\s*|javascript:[^"\']*)["\'][^>]*>(.*?)</a>',
        r"\1",
        result,
        flags=re.IGNORECASE | re.DOTALL,
    )

    return result


def simplify_html(html: str, base_url: str | None = None) -> str:
    """Full HTML simplification pipeline.

    Combines iXBRL stripping, cleaning, and semantic reduction.
    """
    from .html_clean import clean_html
    from .ixbrl_strip import strip_ixbrl

    html = strip_ixbrl(html)
    html = clean_html(html)
    html = reduce_to_semantic(html, base_url)
    return html

