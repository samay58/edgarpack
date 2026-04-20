"""CAGR metric computation and edge cases."""

from __future__ import annotations

import unittest

from edgarpack.query.concepts import METRIC_MAP
from edgarpack.query.financials import _compute_cagr, _compute_derived, _fy_equivalent
from edgarpack.query.models import DerivedValue


def _make_fy_revenue_facts(fy_values: dict[int, float]) -> dict:
    """Build a minimal us-gaap facts blob with annual Revenues for each FY."""
    entries = []
    for fy, val in sorted(fy_values.items()):
        entries.append(
            {
                "val": val,
                "start": f"{fy}-01-01",
                "end": f"{fy}-12-31",
                "fy": fy,
                "fp": "FY",
                "form": "10-K",
                "accn": f"0000000001-{str(fy + 1)[-2:]}-000001",
                "filed": f"{fy + 1}-03-01",
            }
        )
    return {"us-gaap": {"Revenues": {"units": {"USD": entries}}}}


class TestFyEquivalent(unittest.TestCase):
    def test_ltm_collapses_to_lfy(self) -> None:
        self.assertEqual(_fy_equivalent("ltm"), "lfy")

    def test_mrq_collapses_to_lfy(self) -> None:
        self.assertEqual(_fy_equivalent("mrq"), "lfy")

    def test_mrp_collapses_to_lfy(self) -> None:
        self.assertEqual(_fy_equivalent("mrp"), "lfy")

    def test_ltm_n_collapses_to_lfy_n(self) -> None:
        self.assertEqual(_fy_equivalent("ltm-2"), "lfy-2")

    def test_mrq_n_collapses_to_lfy_n(self) -> None:
        self.assertEqual(_fy_equivalent("mrq-3"), "lfy-3")

    def test_lfy_passes_through(self) -> None:
        self.assertEqual(_fy_equivalent("lfy"), "lfy")
        self.assertEqual(_fy_equivalent("lfy-1"), "lfy-1")

    def test_case_insensitive(self) -> None:
        self.assertEqual(_fy_equivalent("LTM-2"), "lfy-2")


class TestComputeCagrHelper(unittest.TestCase):
    def test_cagr_3y_matches_hand_calc(self) -> None:
        facts = _make_fy_revenue_facts({2021: 50.0, 2022: 70.0, 2023: 90.0, 2024: 100.0})
        meta = METRIC_MAP["revenue_cagr_3y"]
        result = _compute_cagr(facts, "revenue_cagr_3y", meta, "Test", "0000000001", "lfy", None)
        self.assertIsNotNone(result)
        # (100 / 50) ^ (1/3) - 1 ~ 0.25992
        self.assertAlmostEqual(result.value, (100.0 / 50.0) ** (1 / 3) - 1, places=6)
        self.assertEqual(result.unit, "pure")
        self.assertEqual(result.fiscal_period, "CAGR-3Y")
        self.assertIn("end", result.components)
        self.assertIn("start", result.components)
        self.assertEqual(result.components["end"].value, 100.0)
        self.assertEqual(result.components["start"].value, 50.0)

    def test_cagr_5y_matches_hand_calc(self) -> None:
        facts = _make_fy_revenue_facts(
            {2019: 20.0, 2020: 30.0, 2021: 50.0, 2022: 70.0, 2023: 90.0, 2024: 100.0}
        )
        meta = METRIC_MAP["revenue_cagr_5y"]
        result = _compute_cagr(facts, "revenue_cagr_5y", meta, "Test", "0000000001", "lfy", None)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.value, (100.0 / 20.0) ** (1 / 5) - 1, places=6)

    def test_missing_start_returns_none(self) -> None:
        facts = _make_fy_revenue_facts({2023: 90.0, 2024: 100.0})
        meta = METRIC_MAP["revenue_cagr_3y"]
        result = _compute_cagr(facts, "revenue_cagr_3y", meta, "Test", "0000000001", "lfy", None)
        self.assertIsNone(result)

    def test_zero_start_returns_none(self) -> None:
        facts = _make_fy_revenue_facts({2021: 0.0, 2022: 10.0, 2023: 20.0, 2024: 30.0})
        meta = METRIC_MAP["revenue_cagr_3y"]
        result = _compute_cagr(facts, "revenue_cagr_3y", meta, "Test", "0000000001", "lfy", None)
        self.assertIsNone(result)

    def test_sign_flip_returns_none(self) -> None:
        # Start negative (net loss), end positive -> CAGR undefined.
        facts = _make_fy_revenue_facts({2021: -50.0, 2022: -20.0, 2023: 10.0, 2024: 30.0})
        meta = METRIC_MAP["revenue_cagr_3y"]
        result = _compute_cagr(facts, "revenue_cagr_3y", meta, "Test", "0000000001", "lfy", None)
        self.assertIsNone(result)

    def test_ltm_parent_substitutes_to_lfy(self) -> None:
        """ltm parent period uses FY-anchored components for CAGR."""
        facts = _make_fy_revenue_facts({2021: 50.0, 2022: 70.0, 2023: 90.0, 2024: 100.0})
        meta = METRIC_MAP["revenue_cagr_3y"]
        via_lfy = _compute_cagr(facts, "revenue_cagr_3y", meta, "Test", "0000000001", "lfy", None)
        via_ltm = _compute_cagr(facts, "revenue_cagr_3y", meta, "Test", "0000000001", "ltm", None)
        self.assertIsNotNone(via_lfy)
        self.assertIsNotNone(via_ltm)
        # Same underlying FY endpoints -> same CAGR value.
        self.assertAlmostEqual(via_lfy.value, via_ltm.value, places=9)
        self.assertEqual(via_lfy.components["end"].fiscal_year, 2024)
        self.assertEqual(via_ltm.components["end"].fiscal_year, 2024)

    def test_lfy_minus_1_parent_shifts_endpoints(self) -> None:
        """lfy-1 parent anchors CAGR on the prior fiscal year's window."""
        facts = _make_fy_revenue_facts(
            {2020: 40.0, 2021: 50.0, 2022: 70.0, 2023: 90.0, 2024: 100.0}
        )
        meta = METRIC_MAP["revenue_cagr_3y"]
        result = _compute_cagr(facts, "revenue_cagr_3y", meta, "Test", "0000000001", "lfy-1", None)
        self.assertIsNotNone(result)
        # End = FY2023 (90), Start = FY2020 (40)
        self.assertEqual(result.components["end"].fiscal_year, 2023)
        self.assertEqual(result.components["start"].fiscal_year, 2020)
        self.assertAlmostEqual(result.value, (90.0 / 40.0) ** (1 / 3) - 1, places=6)


class TestCagrViaComputeDerived(unittest.TestCase):
    """Verify the _compute_derived dispatch routes kind='cagr' correctly."""

    def test_dispatches_to_cagr_path(self) -> None:
        facts = _make_fy_revenue_facts({2021: 50.0, 2022: 70.0, 2023: 90.0, 2024: 100.0})
        meta = METRIC_MAP["revenue_cagr_3y"]
        result = _compute_derived(
            facts,
            "revenue_cagr_3y",
            meta,
            "Test",
            "0000000001",
            "lfy",
            None,
        )
        self.assertIsNotNone(result)
        self.assertIsInstance(result, DerivedValue)
        self.assertEqual(result.fiscal_period, "CAGR-3Y")
        self.assertEqual(result.unit, "pure")


if __name__ == "__main__":
    unittest.main()
