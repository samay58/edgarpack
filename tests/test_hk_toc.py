"""TOC parsing, anchor-index resolution and page slicing for HKEX reports.

The five ``toc_*.txt`` fixtures are the verbatim pypdf text of the table-of-
contents page from each issuer's real FY2025 annual report (Tencent, Meituan,
BYD, Anta, HSBC), covering leading, trailing, bilingual, wrapped-continuation
and coarse-chapter shapes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from edgarpack.hk import load_section_map
from edgarpack.hk.toc import (
    HKSectioningError,
    TocEntry,
    find_toc_page_indices,
    parse_toc,
    resolve_entry_index,
    slice_sections,
)

_FIXTURES = Path(__file__).parent / "fixtures" / "hkex_toc"

_FINANCIAL_IDS = {
    "hkex_income_statement",
    "hkex_balance_sheet",
    "hkex_cash_flow",
    "hkex_comprehensive_income",
    "hkex_equity_changes",
}


def _toc(name: str) -> list[TocEntry]:
    return parse_toc((_FIXTURES / f"toc_{name}.txt").read_text())


def _pairs(entries: list[TocEntry]) -> set[tuple[str, int]]:
    return {(e.title, e.printed_page) for e in entries}


# --- parse_toc: leading / trailing / bilingual / continuation / coarse -------


def test_parse_toc_leading_shape_tencent() -> None:
    pairs = _pairs(_toc("tencent"))
    assert ("CONSOLIDATED INCOME STATEMENT", 129) in pairs
    assert ("CONSOLIDATED STATEMENT OF FINANCIAL POSITION", 131) in pairs
    assert ("CONSOLIDATED STATEMENT OF CASH FLOWS", 138) in pairs
    assert len(_toc("tencent")) == 14


def test_parse_toc_trailing_shape_meituan() -> None:
    pairs = _pairs(_toc("meituan"))
    assert ("Consolidated Income Statement", 211) in pairs
    assert ("Consolidated Statement of Financial Position", 213) in pairs
    assert ("Consolidated Statement of Cash Flows", 219) in pairs


def test_parse_toc_bilingual_keeps_english_and_both_byd_entities() -> None:
    pairs = _pairs(_toc("byd"))
    # English captured, Chinese dropped.
    assert ("Consolidated Balance Sheet", 141) in pairs
    assert ("Consolidated Income Statement", 144) in pairs
    # PRC parent-company-only statements appear too, without "Consolidated".
    assert ("Balance Sheet", 151) in pairs
    assert ("Income Statement", 153) in pairs


def test_parse_toc_joins_wrapped_continuation_lines_anta() -> None:
    pairs = _pairs(_toc("anta"))
    # Two TOC entries wrap onto a second, unnumbered line; joining them keeps
    # the two truncated "Consolidated Statement of" entries distinct.
    assert ("Consolidated Statement of Profit or Loss and Other Comprehensive Income", 133) in pairs
    assert ("Consolidated Statement of Financial Position", 134) in pairs
    assert ("Consolidated Statement of Changes in Equity", 136) in pairs
    assert ("Directors, Company Secretary and Senior Management", 126) in pairs


def test_parse_toc_does_not_join_a_complete_prior_title_anta() -> None:
    # "Management Discussion and Analysis" has no page of its own (its
    # sub-items are numbered), and must NOT be folded into "Chairman's
    # Statement", which is a complete entry.
    titles = [e.title for e in _toc("anta")]
    assert "Chairman’s Statement" in titles
    assert not any(t.startswith("Chairman") and "Management Discussion" in t for t in titles)


def test_parse_toc_coarse_chapter_shape_hsbc_has_no_per_statement_entries() -> None:
    entries = _toc("hsbc")
    pairs = _pairs(entries)
    assert ("Financial statements", 262) in pairs
    assert ("Notes on the financial statements", 274) in pairs
    section_map = load_section_map()
    norm_map = {k.replace(" ", "").upper(): v for k, v in section_map.items()}
    mapped_financial = [
        e.title for e in entries if norm_map.get(e.title.replace(" ", "").upper()) in _FINANCIAL_IDS
    ]
    assert mapped_financial == []


# --- anchor-index resolution ------------------------------------------------


def test_resolve_entry_index_finds_nearest_offset() -> None:
    pages = ["cover", "toc", "", "CONSOLIDATED INCOME STATEMENT\nRevenue 1 2", ""]
    # Printed page 4 but the heading actually sits at pypdf index 3 (offset -1).
    entry = TocEntry("CONSOLIDATED INCOME STATEMENT", 4)
    assert resolve_entry_index(entry, pages) == 3


def test_resolve_entry_index_returns_none_when_title_absent() -> None:
    pages = ["", "", "garbled \x00 text", ""]
    entry = TocEntry("CONSOLIDATED INCOME STATEMENT", 2)
    assert resolve_entry_index(entry, pages) is None


def test_find_toc_page_indices_picks_the_densest_page() -> None:
    toc = (
        "CONTENTS\n1 CHAIRMAN'S STATEMENT\n2 CONSOLIDATED INCOME STATEMENT\n"
        "3 CONSOLIDATED BALANCE SHEET\n4 CONSOLIDATED STATEMENT OF CASH FLOWS\n"
        "5 NOTES TO THE FINANCIAL STATEMENTS"
    )
    pages = ["cover only", toc, "body text", "more body"]
    assert find_toc_page_indices(pages) == [1]


# --- slicing ----------------------------------------------------------------


def _synthetic_report() -> list[str]:
    toc = (
        "CONTENTS\n"
        "1 CHAIRMAN'S STATEMENT\n"
        "2 CONSOLIDATED INCOME STATEMENT\n"
        "3 CONSOLIDATED BALANCE SHEET\n"
        "4 BALANCE SHEET\n"
        "5 NOTES TO THE FINANCIAL STATEMENTS"
    )
    return [
        toc,
        "CHAIRMAN'S STATEMENT\nDear shareholders, results were strong.",
        "CONSOLIDATED INCOME STATEMENT\n2024 2023\nRevenue 100 90\nProfit for the year 20 15",
        "CONSOLIDATED BALANCE SHEET\n2024 2023\nTotal assets 500 450",
        "BALANCE SHEET\nparent-only company statement\n2024 2023\nTotal assets 300 280",
        "NOTES TO THE FINANCIAL STATEMENTS\nBasis of preparation.",
    ]


def test_slice_sections_maps_and_bounds_at_toc_boundaries() -> None:
    sections = slice_sections(_synthetic_report(), load_section_map(), toc_page_indices=[0])
    by_id = {s.section_id: s for s in sections}
    assert by_id["hkex_income_statement"].start_index == 2
    assert by_id["hkex_income_statement"].end_index == 3
    assert "Revenue 100 90" in by_id["hkex_income_statement"].text
    assert set(by_id) >= {
        "hkex_chairman_statement",
        "hkex_income_statement",
        "hkex_balance_sheet",
        "hkex_notes",
    }


def test_slice_sections_skips_byd_style_parent_only_statement() -> None:
    sections = slice_sections(_synthetic_report(), load_section_map(), toc_page_indices=[0])
    balance = [s for s in sections if s.section_id == "hkex_balance_sheet"]
    # Exactly one balance sheet: the consolidated one. The bare "Balance Sheet"
    # parent-only statement is a different entity and is not emitted.
    assert len(balance) == 1
    assert "parent-only" not in balance[0].text
    assert "Total assets 500 450" in balance[0].text


def test_slice_sections_coarse_fallback_locates_statements_in_chapter() -> None:
    toc = (
        "CONTENTS\n"
        "1 CHAIRMAN'S STATEMENT\n"
        "2 FINANCIAL STATEMENTS\n"
        "5 NOTES ON THE FINANCIAL STATEMENTS"
    )
    pages = [
        toc,
        "CHAIRMAN'S STATEMENT\nBody.",
        "FINANCIAL STATEMENTS\nSection divider.",
        "CONSOLIDATED INCOME STATEMENT\n2024 2023\nRevenue 100 90",
        "CONSOLIDATED BALANCE SHEET\n2024 2023\nTotal assets 500 450",
        "NOTES ON THE FINANCIAL STATEMENTS\nDetail.",
    ]
    sections = slice_sections(pages, load_section_map(), toc_page_indices=[0])
    ids = {s.section_id for s in sections}
    assert "hkex_income_statement" in ids
    assert "hkex_balance_sheet" in ids
    income = next(s for s in sections if s.section_id == "hkex_income_statement")
    assert "Revenue 100 90" in income.text


def test_slice_sections_raises_when_statements_unlocatable() -> None:
    toc = "CONTENTS\n1 CHAIRMAN'S STATEMENT\n2 FINANCIAL STATEMENTS\n4 APPENDIX"
    pages = [
        toc,
        "CHAIRMAN'S STATEMENT\nBody.",
        "FINANCIAL STATEMENTS\n\x00 garbled image-only page",
        "\x00 more garble",
        "APPENDIX\nOther.",
    ]
    with pytest.raises(HKSectioningError, match="No financial statements"):
        slice_sections(pages, load_section_map(), toc_page_indices=[0])


def test_slice_sections_raises_when_no_toc_page_found() -> None:
    with pytest.raises(HKSectioningError, match="table-of-contents"):
        slice_sections(["only body text", "more body"], load_section_map())
