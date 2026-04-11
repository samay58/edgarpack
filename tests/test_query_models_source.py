"""Tests for the CitedValue.source field (self-heal v1)."""

from __future__ import annotations

import unittest
from datetime import date

from edgarpack.query.models import CitedValue, DerivedValue


def _make_cited(**overrides) -> CitedValue:
    defaults = dict(
        value=100.0,
        unit="USD",
        metric="revenue",
        concept="Revenues",
        period_end=date(2025, 1, 1),
        fiscal_year=2025,
        fiscal_period="FY",
        form_type="10-K",
        filed=date(2025, 2, 1),
        accession="0001045810-25-000001",
        cik="0001045810",
        company="NVIDIA CORP",
    )
    defaults.update(overrides)
    return CitedValue(**defaults)


class TestCitedValueSource(unittest.TestCase):
    def test_default_source_is_hardcoded(self) -> None:
        cv = _make_cited()
        self.assertEqual(cv.source, "hardcoded")

    def test_source_can_be_set(self) -> None:
        cv = _make_cited(source="learned:fuzzy")
        self.assertEqual(cv.source, "learned:fuzzy")

    def test_derived_inherits_source_field(self) -> None:
        dv = DerivedValue(
            value=150.0,
            unit="USD",
            metric="ebitda",
            concept="operating_income + depreciation_amortization",
            period_end=date(2025, 1, 1),
            fiscal_year=2025,
            fiscal_period="FY",
            form_type="10-K",
            filed=date(2025, 2, 1),
            accession="0001045810-25-000001",
            cik="0001045810",
            company="NVIDIA CORP",
            source="learned:llm",
        )
        self.assertEqual(dv.source, "learned:llm")

    def test_to_cited_dict_includes_source_when_not_hardcoded(self) -> None:
        cv = _make_cited(source="learned:fuzzy")
        d = cv.to_cited_dict()
        self.assertEqual(d.get("source"), "learned:fuzzy")

    def test_to_cited_dict_omits_source_when_hardcoded(self) -> None:
        cv = _make_cited()
        d = cv.to_cited_dict()
        # Either key absent OR key == "hardcoded" is acceptable; we pick absent
        # to keep legacy JSON consumers unchanged.
        self.assertNotIn("source", d)

    def test_to_lean_metric_surfaces_source_when_learned(self) -> None:
        cv = _make_cited(source="learned:llm")
        d = cv.to_lean_metric()
        self.assertEqual(d.get("source"), "learned:llm")


if __name__ == "__main__":
    unittest.main()
