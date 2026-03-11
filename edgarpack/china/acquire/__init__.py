"""Acquisition connectors for China Lens."""

from .cninfo import (
    CninfoManifest,
    ManifestDocument,
    ManifestSnippet,
    build_acquisition_event,
    build_document_hash,
    document_from_cninfo,
    load_cninfo_manifest,
)

__all__ = [
    "CninfoManifest",
    "ManifestDocument",
    "ManifestSnippet",
    "build_acquisition_event",
    "build_document_hash",
    "document_from_cninfo",
    "load_cninfo_manifest",
]
