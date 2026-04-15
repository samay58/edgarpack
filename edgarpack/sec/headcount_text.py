"""Text-scan fallback for employee counts in SEC 10-K / 20-F filings.

Used when dei:EntityNumberOfEmployees is not disclosed as XBRL. Rejects
comparative phrasing ("more than N", "fewer than N", etc.) via negative
lookbehinds so approximate ranges are not reported as precise counts.

HEADCOUNT_PATTERN and the bounds constants are also imported by
edgarpack/hk/extract.py so both paths share a single canonical pattern.
"""

from __future__ import annotations

import re

HEADCOUNT_PATTERN = re.compile(
    r"(?<!less than )(?<!fewer than )(?<!more than )(?<!over )"
    r"(?:approximately\s+)?(\d{1,3}(?:,\d{3})*|\d+)"
    r"[^\S\n]+(?:full[^\S\n]*-?[^\S\n]*time[^\S\n]+)?employees",
    re.IGNORECASE,
)

HEADCOUNT_MIN = 50
HEADCOUNT_MAX = 5_000_000

# Keep private aliases so any remaining internal references still work.
_PATTERN = HEADCOUNT_PATTERN
_MIN = HEADCOUNT_MIN
_MAX = HEADCOUNT_MAX


def scan_headcount_from_text(text: str) -> int | None:
    """Return the first in-bounds employee-count integer, or None."""
    for m in HEADCOUNT_PATTERN.finditer(text):
        raw = m.group(1).replace(",", "")
        try:
            value = int(raw)
        except ValueError:
            continue
        if HEADCOUNT_MIN <= value <= HEADCOUNT_MAX:
            return value
    return None
