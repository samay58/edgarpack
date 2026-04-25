"""Models for static filing diff reports."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .models import ChangeType

ChunkStatus = Literal["available", "missing", "partial"]
ParagraphGroupKind = Literal["changed", "context", "collapsed"]
ReportKind = Literal["pair", "timeline_pair"]
SpanOp = Literal["equal", "insert", "delete", "replace"]
SpanSide = Literal["old", "new"]


class FilingSourceRef(BaseModel):
    accession: str
    cik: str = ""
    company_name: str = ""
    form_type: str = ""
    filing_date: str = ""
    source_url: str | None = None
    pack_dir: str


class SectionSourceRef(BaseModel):
    section_id: str
    title: str
    path: str
    char_start: int = 0
    char_end: int = 0
    sha256: str = ""


class EvidenceAnchor(BaseModel):
    accession: str
    section_id: str
    section_path: str
    paragraph_index: int
    char_start: int
    char_end: int
    chunk_id: str | None = None


class TextSpan(BaseModel):
    side: SpanSide
    op: SpanOp
    text: str


class ReportParagraphDelta(BaseModel):
    change_type: ChangeType
    old_anchor: EvidenceAnchor | None = None
    new_anchor: EvidenceAnchor | None = None
    old_text: str | None = None
    new_text: str | None = None
    old_spans: list[TextSpan] = Field(default_factory=list)
    new_spans: list[TextSpan] = Field(default_factory=list)
    similarity: float = 0.0
    old_word_count: int = 0
    new_word_count: int = 0


class ParagraphGroup(BaseModel):
    kind: ParagraphGroupKind
    paragraphs: list[ReportParagraphDelta] = Field(default_factory=list)
    collapsed_count: int = 0
    collapsed_word_count: int = 0


class ReportSectionDelta(BaseModel):
    section_id: str
    title: str
    change_type: ChangeType
    old_ref: SectionSourceRef | None = None
    new_ref: SectionSourceRef | None = None
    paragraphs_added: int = 0
    paragraphs_removed: int = 0
    paragraphs_modified: int = 0
    paragraphs_unchanged: int = 0
    change_intensity: float = 0.0
    interest_score: float = 0.0
    groups: list[ParagraphGroup] = Field(default_factory=list)


class DiffReport(BaseModel):
    report_kind: ReportKind = "pair"
    before_source: FilingSourceRef
    after_source: FilingSourceRef
    chunk_status: ChunkStatus = "missing"
    sections_unchanged: int = 0
    sections_modified: int = 0
    sections_added: int = 0
    sections_removed: int = 0
    overall_change_intensity: float = 0.0
    sections: list[ReportSectionDelta] = Field(default_factory=list)


class TimelineReportEntry(BaseModel):
    accession: str
    form_type: str
    filing_date: str
    pack_dir: str


class TimelineTransition(BaseModel):
    index: int
    before: TimelineReportEntry
    after: TimelineReportEntry
    output_file: str
    sections_added: int = 0
    sections_removed: int = 0
    sections_modified: int = 0
    sections_unchanged: int = 0
    overall_change_intensity: float = 0.0


class TimelineReport(BaseModel):
    cik: str
    entries: list[TimelineReportEntry] = Field(default_factory=list)
    transitions: list[TimelineTransition] = Field(default_factory=list)
