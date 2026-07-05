"""End-to-end `edgarpack build-hk` wiring with a mocked acquire step.

The acquire step (network) is mocked; a tiny synthetic document exercises the
real TOC slicer, metadata extraction and manifest write. The garbled path
asserts the pack is still written when the facts step fails loudly.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from edgarpack.china.extract.pdf_extract import ExtractedPage
from edgarpack.china.models import ExtractionMethod
from edgarpack.cli import main
from edgarpack.hk.acquire import HKFilingMeta, HKFilingRef


def _page(num: int, text: str) -> ExtractedPage:
    return ExtractedPage(
        page=num, text=text, method=ExtractionMethod.EMBEDDED_TEXT, confidence=0.95
    )


def _synthetic_pages() -> list[ExtractedPage]:
    toc = (
        "CONTENTS\n"
        "1 CHAIRMAN'S STATEMENT\n"
        "2 CONSOLIDATED INCOME STATEMENT\n"
        "3 CONSOLIDATED BALANCE SHEET\n"
        "4 CONSOLIDATED STATEMENT OF CASH FLOWS\n"
        "5 NOTES TO THE FINANCIAL STATEMENTS"
    )
    return [
        _page(1, toc),
        _page(2, "CHAIRMAN'S STATEMENT\nDear shareholders."),
        _page(3, "CONSOLIDATED INCOME STATEMENT\n2024 2023\nRevenue 100 90"),
        _page(4, "CONSOLIDATED BALANCE SHEET\n2024 2023\nTotal assets 500 450"),
        _page(5, "CONSOLIDATED STATEMENT OF CASH FLOWS\n2024 2023\nNet cash 50 40"),
        _page(6, "NOTES TO THE FINANCIAL STATEMENTS\nBasis of preparation."),
    ]


def _patch_acquire_and_pdf(monkeypatch: pytest.MonkeyPatch) -> None:
    ref = HKFilingRef(
        stock_code="00700",
        fiscal_year=2025,
        pdf_url="https://www1.hkexnews.hk/x.pdf",
        announcement_date="09/04/2026",
    )
    monkeypatch.setattr(
        "edgarpack.cli._acquire_hk_filing",
        lambda client, code: (ref, "TENCENT", ["00700", "80700"]),
    )
    monkeypatch.setattr("edgarpack.hk.adapter._download_pdf", lambda ref, out, client=None: out)
    monkeypatch.setattr("edgarpack.hk.adapter.extract_pdf_pages", lambda path: _synthetic_pages())
    monkeypatch.setattr(
        "edgarpack.hk.adapter.extract_filing_metadata",
        lambda path: HKFilingMeta(
            currency="CNY", accounting_standard="IFRS", legal_name="Tencent Holdings Limited"
        ),
    )


def test_build_hk_end_to_end_writes_pack_and_facts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_acquire_and_pdf(monkeypatch)

    rc = main(["build-hk", "0700", "--out", str(tmp_path)])
    assert rc == 0

    pack_dir = tmp_path / "00700" / "00700_2025"
    assert (pack_dir / "manifest.json").exists()
    assert (pack_dir / "sections" / "hkex_income_statement.md").exists()
    facts = json.loads((pack_dir / "facts.json").read_text())
    assert facts["stock_code"] == "00700"
    assert facts["facts"]  # at least one extracted concept


def test_build_hk_garbled_facts_step_fails_loudly_with_pack_written(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_acquire_and_pdf(monkeypatch)

    class _BlockedError(Exception):
        pass

    def _raise(pack_dir: Any) -> Any:
        raise _BlockedError("statement text was image-only")

    # Stand in for the typed error hk-extract-fixes will raise once it lands.
    monkeypatch.setattr(
        "edgarpack.hk.extract.HKExtractionBlockedError", _BlockedError, raising=False
    )
    monkeypatch.setattr("edgarpack.hk.extract.extract_facts_from_pack", _raise)

    rc = main(["build-hk", "0700", "--out", str(tmp_path)])
    assert rc == 1

    pack_dir = tmp_path / "00700" / "00700_2025"
    # Pack (sections + manifest) is still written; facts.json is not.
    assert (pack_dir / "sections" / "hkex_income_statement.md").exists()
    assert not (pack_dir / "facts.json").exists()
    err = capsys.readouterr().err
    assert "blocked" in err.lower()


def test_build_hk_unresolvable_name_errors_cleanly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from edgarpack.errors import UnknownCompany

    def _boom(query: str) -> Any:
        raise UnknownCompany("Unknown company 'nope'. Did you mean: none?")

    monkeypatch.setattr("edgarpack.cli._resolve_cli_company", _boom)
    rc = main(["build-hk", "definitely not a real issuer", "--out", str(tmp_path)])
    assert rc == 2
