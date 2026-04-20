"""Tests for period selection and LTM math."""

from __future__ import annotations

import unittest

from edgarpack.query.concepts import MetricMeta
from edgarpack.query.models import CitedValue, DerivedValue, Diagnostic
from edgarpack.query.periods import (
    _assert_ltm_invariant,
    parse_period_spec,
    select_annual_series,
    select_lfy,
    select_ltm,
    select_ltm_minus_1,
    select_ltm_n,
    select_mrp,
    select_mrq,
    select_mrq_n,
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

    def test_mrq_accepts_10q_amendment(self) -> None:
        """MRQ should treat amended quarterly forms as valid quarter sources."""
        values = [
            {
                "val": 10_000_000_000,
                "start": "2024-01-01",
                "end": "2024-03-31",
                "fy": 2024,
                "fp": "Q1",
                "form": "10-Q/A",
                "accn": "0000000001-24-000010",
                "filed": "2024-05-15",
            },
        ]
        facts = _make_facts("Revenues", values)
        result = select_mrq(facts, "Revenues", "revenue", DURATION_META, COMPANY, CIK)
        self.assertIsNotNone(result)
        self.assertEqual(result.value, 10_000_000_000)

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

    def test_ltm_per_share_uses_annual_not_additive_formula(self) -> None:
        """Per-share metrics should use annual fallback for LTM."""
        eps_meta = MetricMeta(concepts=("EarningsPerShareDiluted",), duration=True)
        values = [
            {
                "val": 4.80,
                "start": "2023-01-01",
                "end": "2023-12-31",
                "fy": 2023,
                "fp": "FY",
                "form": "10-K",
                "accn": "0000000001-24-000001",
                "filed": "2024-03-01",
            },
            {
                "val": 1.05,
                "start": "2024-01-01",
                "end": "2024-03-31",
                "fy": 2024,
                "fp": "Q1",
                "form": "10-Q",
                "accn": "0000000001-24-000002",
                "filed": "2024-05-15",
            },
            {
                "val": 2.10,
                "start": "2024-01-01",
                "end": "2024-06-30",
                "fy": 2024,
                "fp": "Q2",
                "form": "10-Q",
                "accn": "0000000001-24-000003",
                "filed": "2024-08-15",
            },
            {
                "val": 6.20,
                "start": "2024-01-01",
                "end": "2024-12-31",
                "fy": 2024,
                "fp": "FY",
                "form": "10-K",
                "accn": "0000000001-25-000001",
                "filed": "2025-03-01",
            },
        ]
        facts = _make_facts("EarningsPerShareDiluted", values)
        result = select_ltm(facts, "EarningsPerShareDiluted", "eps_diluted", eps_meta, COMPANY, CIK)
        self.assertIsNotNone(result)
        self.assertNotIsInstance(result, DerivedValue)
        self.assertEqual(result.value, 6.20)
        self.assertEqual(result.fiscal_year, 2024)

    def test_ltm_q4_from_10k_short_circuits_to_annual(self) -> None:
        """Q4 values reported in 10-K should short-circuit LTM to the annual value."""
        values = [
            {
                "val": 100_000_000_000,
                "start": "2023-01-01",
                "end": "2023-12-31",
                "fy": 2023,
                "fp": "FY",
                "form": "10-K",
                "accn": "0000000001-24-000001",
                "filed": "2024-03-01",
            },
            {
                "val": 75_000_000_000,
                "start": "2023-01-01",
                "end": "2023-09-30",
                "fy": 2023,
                "fp": "Q3",
                "form": "10-Q",
                "accn": "0000000001-23-000004",
                "filed": "2023-11-15",
            },
            {
                "val": 120_000_000_000,
                "start": "2024-01-01",
                "end": "2024-12-31",
                "fy": 2024,
                "fp": "FY",
                "form": "10-K",
                "accn": "0000000001-25-000001",
                "filed": "2025-03-01",
            },
            {
                "val": 120_000_000_000,
                "start": "2024-01-01",
                "end": "2024-12-31",
                "fy": 2024,
                "fp": "Q4",
                "form": "10-K",
                "accn": "0000000001-25-000001",
                "filed": "2025-03-01",
            },
        ]
        facts = _make_facts("Revenues", values)
        result = select_ltm(facts, "Revenues", "revenue", DURATION_META, COMPANY, CIK)
        self.assertIsNotNone(result)
        self.assertNotIsInstance(result, DerivedValue)
        self.assertEqual(result.value, 120_000_000_000)
        self.assertEqual(result.fiscal_period, "FY")

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

    def test_ltm_missing_prior_year_quarter_returns_none_plus_diagnostic(self) -> None:
        """Missing prior-year same-quarter means LTM is not computable.

        Old behavior silently returned the 9-month MRP YTD. New contract
        refuses to mislabel a 9-month value as LTM; returns None and emits
        a structured ltm_incomputable Diagnostic.
        """
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
        diagnostics: list[Diagnostic] = []
        result = select_ltm(
            facts,
            "Revenues",
            "revenue",
            DURATION_META,
            COMPANY,
            CIK,
            diagnostics=diagnostics,
        )
        self.assertIsNone(result)
        self.assertEqual(len(diagnostics), 1)
        self.assertEqual(diagnostics[0].kind, "ltm_incomputable")
        self.assertEqual(diagnostics[0].metric, "revenue")
        self.assertIn("Q3", diagnostics[0].message)
        self.assertIn("FY2024", diagnostics[0].message)

    def test_ltm_no_annual_history_returns_none_plus_diagnostic(self) -> None:
        """Filer with only quarterlies and no annual: LTM not computable."""
        values = [
            {
                "val": 75_000_000_000,
                "start": "2023-01-01",
                "end": "2023-09-30",
                "fy": 2023,
                "fp": "Q3",
                "form": "10-Q",
                "accn": "0000000001-23-000004",
                "filed": "2023-11-01",
            },
            {
                "val": 90_000_000_000,
                "start": "2024-01-01",
                "end": "2024-09-30",
                "fy": 2024,
                "fp": "Q3",
                "form": "10-Q",
                "accn": "0000000001-24-000004",
                "filed": "2024-11-01",
            },
        ]
        facts = _make_facts("Revenues", values)
        diagnostics: list[Diagnostic] = []
        result = select_ltm(
            facts,
            "Revenues",
            "revenue",
            DURATION_META,
            COMPANY,
            CIK,
            diagnostics=diagnostics,
        )
        self.assertIsNone(result)
        self.assertEqual(len(diagnostics), 1)
        self.assertEqual(diagnostics[0].kind, "ltm_incomputable")
        self.assertIn("no annual history", diagnostics[0].message)

    def test_ltm_no_lfy_returns_none_plus_diagnostic(self) -> None:
        """MRP present, Q3 prior present, but no annual at or before FY-1."""
        values = [
            {
                "val": 90_000_000_000,
                "start": "2024-01-01",
                "end": "2024-09-30",
                "fy": 2024,
                "fp": "Q3",
                "form": "10-Q",
                "accn": "0000000001-24-000004",
                "filed": "2024-11-01",
            },
            {
                "val": 75_000_000_000,
                "start": "2023-01-01",
                "end": "2023-09-30",
                "fy": 2023,
                "fp": "Q3",
                "form": "10-Q",
                "accn": "0000000001-23-000004",
                "filed": "2023-11-01",
            },
            {
                "val": 140_000_000_000,
                "start": "2025-01-01",
                "end": "2025-12-31",
                "fy": 2025,
                "fp": "FY",
                "form": "10-K",
                "accn": "0000000001-26-000001",
                "filed": "2026-03-01",
            },
        ]
        facts = _make_facts("Revenues", values)
        diagnostics: list[Diagnostic] = []
        result = select_ltm(
            facts,
            "Revenues",
            "revenue",
            DURATION_META,
            COMPANY,
            CIK,
            diagnostics=diagnostics,
        )
        self.assertIsNone(result)
        self.assertEqual(len(diagnostics), 1)
        self.assertEqual(diagnostics[0].kind, "ltm_incomputable")
        self.assertIn("no prior FY annual", diagnostics[0].message)


class TestSelectLtmMinus1(unittest.TestCase):
    def test_ltm_minus_1_basic(self) -> None:
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
        result = select_ltm_minus_1(facts, "Revenues", "revenue", DURATION_META, COMPANY, CIK)
        self.assertIsNotNone(result)
        self.assertIsInstance(result, DerivedValue)
        # LTM-1 = 75 + 80 - 60 = 95
        self.assertEqual(result.value, 95_000_000_000)
        self.assertEqual(result.fiscal_period, "LTM-1")
        self.assertEqual(result.components["mrp"].value, 75_000_000_000)
        self.assertEqual(result.components["lfy"].value, 80_000_000_000)
        self.assertEqual(result.components["mrp_prior"].value, 60_000_000_000)

    def test_ltm_minus_1_instant_returns_latest(self) -> None:
        """Balance sheet items should degrade to most recent value (same as LTM)."""
        facts = _make_facts("Assets", ASSETS_VALUES)
        result = select_ltm_minus_1(facts, "Assets", "total_assets", INSTANT_META, COMPANY, CIK)
        self.assertIsNotNone(result)
        self.assertEqual(result.value, 650_000_000_000)

    def test_ltm_minus_1_annual_only_returns_prior_year(self) -> None:
        """With only annual data, LTM-1 should return the second most recent annual (prior FY)."""
        annual_only = [v for v in REVENUE_VALUES if v["fp"] == "FY"]
        facts = _make_facts("Revenues", annual_only)
        result = select_ltm_minus_1(facts, "Revenues", "revenue", DURATION_META, COMPANY, CIK)
        self.assertIsNotNone(result)
        # FY2023=$100B is most recent, FY2022=$80B is prior -> LTM-1 returns $80B
        self.assertEqual(result.value, 80_000_000_000)
        self.assertEqual(result.fiscal_year, 2022)

    def test_ltm_minus_1_missing_prior_returns_none_plus_diagnostic(self) -> None:
        """LTM-1 anchor is Q3 FY2023; prior-year Q3 FY2022 cumulative is missing.

        Old behavior returned the anchor 9-month YTD value mislabeled as LTM-1.
        New contract returns None and emits an ltm_incomputable diagnostic.
        """
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
        diagnostics: list[Diagnostic] = []
        result = select_ltm_minus_1(
            facts,
            "Revenues",
            "revenue",
            DURATION_META,
            COMPANY,
            CIK,
            diagnostics=diagnostics,
        )
        self.assertIsNone(result)
        self.assertEqual(len(diagnostics), 1)
        self.assertEqual(diagnostics[0].kind, "ltm_incomputable")
        self.assertIn("LTM-1", diagnostics[0].message)

    def test_ltm_minus_1_q4_anchor_uses_formula_when_prior_available(self) -> None:
        """LTM-1 should not short-circuit on Q4 anchors when formula inputs exist."""
        values = [
            {
                "val": 70_000_000_000,
                "start": "2021-01-01",
                "end": "2021-12-31",
                "fy": 2021,
                "fp": "FY",
                "form": "10-K",
                "accn": "0000000001-22-000001",
                "filed": "2022-03-01",
            },
            {
                "val": 70_000_000_000,
                "start": "2021-01-01",
                "end": "2021-12-31",
                "fy": 2021,
                "fp": "Q4",
                "form": "10-K",
                "accn": "0000000001-22-000001",
                "filed": "2022-03-01",
            },
            {
                "val": 80_000_000_000,
                "start": "2022-01-01",
                "end": "2022-12-31",
                "fy": 2022,
                "fp": "FY",
                "form": "10-K",
                "accn": "0000000001-23-000001",
                "filed": "2023-03-01",
            },
            {
                "val": 80_000_000_000,
                "start": "2022-01-01",
                "end": "2022-12-31",
                "fy": 2022,
                "fp": "Q4",
                "form": "10-K",
                "accn": "0000000001-23-000001",
                "filed": "2023-03-01",
            },
            {
                "val": 100_000_000_000,
                "start": "2023-01-01",
                "end": "2023-12-31",
                "fy": 2023,
                "fp": "FY",
                "form": "10-K",
                "accn": "0000000001-24-000001",
                "filed": "2024-03-01",
            },
            {
                "val": 100_000_000_000,
                "start": "2023-01-01",
                "end": "2023-12-31",
                "fy": 2023,
                "fp": "Q4",
                "form": "10-K",
                "accn": "0000000001-24-000001",
                "filed": "2024-03-01",
            },
        ]
        facts = _make_facts("Revenues", values)
        result = select_ltm_minus_1(facts, "Revenues", "revenue", DURATION_META, COMPANY, CIK)
        self.assertIsNotNone(result)
        self.assertIsInstance(result, DerivedValue)
        # Anchor is Q4 FY2022 -> 80 + 70 - 70 = 80
        self.assertEqual(result.value, 80_000_000_000)
        self.assertEqual(result.components["mrp"].fiscal_year, 2022)
        self.assertEqual(result.components["mrp_prior"].fiscal_year, 2021)

    def test_ltm_minus_1_annual_only_skips_stub_periods(self) -> None:
        """Annual-only LTM-1 should skip known partial-year annual windows."""
        values = [
            {
                "val": 400_000_000_000,
                "start": "2023-04-01",
                "end": "2024-03-31",
                "fy": 2024,
                "fp": "FY",
                "form": "20-F",
                "accn": "0000000001-24-000001",
                "filed": "2024-06-01",
            },
            {
                "val": 120_000_000_000,
                "start": "2022-04-01",
                "end": "2022-09-30",
                "fy": 2023,
                "fp": "FY",
                "form": "20-F",
                "accn": "0000000001-23-000001",
                "filed": "2023-01-15",
            },
            {
                "val": 320_000_000_000,
                "start": "2021-04-01",
                "end": "2022-03-31",
                "fy": 2022,
                "fp": "FY",
                "form": "20-F",
                "accn": "0000000001-22-000001",
                "filed": "2022-06-01",
            },
        ]
        facts = _make_facts("Revenues", values)
        result = select_ltm_minus_1(facts, "Revenues", "revenue", DURATION_META, COMPANY, CIK)
        self.assertIsNotNone(result)
        self.assertEqual(result.value, 320_000_000_000)
        self.assertEqual(result.fiscal_year, 2022)

    def test_ltm_minus_1_per_share_uses_prior_annual(self) -> None:
        """Per-share LTM-1 should use LFY-1 annual data."""
        eps_meta = MetricMeta(concepts=("EarningsPerShareDiluted",), duration=True)
        values = [
            {
                "val": 4.20,
                "start": "2023-01-01",
                "end": "2023-12-31",
                "fy": 2023,
                "fp": "FY",
                "form": "10-K",
                "accn": "0000000001-24-000001",
                "filed": "2024-03-01",
            },
            {
                "val": 5.50,
                "start": "2024-01-01",
                "end": "2024-12-31",
                "fy": 2024,
                "fp": "FY",
                "form": "10-K",
                "accn": "0000000001-25-000001",
                "filed": "2025-03-01",
            },
        ]
        facts = _make_facts("EarningsPerShareDiluted", values)
        result = select_ltm_minus_1(
            facts, "EarningsPerShareDiluted", "eps_diluted", eps_meta, COMPANY, CIK
        )
        self.assertIsNotNone(result)
        self.assertNotIsInstance(result, DerivedValue)
        self.assertEqual(result.value, 4.20)
        self.assertEqual(result.fiscal_year, 2023)

    def test_ltm_minus_1_via_select_period(self) -> None:
        """Verify the select_period router handles ltm-1."""
        facts = _make_facts("Assets", ASSETS_VALUES)
        result = select_period(facts, "Assets", "total_assets", INSTANT_META, COMPANY, CIK, "ltm-1")
        self.assertIsNotNone(result)
        self.assertEqual(result.value, 650_000_000_000)

    def test_routing_via_select_period(self) -> None:
        """Verify select_period routes 'ltm-1' correctly."""
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
                "val": 60_000_000_000,
                "start": "2022-01-31",
                "end": "2022-10-30",
                "fy": 2022,
                "fp": "Q3",
                "form": "10-Q",
                "accn": "0000000001-22-000004",
                "filed": "2022-12-01",
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

        direct = select_ltm_minus_1(facts, "Revenues", "revenue", DURATION_META, COMPANY, CIK)
        routed = select_period(facts, "Revenues", "revenue", DURATION_META, COMPANY, CIK, "ltm-1")
        self.assertEqual(direct.value, routed.value)
        self.assertEqual(direct.fiscal_period, routed.fiscal_period)


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


class TestAnnualOnlyFilerGrowth(unittest.TestCase):
    """20-F / annual-only filers: LTM-1 should return the prior fiscal year, not the same one."""

    def test_ltm_minus_1_annual_only_returns_prior_year(self) -> None:
        """With two annual entries and no quarterly data, LTM-1 should pick FY2023 (not FY2024)."""
        values = [
            {
                "val": 70_000_000_000,
                "start": "2023-01-01",
                "end": "2023-12-31",
                "fy": 2023,
                "fp": "FY",
                "form": "20-F",
                "accn": "0000000001-24-000001",
                "filed": "2024-04-01",
            },
            {
                "val": 90_000_000_000,
                "start": "2024-01-01",
                "end": "2024-12-31",
                "fy": 2024,
                "fp": "FY",
                "form": "20-F",
                "accn": "0000000001-25-000001",
                "filed": "2025-04-01",
            },
        ]
        facts = _make_facts("Revenues", values)
        result = select_ltm_minus_1(facts, "Revenues", "revenue", DURATION_META, COMPANY, CIK)
        self.assertIsNotNone(result)
        self.assertEqual(result.value, 70_000_000_000)
        self.assertEqual(result.fiscal_year, 2023)

    def test_ltm_minus_1_annual_only_insufficient_history(self) -> None:
        """With only one annual entry, LTM-1 should return None (not enough data)."""
        values = [
            {
                "val": 90_000_000_000,
                "start": "2024-01-01",
                "end": "2024-12-31",
                "fy": 2024,
                "fp": "FY",
                "form": "20-F",
                "accn": "0000000001-25-000001",
                "filed": "2025-04-01",
            },
        ]
        facts = _make_facts("Revenues", values)
        result = select_ltm_minus_1(facts, "Revenues", "revenue", DURATION_META, COMPANY, CIK)
        self.assertIsNone(result)


class TestStockSplitWarning(unittest.TestCase):
    """Per-share LTM paths should avoid additive stock-split contamination."""

    def test_per_share_ltm_uses_annual_fallback(self) -> None:
        """EPS LTM should return annual value instead of additive derived math."""
        eps_meta = MetricMeta(concepts=("EarningsPerShareDiluted",), duration=True)
        values = [
            {
                "val": 50.0,
                "start": "2023-01-30",
                "end": "2024-01-28",
                "fy": 2023,
                "fp": "FY",
                "form": "10-K",
                "accn": "0000000001-24-000001",
                "filed": "2024-03-01",
            },
            {
                "val": 41.0,
                "start": "2023-01-30",
                "end": "2023-10-29",
                "fy": 2023,
                "fp": "Q3",
                "form": "10-Q",
                "accn": "0000000001-23-000004",
                "filed": "2023-12-01",
            },
            {
                "val": 0.5,
                "start": "2024-01-29",
                "end": "2024-10-27",
                "fy": 2024,
                "fp": "Q3",
                "form": "10-Q",
                "accn": "0000000001-24-000004",
                "filed": "2024-12-01",
            },
        ]
        facts = _make_facts("EarningsPerShareDiluted", values)
        result = select_ltm(facts, "EarningsPerShareDiluted", "eps_diluted", eps_meta, COMPANY, CIK)
        self.assertIsNotNone(result)
        self.assertNotIsInstance(result, DerivedValue)
        self.assertEqual(result.value, 50.0)
        self.assertEqual(result.fiscal_period, "FY")

    def test_non_per_share_no_warning(self) -> None:
        """Revenue should never get a split warning regardless of value jumps."""
        facts = _make_facts("Revenues", REVENUE_VALUES)
        result = select_ltm(facts, "Revenues", "revenue", DURATION_META, COMPANY, CIK)
        self.assertIsNotNone(result)
        self.assertIsInstance(result, DerivedValue)
        self.assertEqual(result.warnings, [])


class TestEdgeCaseBoundary(unittest.TestCase):
    """Additional edge cases for boundary conditions in period selection."""

    def test_ltm_single_quarter_available(self) -> None:
        """Only Q1 FY2024 exists alongside FY2023 annual; prior-year Q1 is missing.

        New contract refuses to return the Q1 YTD as LTM. Result is None with a
        structured diagnostic so the caller can render 'n/a' instead of a
        mislabeled 3-month value.
        """
        values = [
            {
                "val": 100_000_000_000,
                "start": "2023-01-01",
                "end": "2023-12-31",
                "fy": 2023,
                "fp": "FY",
                "form": "10-K",
                "accn": "0000000001-24-000001",
                "filed": "2024-03-01",
            },
            {
                "val": 28_000_000_000,
                "start": "2024-01-01",
                "end": "2024-03-31",
                "fy": 2024,
                "fp": "Q1",
                "form": "10-Q",
                "accn": "0000000001-24-000002",
                "filed": "2024-05-15",
            },
        ]
        facts = _make_facts("Revenues", values)
        diagnostics: list[Diagnostic] = []
        result = select_ltm(
            facts,
            "Revenues",
            "revenue",
            DURATION_META,
            COMPANY,
            CIK,
            diagnostics=diagnostics,
        )
        self.assertIsNone(result)
        self.assertEqual(len(diagnostics), 1)
        self.assertEqual(diagnostics[0].kind, "ltm_incomputable")

    def test_ltm_minus_1_only_two_years_data(self) -> None:
        """Exactly 2 annual values; LTM-1 should pick the older one for annual-only filer."""
        values = [
            {
                "val": 50_000_000_000,
                "start": "2022-01-01",
                "end": "2022-12-31",
                "fy": 2022,
                "fp": "FY",
                "form": "20-F",
                "accn": "0000000001-23-000001",
                "filed": "2023-04-01",
            },
            {
                "val": 65_000_000_000,
                "start": "2023-01-01",
                "end": "2023-12-31",
                "fy": 2023,
                "fp": "FY",
                "form": "20-F",
                "accn": "0000000001-24-000001",
                "filed": "2024-04-01",
            },
        ]
        facts = _make_facts("Revenues", values)
        result = select_ltm_minus_1(facts, "Revenues", "revenue", DURATION_META, COMPANY, CIK)
        self.assertIsNotNone(result)
        self.assertEqual(result.value, 50_000_000_000)
        self.assertEqual(result.fiscal_year, 2022)

    def test_fiscal_year_boundary_crossing(self) -> None:
        """Company with Jan FY end; verify LTM works across calendar-year boundary."""
        values = [
            {
                "val": 100_000_000_000,
                "start": "2023-02-01",
                "end": "2024-01-31",
                "fy": 2024,
                "fp": "FY",
                "form": "10-K",
                "accn": "0000000001-24-000001",
                "filed": "2024-04-01",
            },
            {
                "val": 78_000_000_000,
                "start": "2023-02-01",
                "end": "2023-10-31",
                "fy": 2024,
                "fp": "Q3",
                "form": "10-Q",
                "accn": "0000000001-23-000004",
                "filed": "2023-12-15",
            },
            {
                "val": 88_000_000_000,
                "start": "2024-02-01",
                "end": "2024-10-31",
                "fy": 2025,
                "fp": "Q3",
                "form": "10-Q",
                "accn": "0000000001-24-000004",
                "filed": "2024-12-15",
            },
        ]
        facts = _make_facts("Revenues", values)
        result = select_ltm(facts, "Revenues", "revenue", DURATION_META, COMPANY, CIK)
        self.assertIsNotNone(result)
        self.assertIsInstance(result, DerivedValue)
        # LTM = 88 + 100 - 78 = 110
        self.assertEqual(result.value, 110_000_000_000)

    def test_instant_metric_ltm_minus_1(self) -> None:
        """Balance sheet metric should return latest value regardless of years_back."""
        facts = _make_facts("Assets", ASSETS_VALUES)
        result = select_ltm_minus_1(facts, "Assets", "total_assets", INSTANT_META, COMPANY, CIK)
        self.assertIsNotNone(result)
        # Instant metrics always return the most recent value
        self.assertEqual(result.value, 650_000_000_000)


class TestSegmentFiltering(unittest.TestCase):
    """Segment-level entries should be filtered when consolidated values exist."""

    def test_framed_entry_preferred_over_unframed(self) -> None:
        """When both framed (consolidated) and unframed (segment) entries exist,
        only the framed one should survive filtering."""
        values = [
            # Consolidated entry (has frame)
            {
                "val": 100_000_000_000,
                "start": "2024-01-01",
                "end": "2024-12-31",
                "fy": 2025,
                "fp": "FY",
                "form": "10-K",
                "accn": "0000000001-25-000001",
                "filed": "2025-03-01",
                "frame": "CY2024",
            },
            # Segment entry (no frame, same context)
            {
                "val": 30_000_000_000,
                "start": "2024-01-01",
                "end": "2024-12-31",
                "fy": 2025,
                "fp": "FY",
                "form": "10-K",
                "accn": "0000000001-25-000001",
                "filed": "2025-03-01",
            },
        ]
        facts = _make_facts("GrossProfit", values)
        result = select_lfy(facts, "GrossProfit", "gross_profit", DURATION_META, COMPANY, CIK)
        self.assertIsNotNone(result)
        self.assertEqual(result.value, 100_000_000_000)

    def test_no_frame_keeps_largest_value(self) -> None:
        """When no entries have frame data, the largest absolute value wins
        (consolidated totals > segment breakdowns)."""
        values = [
            # Consolidated (larger, no frame)
            {
                "val": 100_000_000_000,
                "start": "2024-01-01",
                "end": "2024-12-31",
                "fy": 2025,
                "fp": "FY",
                "form": "10-K",
                "accn": "0000000001-25-000001",
                "filed": "2025-03-01",
            },
            # Segment (smaller, no frame, same context)
            {
                "val": 30_000_000_000,
                "start": "2024-01-01",
                "end": "2024-12-31",
                "fy": 2025,
                "fp": "FY",
                "form": "10-K",
                "accn": "0000000001-25-000001",
                "filed": "2025-03-01",
            },
        ]
        facts = _make_facts("GrossProfit", values)
        result = select_lfy(facts, "GrossProfit", "gross_profit", DURATION_META, COMPANY, CIK)
        self.assertIsNotNone(result)
        self.assertEqual(result.value, 100_000_000_000)

    def test_different_start_dates_not_collapsed(self) -> None:
        """Cumulative and standalone entries (different start dates) should both survive."""
        values = [
            # 6-month cumulative Q2
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
            # 3-month standalone Q2
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
        ]
        facts = _make_facts("Revenues", values)
        # MRQ picks standalone; LTM picks cumulative -- both need to be available
        from edgarpack.query.periods import _extract_values

        extracted = _extract_values(facts, "Revenues")
        self.assertEqual(len(extracted), 2)

    def test_single_entry_passes_through(self) -> None:
        """A lone entry without frame should not be filtered out."""
        values = [
            {
                "val": 50_000_000_000,
                "start": "2024-01-01",
                "end": "2024-12-31",
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
        self.assertEqual(result.value, 50_000_000_000)

    def test_multiple_segments_collapsed_to_largest(self) -> None:
        """Three segment entries without frame: keep only the largest (consolidated)."""
        values = [
            {
                "val": 100_000_000_000,
                "start": "2024-01-01",
                "end": "2024-12-31",
                "fy": 2025,
                "fp": "FY",
                "form": "10-K",
                "accn": "0000000001-25-000001",
                "filed": "2025-03-01",
            },
            {
                "val": 40_000_000_000,
                "start": "2024-01-01",
                "end": "2024-12-31",
                "fy": 2025,
                "fp": "FY",
                "form": "10-K",
                "accn": "0000000001-25-000001",
                "filed": "2025-03-01",
            },
            {
                "val": 60_000_000_000,
                "start": "2024-01-01",
                "end": "2024-12-31",
                "fy": 2025,
                "fp": "FY",
                "form": "10-K",
                "accn": "0000000001-25-000001",
                "filed": "2025-03-01",
            },
        ]
        from edgarpack.query.periods import _extract_values

        facts = _make_facts("GrossProfit", values)
        extracted = _extract_values(facts, "GrossProfit")
        self.assertEqual(len(extracted), 1)
        self.assertEqual(extracted[0]["val"], 100_000_000_000)


class TestLtmInvariant(unittest.TestCase):
    """Direct unit tests for the _assert_ltm_invariant citation-contract check."""

    def _cv(
        self,
        *,
        value: float = 100.0,
        fiscal_period: str = "LTM",
        fiscal_year: int = 2024,
    ) -> CitedValue:
        from datetime import date

        return CitedValue(
            value=value,
            unit="USD",
            metric="revenue",
            concept="Revenues",
            period_start=date(2023, 1, 1),
            period_end=date(2024, 9, 30),
            fiscal_year=fiscal_year,
            fiscal_period=fiscal_period,
            form_type="10-Q",
            filed=date(2024, 11, 1),
            accession="0000000001-24-000004",
            cik=CIK,
            company=COMPANY,
        )

    def test_none_result_passes(self) -> None:
        _assert_ltm_invariant(None, "LTM")

    def test_q4_plain_cited_value_passes(self) -> None:
        _assert_ltm_invariant(self._cv(fiscal_period="FY"), "LTM")
        _assert_ltm_invariant(self._cv(fiscal_period="Q4"), "LTM")

    def test_plain_q3_cited_value_raises(self) -> None:
        """A plain CitedValue with fiscal_period=Q3 is exactly the silent-fallback
        bug we're closing: a 9-month YTD masquerading as LTM."""
        with self.assertRaises(RuntimeError) as ctx:
            _assert_ltm_invariant(self._cv(fiscal_period="Q3"), "LTM")
        self.assertIn("plain CitedValue", str(ctx.exception))

    def test_derived_missing_mrp_prior_raises(self) -> None:
        mrp = self._cv(fiscal_period="Q3")
        lfy = self._cv(fiscal_period="FY", fiscal_year=2023)
        broken = DerivedValue(
            value=100.0,
            unit="USD",
            metric="revenue",
            concept="Revenues",
            period_start=mrp.period_start,
            period_end=mrp.period_end,
            fiscal_year=mrp.fiscal_year,
            fiscal_period="LTM",
            form_type=mrp.form_type,
            filed=mrp.filed,
            accession=mrp.accession,
            cik=CIK,
            company=COMPANY,
            derived=True,
            components={"mrp": mrp, "lfy": lfy},
        )
        with self.assertRaises(RuntimeError) as ctx:
            _assert_ltm_invariant(broken, "LTM")
        self.assertIn("missing roles", str(ctx.exception))

    def test_derived_with_wrong_fiscal_period_raises(self) -> None:
        mrp = self._cv(fiscal_period="Q3")
        lfy = self._cv(fiscal_period="FY", fiscal_year=2023)
        prior = self._cv(fiscal_period="Q3", fiscal_year=2023)
        wrong = DerivedValue(
            value=100.0,
            unit="USD",
            metric="revenue",
            concept="Revenues",
            period_start=mrp.period_start,
            period_end=mrp.period_end,
            fiscal_year=mrp.fiscal_year,
            fiscal_period="Q3",
            form_type=mrp.form_type,
            filed=mrp.filed,
            accession=mrp.accession,
            cik=CIK,
            company=COMPANY,
            derived=True,
            components={"mrp": mrp, "lfy": lfy, "mrp_prior": prior},
        )
        with self.assertRaises(RuntimeError) as ctx:
            _assert_ltm_invariant(wrong, "LTM")
        self.assertIn("expected LTM*", str(ctx.exception))

    def test_derived_with_all_three_roles_passes(self) -> None:
        mrp = self._cv(fiscal_period="Q3")
        lfy = self._cv(fiscal_period="FY", fiscal_year=2023)
        prior = self._cv(fiscal_period="Q3", fiscal_year=2023)
        good = DerivedValue(
            value=130.0,
            unit="USD",
            metric="revenue",
            concept="Revenues",
            period_start=mrp.period_start,
            period_end=mrp.period_end,
            fiscal_year=mrp.fiscal_year,
            fiscal_period="LTM",
            form_type=mrp.form_type,
            filed=mrp.filed,
            accession=mrp.accession,
            cik=CIK,
            company=COMPANY,
            derived=True,
            components={"mrp": mrp, "lfy": lfy, "mrp_prior": prior},
        )
        _assert_ltm_invariant(good, "LTM")
        _assert_ltm_invariant(good, "LTM-1")


class TestSelectLtmN(unittest.TestCase):
    """Generalized ltm-N selector (N >= 2)."""

    def _build_values(self, years: int) -> list[dict]:
        """Emit FY + Q3 cumulative entries for the newest `years` fiscal years."""
        values: list[dict] = []
        base_fy = 2024
        for i in range(years):
            fy = base_fy - i
            accn = f"0000000001-{str(fy + 1)[-2:]}-000001"
            start = f"{fy}-01-01"
            end = f"{fy}-12-31"
            values.append(
                {
                    "val": (10 + i) * 10_000_000_000,
                    "start": start,
                    "end": end,
                    "fy": fy,
                    "fp": "FY",
                    "form": "10-K",
                    "accn": accn,
                    "filed": f"{fy + 1}-03-01",
                }
            )
            # Q3 cumulative for each year
            values.append(
                {
                    "val": (7 + i) * 10_000_000_000,
                    "start": start,
                    "end": f"{fy}-09-30",
                    "fy": fy,
                    "fp": "Q3",
                    "form": "10-Q",
                    "accn": f"0000000001-{str(fy)[-2:]}-000004",
                    "filed": f"{fy}-11-15",
                }
            )
        return values

    def test_ltm_2_resolves_to_window_two_years_back(self) -> None:
        facts = _make_facts("Revenues", self._build_values(4))
        result = select_ltm_n(
            facts, "Revenues", "revenue", DURATION_META, COMPANY, CIK, years_back=2
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.fiscal_period, "LTM-2")

    def test_ltm_3_resolves(self) -> None:
        facts = _make_facts("Revenues", self._build_values(5))
        result = select_ltm_n(
            facts, "Revenues", "revenue", DURATION_META, COMPANY, CIK, years_back=3
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.fiscal_period, "LTM-3")

    def test_ltm_0_equals_ltm(self) -> None:
        facts = _make_facts("Revenues", self._build_values(3))
        baseline = select_ltm(facts, "Revenues", "revenue", DURATION_META, COMPANY, CIK)
        zeroed = select_ltm_n(
            facts, "Revenues", "revenue", DURATION_META, COMPANY, CIK, years_back=0
        )
        self.assertIsNotNone(baseline)
        self.assertIsNotNone(zeroed)
        self.assertEqual(baseline.value, zeroed.value)
        self.assertEqual(baseline.fiscal_period, zeroed.fiscal_period)


class TestSelectMrqN(unittest.TestCase):
    """Generalized mrq-N selector (same fiscal quarter, N years back)."""

    def test_mrq_0_equals_mrq(self) -> None:
        facts = _make_facts("Revenues", REVENUE_VALUES)
        baseline = select_mrq(facts, "Revenues", "revenue", DURATION_META, COMPANY, CIK)
        zeroed = select_mrq_n(
            facts, "Revenues", "revenue", DURATION_META, COMPANY, CIK, years_back=0
        )
        self.assertIsNotNone(baseline)
        self.assertIsNotNone(zeroed)
        self.assertEqual(baseline.value, zeroed.value)

    def test_mrq_1_picks_same_fp_prior_year(self) -> None:
        facts = _make_facts("Revenues", REVENUE_VALUES)
        result = select_mrq_n(
            facts, "Revenues", "revenue", DURATION_META, COMPANY, CIK, years_back=1
        )
        self.assertIsNotNone(result)
        # Newest quarter is Q3 FY2024 standalone ($40B); mrq-1 = Q3 FY2023 standalone ($28B)
        self.assertEqual(result.fiscal_year, 2023)
        self.assertEqual(result.fiscal_period, "Q3")
        self.assertEqual(result.value, 28_000_000_000)

    def test_mrq_n_degrades_when_prior_fp_missing(self) -> None:
        """With only two years of quarterly history, mrq-5 should fall back to earliest prior fp."""
        # Strip everything except Q3 for FY2023 and FY2024.
        compact = [
            v
            for v in REVENUE_VALUES
            if v["fp"] == "Q3" and v.get("start") in ("2023-07-30", "2024-07-28")
        ]
        facts = _make_facts("Revenues", compact)
        result = select_mrq_n(
            facts, "Revenues", "revenue", DURATION_META, COMPANY, CIK, years_back=5
        )
        self.assertIsNotNone(result)
        # Degraded to earliest available Q3 (FY2023)
        self.assertEqual(result.fiscal_year, 2023)
        self.assertEqual(result.fiscal_period, "Q3")


class TestSelectPeriodRouter(unittest.TestCase):
    """Router-level regex dispatch for new selector forms."""

    def test_ltm_2_via_select_period(self) -> None:
        values = [
            {
                "val": 50_000_000_000,
                "start": "2021-01-01",
                "end": "2021-12-31",
                "fy": 2021,
                "fp": "FY",
                "form": "10-K",
                "accn": "0000000001-22-000001",
                "filed": "2022-03-01",
            },
            {
                "val": 70_000_000_000,
                "start": "2022-01-01",
                "end": "2022-12-31",
                "fy": 2022,
                "fp": "FY",
                "form": "10-K",
                "accn": "0000000001-23-000001",
                "filed": "2023-03-01",
            },
            {
                "val": 100_000_000_000,
                "start": "2023-01-01",
                "end": "2023-12-31",
                "fy": 2023,
                "fp": "FY",
                "form": "10-K",
                "accn": "0000000001-24-000001",
                "filed": "2024-03-01",
            },
            {
                "val": 120_000_000_000,
                "start": "2024-01-01",
                "end": "2024-12-31",
                "fy": 2024,
                "fp": "FY",
                "form": "10-K",
                "accn": "0000000001-25-000001",
                "filed": "2025-03-01",
            },
        ]
        facts = _make_facts("Revenues", values)
        routed = select_period(
            facts, "Revenues", "revenue", DURATION_META, COMPANY, CIK, "ltm-2"
        )
        self.assertIsNotNone(routed)

    def test_mrq_2_via_select_period(self) -> None:
        facts = _make_facts("Revenues", REVENUE_VALUES)
        routed = select_period(
            facts, "Revenues", "revenue", DURATION_META, COMPANY, CIK, "mrq-2"
        )
        direct = select_mrq_n(
            facts, "Revenues", "revenue", DURATION_META, COMPANY, CIK, years_back=2
        )
        # Both should return the same degraded result (or both None).
        if direct is None:
            self.assertIsNone(routed)
        else:
            self.assertEqual(routed.value, direct.value)


class TestParsePeriodSpec(unittest.TestCase):
    def test_single_scalar(self) -> None:
        self.assertEqual(parse_period_spec("lfy"), ["lfy"])
        self.assertEqual(parse_period_spec("ltm-2"), ["ltm-2"])
        self.assertEqual(parse_period_spec("mrq-3"), ["mrq-3"])

    def test_csv_preserves_order(self) -> None:
        self.assertEqual(
            parse_period_spec("lfy,lfy-1,lfy-2"),
            ["lfy", "lfy-1", "lfy-2"],
        )
        self.assertEqual(
            parse_period_spec("ltm,ltm-1,ltm-2"),
            ["ltm", "ltm-1", "ltm-2"],
        )
        self.assertEqual(
            parse_period_spec("mrq,mrq-1,mrq-2"),
            ["mrq", "mrq-1", "mrq-2"],
        )

    def test_zero_suffix_canonicalizes(self) -> None:
        self.assertEqual(parse_period_spec("lfy-0"), ["lfy"])
        self.assertEqual(parse_period_spec("ltm-0"), ["ltm"])
        self.assertEqual(parse_period_spec("mrq-0"), ["mrq"])

    def test_dedupe_preserves_first_occurrence(self) -> None:
        self.assertEqual(
            parse_period_spec("lfy,lfy-0,lfy-1"),
            ["lfy", "lfy-1"],
        )

    def test_case_insensitive(self) -> None:
        self.assertEqual(parse_period_spec("LFY,LFY-1"), ["lfy", "lfy-1"])

    def test_whitespace_tolerated(self) -> None:
        self.assertEqual(
            parse_period_spec(" lfy , lfy-1 , lfy-2 "),
            ["lfy", "lfy-1", "lfy-2"],
        )

    def test_rejects_series_mixed_with_scalar(self) -> None:
        with self.assertRaises(ValueError):
            parse_period_spec("annual:3,ltm")
        with self.assertRaises(ValueError):
            parse_period_spec("ltm,quarterly:4")

    def test_series_alone_allowed(self) -> None:
        self.assertEqual(parse_period_spec("annual:3"), ["annual:3"])
        self.assertEqual(parse_period_spec("quarterly:4"), ["quarterly:4"])

    def test_rejects_unknown_selector(self) -> None:
        with self.assertRaises(ValueError):
            parse_period_spec("wat")
        with self.assertRaises(ValueError):
            parse_period_spec("lfy,bogus")

    def test_rejects_empty(self) -> None:
        with self.assertRaises(ValueError):
            parse_period_spec("")
        with self.assertRaises(ValueError):
            parse_period_spec(",,")


if __name__ == "__main__":
    unittest.main()
