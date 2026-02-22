"""China Lens domain and API models.

These models intentionally preserve provenance and citation links so findings can
be audited end-to-end.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    """Return timezone-aware UTC timestamp."""
    return datetime.now(UTC)


class ExtractionMethod(StrEnum):
    EMBEDDED_TEXT = "embedded_text"
    OCR = "ocr"


class CoverageStatus(StrEnum):
    PENDING = "pending"
    PARTIAL = "partial"
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"


class FindingStatus(StrEnum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"


class PackStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    READY = "ready"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELED = "canceled"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class PipelineStage(StrEnum):
    DOWNLOAD = "download"
    EXTRACT = "extract"
    TRANSLATE = "translate"
    SUMMARIZE = "summarize"
    INDEX = "index"


PIPELINE_STAGES: tuple[PipelineStage, ...] = (
    PipelineStage.DOWNLOAD,
    PipelineStage.EXTRACT,
    PipelineStage.TRANSLATE,
    PipelineStage.SUMMARIZE,
    PipelineStage.INDEX,
)


class Company(BaseModel):
    id: str
    display_name_en: str
    display_name_zh: str
    ticker: str
    exchange: str
    aliases: list[str] = Field(default_factory=list)


class Document(BaseModel):
    id: str
    company_id: str
    title: str
    filing_type: str
    filing_date: str
    source: str
    source_url: str
    file_hash: str
    pages: int
    language: str
    acquired_at: datetime
    acquisition_log_id: str


class EvidenceChunk(BaseModel):
    id: str
    doc_id: str
    page_start: int
    page_end: int
    text_zh: str
    text_en: str
    language: str
    extraction_method: ExtractionMethod
    confidence: float = Field(ge=0.0, le=1.0)
    char_start: int | None = None
    char_end: int | None = None
    bbox: dict[str, float] | None = None
    embedding_model: str = ""
    embedding: list[float] = Field(default_factory=list)


class CitationRef(BaseModel):
    chunk_id: str
    doc_id: str
    page: int
    quote_start: int = 0
    quote_end: int = 0
    citation_label: str


class Finding(BaseModel):
    id: str
    pack_id: str
    section_id: str
    claim_text: str
    claim_type: str
    key_numbers: list[str] = Field(default_factory=list)
    citations: list[CitationRef] = Field(default_factory=list)
    status: FindingStatus = FindingStatus.SUPPORTED
    unknown_reason: str = ""


class PackSection(BaseModel):
    id: str
    title: str
    thesis: str
    key_points: list[str] = Field(default_factory=list)
    key_tables: list[list[str]] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    coverage_status: CoverageStatus = CoverageStatus.PENDING
    updated_at: datetime = Field(default_factory=utc_now)


class Pack(BaseModel):
    id: str
    company_id: str
    created_at: datetime
    updated_at: datetime
    doc_set: list[str]
    time_range: str
    translation_mode: str
    template: str
    status: PackStatus
    sections: list[PackSection] = Field(default_factory=list)
    build_logs: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class PackJob(BaseModel):
    id: str
    pack_id: str
    status: JobStatus
    stage: PipelineStage
    stage_progress: dict[PipelineStage, int] = Field(default_factory=dict)
    progress_pct: int = 0
    cancel_requested: bool = False
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime | None = None
    stage_logs: list[str] = Field(default_factory=list)


class AcquisitionEvent(BaseModel):
    id: str
    company_id: str
    source: str
    source_url: str
    occurred_at: datetime
    file_hash: str
    outcome: str
    details: str


class CreatePackRequest(BaseModel):
    company_id: str
    time_range: str = "last annual + last 2 interim"
    doc_selection: list[str] = Field(default_factory=list)
    translation_mode: str = "key_sections"
    template: str = "Investor diligence"


class CreatePackResponse(BaseModel):
    pack_id: str
    job_id: str
    status: PackStatus


class PackStatusResponse(BaseModel):
    pack_id: str
    job_id: str
    status: JobStatus
    stage: PipelineStage
    progress_pct: int
    stage_progress: dict[PipelineStage, int]
    cancel_requested: bool
    logs: list[str]


class SearchEvidenceRequest(BaseModel):
    query: str
    company_id: str | None = None
    pack_id: str | None = None
    limit: int = Field(default=10, ge=1, le=50)


class SearchEvidenceHit(BaseModel):
    chunk_id: str
    doc_id: str
    page: int
    score: float
    text_zh: str
    text_en: str
    citation_label: str


class SearchEvidenceResponse(BaseModel):
    hits: list[SearchEvidenceHit]


class AskRequest(BaseModel):
    question: str
    company_id: str
    pack_id: str | None = None
    top_k: int = Field(default=6, ge=1, le=20)


class AskAnswerBlock(BaseModel):
    text: str
    citations: list[CitationRef]


class AskResponse(BaseModel):
    answer: list[AskAnswerBlock]
    not_found: bool
    guidance: str


class CitationResolveRequest(BaseModel):
    chunk_id: str


class ResolvedCitation(BaseModel):
    chunk_id: str
    doc_id: str
    page: int
    text_zh: str
    text_en: str
    citation_label: str


class CninfoSyncRequest(BaseModel):
    company_id: str
    start_date: str | None = None
    end_date: str | None = None


class CninfoSyncResponse(BaseModel):
    events: list[AcquisitionEvent]
    documents: list[Document]


class DocumentPageResponse(BaseModel):
    doc_id: str
    page: int
    snippet_zh: str
    snippet_en: str
    image_url: str


class QAIssue(BaseModel):
    code: str
    message: str
    finding_id: str | None = None
    section_id: str | None = None


class QAReport(BaseModel):
    passed: bool
    issues: list[QAIssue] = Field(default_factory=list)
