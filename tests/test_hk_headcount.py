"""Tests for HKEX headcount extraction + SEC fallback."""

from __future__ import annotations

from pathlib import Path

from edgarpack.hk.extract import extract_headcount_from_pack
from edgarpack.sec.headcount_text import scan_headcount_from_text


def test_minimax_headcount_is_385():
    pack = Path("tests/fixtures/china_packs/minimax_2024")
    fact = extract_headcount_from_pack(pack)
    assert fact is not None
    assert fact.value == 385
    assert fact.unit == "headcount"


def test_zhipu_headcount_is_883():
    pack = Path("tests/fixtures/china_packs/zhipu_2024")
    fact = extract_headcount_from_pack(pack)
    assert fact is not None
    assert fact.value == 883
    assert fact.unit == "headcount"


def test_out_of_bounds_value_is_rejected(tmp_path: Path):
    sections = tmp_path / "sections"
    sections.mkdir()
    (sections / "business_overview.md").write_text(
        "As of December 31, 2024, we had 42 employees at our Page 42 office.\n"
        "Background: 7 employees at founding.\n"
    )
    (tmp_path / "manifest.json").write_text(
        '{"stock_code": "XXXX", "company": "Test", "accounting_standard": "HKFRS", '
        '"reporting_currency": "USD", "fiscal_year": 2024}'
    )
    fact = extract_headcount_from_pack(tmp_path)
    assert fact is None


def test_sec_text_scan_finds_approximate_phrase():
    text = (
        "Human Capital Resources\n\n"
        "As of December 31, 2024, we had approximately 32,000 full-time employees "
        "globally across our research, product, and operations teams."
    )
    assert scan_headcount_from_text(text) == 32_000


def test_sec_text_scan_respects_bounds():
    text = "We had 7 employees at founding; by year-end we reached 0 full-time employees."
    assert scan_headcount_from_text(text) is None


def test_sec_text_scan_returns_none_when_absent():
    text = "No disclosure of human capital resources."
    assert scan_headcount_from_text(text) is None


def test_sec_text_scan_ignores_comparative_phrasing():
    text = "We had more than 50,000 employees globally."
    assert scan_headcount_from_text(text) is None
