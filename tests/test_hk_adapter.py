"""build_hk_pack: TOC-sliced sections plus a manifest whose currency/standard
come from the filing itself (via extract_filing_metadata), not a hardcoded dict.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from edgarpack.china.extract.pdf_extract import ExtractedPage
from edgarpack.china.models import ExtractionMethod
from edgarpack.hk.acquire import HKFilingMeta, HKFilingRef
from edgarpack.hk.adapter import PackRef, build_hk_pack
from edgarpack.hk.toc import HKSectioningError


def _page(num: int, text: str) -> ExtractedPage:
    return ExtractedPage(
        page=num, text=text, method=ExtractionMethod.EMBEDDED_TEXT, confidence=0.95
    )


def _ref(stock_code: str = "00700", fiscal_year: int = 2025) -> HKFilingRef:
    return HKFilingRef(
        stock_code=stock_code,
        fiscal_year=fiscal_year,
        pdf_url=f"https://www1.hkexnews.hk/{stock_code}_{fiscal_year}.pdf",
        announcement_date="09/04/2026",
    )


def _report_pages() -> list[ExtractedPage]:
    toc = (
        "CONTENTS\n"
        "1 CHAIRMAN'S STATEMENT\n"
        "2 CONSOLIDATED INCOME STATEMENT\n"
        "3 CONSOLIDATED BALANCE SHEET\n"
        "4 BALANCE SHEET\n"
        "5 CONSOLIDATED STATEMENT OF CASH FLOWS\n"
        "6 NOTES TO THE FINANCIAL STATEMENTS"
    )
    return [
        _page(1, toc),
        _page(2, "CHAIRMAN'S STATEMENT\nDear shareholders."),
        _page(3, "CONSOLIDATED INCOME STATEMENT\n2024 2023\nRevenue 100 90"),
        _page(4, "CONSOLIDATED BALANCE SHEET\n2024 2023\nTotal assets 500 450"),
        _page(5, "BALANCE SHEET\nparent-only company statement\n2024 2023\nTotal assets 300 280"),
        _page(6, "CONSOLIDATED STATEMENT OF CASH FLOWS\n2024 2023\nNet cash 50 40"),
        _page(7, "NOTES TO THE FINANCIAL STATEMENTS\nBasis of preparation."),
    ]


def _patch_build(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    pages: list[ExtractedPage] | None = None,
    meta: HKFilingMeta,
) -> None:
    fake_pdf = tmp_path / "src.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr("edgarpack.hk.adapter._download_pdf", lambda ref, out, client=None: out)
    monkeypatch.setattr(
        "edgarpack.hk.adapter.extract_pdf_pages",
        lambda path: pages if pages is not None else _report_pages(),
    )
    monkeypatch.setattr("edgarpack.hk.adapter.extract_filing_metadata", lambda path: meta)


def test_build_hk_pack_writes_toc_sliced_sections_and_filing_metadata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    meta = HKFilingMeta(
        currency="CNY", accounting_standard="IFRS", legal_name="Tencent Holdings Limited"
    )
    _patch_build(monkeypatch, tmp_path, meta=meta)
    out_dir = tmp_path / "pack"

    pack = build_hk_pack(
        _ref(),
        out_dir,
        company_name="TENCENT",
        dual_counter_codes=["00700", "80700"],
    )

    assert isinstance(pack, PackRef)
    manifest = json.loads((out_dir / "manifest.json").read_text())
    assert manifest["source"] == "HKEX"
    assert manifest["stock_code"] == "00700"
    assert manifest["fiscal_year"] == 2025
    # Currency and standard come from the filing, not a hardcoded dict; the
    # legal name from the cover overrides the search short name.
    assert manifest["reporting_currency"] == "CNY"
    assert manifest["accounting_standard"] == "IFRS"
    assert manifest["company"] == "Tencent Holdings Limited"
    assert manifest["dual_counter_codes"] == ["00700", "80700"]

    section_files = {p.stem for p in (out_dir / "sections").glob("*.md")}
    assert {
        "hkex_chairman_statement",
        "hkex_income_statement",
        "hkex_balance_sheet",
        "hkex_cash_flow",
    } <= section_files
    income = (out_dir / "sections" / "hkex_income_statement.md").read_text()
    assert "Revenue 100 90" in income


def test_build_hk_pack_skips_parent_only_balance_sheet(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    meta = HKFilingMeta(currency="CNY", accounting_standard="CAS", legal_name=None)
    _patch_build(monkeypatch, tmp_path, meta=meta)
    out_dir = tmp_path / "pack"

    build_hk_pack(_ref("01211"), out_dir, company_name="BYD")

    balance = (out_dir / "sections" / "hkex_balance_sheet.md").read_text()
    assert "Total assets 500 450" in balance
    assert "parent-only" not in balance
    # The parent-only statement must not have produced a second balance sheet.
    assert not (out_dir / "sections" / "hkex_balance_sheet_02.md").exists()


def test_build_hk_pack_falls_back_to_search_short_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    meta = HKFilingMeta(currency="HKD", accounting_standard="HKFRS", legal_name=None)
    _patch_build(monkeypatch, tmp_path, meta=meta)
    out_dir = tmp_path / "pack"

    build_hk_pack(
        _ref("00005"), out_dir, company_name="HSBC HOLDINGS", dual_counter_codes=["00005"]
    )

    manifest = json.loads((out_dir / "manifest.json").read_text())
    assert manifest["company"] == "HSBC HOLDINGS"
    # Single counter: no dual_counter_codes field.
    assert "dual_counter_codes" not in manifest


def test_build_hk_pack_records_joint_standard_citation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    meta = HKFilingMeta(
        currency="CNY",
        accounting_standard="IFRS",
        legal_name="ANTA Sports Products Limited",
        standard_note="IFRS and HKFRS Accounting Standards (joint citation, normalized to IFRS)",
    )
    _patch_build(monkeypatch, tmp_path, meta=meta)
    out_dir = tmp_path / "pack"

    build_hk_pack(_ref("02020"), out_dir, company_name="ANTA SPORTS")

    manifest = json.loads((out_dir / "manifest.json").read_text())
    assert manifest["accounting_standard"] == "IFRS"
    assert "HKFRS" in manifest["accounting_standard_citation"]


def test_build_hk_pack_raises_when_statements_cannot_be_located(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    garbled = [
        _page(1, "CONTENTS\n1 CHAIRMAN'S STATEMENT\n2 FINANCIAL STATEMENTS\n4 GLOSSARY"),
        _page(2, "CHAIRMAN'S STATEMENT\nBody."),
        _page(3, "FINANCIAL STATEMENTS\n\x00 image-only garble"),
        _page(4, "GLOSSARY\nTerms."),
    ]
    meta = HKFilingMeta(currency="CNY", accounting_standard="IFRS", legal_name=None)
    _patch_build(monkeypatch, tmp_path, pages=garbled, meta=meta)

    with pytest.raises(HKSectioningError):
        build_hk_pack(_ref(), tmp_path / "pack", company_name="X")


def test_download_pdf_helper_threads_client_through(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen: dict[str, Any] = {}

    def _fake_download(ref: Any, out: Path, *, client: Any = None) -> None:
        seen["client"] = client
        out.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr("edgarpack.hk.adapter.download_pdf", _fake_download)
    from edgarpack.hk.adapter import _download_pdf

    sentinel = object()
    _download_pdf(_ref(), tmp_path / "x.pdf", client=sentinel)
    assert seen["client"] is sentinel
