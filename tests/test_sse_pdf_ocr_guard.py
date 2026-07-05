from __future__ import annotations

from pathlib import Path

import pytest

pymupdf = pytest.importorskip("pymupdf")


def _scanned_pdf(tmp_path: Path) -> Path:
    """An image-only page with no native text layer, like a scanned filing."""
    doc = pymupdf.open()
    page = doc.new_page()
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 40, 40))
    pix.set_rect(pix.irect, (120, 120, 120))
    page.insert_image(page.rect, stream=pix.tobytes("png"))
    pdf_path = tmp_path / "scanned.pdf"
    doc.save(pdf_path)
    doc.close()
    return pdf_path


def _digital_pdf(tmp_path: Path) -> Path:
    """A normal digitally typeset page: plenty of native text, no images."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((36, 72), "Ordinary digitally typeset annual report text. " * 5)
    pdf_path = tmp_path / "digital.pdf"
    doc.save(pdf_path)
    doc.close()
    return pdf_path


def test_warn_on_ocr_dependency_fires_for_image_heavy_textless_page(tmp_path):
    from edgarpack.sse.pdf_to_md import _warn_on_ocr_dependency

    pdf_path = _scanned_pdf(tmp_path)

    with pytest.warns(UserWarning, match="chi_sim"):
        _warn_on_ocr_dependency(pdf_path)


def test_warn_on_ocr_dependency_silent_for_text_embedded_page(tmp_path, recwarn):
    from edgarpack.sse.pdf_to_md import _warn_on_ocr_dependency

    pdf_path = _digital_pdf(tmp_path)

    _warn_on_ocr_dependency(pdf_path)

    assert len(recwarn.list) == 0


def test_pdf_to_markdown_surfaces_ocr_warning_without_failing_build(tmp_path, monkeypatch):
    from edgarpack.sse import pdf_to_md

    pdf_path = _scanned_pdf(tmp_path)
    monkeypatch.setattr("pymupdf4llm.to_markdown", lambda _path: "stub content")

    with pytest.warns(UserWarning, match="chi_sim"):
        result = pdf_to_md.pdf_to_markdown(pdf_path)

    assert "stub content" in result


def test_pdf_to_markdown_silent_on_modern_text_embedded_filing(tmp_path, monkeypatch, recwarn):
    from edgarpack.sse import pdf_to_md

    pdf_path = _digital_pdf(tmp_path)
    monkeypatch.setattr("pymupdf4llm.to_markdown", lambda _path: "stub content")

    pdf_to_md.pdf_to_markdown(pdf_path)

    assert len(recwarn.list) == 0
