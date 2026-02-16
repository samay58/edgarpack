"""Tests for GAAP concept normalization."""

from __future__ import annotations

import unittest

from edgarpack.query.concepts import ALL_METRICS, METRIC_MAP, get_metric_meta, resolve_concept


class TestMetricMap(unittest.TestCase):
    def test_all_metrics_have_entries(self) -> None:
        for metric in ALL_METRICS:
            self.assertIn(metric, METRIC_MAP)

    def test_non_derived_have_concepts(self) -> None:
        for name, meta in METRIC_MAP.items():
            if not meta.derived:
                self.assertTrue(
                    len(meta.concepts) > 0,
                    f"Non-derived metric {name} has no concepts",
                )

    def test_derived_have_formula_and_components(self) -> None:
        for name, meta in METRIC_MAP.items():
            if meta.derived:
                self.assertIsNotNone(meta.formula, f"Derived metric {name} has no formula")
                self.assertTrue(
                    len(meta.components) > 0,
                    f"Derived metric {name} has no components",
                )

    def test_derived_components_exist_in_map(self) -> None:
        for name, meta in METRIC_MAP.items():
            if meta.derived:
                for comp in meta.components:
                    self.assertIn(
                        comp,
                        METRIC_MAP,
                        f"Derived metric {name} references unknown component {comp}",
                    )

    def test_known_metrics_count(self) -> None:
        # Plan specifies ~30 metrics
        self.assertGreaterEqual(len(ALL_METRICS), 28)


class TestResolveConceptFallback(unittest.TestCase):
    def test_first_concept_matched(self) -> None:
        facts = {
            "us-gaap": {
                "Revenues": {"units": {"USD": [{"val": 100}]}},
                "SalesRevenueNet": {"units": {"USD": [{"val": 99}]}},
            }
        }
        concept = resolve_concept("revenue", facts)
        self.assertEqual(concept, "Revenues")

    def test_fallback_to_second_concept(self) -> None:
        facts = {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {"USD": [{"val": 100}]}
                },
            }
        }
        concept = resolve_concept("revenue", facts)
        self.assertEqual(concept, "RevenueFromContractWithCustomerExcludingAssessedTax")

    def test_no_concept_found(self) -> None:
        facts = {"us-gaap": {"SomeOtherConcept": {"units": {"USD": [{"val": 1}]}}}}
        concept = resolve_concept("revenue", facts)
        self.assertIsNone(concept)

    def test_derived_metric_returns_none(self) -> None:
        facts = {"us-gaap": {}}
        concept = resolve_concept("gross_margin", facts)
        self.assertIsNone(concept)

    def test_unknown_metric_returns_none(self) -> None:
        facts = {"us-gaap": {}}
        concept = resolve_concept("nonexistent_metric", facts)
        self.assertIsNone(concept)


class TestResolveConceptRecency(unittest.TestCase):
    def test_prefers_concept_with_newer_annual_data(self) -> None:
        """FY2018 vs FY2025: pick the concept with FY2025 data."""
        facts = {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [{"val": 100, "fy": 2018, "fp": "FY"}],
                    }
                },
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {
                        "USD": [{"val": 200, "fy": 2025, "fp": "FY"}],
                    }
                },
            }
        }
        concept = resolve_concept("revenue", facts)
        self.assertEqual(concept, "RevenueFromContractWithCustomerExcludingAssessedTax")

    def test_same_year_prefers_priority_order(self) -> None:
        """Both FY2025: pick the higher-priority concept (Revenues)."""
        facts = {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [{"val": 100, "fy": 2025, "fp": "FY"}],
                    }
                },
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {
                        "USD": [{"val": 200, "fy": 2025, "fp": "FY"}],
                    }
                },
            }
        }
        concept = resolve_concept("revenue", facts)
        self.assertEqual(concept, "Revenues")

    def test_concept_with_only_quarterly_data(self) -> None:
        """Annual concept (FY2024) beats quarterly-only concept (Q1 2025)."""
        facts = {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [{"val": 100, "fy": 2025, "fp": "Q1"}],
                    }
                },
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {
                        "USD": [{"val": 200, "fy": 2024, "fp": "FY"}],
                    }
                },
            }
        }
        concept = resolve_concept("revenue", facts)
        self.assertEqual(concept, "RevenueFromContractWithCustomerExcludingAssessedTax")

    def test_quarterly_only_beats_nothing(self) -> None:
        """Quarterly-only concept is returned over nothing."""
        facts = {
            "us-gaap": {
                "SalesRevenueNet": {
                    "units": {
                        "USD": [{"val": 50, "fy": 2025, "fp": "Q1"}],
                    }
                },
            }
        }
        concept = resolve_concept("revenue", facts)
        self.assertEqual(concept, "SalesRevenueNet")


class TestGetMetricMeta(unittest.TestCase):
    def test_known_metric(self) -> None:
        meta = get_metric_meta("revenue")
        self.assertIsNotNone(meta)
        self.assertTrue(meta.duration)
        self.assertFalse(meta.derived)

    def test_derived_metric(self) -> None:
        meta = get_metric_meta("gross_margin")
        self.assertIsNotNone(meta)
        self.assertTrue(meta.derived)

    def test_unknown_metric(self) -> None:
        self.assertIsNone(get_metric_meta("bogus"))


if __name__ == "__main__":
    unittest.main()
