import json
from unittest.mock import patch

import pytest

from edgarpack.china.extract.pdf_extract import ExtractedPage
from edgarpack.china.models import ExtractionMethod
from edgarpack.hk.acquire import HKFilingRef
from edgarpack.hk.adapter import PackRef, UnknownHKFilerError, build_hk_pack


def _page(num: int, text: str) -> ExtractedPage:
    return ExtractedPage(
        page=num,
        text=text,
        method=ExtractionMethod.EMBEDDED_TEXT,
        confidence=0.95,
    )


def test_build_hk_pack_emits_sec_shaped_manifest(tmp_path):
    ref = HKFilingRef(
        stock_code="00700",
        fiscal_year=2023,
        pdf_url="https://example/0700_2023.pdf",
        announcement_date="26/03/2024",
    )
    out_dir = tmp_path / "tencent_2023"

    fake_pdf = tmp_path / "0700_2023.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4\n")

    fake_pages = [
        _page(1, "CHAIRMAN'S STATEMENT\n\nDear shareholders..."),
        _page(2, "MANAGEMENT DISCUSSION AND ANALYSIS\n\nRevenue grew..."),
        _page(3, "CONSOLIDATED STATEMENT OF PROFIT OR LOSS\n\nRevenue: 609,015M"),
    ]

    with (
        patch("edgarpack.hk.adapter._download_pdf", return_value=fake_pdf),
        patch("edgarpack.hk.adapter.extract_pdf_pages", return_value=fake_pages),
    ):
        pack = build_hk_pack(ref, out_dir)

    assert isinstance(pack, PackRef)
    assert pack.path == out_dir
    assert pack.stock_code == "00700"
    assert pack.fiscal_year == 2023

    manifest = json.loads((out_dir / "manifest.json").read_text())
    assert manifest["source"] == "HKEX"
    assert manifest["stock_code"] == "00700"
    assert manifest["fiscal_year"] == 2023
    assert manifest["reporting_currency"] == "CNY"
    assert manifest["accounting_standard"] == "HKFRS"
    assert manifest["company"] == "Tencent Holdings"

    sections_dir = out_dir / "sections"
    section_files = {p.stem for p in sections_dir.iterdir() if p.suffix == ".md"}
    assert "hkex_chairman_statement" in section_files
    assert "hkex_mdna" in section_files
    assert "hkex_income_statement" in section_files

    chunks_path = out_dir / "chunks.ndjson"
    assert chunks_path.exists()
    lines = chunks_path.read_text().strip().splitlines()
    assert len(lines) == 3
    rows = [json.loads(line) for line in lines]
    section_ids = {row["section_id"] for row in rows}
    assert {"hkex_chairman_statement", "hkex_mdna", "hkex_income_statement"} <= section_ids


def test_build_hk_pack_falls_back_for_unknown_heading(tmp_path):
    ref = HKFilingRef(
        stock_code="00700",
        fiscal_year=2023,
        pdf_url="https://example/x.pdf",
        announcement_date="01/01/2024",
    )
    out_dir = tmp_path / "pack"
    fake_pdf = tmp_path / "x.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4\n")

    pages = [_page(1, "SOME UNRECOGNIZED HEADING\n\nBody text here.")]

    with (
        patch("edgarpack.hk.adapter._download_pdf", return_value=fake_pdf),
        patch("edgarpack.hk.adapter.extract_pdf_pages", return_value=pages),
    ):
        build_hk_pack(ref, out_dir)

    section_files = list((out_dir / "sections").iterdir())
    assert len(section_files) == 1
    assert section_files[0].stem.startswith("hkex_unmapped_")


def test_build_hk_pack_uses_meituan_metadata(tmp_path):
    ref = HKFilingRef(
        stock_code="03690",
        fiscal_year=2023,
        pdf_url="https://example/3690.pdf",
        announcement_date="01/04/2024",
    )
    out_dir = tmp_path / "meituan"
    fake_pdf = tmp_path / "m.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4\n")

    with (
        patch("edgarpack.hk.adapter._download_pdf", return_value=fake_pdf),
        patch(
            "edgarpack.hk.adapter.extract_pdf_pages",
            return_value=[_page(1, "CHAIRMAN'S STATEMENT\n\nDear shareholders...")],
        ),
    ):
        build_hk_pack(ref, out_dir)

    manifest = json.loads((out_dir / "manifest.json").read_text())
    assert manifest["company"] == "Meituan"
    assert manifest["reporting_currency"] == "CNY"
    assert manifest["accounting_standard"] == "HKFRS"


def test_build_hk_pack_raises_for_unknown_filer(tmp_path):
    ref = HKFilingRef(
        stock_code="09999",
        fiscal_year=2024,
        pdf_url="https://example/9999.pdf",
        announcement_date="01/01/2025",
    )
    out_dir = tmp_path / "unknown"
    fake_pdf = tmp_path / "u.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4\n")

    with (
        patch("edgarpack.hk.adapter._download_pdf", return_value=fake_pdf),
        patch(
            "edgarpack.hk.adapter.extract_pdf_pages",
            return_value=[_page(1, "CHAIRMAN'S STATEMENT\n\nBody.")],
        ),
        pytest.raises(UnknownHKFilerError) as exc,
    ):
        build_hk_pack(ref, out_dir)

    message = str(exc.value)
    assert "09999" in message
    assert "_COMPANY_META" in message
