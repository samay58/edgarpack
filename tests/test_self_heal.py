"""Tests for self-heal internals (fuzzy match, verifier, orchestrator)."""

from __future__ import annotations

import unittest

from edgarpack.query.self_heal import (
    METRIC_HINTS,
    _company_concepts,
    _fuzzy_match,
)

# Small synthetic companyfacts fragment for fuzzy-match tests
_FAKE_FACTS = {
    "us-gaap": {
        "Revenues": {
            "units": {"USD": [{"val": 130_000_000_000, "fy": 2024, "fp": "FY"}]},
        },
        "NetCashProvidedByUsedInOperatingActivities": {
            "units": {"USD": [{"val": 28_000_000_000, "fy": 2024, "fp": "FY"}]},
        },
        "PaymentsToAcquirePropertyPlantAndEquipment": {
            "units": {"USD": [{"val": 1_100_000_000, "fy": 2024, "fp": "FY"}]},
        },
        "EarningsPerShareDiluted": {
            "units": {"USD/shares": [{"val": 2.97, "fy": 2024, "fp": "FY"}]},
        },
    },
    "dei": {
        # Non-financial, should be ignored
        "EntityCommonStockSharesOutstanding": {
            "units": {"shares": [{"val": 24_600_000_000, "fy": 2024, "fp": "FY"}]},
        },
    },
}


class TestCompanyConcepts(unittest.TestCase):
    def test_lists_us_gaap_and_ifrs_concepts(self) -> None:
        concepts = _company_concepts(_FAKE_FACTS)
        self.assertIn(("Revenues", "us-gaap"), concepts)
        self.assertIn(("NetCashProvidedByUsedInOperatingActivities", "us-gaap"), concepts)

    def test_skips_dei_and_other_taxonomies(self) -> None:
        concepts = _company_concepts(_FAKE_FACTS)
        for _name, taxonomy in concepts:
            self.assertIn(taxonomy, ("us-gaap", "ifrs-full"))

    def test_skips_concepts_with_no_non_none_values(self) -> None:
        facts = {
            "us-gaap": {
                "AllNone": {"units": {"USD": [{"val": None}]}},
                "OK":      {"units": {"USD": [{"val": 100}]}},
            }
        }
        concepts = _company_concepts(facts)
        names = {c[0] for c in concepts}
        self.assertIn("OK", names)
        self.assertNotIn("AllNone", names)


class TestFuzzyMatch(unittest.TestCase):
    def test_matches_operating_cash_flow_on_hint(self) -> None:
        candidates = _company_concepts(_FAKE_FACTS)
        hit = _fuzzy_match(
            metric="operating_cash_flow",
            candidates=candidates,
            facts=_FAKE_FACTS,
        )
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit[0], "NetCashProvidedByUsedInOperatingActivities")
        self.assertEqual(hit[1], "us-gaap")

    def test_matches_capex_via_hint_tokens(self) -> None:
        candidates = _company_concepts(_FAKE_FACTS)
        hit = _fuzzy_match(
            metric="capex",
            candidates=candidates,
            facts=_FAKE_FACTS,
        )
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit[0], "PaymentsToAcquirePropertyPlantAndEquipment")

    def test_returns_none_below_threshold(self) -> None:
        candidates = _company_concepts(_FAKE_FACTS)
        hit = _fuzzy_match(
            metric="xyz_nonsense_unrelated",
            candidates=candidates,
            facts=_FAKE_FACTS,
        )
        self.assertIsNone(hit)

    def test_metric_hints_dict_is_non_empty(self) -> None:
        # Sanity check: we want at least the core metrics hinted
        for m in ("revenue", "operating_cash_flow", "capex", "free_cash_flow"):
            self.assertIn(m, METRIC_HINTS)


from edgarpack.query.self_heal import verify_order_of_magnitude


class TestVerifyOrderOfMagnitude(unittest.TestCase):
    def test_exact_match_passes(self) -> None:
        self.assertTrue(verify_order_of_magnitude(100.0, 100.0))

    def test_within_2x_passes(self) -> None:
        self.assertTrue(verify_order_of_magnitude(150.0, 100.0))
        self.assertTrue(verify_order_of_magnitude(70.0, 100.0))

    def test_within_4x_passes(self) -> None:
        self.assertTrue(verify_order_of_magnitude(399.0, 100.0))
        self.assertTrue(verify_order_of_magnitude(26.0, 100.0))

    def test_beyond_4x_fails(self) -> None:
        self.assertFalse(verify_order_of_magnitude(500.0, 100.0))
        self.assertFalse(verify_order_of_magnitude(20.0, 100.0))

    def test_zero_prior_year_fails(self) -> None:
        self.assertFalse(verify_order_of_magnitude(100.0, 0.0))

    def test_none_prior_year_fails(self) -> None:
        self.assertFalse(verify_order_of_magnitude(100.0, None))

    def test_handles_negative_values(self) -> None:
        # Operating losses: -100 and -150 should pass
        self.assertTrue(verify_order_of_magnitude(-150.0, -100.0))
        # Sign flip is suspicious but within 4x magnitude is still accepted
        self.assertTrue(verify_order_of_magnitude(100.0, -150.0))


if __name__ == "__main__":
    unittest.main()
