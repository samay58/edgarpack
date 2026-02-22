"""CNINFO acquisition connector.

MVP implementation intentionally keeps connector behavior deterministic.
"""

from __future__ import annotations

from hashlib import sha256

from ..models import AcquisitionEvent, Company, Document, utc_now


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
        file_hash=build_document_hash(company, title, filing_date),
        pages=pages,
        language="zh",
        acquired_at=utc_now(),
        acquisition_log_id=acquisition_log_id,
    )
