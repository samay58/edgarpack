"""Convert SSE prospectus PDFs to structured markdown via pymupdf4llm."""

import re
import warnings
from pathlib import Path

# Pages with images but fewer native characters than this are treated as
# image-heavy (i.e. likely scanned rather than digitally typeset).
_OCR_TEXT_THRESHOLD_CHARS = 40


def pdf_to_markdown(pdf_path: Path) -> str:
    """Convert a PDF file to markdown using pymupdf4llm.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        Markdown string of the full document.
    """
    try:
        import pymupdf4llm
    except ImportError as e:
        raise ImportError(
            "pymupdf4llm is required for SSE PDF support. Install with: uv pip install -e '.[sse]'"
        ) from e

    _warn_on_ocr_dependency(pdf_path)
    md = pymupdf4llm.to_markdown(str(pdf_path))
    return _post_process(md)


def _warn_on_ocr_dependency(pdf_path: Path) -> None:
    """Warn once if the PDF has image-heavy, text-empty pages.

    pymupdf4llm falls back to PyMuPDF's built-in Tesseract OCR (`pdfocr`) for
    pages whose native text layer is empty. That fallback is silent: on a host
    missing the `chi_sim` tessdata language pack, OCR still runs and emits
    garbage text for Chinese pages rather than raising. Detecting the input
    condition ahead of conversion lets us name the dependency without ever
    hard-failing a build of a modern, text-embedded filing.
    """
    try:
        import pymupdf
    except ImportError:
        return

    ocr_risk_pages: list[int] = []
    try:
        with pymupdf.open(str(pdf_path)) as doc:  # type: ignore[no-untyped-call]
            for page in doc:
                if not page.get_images():
                    continue
                if len(page.get_text("text").strip()) < _OCR_TEXT_THRESHOLD_CHARS:
                    ocr_risk_pages.append(page.number + 1)
    except Exception:
        # Best-effort detection only; a real problem opening the file surfaces
        # from the pymupdf4llm conversion call that follows this check.
        return

    if not ocr_risk_pages:
        return

    warnings.warn(
        f"{pdf_path.name}: {len(ocr_risk_pages)} page(s) {ocr_risk_pages} look "
        "image-heavy with no embedded text layer. pymupdf4llm falls back to "
        "system Tesseract OCR for pages like this, which needs the 'chi_sim' "
        "tessdata language pack for Chinese filings; without it, OCR output "
        "can be silently wrong instead of failing loudly.",
        stacklevel=2,
    )


def _post_process(md: str) -> str:
    """Normalize whitespace and clean up PDF conversion artifacts."""
    # Remove page break markers (form feed, horizontal rules from page breaks)
    md = md.replace("\f", "\n")
    md = re.sub(r"\n-{3,}\n", "\n\n", md)

    # Collapse runs of 3+ blank lines to 2
    md = re.sub(r"\n{4,}", "\n\n\n", md)

    # Strip trailing whitespace per line
    md = "\n".join(line.rstrip() for line in md.split("\n"))

    # Ensure final newline
    if not md.endswith("\n"):
        md += "\n"

    return md
