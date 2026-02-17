"""Tests for period selection and LTM math."""

from __future__ import annotations

import unittest

from edgarpack.query.concepts import MetricMeta
from edgarpack.query.models import DerivedValue
from edgarpack.query.periods import (
    select_annual_series,
    select_lfy,
    select_ltm,
    select_mrp,
    select_mrq,
    select_period,
    select_quarterly_series,
)

# Shared test fixtures: a minimal companyfacts-like structure
DURATION_META = MetricMeta(concepts=("Revenues",), duration=True)
INSTANT_META = MetricMeta(concepts=("Assets",), duration=False)

COMPANY = "Test Corp"
CIK = "0000000001"


def _make_facts(concept: str, values: list[dict]) -> dict:
    """Build a minimal companyfacts structure."""
    return {
        "us-gaap": {
            concept: {
                "units": {
                    "USD": values,
                }
            }
        }
    }


# Revenue-like values: FY2022-2023 annual + Q1-Q3 FY2023 and FY2024 quarterly.
# Mirrors real SEC data: Q2+ quarters have BOTH cumulative YTD and standalone 3-month entries.
REVENUE_VALUES = [
    # Annual FY2022
    {
        "val": 80_000_000_000,
        "start": "2022-01-30",
        "end": "2023-01-29",
        "fy": 2022,
        "fp": "FY",
        "form": "10-K",
        "accn": "0000000001-23-000001",
        "filed": "2023-03-01",
    },
    # Q1 FY2023 (3-month standalone = cumulative for Q1)
    {
        "val": 22_000_000_000,
        "start": "2023-01-30",
        "end": "2023-04-30",
        "fy": 2023,
        "fp": "Q1",
        "form": "10-Q",
        "accn": "0000000001-23-000002",
        "filed": "2023-06-01",
    },
    # Q2 FY2023 (6-month cumulative)
    {
        "val": 47_000_000_000,
        "start": "2023-01-30",
        "end": "2023-07-30",
        "fy": 2023,
        "fp": "Q2",
        "form": "10-Q",
        "accn": "0000000001-23-000003",
        "filed": "2023-09-01",
    },
    # Q2 FY2023 (3-month standalone)
    {
        "val": 25_000_000_000,
        "start": "2023-04-30",
        "end": "2023-07-30",
        "fy": 2023,
        "fp": "Q2",
        "form": "10-Q",
        "accn": "0000000001-23-000003",
        "filed": "2023-09-01",
    },
    # Q3 FY2023 (9-month cumulative)
    {
        "val": 75_000_000_000,
        "start": "2023-01-30",
        "end": "2023-10-29",
        "fy": 2023,
        "fp": "Q3",
        "form": "10-Q",
        "accn": "0000000001-23-000004",
        "filed": "2023-12-01",
    },
    # Q3 FY2023 (3-month standalone)
    {
        "val": 28_000_000_000,
        "start": "2023-07-30",
        "end": "2023-10-29",
        "fy": 2023,
        "fp": "Q3",
        "form": "10-Q",
        "accn": "0000000001-23-000004",
        "filed": "2023-12-01",
    },
    # Annual FY2023
    {
        "val": 100_000_000_000,
        "start": "2023-01-30",
        "end": "2024-01-28",
        "fy": 2023,
        "fp": "FY",
        "form": "10-K",
        "accn": "0000000001-24-000001",
        "filed": "2024-03-01",
    },
    # Q1 FY2024 (3-month standalone = cumulative for Q1)
    {
        "val": 30_000_000_000,
        "start": "2024-01-29",
        "end": "2024-04-28",
        "fy": 2024,
        "fp": "Q1",
        "form": "10-Q",
        "accn": "0000000001-24-000002",
        "filed": "2024-06-01",
    },
    # Q2 FY2024 (6-month cumulative)
    {
        "val": 65_000_000_000,
        "start": "2024-01-29",
        "end": "2024-07-28",
        "fy": 2024,
        "fp": "Q2",
        "form": "10-Q",
        "accn": "0000000001-24-000003",
        "filed": "2024-09-01",
    },
    # Q2 FY2024 (3-month standalone)
    {
        "val": 35_000_000_000,
        "start": "2024-04-28",
        "end": "2024-07-28",
        "fy": 2024,
        "fp": "Q2",
        "form": "10-Q",
        "accn": "0000000001-24-000003",
        "filed": "2024-09-01",
    },
    # Q3 FY2024 (9-month cumulative)
    {
        "val": 105_000_000_000,
        "start": "2024-01-29",
        "end": "2024-10-27",
        "fy": 2024,
        "fp": "Q3",
        "form": "10-Q",
        "accn": "0000000001-24-000004",
        "filed": "2024-12-01",
    },
    # Q3 FY2024 (3-month standalone)
    {
        "val": 40_000_000_000,
        "start": "2024-07-28",
        "end": "2024-10-27",
        "fy": 2024,
        "fp": "Q3",
        "form": "10-Q",
        "accn": "0000000001-24-000004",
        "filed": "2024-12-01",
    },
]

# Balance sheet values (instant, no cumulative/standalone ambiguity)
ASSETS_VALUES = [
    {
        "val": 500_000_000_000,
        "end": "2023-01-29",
        "fy": 2022,
        "fp": "FY",
        "form": "10-K",
        "accn": "0000000001-23-000001",
        "filed": "2023-03-01",
    },
    {
        "val": 550_000_000_000,
        "end": "2023-04-30",
        "fy": 2023,
        "fp": "Q1",
        "form": "10-Q",
        "accn": "0000000001-23-000002",
        "filed": "2023-06-01",
    },
    {
        "val": 600_000_000_000,
        "end": "2024-01-28",
        "fy": 2023,
        "fp": "FY",
        "form": "10-K",
        "accn": "0000000001-24-000001",
        "filed": "2024-03-01",
    },
    {
        "val": 650_000_000_000,
        "end": "2024-10-27",
        "fy": 2024,
        "fp": "Q3",
        "form": "10-Q",
        "accn": "0000000001-24-000004",
        "filed": "2024-12-01",
    },
]


class TestSelectLfy(unittest.TestCase):
    def test_lfy_duration(self) -> None:
        facts = _make_facts("Revenues", REVENUE_VALUES)
        result = select_lfy(facts, "Revenues", "revenue", DURATION_META, COMPANY, CIK)
        self.assertIsNotNone(result)
        self.assertEqual(result.value, 100_000_000_000)
        self.assertEqual(result.fiscal_year, 2023)
        self.assertEqual(result.fiscal_period, "FY")

    def test_lfy_instant(self) -> None:
        facts = _make_facts("Assets", ASSETS_VALUES)
        result = select_lfy(facts, "Assets", "total_assets", INSTANT_META, COMPANY, CIK)
        self.assertIsNotNone(result)
        self.assertEqual(result.value, 600_000_000_000)
        self.assertEqual(result.fiscal_year, 2023)

    def test_lfy_no_data(self) -> None:
        facts = _make_facts("Revenues", [])
        result = select_lfy(facts, "Revenues", "revenue", DURATION_META, COMPANY, CIK)
        self.assertIsNone(result)


class TestSelectMrq(unittest.TestCase):
    def test_mrq_picks_standalone_not_cumulative(self) -> None:
        """MRQ should return the standalone ~90-day value, not the cumulative YTD."""
        facts = _make_facts("Revenues", REVENUE_VALUES)
        result = select_mrq(facts, "Revenues", "revenue", DURATION_META, COMPANY, CIK)
        self.assertIsNotNone(result)
        self.assertEqual(result.fiscal_year, 2024)
        self.assertEqual(result.fiscal_period, "Q3")
        # Must be the standalone $40B, NOT the cumulative $105B
        self.assertEqual(result.value, 40_000_000_000)

    def test_mrq_q1_works(self) -> None:
        """Q1 standalone = Q1 cumulative, so MRQ should still return it."""
        q1_only = [v for v in REVENUE_VALUES if v["fp"] in ("FY", "Q1")]
        facts = _make_facts("Revenues", q1_only)
        result = select_mrq(facts, "Revenues", "revenue", DURATION_META, COMPANY, CIK)
        self.assertIsNotNone(result)
        self.assertEqual(result.fiscal_period, "Q1")
        self.assertEqual(result.value, 30_000_000_000)

    def test_mrq_instant(self) -> None:
        facts = _make_facts("Assets", ASSETS_VALUES)
        result = select_mrq(facts, "Assets", "total_assets", INSTANT_META, COMPANY, CIK)
        self.assertIsNotNone(result)
        self.assertEqual(result.value, 650_000_000_000)

    def test_mrq_no_standalone_returns_none(self) -> None:
        """If only cumulative entries exist (no standalone), MRQ returns None for duration."""
        cumulative_only = [
            v for v in REVENUE_VALUES if v["fp"] == "FY" or v.get("start") == "2024-01-29"
        ]
        # Keep only the 9-month cumulative Q3
        cumulative_only = [
            v
            for v in cumulative_only
            if not (v["fp"] == "Q3" and v.get("start") == "2024-07-28")
            and not (v["fp"] == "Q2" and v.get("start") == "2024-04-28")
        ]
        # Remove Q1 too so only cumulative Q2/Q3 remain as quarterly
        cumulative_only = [v for v in cumulative_only if v["fp"] not in ("Q1",)]
        facts = _make_facts("Revenues", cumulative_only)
        result = select_mrq(facts, "Revenues", "revenue", DURATION_META, COMPANY, CIK)
        # With only cumulative entries (>100 days), MRQ should return None
        self.assertIsNone(result)


class TestSelectMrp(unittest.TestCase):
    def test_mrp_returns_most_recent_filed(self) -> None:
        facts = _make_facts("Revenues", REVENUE_VALUES)
        result = select_mrp(facts, "Revenues", "revenue", DURATION_META, COMPANY, CIK)
        self.assertIsNotNone(result)
        self.assertEqual(result.fiscal_year, 2024)


class TestSelectLtm(unittest.TestCase):
    def test_ltm_uses_cumulative_values(self) -> None:
        """LTM = MRP_cumulative + LFY - MRP_prior_cumulative.

        MRP (Q3 FY2024 9-month cumulative): $105B
        LFY (FY2023 annual): $100B
        MRP_prior (Q3 FY2023 9-month cumulative): $75B
        LTM = 105 + 100 - 75 = $130B

        If we accidentally picked standalone values:
        MRP_standalone (Q3 FY2024 3-month): $40B
        MRP_prior_standalone (Q3 FY2023 3-month): $28B
        Wrong LTM = 40 + 100 - 28 = $112B (incorrect)
        """
        facts = _make_facts("Revenues", REVENUE_VALUES)
        result = select_ltm(facts, "Revenues", "revenue", DURATION_META, COMPANY, CIK)
        self.assertIsNotNone(result)
        self.assertIsInstance(result, DerivedValue)
        self.assertAlmostEqual(result.value, 130_000_000_000)
        self.assertEqual(result.fiscal_period, "LTM")
        # Verify components are present and use cumulative values
        self.assertIn("mrp", result.components)
        self.assertIn("lfy", result.components)
        self.assertIn("mrp_prior", result.components)
        # MRP should be the cumulative $105B, not standalone $40B
        self.assertEqual(result.components["mrp"].value, 105_000_000_000)
        # MRP_prior should be the cumulative $75B, not standalone $28B
        self.assertEqual(result.components["mrp_prior"].value, 75_000_000_000)

    def test_ltm_instant_returns_latest(self) -> None:
        """Balance sheet items should just return the most recent value."""
        facts = _make_facts("Assets", ASSETS_VALUES)
        result = select_ltm(facts, "Assets", "total_assets", INSTANT_META, COMPANY, CIK)
        self.assertIsNotNone(result)
        self.assertEqual(result.value, 650_000_000_000)

    def test_ltm_annual_only(self) -> None:
        """Company with only annual data should fall back to LFY."""
        annual_only = [v for v in REVENUE_VALUES if v["fp"] == "FY"]
        facts = _make_facts("Revenues", annual_only)
        result = select_ltm(facts, "Revenues", "revenue", DURATION_META, COMPANY, CIK)
        self.assertIsNotNone(result)
        self.assertEqual(result.value, 100_000_000_000)

    def test_ltm_non_calendar_fiscal_year_uses_prior_year_same_quarter(self) -> None:
        """LTM should match the prior fiscal year's same quarter for non-calendar filers."""
        values = [
            # FY2024 annual (fiscal year ends in June)
            {
                "val": 100_000_000_000,
                "start": "2023-07-01",
                "end": "2024-06-30",
                "fy": 2024,
                "fp": "FY",
                "form": "10-K",
                "accn": "0000000001-24-000001",
                "filed": "2024-08-15",
            },
            # Q3 FY2024 cumulative (prior-year comparable, 9 months)
            {
                "val": 70_000_000_000,
                "start": "2023-07-01",
                "end": "2024-03-31",
                "fy": 2024,
                "fp": "Q3",
                "form": "10-Q",
                "accn": "0000000001-24-000003",
                "filed": "2024-05-15",
            },
            # Q3 FY2024 standalone (3 months, should not be used for LTM)
            {
                "val": 25_000_000_000,
                "start": "2024-01-01",
                "end": "2024-03-31",
                "fy": 2024,
                "fp": "Q3",
                "form": "10-Q",
                "accn": "0000000001-24-000003",
                "filed": "2024-05-15",
            },
            # Q3 FY2025 cumulative (MRP, 9 months)
            {
                "val": 90_000_000_000,
                "start": "2024-07-01",
                "end": "2025-03-31",
                "fy": 2025,
                "fp": "Q3",
                "form": "10-Q",
                "accn": "0000000001-25-000003",
                "filed": "2025-05-15",
            },
            # Q3 FY2025 standalone (3 months, should not be used for LTM)
            {
                "val": 35_000_000_000,
                "start": "2025-01-01",
                "end": "2025-03-31",
                "fy": 2025,
                "fp": "Q3",
                "form": "10-Q",
                "accn": "0000000001-25-000003",
                "filed": "2025-05-15",
            },
        ]
        facts = _make_facts("Revenues", values)
        result = select_ltm(facts, "Revenues", "revenue", DURATION_META, COMPANY, CIK)
        self.assertIsNotNone(result)
        self.assertIsInstance(result, DerivedValue)
        # LTM = 90 + 100 - 70 = 120
        self.assertEqual(result.value, 120_000_000_000)
        self.assertEqual(result.components["mrp_prior"].fiscal_year, 2024)
        self.assertEqual(result.components["mrp_prior"].fiscal_period, "Q3")

    def test_ltm_missing_prior_year_quarter_returns_mrp(self) -> None:
        """Missing prior-year comparable should return MRP rather than crashing."""
        values = [
            {
                "val": 100_000_000_000,
                "start": "2023-07-01",
                "end": "2024-06-30",
                "fy": 2024,
                "fp": "FY",
                "form": "10-K",
                "accn": "0000000001-24-000001",
                "filed": "2024-08-15",
            },
            {
                "val": 90_000_000_000,
                "start": "2024-07-01",
                "end": "2025-03-31",
                "fy": 2025,
                "fp": "Q3",
                "form": "10-Q",
                "accn": "0000000001-25-000003",
                "filed": "2025-05-15",
            },
        ]
        facts = _make_facts("Revenues", values)
        result = select_ltm(facts, "Revenues", "revenue", DURATION_META, COMPANY, CIK)
        self.assertIsNotNone(result)
        self.assertNotIsInstance(result, DerivedValue)
        self.assertEqual(result.value, 90_000_000_000)

    def test_ltm_minus_1_shifts_anchor_back_one_year(self) -> None:
        """LTM-1 should compute prior-year equivalent trailing window."""
        values = [
            # FY2022 annual
            {
                "val": 80_000_000_000,
                "start": "2022-01-31",
                "end": "2023-01-29",
                "fy": 2022,
                "fp": "FY",
                "form": "10-K",
                "accn": "0000000001-23-000001",
                "filed": "2023-03-01",
            },
            # Q3 FY2022 cumulative (prior for LTM-1)
            {
                "val": 60_000_000_000,
                "start": "2022-01-31",
                "end": "2022-10-30",
                "fy": 2022,
                "fp": "Q3",
                "form": "10-Q",
                "accn": "0000000001-22-000004",
                "filed": "2022-12-01",
            },
            # FY2023 annual
            {
                "val": 100_000_000_000,
                "start": "2023-01-30",
                "end": "2024-01-28",
                "fy": 2023,
                "fp": "FY",
                "form": "10-K",
                "accn": "0000000001-24-000001",
                "filed": "2024-03-01",
            },
            # Q3 FY2023 cumulative (anchor for LTM-1)
            {
                "val": 75_000_000_000,
                "start": "2023-01-30",
                "end": "2023-10-29",
                "fy": 2023,
                "fp": "Q3",
                "form": "10-Q",
                "accn": "0000000001-23-000004",
                "filed": "2023-12-01",
            },
            # Q3 FY2024 cumulative (latest quarter anchor for LTM)
            {
                "val": 105_000_000_000,
                "start": "2024-01-29",
                "end": "2024-10-27",
                "fy": 2024,
                "fp": "Q3",
                "form": "10-Q",
                "accn": "0000000001-24-000004",
                "filed": "2024-12-01",
            },
        ]
        facts = _make_facts("Revenues", values)
        result = select_period(facts, "Revenues", "revenue", DURATION_META, COMPANY, CIK, "ltm-1")
        self.assertIsNotNone(result)
        self.assertIsInstance(result, DerivedValue)
        # LTM-1 = 75 + 80 - 60 = 95
        self.assertEqual(result.value, 95_000_000_000)
        self.assertEqual(result.fiscal_period, "LTM-1")
        self.assertEqual(result.components["mrp"].value, 75_000_000_000)
        self.assertEqual(result.components["lfy"].value, 80_000_000_000)
        self.assertEqual(result.components["mrp_prior"].value, 60_000_000_000)

    def test_ltm_minus_1_missing_prior_returns_anchor_quarter(self) -> None:
        """If LTM-1 prior-year comparable is missing, return anchored quarter value."""
        values = [
            {
                "val": 80_000_000_000,
                "start": "2022-01-31",
                "end": "2023-01-29",
                "fy": 2022,
                "fp": "FY",
                "form": "10-K",
                "accn": "0000000001-23-000001",
                "filed": "2023-03-01",
            },
            {
                "val": 100_000_000_000,
                "start": "2023-01-30",
                "end": "2024-01-28",
                "fy": 2023,
                "fp": "FY",
                "form": "10-K",
                "accn": "0000000001-24-000001",
                "filed": "2024-03-01",
            },
            {
                "val": 75_000_000_000,
                "start": "2023-01-30",
                "end": "2023-10-29",
                "fy": 2023,
                "fp": "Q3",
                "form": "10-Q",
                "accn": "0000000001-23-000004",
                "filed": "2023-12-01",
            },
            {
                "val": 105_000_000_000,
                "start": "2024-01-29",
                "end": "2024-10-27",
                "fy": 2024,
                "fp": "Q3",
                "form": "10-Q",
                "accn": "0000000001-24-000004",
                "filed": "2024-12-01",
            },
        ]
        facts = _make_facts("Revenues", values)
        result = select_period(facts, "Revenues", "revenue", DURATION_META, COMPANY, CIK, "ltm-1")
        self.assertIsNotNone(result)
        self.assertNotIsInstance(result, DerivedValue)
        self.assertEqual(result.value, 75_000_000_000)


class TestAnnualSeries(unittest.TestCase):
    def test_returns_n_years(self) -> None:
        facts = _make_facts("Revenues", REVENUE_VALUES)
        results = select_annual_series(
            facts, "Revenues", "revenue", DURATION_META, COMPANY, CIK, n=2
        )
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].fiscal_year, 2023)
        self.assertEqual(results[1].fiscal_year, 2022)

    def test_deduplicates_fiscal_years(self) -> None:
        facts = _make_facts("Revenues", REVENUE_VALUES)
        results = select_annual_series(
            facts, "Revenues", "revenue", DURATION_META, COMPANY, CIK, n=10
        )
        fys = [r.fiscal_year for r in results]
        self.assertEqual(len(fys), len(set(fys)))


class TestQuarterlySeries(unittest.TestCase):
    def test_returns_standalone_values(self) -> None:
        """Quarterly series should return standalone 3-month values, not cumulative."""
        facts = _make_facts("Revenues", REVENUE_VALUES)
        results = select_quarterly_series(
            facts, "Revenues", "revenue", DURATION_META, COMPANY, CIK, n=4
        )
        self.assertGreater(len(results), 0)
        # Most recent should be Q3 FY2024 standalone ($40B), not cumulative ($105B)
        self.assertEqual(results[0].fiscal_year, 2024)
        self.assertEqual(results[0].fiscal_period, "Q3")
        self.assertEqual(results[0].value, 40_000_000_000)

    def test_series_ordered_most_recent_first(self) -> None:
        facts = _make_facts("Revenues", REVENUE_VALUES)
        results = select_quarterly_series(
            facts, "Revenues", "revenue", DURATION_META, COMPANY, CIK, n=6
        )
        # Verify descending order by (fy, quarter)
        for i in range(len(results) - 1):
            a = (results[i].fiscal_year, results[i].fiscal_period)
            b = (results[i + 1].fiscal_year, results[i + 1].fiscal_period)
            self.assertGreaterEqual(a, b)

    def test_deduplicates_quarters(self) -> None:
        """Each (fy, fp) pair should appear at most once."""
        facts = _make_facts("Revenues", REVENUE_VALUES)
        results = select_quarterly_series(
            facts, "Revenues", "revenue", DURATION_META, COMPANY, CIK, n=10
        )
        keys = [(r.fiscal_year, r.fiscal_period) for r in results]
        self.assertEqual(len(keys), len(set(keys)))

    def test_instant_quarterly_series(self) -> None:
        """Instant metrics don't need duration filtering."""
        facts = _make_facts("Assets", ASSETS_VALUES)
        results = select_quarterly_series(
            facts, "Assets", "total_assets", INSTANT_META, COMPANY, CIK, n=4
        )
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0].value, 650_000_000_000)


class TestNullSafety(unittest.TestCase):
    def test_fy_null_in_annual(self) -> None:
        """SEC data with "fy": null should not crash."""
        values = [
            {
                "val": 50_000_000_000,
                "start": "2023-01-01",
                "end": "2024-01-01",
                "fy": None,
                "fp": "FY",
                "form": "10-K",
                "accn": "0000000001-24-000001",
                "filed": "2024-03-01",
            },
            {
                "val": 100_000_000_000,
                "start": "2024-01-01",
                "end": "2025-01-01",
                "fy": 2025,
                "fp": "FY",
                "form": "10-K",
                "accn": "0000000001-25-000001",
                "filed": "2025-03-01",
            },
        ]
        facts = _make_facts("Revenues", values)
        result = select_lfy(facts, "Revenues", "revenue", DURATION_META, COMPANY, CIK)
        self.assertIsNotNone(result)
        self.assertEqual(result.value, 100_000_000_000)

    def test_val_null_skipped(self) -> None:
        """Entries with val=None should be filtered out."""
        values = [
            {
                "val": None,
                "start": "2024-01-01",
                "end": "2025-01-01",
                "fy": 2025,
                "fp": "FY",
                "form": "10-K",
                "accn": "0000000001-25-000001",
                "filed": "2025-03-01",
            },
        ]
        facts = _make_facts("Revenues", values)
        result = select_lfy(facts, "Revenues", "revenue", DURATION_META, COMPANY, CIK)
        self.assertIsNone(result)


class TestAnnualFormDetection(unittest.TestCase):
    def test_20f_recognized_as_annual(self) -> None:
        """20-F filings (foreign private issuers) should be treated as annual."""
        values = [
            {
                "val": 28_262_000_000,
                "start": "2024-01-01",
                "end": "2024-12-31",
                "fy": 2024,
                "fp": "FY",
                "form": "20-F",
                "accn": "0000000001-25-000001",
                "filed": "2025-02-15",
            },
        ]
        facts = _make_facts("Revenues", values)
        result = select_lfy(facts, "Revenues", "revenue", DURATION_META, COMPANY, CIK)
        self.assertIsNotNone(result)
        self.assertEqual(result.value, 28_262_000_000)
        self.assertEqual(result.form_type, "20-F")


if __name__ == "__main__":
    unittest.main()
