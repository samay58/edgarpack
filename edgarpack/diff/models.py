"""Data models for the diff engine."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class ChangeType(StrEnum):
    UNCHANGED = "unchanged"
    MODIFIED = "modified"
    ADDED = "added"
    REMOVED = "removed"


class ParagraphDelta(BaseModel):
    """A single paragraph-level change."""

    change_type: ChangeType
    old_text: str | None = None
    new_text: str | None = None
    similarity: float = 0.0
    old_word_count: int = 0
    new_word_count: int = 0
    is_boilerplate: bool = False


class SectionDelta(BaseModel):
    """Change information for a single section across two filings."""

    section_id: str
    title: str
    change_type: ChangeType
    section_type: str = "prose"
    paragraphs_added: int = 0
    paragraphs_removed: int = 0
    paragraphs_modified: int = 0
    paragraphs_unchanged: int = 0
    change_intensity: float = 0.0
    interest_score: float = 0.0
    paragraph_deltas: list[ParagraphDelta] = Field(default_factory=list)


class DiffResult(BaseModel):
    """Result of diffing two filings."""

    company: str
    form_type: str
    before_accession: str
    before_date: str
    after_accession: str
    after_date: str
    sections_unchanged: int = 0
    sections_modified: int = 0
    sections_added: int = 0
    sections_removed: int = 0
    overall_change_intensity: float = 0.0
    section_deltas: list[SectionDelta] = Field(default_factory=list)
