"""CNINFO acquisition connector.

MVP implementation intentionally keeps connector behavior deterministic.
"""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from pydantic import BaseModel, Field

from ..models import AcquisitionEvent, Company, Document, ExtractionMethod, utc_now


class ManifestSnippet(BaseModel):
    """One citation-ready snippet from a source document page."""

    page: int = Field(ge=1)
    text_zh: str
    text_en: str = ""
    extraction_method: ExtractionMethod = ExtractionMethod.EMBEDDED_TEXT
    confidence: float = Field(default=0.95, ge=0.0, le=1.0)


class ManifestDocument(BaseModel):
    """Normalized CNINFO document metadata from a local manifest."""

    doc_id: str
    title: str
    filing_date: str
    source_url: str
    pages: int = Field(ge=1)
    local_pdf_path: str | None = None
    file_hash: str | None = None
    snippets: list[ManifestSnippet] = Field(default_factory=list)


class CninfoManifest(BaseModel):
    """CNINFO sync manifest for deterministic/local ingestion workflows."""

    company_id: str
    documents: list[ManifestDocument] = Field(default_factory=list)


def build_document_hash(company: Company, title: str, filing_date: str) -> str:
    """Generate deterministic file hash placeholder for connector events."""
    payload = f"{company.id}|{title}|{filing_date}".encode()
    return sha256(payload).hexdigest()


def build_acquisition_event(
    event_id: str,
    company_id: str,
    source_url: str,
    file_hash: str,
    outcome: str,
    details: str,
) -> AcquisitionEvent:
    """Create an acquisition event record for connector observability."""
    return AcquisitionEvent(
        id=event_id,
        company_id=company_id,
        source="CNINFO",
        source_url=source_url,
        occurred_at=utc_now(),
        file_hash=file_hash,
        outcome=outcome,
        details=details,
    )


def document_from_cninfo(
    doc_id: str,
    company: Company,
    title: str,
    filing_date: str,
    source_url: str,
    pages: int,
    acquisition_log_id: str,
    file_hash: str | None = None,
    object_key: str = "",
    storage_url: str = "",
) -> Document:
    """Build a normalized Document model from CNINFO metadata."""
    return Document(
        id=doc_id,
        company_id=company.id,
        title=title,
        filing_type="annual_report" if "annual" in title.lower() else "interim_report",
        filing_date=filing_date,
        source="CNINFO",
        source_url=source_url,
        file_hash=file_hash or build_document_hash(company, title, filing_date),
        pages=pages,
        language="zh",
        acquired_at=utc_now(),
        acquisition_log_id=acquisition_log_id,
        object_key=object_key,
        storage_url=storage_url,
    )


def load_cninfo_manifest(path: str, company_id: str | None = None) -> list[ManifestDocument]:
    """Load a CNINFO manifest from disk and return document definitions.

    Accepted JSON shapes:
    - {"company_id": "...", "documents": [...]}
    - [{"doc_id": "...", ...}, ...]
    """
    manifest_path = Path(path).expanduser()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    if isinstance(payload, list):
        docs = [ManifestDocument.model_validate(item) for item in payload]
    else:
        manifest = CninfoManifest.model_validate(payload)
        if company_id and manifest.company_id != company_id:
            return []
        docs = list(manifest.documents)

    resolved_docs: list[ManifestDocument] = []
    for doc in docs:
        local_pdf_path = doc.local_pdf_path
        if local_pdf_path:
            local_path = Path(local_pdf_path)
            if not local_path.is_absolute():
                local_path = (manifest_path.parent / local_path).resolve()
            doc = doc.model_copy(update={"local_pdf_path": str(local_path)})
        resolved_docs.append(doc)

    return resolved_docs
