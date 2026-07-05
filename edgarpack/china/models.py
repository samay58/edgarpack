"""Shared China Lens extraction types.

The Evidence Explorer workspace models that used to live here were removed
with the parked FastAPI/web stack (docs/STREAMLINE-PLAN.md, Phase 1).
"""

from __future__ import annotations

from enum import StrEnum


class ExtractionMethod(StrEnum):
    EMBEDDED_TEXT = "embedded_text"
    OCR = "ocr"
