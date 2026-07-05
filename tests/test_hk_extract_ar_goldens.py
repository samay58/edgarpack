"""Real-filing regression goldens for the hk-extract-fixes packet.

Fixtures are pypdf text excerpts of the financial-statement pages from four
real large-cap HKEX annual reports (Tencent, Meituan, BYD, Anta) plus one
garbled HSBC page, taken from the hk-construct-prototype evidence. Expected
values are hand-verified against the source PDFs, not against the prior
(buggy) extractor output.

Before the fix, `extract_with_regex` counted year columns from a fixed
character window that also caught boilerplate year mentions ("Annual Report
2025", "For the year ended 31 December 2025"). The inflated count dropped
correct 2-column rows while rows carrying a leading note-reference digit
coincidentally matched the inflated count, so the note number was read as
the value (e.g. Meituan R&D FY2025 came out as 7, Anta cash as 19).
"""

from pathlib import Path

import pytest

from edgarpack.hk.extract import HKExtractionBlockedError, extract_with_regex

FIXTURES = Path(__file__).parent / "fixtures" / "hkex_statements"


def _facts_by_metric_year(text: str, section_id: str) -> dict[tuple[str, int], int | float]:
    facts = extract_with_regex(text, section_id, "HKFRS", max_fy=2025)
    return {(f.metric, f.fiscal_year): f.value for f in facts}


def test_tencent_income_statement_both_years_correct():
    # Tencent's revenue total sits on an unlabeled note-reference row (the
    # label "Revenues" is a bare section header with no numbers on its own
    # line), so revenue is not extracted here; that is a pre-existing gap,
    # not one of this packet's four fixes. The rows that do carry the label
    # and the values on the same line must come out exactly right.
    text = (FIXTURES / "tencent_income_statement.txt").read_text()
    by = _facts_by_metric_year(text, "hkex_income_statement")
    assert by[("gross_profit", 2025)] == 422_593_000_000
    assert by[("gross_profit", 2024)] == 349_246_000_000
    assert by[("operating_income", 2025)] == 241_562_000_000
    assert by[("operating_income", 2024)] == 208_099_000_000
    assert by[("net_income", 2025)] == 229_801_000_000
    assert by[("net_income", 2024)] == 196_467_000_000
    # None of the note-reference digits leak through as a value.
    assert 7 not in by.values()


def test_meituan_income_statement_revenue_and_rd_both_years_correct():
    # The dominant bug, reproduced directly: "Revenues 5,6 364,854,746
    # 337,591,576" and "Research and development expenses 7 (25,998,265)
    # (21,053,601)" both carry a leading note-reference digit. Before the
    # header-anchor fix, rd_expense FY2025 came out as 7 (the note number).
    text = (FIXTURES / "meituan_income_statement.txt").read_text()
    by = _facts_by_metric_year(text, "hkex_income_statement")
    assert by[("revenue", 2025)] == 364_854_746_000
    assert by[("revenue", 2024)] == 337_591_576_000
    assert by[("gross_profit", 2025)] == 111_008_626_000
    assert by[("gross_profit", 2024)] == 129_784_594_000
    assert by[("rd_expense", 2025)] == 25_998_265_000
    assert by[("rd_expense", 2024)] == 21_053_601_000


def test_byd_income_statement_rd_and_net_income_both_years_correct():
    # BYD's R&D row carries a leading note reference ("49") before the two
    # comma-grouped values; before the fix FY2025 came out as 49 (the note
    # number, scaled by the RMB'000 multiplier to 49000).
    text = (FIXTURES / "byd_income_statement.txt").read_text()
    by = _facts_by_metric_year(text, "hkex_income_statement")
    assert by[("rd_expense", 2025)] == 57_978_105_000
    assert by[("rd_expense", 2024)] == 53_194_745_000
    assert by[("net_income", 2025)] == 33_760_758_000
    assert by[("net_income", 2024)] == 41_587_940_000


def test_byd_balance_sheet_split_year_header_yields_nothing_not_a_wrong_value():
    # BYD's balance sheet header splits each year onto its own line ("31
    # December\n2025\n31 December\n2024"), so no single line anchors a
    # 2-year header. That must yield no facts, not a wrong value: falling
    # through to the single-value fallback would silently read the last
    # (FY2024) column of a 2-column row and mislabel it as the current
    # period.
    text = (FIXTURES / "byd_balance_sheet.txt").read_text()
    facts = extract_with_regex(text, "hkex_balance_sheet", "HKFRS", max_fy=2025)
    assert facts == []


def test_blank_comparative_with_leading_note_ref_fails_closed():
    # A first-time-disclosed line item (or a dropped comparative cell) leaves a
    # bare note ref and one value: "... 8 12,345" with a 2-year header. The
    # note number must not be emitted as the current-year value; which year the
    # lone value belongs to is ambiguous, so parsing fails closed (None).
    from edgarpack.hk.extract import _parse_columns_plain

    assert _parse_columns_plain("Research and development expenses 8 12,345", 2) is None
    # A genuine two-year row of small similar-magnitude values is unaffected.
    assert _parse_columns_plain("Some line item 80 75", 2) == [80, 75]
    # The note-ref-plus-two-years case still drops just the note column.
    assert _parse_columns_plain("Research and development expenses 8 12,345 11,200", 2) == [
        12345,
        11200,
    ]


def test_anta_income_statement_all_metrics_both_years_correct():
    text = (FIXTURES / "anta_income_statement.txt").read_text()
    by = _facts_by_metric_year(text, "hkex_income_statement")
    assert by[("revenue", 2025)] == 80_219_000_000
    assert by[("revenue", 2024)] == 70_826_000_000
    assert by[("gross_profit", 2025)] == 49_734_000_000
    assert by[("gross_profit", 2024)] == 44_032_000_000
    assert by[("operating_income", 2025)] == 19_091_000_000
    assert by[("operating_income", 2024)] == 16_595_000_000
    assert by[("net_income", 2025)] == 15_662_000_000
    assert by[("net_income", 2024)] == 16_989_000_000


def test_anta_balance_sheet_million_shorthand_and_note_ref_both_correct():
    # Anta's header declares "RMB'million" (apostrophe + "million", not the
    # "in millions" phrase _detect_multiplier already recognized), so
    # before the fix every value here came out a million times too small.
    # Cash also carries a leading note reference ("19"), which is the exact
    # digit the header-anchor bug used to emit as the value.
    text = (FIXTURES / "anta_balance_sheet.txt").read_text()
    by = _facts_by_metric_year(text, "hkex_balance_sheet")
    assert by[("total_assets", 2025)] == 124_295_000_000
    assert by[("total_assets", 2024)] == 112_615_000_000
    assert by[("total_liabilities", 2025)] == 51_890_000_000
    assert by[("total_liabilities", 2024)] == 45_876_000_000
    assert by[("cash_and_equivalents", 2025)] == 12_181_000_000
    assert by[("cash_and_equivalents", 2024)] == 11_390_000_000
    # The note-reference digit ("19") must not appear as a value anywhere.
    assert 19 not in by.values()


def test_hsbc_garbled_page_raises_typed_blocked_error():
    text = (FIXTURES / "hsbc_income_statement_garbled.txt").read_text()
    with pytest.raises(HKExtractionBlockedError):
        extract_with_regex(text, "hkex_income_statement", "HKFRS", max_fy=2025)
