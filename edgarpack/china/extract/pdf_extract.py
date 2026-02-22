"""PDF extraction primitives for China Lens.

The MVP extraction policy prefers embedded text and falls back to OCR only when
embedded text is unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..models import ExtractionMethod


@dataclass(frozen=True)
class ExtractedPage:
    page: int
    text: str
    method: ExtractionMethod
    confidence: float


def extract_page_text(page: int, embedded_text: str | None) -> ExtractedPage:
    """Return extracted text for one page using deterministic fallback policy."""
    if embedded_text and embedded_text.strip():
        return ExtractedPage(
            page=page,
            text=embedded_text,
            method=ExtractionMethod.EMBEDDED_TEXT,
            confidence=0.95,
        )

    # OCR fallback placeholder for MVP scaffolding.
    return ExtractedPage(
        page=page,
        text="",
        method=ExtractionMethod.OCR,
        confidence=0.55,
    )
