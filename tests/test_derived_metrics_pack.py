"""Coverage for the expanded derived metrics pack.

Exercises growth / trend / intensity / quality metrics against synthetic facts.
The CAGR family is tested separately in test_cagr.py.
"""

from __future__ import annotations

import unittest

from edgarpack.query.concepts import METRIC_MAP
from edgarpack.query.financials import _compute_derived, _derived_unit


def _entry(concept_fy: int, val: float, fp: str = "FY") -> dict:
    year = concept_fy
    return {
        "val": val,
        "start": f"{year}-01-01",
        "end": f"{year}-12-31",
        "fy": year,
        "fp": fp,
        "form": "10-K",
        "accn": f"0000000001-{str(year + 1)[-2:]}-000001",
        "filed": f"{year + 1}-03-01",
    }


def _facts_with(concept_entries: dict[str, list[dict]]) -> dict:
    """Build a us-gaap facts blob with `{concept: [entries...]}`."""
    return {
        "us-gaap": {
            concept: {"units": {"USD": entries}} for concept, entries in concept_entries.items()
        }
    }


class TestGrowthFamily(unittest.TestCase):
    def test_net_income_growth_yoy(self) -> None:
        facts = _facts_with(
            {
                "NetIncomeLoss": [
                    _entry(2023, 10_000_000_000),
                    _entry(2024, 15_000_000_000),
                ],
            }
        )
        meta = METRIC_MAP["net_income_growth_yoy"]
        result = _compute_derived(
            facts, "net_income_growth_yoy", meta, "Test", "0000000001", "lfy", None
        )
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.value, 0.5, places=6)

    def test_operating_income_growth_yoy(self) -> None:
        facts = _facts_with(
            {
                "OperatingIncomeLoss": [
                    _entry(2023, 4_000_000_000),
                    _entry(2024, 6_000_000_000),
                ],
            }
        )
        meta = METRIC_MAP["operating_income_growth_yoy"]
        result = _compute_derived(
            facts, "operating_income_growth_yoy", meta, "Test", "0000000001", "lfy", None
        )
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.value, 0.5, places=6)

    def test_eps_growth_yoy(self) -> None:
        facts = _facts_with(
            {
                "EarningsPerShareDiluted": [
                    _entry(2023, 4.0),
                    _entry(2024, 6.0),
                ],
            }
        )
        meta = METRIC_MAP["eps_growth_yoy"]
        result = _compute_derived(facts, "eps_growth_yoy", meta, "Test", "0000000001", "lfy", None)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.value, 0.5, places=6)


class TestMarginTrends(unittest.TestCase):
    def test_operating_margin_trend(self) -> None:
        facts = _facts_with(
            {
                "Revenues": [
                    _entry(2023, 100.0),
                    _entry(2024, 200.0),
                ],
                "OperatingIncomeLoss": [
                    _entry(2023, 10.0),
                    _entry(2024, 40.0),
                ],
            }
        )
        meta = METRIC_MAP["operating_margin_trend"]
        result = _compute_derived(
            facts, "operating_margin_trend", meta, "Test", "0000000001", "lfy", None
        )
        self.assertIsNotNone(result)
        # 40/200 - 10/100 = 0.2 - 0.1 = 0.1
        self.assertAlmostEqual(result.value, 0.1, places=6)

    def test_net_margin_trend(self) -> None:
        facts = _facts_with(
            {
                "Revenues": [
                    _entry(2023, 100.0),
                    _entry(2024, 200.0),
                ],
                "NetIncomeLoss": [
                    _entry(2023, 5.0),
                    _entry(2024, 30.0),
                ],
            }
        )
        meta = METRIC_MAP["net_margin_trend"]
        result = _compute_derived(
            facts, "net_margin_trend", meta, "Test", "0000000001", "lfy", None
        )
        self.assertIsNotNone(result)
        # 30/200 - 5/100 = 0.15 - 0.05 = 0.1
        self.assertAlmostEqual(result.value, 0.1, places=6)


class TestIntensityFamily(unittest.TestCase):
    def test_sga_intensity(self) -> None:
        facts = _facts_with(
            {
                "Revenues": [_entry(2024, 1_000_000_000)],
                "SellingGeneralAndAdministrativeExpense": [_entry(2024, 100_000_000)],
            }
        )
        meta = METRIC_MAP["sga_intensity"]
        result = _compute_derived(facts, "sga_intensity", meta, "Test", "0000000001", "lfy", None)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.value, 0.1, places=6)

    def test_capex_intensity(self) -> None:
        facts = _facts_with(
            {
                "Revenues": [_entry(2024, 1_000_000_000)],
                "PaymentsToAcquirePropertyPlantAndEquipment": [_entry(2024, 50_000_000)],
            }
        )
        meta = METRIC_MAP["capex_intensity"]
        result = _compute_derived(facts, "capex_intensity", meta, "Test", "0000000001", "lfy", None)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.value, 0.05, places=6)


class TestQualityComposite(unittest.TestCase):
    def test_fcf_to_net_income(self) -> None:
        facts = _facts_with(
            {
                "NetIncomeLoss": [_entry(2024, 100.0)],
                "NetCashProvidedByUsedInOperatingActivities": [_entry(2024, 150.0)],
                "PaymentsToAcquirePropertyPlantAndEquipment": [_entry(2024, 30.0)],
            }
        )
        meta = METRIC_MAP["fcf_to_net_income"]
        result = _compute_derived(
            facts, "fcf_to_net_income", meta, "Test", "0000000001", "lfy", None
        )
        self.assertIsNotNone(result)
        # FCF = 150 - 30 = 120; ratio = 120 / 100 = 1.2
        self.assertAlmostEqual(result.value, 1.2, places=6)

    def test_rule_of_40(self) -> None:
        facts = _facts_with(
            {
                "Revenues": [
                    _entry(2023, 100.0),
                    _entry(2024, 150.0),
                ],
                "NetCashProvidedByUsedInOperatingActivities": [
                    _entry(2023, 10.0),
                    _entry(2024, 30.0),
                ],
                "PaymentsToAcquirePropertyPlantAndEquipment": [
                    _entry(2023, 0.0),
                    _entry(2024, 15.0),
                ],
            }
        )
        meta = METRIC_MAP["rule_of_40"]
        result = _compute_derived(facts, "rule_of_40", meta, "Test", "0000000001", "lfy", None)
        self.assertIsNotNone(result)
        # revenue_growth_yoy = 150/100 - 1 = 0.5
        # FCF FY24 = 30 - 15 = 15; fcf_margin = 15 / 150 = 0.1
        # rule_of_40 = 0.5 + 0.1 = 0.6
        self.assertAlmostEqual(result.value, 0.6, places=6)


class TestUnitClassification(unittest.TestCase):
    """Growth / trend / intensity / quality metrics must render as ratios."""

    def test_new_metrics_are_pure_unit(self) -> None:
        from edgarpack.query.models import CitedValue

        components = {
            "a": CitedValue(
                value=1.0,
                unit="USD",
                metric="foo",
                concept="Foo",
                period_end=__import__("datetime").date(2024, 12, 31),
                fiscal_year=2024,
                fiscal_period="FY",
                form_type="10-K",
                filed=__import__("datetime").date(2025, 3, 1),
                accession="0000000001-25-000001",
                cik="0000000001",
                company="Test",
            )
        }
        for metric in (
            "net_income_growth_yoy",
            "operating_income_growth_yoy",
            "eps_growth_yoy",
            "operating_margin_trend",
            "net_margin_trend",
            "sga_intensity",
            "sm_intensity",
            "capex_intensity",
            "fcf_to_net_income",
            "rule_of_40",
            "revenue_growth_yoy",
            "gross_margin_trend",
            "r_and_d_intensity",
        ):
            self.assertEqual(
                _derived_unit(metric, components),
                "pure",
                msg=f"{metric} should be pure (dimensionless)",
            )


if __name__ == "__main__":
    unittest.main()
