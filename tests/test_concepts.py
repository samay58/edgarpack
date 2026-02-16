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
        result = resolve_concept("revenue", facts)
        self.assertIsNotNone(result)
        concept, taxonomy = result
        self.assertEqual(concept, "Revenues")
        self.assertEqual(taxonomy, "us-gaap")

    def test_fallback_to_second_concept(self) -> None:
        facts = {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {"USD": [{"val": 100}]}
                },
            }
        }
        result = resolve_concept("revenue", facts)
        self.assertIsNotNone(result)
        concept, taxonomy = result
        self.assertEqual(concept, "RevenueFromContractWithCustomerExcludingAssessedTax")
        self.assertEqual(taxonomy, "us-gaap")

    def test_no_concept_found(self) -> None:
        facts = {"us-gaap": {"SomeOtherConcept": {"units": {"USD": [{"val": 1}]}}}}
        result = resolve_concept("revenue", facts)
        self.assertIsNone(result)

    def test_derived_metric_returns_none(self) -> None:
        facts = {"us-gaap": {}}
        result = resolve_concept("gross_margin", facts)
        self.assertIsNone(result)

    def test_unknown_metric_returns_none(self) -> None:
        facts = {"us-gaap": {}}
        result = resolve_concept("nonexistent_metric", facts)
        self.assertIsNone(result)

    def test_total_debt_prefers_non_lease_concept(self) -> None:
        """total_debt should prefer debt tags that do not include lease liabilities."""
        facts = {
            "us-gaap": {
                "LongTermDebt": {"units": {"USD": [{"val": 100, "fy": 2025, "fp": "FY"}]}},
                "LongTermDebtAndCapitalLeaseObligations": {
                    "units": {"USD": [{"val": 140, "fy": 2025, "fp": "FY"}]}
                },
                "OperatingLeaseLiability": {
                    "units": {"USD": [{"val": 40, "fy": 2025, "fp": "FY"}]}
                },
            }
        }
        result = resolve_concept("total_debt", facts)
        self.assertIsNotNone(result)
        concept, taxonomy = result
        self.assertEqual(concept, "LongTermDebt")
        self.assertEqual(taxonomy, "us-gaap")

    def test_cash_prefers_cash_only_tag(self) -> None:
        """cash should prioritize cash-only tags over cash-plus-investments tags."""
        facts = {
            "us-gaap": {
                "CashAndCashEquivalentsAtCarryingValue": {
                    "units": {"USD": [{"val": 80, "fy": 2025, "fp": "FY"}]}
                },
                "CashCashEquivalentsAndShortTermInvestments": {
                    "units": {"USD": [{"val": 140, "fy": 2025, "fp": "FY"}]}
                },
            }
        }
        result = resolve_concept("cash", facts)
        self.assertIsNotNone(result)
        concept, _taxonomy = result
        self.assertEqual(concept, "CashAndCashEquivalentsAtCarryingValue")


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
        result = resolve_concept("revenue", facts)
        self.assertIsNotNone(result)
        concept, _ = result
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
        result = resolve_concept("revenue", facts)
        self.assertIsNotNone(result)
        concept, _ = result
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
        result = resolve_concept("revenue", facts)
        self.assertIsNotNone(result)
        concept, _ = result
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
        result = resolve_concept("revenue", facts)
        self.assertIsNotNone(result)
        concept, _ = result
        self.assertEqual(concept, "SalesRevenueNet")


class TestNullSafety(unittest.TestCase):
    def test_max_annual_fy_with_null(self) -> None:
        """_max_annual_fy should handle fy=None entries without crashing."""
        from edgarpack.query.concepts import _max_annual_fy

        units = {
            "USD": [
                {"val": 100, "fy": None, "fp": "FY"},
                {"val": 200, "fy": 2024, "fp": "FY"},
            ]
        }
        result = _max_annual_fy(units)
        self.assertEqual(result, 2024)

    def test_max_any_fy_with_null(self) -> None:
        """_max_any_fy should handle fy=None entries without crashing."""
        from edgarpack.query.concepts import _max_any_fy

        units = {
            "USD": [
                {"val": 100, "fy": None, "fp": "Q1"},
                {"val": 200, "fy": 2025, "fp": "Q1"},
            ]
        }
        result = _max_any_fy(units)
        self.assertEqual(result, 2025)


class TestIfrsFallback(unittest.TestCase):
    def test_ifrs_fallback_when_no_gaap(self) -> None:
        """resolve_concept should fall back to ifrs-full when us-gaap has no data."""
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "Revenue": {"units": {"EUR": [{"val": 28_000_000_000, "fy": 2024, "fp": "FY"}]}},
            },
        }
        result = resolve_concept("revenue", facts)
        self.assertIsNotNone(result)
        concept, taxonomy = result
        self.assertEqual(concept, "Revenue")
        self.assertEqual(taxonomy, "ifrs-full")

    def test_gaap_preferred_over_ifrs(self) -> None:
        """When both taxonomies have data, us-gaap with recent data wins."""
        facts = {
            "us-gaap": {
                "Revenues": {"units": {"USD": [{"val": 100, "fy": 2025, "fp": "FY"}]}},
            },
            "ifrs-full": {
                "Revenue": {"units": {"EUR": [{"val": 200, "fy": 2025, "fp": "FY"}]}},
            },
        }
        result = resolve_concept("revenue", facts)
        self.assertIsNotNone(result)
        concept, taxonomy = result
        self.assertEqual(concept, "Revenues")
        self.assertEqual(taxonomy, "us-gaap")

    def test_ifrs_wins_when_gaap_stale(self) -> None:
        """IFRS with FY2025 should beat us-gaap with only FY=0 (no annual data)."""
        facts = {
            "us-gaap": {
                "Revenues": {"units": {"USD": [{"val": 10, "fy": 0, "fp": "Q1"}]}},
            },
            "ifrs-full": {
                "Revenue": {"units": {"EUR": [{"val": 200, "fy": 2025, "fp": "FY"}]}},
            },
        }
        result = resolve_concept("revenue", facts)
        self.assertIsNotNone(result)
        concept, taxonomy = result
        self.assertEqual(concept, "Revenue")
        self.assertEqual(taxonomy, "ifrs-full")


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
