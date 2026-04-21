"""Convert SSE prospectus PDFs to structured markdown via pymupdf4llm."""

import re
from pathlib import Path


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

    md = pymupdf4llm.to_markdown(str(pdf_path))
    return _post_process(md)


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
