"""Section-level diff engine for filing comparison."""

from .models import ChangeType, DiffResult, ParagraphDelta, SectionDelta
from .section_diff import diff_filings
from .text_diff import diff_paragraphs
from .timeline import TimelineEntry, build_timeline

__all__ = [
    "ChangeType",
    "DiffResult",
    "ParagraphDelta",
    "SectionDelta",
    "TimelineEntry",
    "build_timeline",
    "diff_filings",
    "diff_paragraphs",
]
