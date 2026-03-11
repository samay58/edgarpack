"""PDF extraction primitives for China Lens.

The MVP extraction policy prefers embedded text and falls back to OCR only when
embedded text is unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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


def extract_pdf_pages(pdf_path: str) -> list[ExtractedPage]:
    """Extract per-page text from a PDF using embedded text with OCR fallback marks.

    OCR is represented as a low-confidence placeholder when a page has no embedded
    text. The OCR execution itself is intentionally out of scope for this module.
    """
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    try:
        from pypdf import PdfReader
    except Exception as exc:  # pragma: no cover - import path depends on optional extras
        raise RuntimeError(
            "pypdf is required for PDF extraction. Install with: uv pip install -e '.[china]'"
        ) from exc

    reader = PdfReader(str(path))
    pages: list[ExtractedPage] = []
    for idx, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append(extract_page_text(idx, text))
    return pages
