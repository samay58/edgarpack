"""CitedValue is the core value type across all query output. We extend it
with two optional S-1-specific fields: is_pro_forma + pro_forma_note.
Existing periodic-filing paths must continue to work without change.
"""

from datetime import date

from edgarpack.query.models import CitedValue


def test_cited_value_defaults_is_pro_forma_false():
    cv = CitedValue(
        value=1,
        unit="USD",
        metric="revenue",
        concept="Revenues",
        period_end=date(2024, 12, 31),
        fiscal_year=2024,
        fiscal_period="FY",
        form_type="10-K",
        filed=date(2025, 2, 1),
        accession="0000320193-25-000006",
        cik="0000320193",
        company="Apple Inc.",
    )
    assert cv.is_pro_forma is False
    assert cv.pro_forma_note is None


def test_cited_value_accepts_pro_forma_fields():
    cv = CitedValue(
        value=1,
        unit="USD",
        metric="cash_and_equivalents",
        concept="CashAndCashEquivalentsAtCarryingValue",
        period_end=date(2025, 12, 31),
        fiscal_year=2025,
        fiscal_period="FY",
        form_type="S-1",
        filed=date(2026, 4, 17),
        accession="0001628280-26-025762",
        cik="0002021728",
        company="Cerebras Systems Inc.",
        source="s1_snapshot",
        is_pro_forma=True,
        pro_forma_note="assumes IPO price $32.50, midpoint",
    )
    assert cv.is_pro_forma is True
    assert cv.pro_forma_note == "assumes IPO price $32.50, midpoint"
    assert cv.source == "s1_snapshot"
