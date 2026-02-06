"""Strip iXBRL tags and namespaces from HTML."""

import re


# iXBRL namespace prefixes
IXBRL_PREFIXES = [
    "ix:",
    "xbrli:",
    "xbrldi:",
    "xbrldt:",
    "link:",
    "xlink:",
    "iso4217:",
    "dei:",
    "us-gaap:",
    "srt:",
    "country:",
]

# Pattern to match iXBRL tags
IXBRL_TAG_PATTERN = re.compile(
    r"</?(" + "|".join(re.escape(p) for p in IXBRL_PREFIXES) + r")[^>]*>",
    re.IGNORECASE | re.DOTALL,
)

# Pattern to match xmlns declarations for iXBRL
XMLNS_PATTERN = re.compile(
    r'\s+xmlns(?::[a-zA-Z0-9_-]+)?="[^"]*(?:xbrl|ixbrl|fasb|sec\.gov)[^"]*"',
    re.IGNORECASE,
)


def strip_ixbrl(html: str) -> str:
    """Remove iXBRL tags and namespaces from HTML.

    Preserves text content inside iXBRL tags while removing the tags themselves.
    Also removes iXBRL-related namespace declarations.

    Args:
        html: Raw HTML string potentially containing iXBRL

    Returns:
        HTML with iXBRL elements removed
    """
    # First pass: use regex to remove iXBRL tags while preserving content
    # This handles nested iXBRL tags correctly
    result = IXBRL_TAG_PATTERN.sub("", html)

    # Remove xmlns declarations for iXBRL namespaces
    result = XMLNS_PATTERN.sub("", result)

    # Clean up any double spaces left behind
    result = re.sub(r"  +", " ", result)

    return result


def strip_ixbrl_selectolax(html: str) -> str:
    """Compatibility alias for older implementations.

    EdgarPack previously had a DOM-based implementation here. The current
    regex approach is faster and more reliable for namespaced iXBRL tags.
    """
    return strip_ixbrl(html)


def has_ixbrl(html: str) -> bool:
    """Check if HTML contains iXBRL content.

    Args:
        html: HTML string to check

    Returns:
        True if iXBRL content detected
    """
    # Quick check for common iXBRL indicators
    html_lower = html.lower()
    return any([
        "ix:" in html_lower,
        "xbrli:" in html_lower,
        "inline xbrl" in html_lower,
        'xmlns:ix="' in html_lower,
    ])
