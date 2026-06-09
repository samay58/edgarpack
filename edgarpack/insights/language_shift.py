"""Language shift detection: flag sections with abnormally high change rates."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from ..diff.models import ChangeType, ParagraphDelta
from ..diff.section_diff import diff_filings


class LanguageShift(BaseModel):
    """A section with unusually high language change."""

    section_id: str
    title: str
    change_intensity: float
    paragraphs_added: int
    paragraphs_removed: int
    paragraphs_modified: int
    words_changed: int = 0
    words_total: int = 0
    company: str
    form_type: str
    before_date: str
    after_date: str
    paragraph_deltas: list[ParagraphDelta] = Field(default_factory=list)


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

        # Compute word-level metrics for traceability
        words_changed = 0
        words_total = 0
        for pd in delta.paragraph_deltas:
            w = max(pd.old_word_count, pd.new_word_count)
            words_total += w
            if pd.is_boilerplate:
                continue
            if pd.change_type == ChangeType.MOVED:
                # Movement is not language shift; edits inside moved paragraphs
                # are below the signal bar for this insight.
                continue
            if pd.change_type in {ChangeType.ADDED, ChangeType.REMOVED}:
                words_changed += w
            elif pd.change_type == ChangeType.MODIFIED:
                words_changed += int(round(w * (1.0 - pd.similarity)))

        # Only include non-unchanged deltas to keep payload manageable
        changed_deltas = [
            pd for pd in delta.paragraph_deltas if pd.change_type != ChangeType.UNCHANGED
        ]

        shifts.append(
            LanguageShift(
                section_id=delta.section_id,
                title=delta.title,
                change_intensity=delta.change_intensity,
                paragraphs_added=delta.paragraphs_added,
                paragraphs_removed=delta.paragraphs_removed,
                paragraphs_modified=delta.paragraphs_modified,
                words_changed=words_changed,
                words_total=words_total,
                company=result.company,
                form_type=result.form_type,
                before_date=result.before_date,
                after_date=result.after_date,
                paragraph_deltas=changed_deltas,
            )
        )

    shifts.sort(key=lambda s: s.change_intensity, reverse=True)
    return shifts
