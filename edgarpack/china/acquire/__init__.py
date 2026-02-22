"""Acquisition connectors for China Lens."""

from .cninfo import build_acquisition_event, build_document_hash, document_from_cninfo

__all__ = ["build_acquisition_event", "build_document_hash", "document_from_cninfo"]
