"""Acquisition connectors for China Lens."""

from .cninfo import (
    CninfoAnnualReportRef,
    CninfoManifest,
    ManifestDocument,
    ManifestSnippet,
    build_acquisition_event,
    build_document_hash,
    document_from_cninfo,
    find_latest_annual_report,
    latest_annual_from_cninfo_payload,
    load_cninfo_manifest,
)

__all__ = [
    "CninfoAnnualReportRef",
    "CninfoManifest",
    "ManifestDocument",
    "ManifestSnippet",
    "build_acquisition_event",
    "build_document_hash",
    "document_from_cninfo",
    "find_latest_annual_report",
    "latest_annual_from_cninfo_payload",
    "load_cninfo_manifest",
]
