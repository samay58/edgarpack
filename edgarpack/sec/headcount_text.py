"""Text-scan fallback for employee counts in SEC 10-K / 20-F filings.

Used when dei:EntityNumberOfEmployees is not disclosed as XBRL. The regex
is deliberately simple: find the first 'N employees' phrase whose integer
value falls within bounded expectations.
"""

from __future__ import annotations

import re

_PATTERN = re.compile(
    r"(?:approximately\s+)?(\d{1,3}(?:,\d{3})*|\d+)\s+(?:full[\s\-]time\s+)?employees",
    re.IGNORECASE,
)

_MIN = 50
_MAX = 5_000_000


def scan_headcount_from_text(text: str) -> int | None:
    """Return the first in-bounds employee-count integer, or None."""
    for m in _PATTERN.finditer(text):
        raw = m.group(1).replace(",", "")
        try:
            value = int(raw)
        except ValueError:
            continue
        if _MIN <= value <= _MAX:
            return value
    return None
