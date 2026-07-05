"""Regression tests for CitedValue.period_end becoming date | None.

Follows the china-provenance packet: facts.json was made to honestly omit
period-end dates for HKEX packs whose manifests carry no fiscal year end, but
the SEC-shared ``_value_to_cited`` re-fabricated a ``date.min`` (0001-01-01)
end for them. A China fact with no end must surface ``period_end=None`` (n/a in
tables, null in JSON, never 0001-01-01). SEC facts, which always carry a real
end date, must stay byte-identical, and a corrupt SEC fact with no end must
fail loud rather than fabricate a date. FX conversion of a None-period_end flow
fails closed.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from edgarpack.query.currency import convert_cited_to_usd, format_cited_currency
from edgarpack.query.models import CitedValue
from edgarpack.query.periods import _value_to_cited


def _sec_fact() -> dict[str, object]:
    return {
        "val": 100_000_000_000,
        "start": "2023-01-30",
        "end": "2024-01-28",
        "fy": 2023,
        "fp": "FY",
        "form": "10-K",
        "accn": "0001045810-24-000029",
        "filed": "2024-02-21",
    }


def _china_point_no_end() -> dict[str, object]:
    # Real HKEX regex fact: extraction_method present, no SEC frame tag, and no
    # end date because the pack manifest states no fiscal year end.
    return {
        "val": 5_000_000_000,
        "fy": 2024,
        "fp": "FY",
        "form": "ANNUAL-REPORT",
        "accn": "",
        "extraction_method": "regex",
        "section_id": "hkex_income_statement",
    }


def test_china_fact_without_end_has_none_period_end() -> None:
    cited = _value_to_cited(
        _china_point_no_end(),
        metric="revenue",
        concept="Revenue",
        unit="CNY",
        company="Zhipu",
        cik="0899",
        taxonomy="hkfrs",
    )
    assert cited.period_end is None
    assert cited._period_str() == "n/a"

    record = cited.to_citation_record("C1")
    assert record["period_end"] is None
    assert record["period"] == "n/a"

    cited_dict = cited.to_cited_dict()
    assert cited_dict["period_end"] is None

    assert "0001-01-01" not in json.dumps(record)
    assert "0001-01-01" not in json.dumps(cited_dict)


def test_sec_fact_with_end_is_unchanged() -> None:
    cited = _value_to_cited(
        _sec_fact(),
        metric="revenue",
        concept="Revenues",
        unit="USD",
        company="NVIDIA",
        cik="0001045810",
        taxonomy="us-gaap",
    )
    assert cited.period_end == date(2024, 1, 28)
    assert cited._period_str() == "2023-01-30/2024-01-28"

    record = cited.to_citation_record("C1")
    assert record["period_end"] == "2024-01-28"
    assert record["period"] == "2023-01-30/2024-01-28"

    # The stable fact-id / citation key still carries the real end date.
    assert "|2024-01-28|" in cited.citation_key

    cited_dict = cited.to_cited_dict()
    assert cited_dict["period_end"] == "2024-01-28"


def test_sec_fact_missing_end_raises() -> None:
    bad = _sec_fact()
    bad.pop("end")
    with pytest.raises(ValueError, match="period end"):
        _value_to_cited(
            bad,
            metric="revenue",
            concept="Revenues",
            unit="USD",
            company="NVIDIA",
            cik="0001045810",
            taxonomy="us-gaap",
        )


def test_fx_conversion_fails_closed_on_absent_period_end() -> None:
    cited = CitedValue(
        value=5_000_000_000,
        unit="CNY",
        metric="revenue",
        concept="Revenue",
        period_end=None,
        fiscal_year=2024,
        fiscal_period="FY",
        form_type="ANNUAL-REPORT",
        filed=None,
        accession="",
        cik="0899",
        company="Zhipu",
        reporting_currency="CNY",
        accounting_standard="HKFRS",
    )
    # No fabricated as_of date -> no conversion at all.
    assert convert_cited_to_usd(cited) is None
    # Formatting falls back to the native figure instead of crashing.
    assert format_cited_currency(cited, mode="both") == format_cited_currency(cited, mode="native")
