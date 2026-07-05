"""Currency / accounting-standard anchor shapes added for build-hk-construct.

Covers the three anchor shapes (presentation clause, Anta's parenthetical note
header, BYD's numbered reporting-currency note), CAS detection, joint IFRS/HKFRS
citation normalization, and the both-anchors-missing failure. The Anta and BYD
fixtures are real excerpts from their FY2025 annual reports.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from edgarpack.hk.acquire import (
    HKFilingMetadataError,
    extract_metadata_from_text,
)

_FIXTURES = Path(__file__).parent / "fixtures" / "hkex_toc"


def test_presentation_clause_anchor_still_resolves_currency() -> None:
    text = (
        "2.4 Presentation currency\n"
        "The Group presents its financial statements in United States dollars, which is "
        "also the functional currency of the Company.\n"
        "These financial statements comply with IFRS Accounting Standards."
    )
    meta = extract_metadata_from_text(text, source="synthetic.pdf")
    assert meta.currency == "USD"
    assert meta.accounting_standard == "IFRS"


def test_anta_parenthetical_note_and_joint_citation_normalizes_to_ifrs() -> None:
    meta = extract_metadata_from_text(
        (_FIXTURES / "metadata_anta_joint.txt").read_text(), source="anta.pdf"
    )
    assert meta.currency == "CNY"
    assert meta.accounting_standard == "IFRS"
    assert meta.standard_note is not None
    assert "HKFRS" in meta.standard_note


def test_byd_reporting_currency_note_and_cas_basis_of_preparation() -> None:
    meta = extract_metadata_from_text(
        (_FIXTURES / "metadata_byd_cas.txt").read_text(), source="byd.pdf"
    )
    assert meta.currency == "CNY"
    assert meta.accounting_standard == "CAS"
    assert meta.standard_note is None


def test_hkfrs_only_filing_gets_no_joint_note() -> None:
    text = (
        "These financial statements have been prepared in accordance with Hong Kong "
        "Financial Reporting Standards (HKFRS).\n"
        "The Group presents its financial statements in Hong Kong dollars."
    )
    meta = extract_metadata_from_text(text, source="synthetic.pdf")
    assert meta.accounting_standard == "HKFRS"
    assert meta.currency == "HKD"
    assert meta.standard_note is None


def test_both_anchors_missing_raises() -> None:
    text = "CHAIRMAN'S STATEMENT\nThe year was strong across all segments.\n"
    with pytest.raises(HKFilingMetadataError):
        extract_metadata_from_text(text, source="bare.pdf")
