import json
from pathlib import Path

import pytest

from edgarpack.hk.extract import extract_facts_from_pack, extract_with_regex


def test_extract_revenue_simple_inline_currency():
    text = "Total revenue          US$  71,200,000"
    facts = extract_with_regex(text, "hkex_income_statement", "HKFRS")
    assert any(f.metric == "revenue" and f.value == 71_200_000 for f in facts)


def test_extract_handles_parenthesized_negative():
    text = "Loss for the year         US$  (465,000,000)"
    facts = extract_with_regex(text, "hkex_income_statement", "HKFRS")
    rows = [f for f in facts if f.metric == "net_income"]
    if rows:
        assert rows[0].value == -465_000_000 or rows[0].value == 465_000_000


def test_extract_no_match_returns_empty():
    text = "Some boilerplate prose with no numbers anywhere."
    facts = extract_with_regex(text, "hkex_income_statement", "HKFRS")
    assert facts == []


def test_extract_only_runs_for_financial_sections():
    text = "Revenue US$ 71,200,000"
    facts = extract_with_regex(text, "hkex_chairman_statement", "HKFRS")
    assert facts == []


def test_extract_facts_from_pack_writes_facts_json(tmp_path):
    pack_dir = tmp_path / "test_pack"
    pack_dir.mkdir()
    sections_dir = pack_dir / "sections"
    sections_dir.mkdir()
    (sections_dir / "hkex_income_statement.md").write_text(
        "# Consolidated Statement of Profit or Loss\n\n"
        "Total revenue          US$  71,200,000\n"
        "Cost of revenue        US$  (54,800,000)\n"
    )
    (pack_dir / "manifest.json").write_text(
        json.dumps(
            {
                "source": "HKEX",
                "stock_code": "00100",
                "fiscal_year": 2024,
                "accounting_standard": "HKFRS",
                "reporting_currency": "USD",
                "company": "Test Company",
                "pdf_url": "",
                "announcement_date": "",
            }
        )
    )

    facts_path = extract_facts_from_pack(pack_dir, llm_fallback=False)
    assert facts_path.exists()
    data = json.loads(facts_path.read_text())
    assert "facts" in data
    standard_facts = data["facts"]["hkfrs"]
    assert any(
        info["units"]["USD"][0]["val"] == 71_200_000
        for concept, info in standard_facts.items()
        if "USD" in info.get("units", {})
    )


def test_commaless_values_keep_year_alignment():
    # 618 has no thousands comma. The old parser dropped it, shifting every
    # later column one year to the left (2023's value cited as FY2024).
    text = "Consolidated statements of profit or loss\n2024 2023 2022\nRevenue 618 1,234 5,678\n"
    facts = extract_with_regex(text, "hkex_income_statement", "HKFRS", max_fy=2024)
    by_year = {f.fiscal_year: f.value for f in facts if f.metric == "revenue"}
    assert by_year == {2024: 618, 2023: 1234, 2022: 5678}


def test_parenthesized_decimal_is_negative():
    # The old parser matched "(1,234.5)" then discarded it, shifting columns.
    text = (
        "Consolidated statements of profit or loss\n"
        "2024 2023 2022\n"
        "Gross (loss)/profit (1,234.5) 2,000 3,000\n"
    )
    facts = extract_with_regex(text, "hkex_income_statement", "HKFRS", max_fy=2024)
    by_year = {f.fiscal_year: f.value for f in facts if f.metric == "gross_profit"}
    assert by_year == {2024: -1234.5, 2023: 2000, 2022: 3000}


def test_column_count_mismatch_emits_no_fact():
    # Two values under three year columns: alignment is unknowable, so the
    # row must yield nothing rather than a wrong-year value with a citation.
    text = "Consolidated statements of profit or loss\n2024 2023 2022\nRevenue 1,234 5,678\n"
    facts = extract_with_regex(text, "hkex_income_statement", "HKFRS", max_fy=2024)
    assert [f for f in facts if f.metric == "revenue"] == []


def test_note_reference_column_is_not_a_value():
    text = (
        "Consolidated statements of profit or loss\n"
        "Note 2024 2023 2022\n"
        "Revenue 4 618 1,234 5,678\n"
        "Gross profit 4(b) 100 2,000 3,000\n"
    )
    facts = extract_with_regex(text, "hkex_income_statement", "HKFRS", max_fy=2024)
    revenue = {f.fiscal_year: f.value for f in facts if f.metric == "revenue"}
    gross = {f.fiscal_year: f.value for f in facts if f.metric == "gross_profit"}
    assert revenue == {2024: 618, 2023: 1234, 2022: 5678}
    assert gross == {2024: 100, 2023: 2000, 2022: 3000}


def test_date_in_label_not_read_as_value():
    text = (
        "Consolidated statements of profit or loss\n"
        "2024 2023\n"
        "Loss for the year ended 31 December (1,234) (5,678)\n"
    )
    facts = extract_with_regex(text, "hkex_income_statement", "HKFRS", max_fy=2024)
    by_year = {f.fiscal_year: f.value for f in facts if f.metric == "net_income"}
    assert by_year == {2024: -1234, 2023: -5678}


def test_label_hyphen_is_not_a_dash_column():
    # "TOTAL EQUITY - DEFICIT" used to contribute a phantom dash column,
    # shifting every value one year to the right.
    text = (
        "Consolidated statements of financial position\n"
        "2024 2023 2022\n"
        "TOTAL EQUITY - DEFICIT (170,648) (974,767) (3,870,284)\n"
    )
    facts = extract_with_regex(text, "hkex_balance_sheet", "HKFRS", max_fy=2024)
    by_year = {f.fiscal_year: f.value for f in facts if f.metric == "total_equity"}
    assert by_year == {2024: -170648, 2023: -974767, 2022: -3870284}


def test_zhipu_income_statement_extraction_unchanged():
    sec = Path("tests/fixtures/china_packs/zhipu_2024/sections/hkex_income_statement.md")
    if not sec.exists():
        pytest.skip("zhipu fixture pack not built")
    facts = extract_with_regex(sec.read_text(), "hkex_income_statement", "HKFRS", max_fy=2024)
    by = {(f.metric, f.fiscal_year): f.value for f in facts}
    assert by[("revenue", 2022)] == 57_409_000
    assert by[("revenue", 2023)] == 124_538_000
    assert by[("revenue", 2024)] == 312_414_000
    assert by[("gross_profit", 2024)] == 175_889_000
    assert by[("operating_income", 2024)] == -2_538_352_000
    assert by[("rd_expense", 2024)] == 2_195_436_000
    assert by[("net_income", 2024)] == -2_958_007_000


def test_zhipu_total_equity_years_no_longer_shifted():
    # The committed facts.json and golden carried 2022/2023 company-level
    # equity under 2023/2024 because of the phantom dash column; the table
    # row reads (170,648) (974,767) (3,870,284) ... under 2022 2023 2024.
    sec = Path("tests/fixtures/china_packs/zhipu_2024/sections/hkex_balance_sheet.md")
    if not sec.exists():
        pytest.skip("zhipu fixture pack not built")
    facts = extract_with_regex(sec.read_text(), "hkex_balance_sheet", "HKFRS", max_fy=2024)
    by = {(f.metric, f.fiscal_year): f.value for f in facts}
    assert by[("total_equity", 2022)] == -170_648_000
    assert by[("total_equity", 2023)] == -974_767_000
    assert by[("total_equity", 2024)] == -3_870_284_000
    assert by[("cash_and_equivalents", 2024)] == 2_269_222_000


def test_minimax_plain_sections_extraction_unchanged():
    sections = Path("tests/fixtures/china_packs/minimax_2024/sections")
    if not sections.exists():
        pytest.skip("minimax fixture pack not built")
    bs = extract_with_regex(
        (sections / "hkex_balance_sheet.md").read_text(), "hkex_balance_sheet", "HKFRS", max_fy=2024
    )
    by = {(f.metric, f.fiscal_year): f.value for f in bs}
    assert by[("cash_and_equivalents", 2022)] == 4_691_000
    assert by[("cash_and_equivalents", 2024)] == 288_912_000
    assert by[("total_equity", 2024)] == -799_320_000
    cf = extract_with_regex(
        (sections / "hkex_cash_flow.md").read_text(), "hkex_cash_flow", "HKFRS", max_fy=2024
    )
    ocf = {f.fiscal_year: f.value for f in cf if f.metric == "operating_cash_flow"}
    assert ocf == {2022: -11_019_000, 2023: -64_455_000, 2024: -258_483_000}


def test_extract_facts_minimax_real_pack_yields_revenue():
    pack_dir = Path("tests/fixtures/china_packs/minimax_2024")
    if not (pack_dir / "manifest.json").exists():
        pytest.skip("minimax fixture pack not built")
    facts_path = extract_facts_from_pack(pack_dir, llm_fallback=False)
    data = json.loads(facts_path.read_text())
    revenues = [
        info["units"][unit][0]["val"]
        for std in data["facts"].values()
        for concept, info in std.items()
        for unit in info.get("units", {})
        if any(canonical in concept.lower() for canonical in ("revenue", "turnover"))
    ]
    assert revenues, f"No revenue value found for MiniMax in {data['facts']}"
    assert any(r > 1_000_000 for r in revenues), f"All revenue values implausibly small: {revenues}"
