"""Language shift detection: flag sections with abnormally high change rates."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from ..diff.models import ChangeType
from ..diff.section_diff import diff_filings


class LanguageShift(BaseModel):
    """A section with unusually high language change."""

    section_id: str
    title: str
    change_intensity: float
    paragraphs_added: int
    paragraphs_removed: int
    paragraphs_modified: int
    company: str
    form_type: str
    before_date: str
    after_date: str


def detect_language_shifts(
    before_dir: Path,
    after_dir: Path,
    threshold: float = 0.25,
) -> list[LanguageShift]:
    """Flag sections where change intensity exceeds the threshold.

    A typical year-over-year 10-K section changes ~10-15% of paragraphs.
    Sections exceeding the threshold are flagged as language shifts.

    Args:
        before_dir: Earlier filing pack directory
        after_dir: Later filing pack directory
        threshold: Change intensity threshold (default 0.25 = 25%)

    Returns:
        List of LanguageShift objects sorted by intensity (descending)
    """
    result = diff_filings(before_dir, after_dir)
    shifts: list[LanguageShift] = []

    for delta in result.section_deltas:
        if delta.change_type != ChangeType.MODIFIED:
            continue
        if delta.change_intensity < threshold:
            continue

        shifts.append(
            LanguageShift(
                section_id=delta.section_id,
                title=delta.title,
                change_intensity=delta.change_intensity,
                paragraphs_added=delta.paragraphs_added,
                paragraphs_removed=delta.paragraphs_removed,
                paragraphs_modified=delta.paragraphs_modified,
                company=result.company,
                form_type=result.form_type,
                before_date=result.before_date,
                after_date=result.after_date,
            )
        )

    shifts.sort(key=lambda s: s.change_intensity, reverse=True)
    return shifts
