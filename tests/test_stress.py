"""Stress tests for edge cases in the query system.

These tests push the query layer's boundaries: cascading nulls, mixed taxonomies,
zero denominators, LTM with Q1, formatting thresholds, and more.
"""

from __future__ import annotations

import json
import unittest
from datetime import date
from unittest.mock import AsyncMock, patch

from edgarpack.query.comps import _format_currency, _format_value
from edgarpack.query.financials import financials
from edgarpack.query.models import CitedValue, DerivedValue

_P = "edgarpack.query.financials"

# Empty submissions mock (stress tests use custom CIKs with no real submissions)
EMPTY_SUBMISSIONS = {
    "cik": 0,
    "name": "MOCK",
    "filings": {
        "recent": {
            "accessionNumber": [],
            "primaryDocument": [],
            "form": [],
            "filingDate": [],
        }
    },
}


def _mock_empty_submissions(*args, **kwargs):
    return EMPTY_SUBMISSIONS


# ---------------------------------------------------------------------------
# Helpers: build minimal companyfacts fixtures
# ---------------------------------------------------------------------------


def _entry(
    val,
    start: str,
    end: str,
    fy: int,
    fp: str,
    form: str,
    accn: str,
    filed: str,
    unit: str = "USD",
) -> dict:
    """Build a single SEC companyfacts entry."""
    d: dict = {
        "val": val,
        "end": end,
        "fy": fy,
        "fp": fp,
        "form": form,
        "accn": accn,
        "filed": filed,
    }
    if start:
        d["start"] = start
    return d


def _facts(
    cik: int,
    name: str,
    gaap: dict | None = None,
    ifrs: dict | None = None,
) -> dict:
    """Build a minimal companyfacts response."""
    facts: dict = {}
    if gaap is not None:
        facts["us-gaap"] = gaap
    if ifrs is not None:
        facts["ifrs-full"] = ifrs
    return {"cik": cik, "entityName": name, "facts": facts}


def _concept_block(entries: list[dict], unit: str = "USD") -> dict:
    """Wrap entries into a concept's units structure."""
    return {"units": {unit: entries}}


# ---------------------------------------------------------------------------
# 1. Cascading nulls in LTM
# ---------------------------------------------------------------------------


class TestCascadingNullsLtm(unittest.IsolatedAsyncioTestCase):
    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_empty_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_ltm_all_nulls_returns_none(self, mock_resolve, mock_facts, mock_subs) -> None:
        """LTM with no quarterly data at all should return None, not crash."""
        mock_resolve.return_value = ("0009999999", "NULL CORP")
        mock_facts.return_value = _facts(9999999, "NULL CORP", gaap={})

        result = await financials("NULL", "revenue", period="ltm")
        self.assertIsNone(result.metrics["revenue"])

    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_empty_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_ltm_only_annual_falls_back(self, mock_resolve, mock_facts, mock_subs) -> None:
        """LTM with only annual data should fall back to LFY."""
        mock_resolve.return_value = ("0009999999", "ANNUAL ONLY CORP")
        mock_facts.return_value = _facts(
            9999999,
            "ANNUAL ONLY CORP",
            gaap={
                "Revenues": _concept_block(
                    [
                        _entry(
                            50_000_000_000,
                            "2024-01-01",
                            "2025-01-01",
                            2025,
                            "FY",
                            "10-K",
                            "0009999999-25-000001",
                            "2025-03-01",
                        ),
                    ]
                )
            },
        )

        result = await financials("AOC", "revenue", period="ltm")
        revenue = result.metrics["revenue"]
        self.assertIsNotNone(revenue)
        self.assertEqual(revenue.value, 50_000_000_000)
        self.assertEqual(revenue.fiscal_period, "FY")


# ---------------------------------------------------------------------------
# 2. Mixed taxonomy per-metric
# ---------------------------------------------------------------------------


class TestMixedTaxonomy(unittest.IsolatedAsyncioTestCase):
    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_empty_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_revenue_gaap_assets_ifrs(self, mock_resolve, mock_facts, mock_subs) -> None:
        """Revenue from us-gaap, total_assets from ifrs-full, same company."""
        mock_resolve.return_value = ("0008888888", "MIXED TAX CORP")
        mock_facts.return_value = _facts(
            8888888,
            "MIXED TAX CORP",
            gaap={
                "Revenues": _concept_block(
                    [
                        _entry(
                            10_000_000_000,
                            "2024-01-01",
                            "2025-01-01",
                            2025,
                            "FY",
                            "10-K",
                            "0008888888-25-000001",
                            "2025-03-01",
                        ),
                    ]
                )
            },
            ifrs={
                "Assets": _concept_block(
                    [
                        _entry(
                            80_000_000_000,
                            "",
                            "2025-01-01",
                            2025,
                            "FY",
                            "20-F",
                            "0008888888-25-000002",
                            "2025-04-01",
                        ),
                    ]
                )
            },
        )

        result = await financials("MIX", ["revenue", "total_assets"], period="lfy")
        self.assertIsNotNone(result.metrics["revenue"])
        self.assertEqual(result.metrics["revenue"].value, 10_000_000_000)
        self.assertIsNotNone(result.metrics["total_assets"])
        self.assertEqual(result.metrics["total_assets"].value, 80_000_000_000)


# ---------------------------------------------------------------------------
# 3. Empty companyfacts
# ---------------------------------------------------------------------------


class TestEmptyFacts(unittest.IsolatedAsyncioTestCase):
    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_empty_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_empty_facts_all_none(self, mock_resolve, mock_facts, mock_subs) -> None:
        """Empty facts dict should return all None, no crash."""
        mock_resolve.return_value = ("0007777777", "EMPTY CORP")
        mock_facts.return_value = {"cik": 7777777, "entityName": "EMPTY CORP", "facts": {}}

        result = await financials("EMPTY", ["revenue", "net_income", "gross_margin"], period="lfy")
        for metric_name in ["revenue", "net_income", "gross_margin"]:
            self.assertIsNone(result.metrics[metric_name])

    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_empty_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_empty_facts_lean_json_valid(self, mock_resolve, mock_facts, mock_subs) -> None:
        """Lean JSON output with all-None metrics should be valid JSON."""
        mock_resolve.return_value = ("0007777777", "EMPTY CORP")
        mock_facts.return_value = {"cik": 7777777, "entityName": "EMPTY CORP", "facts": {}}

        result = await financials("EMPTY", "revenue", period="lfy")
        d = result.to_lean_dict()
        # Should be serializable
        json_str = json.dumps(d, default=str)
        parsed = json.loads(json_str)
        self.assertIsNone(parsed["metrics"]["revenue"])


# ---------------------------------------------------------------------------
# 4. LTM with Q1 as MRP (cumulative = standalone)
# ---------------------------------------------------------------------------


class TestLtmWithQ1(unittest.IsolatedAsyncioTestCase):
    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_empty_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_ltm_q1_mrp(self, mock_resolve, mock_facts, mock_subs) -> None:
        """LTM with Q1 as MRP: Q1 cumulative = standalone, formula still works."""
        mock_resolve.return_value = ("0006666666", "Q1 CORP")
        mock_facts.return_value = _facts(
            6666666,
            "Q1 CORP",
            gaap={
                "Revenues": _concept_block(
                    [
                        # FY2025 annual
                        _entry(
                            100_000_000_000,
                            "2024-01-01",
                            "2025-01-01",
                            2025,
                            "FY",
                            "10-K",
                            "0006666666-25-000001",
                            "2025-03-01",
                        ),
                        # Q1 FY2025 prior year (90 days)
                        _entry(
                            20_000_000_000,
                            "2024-01-01",
                            "2024-04-01",
                            2025,
                            "Q1",
                            "10-Q",
                            "0006666666-24-000010",
                            "2024-05-15",
                        ),
                        # Q1 FY2026 (MRP, 90 days)
                        _entry(
                            30_000_000_000,
                            "2025-01-01",
                            "2025-04-01",
                            2026,
                            "Q1",
                            "10-Q",
                            "0006666666-25-000020",
                            "2025-05-15",
                        ),
                    ]
                )
            },
        )

        result = await financials("Q1C", "revenue", period="ltm")
        revenue = result.metrics["revenue"]
        self.assertIsNotNone(revenue)
        self.assertIsInstance(revenue, DerivedValue)
        # LTM = MRP + LFY - MRP_prior = 30B + 100B - 20B = 110B
        self.assertEqual(revenue.value, 110_000_000_000)
        self.assertEqual(revenue.fiscal_period, "LTM")


# ---------------------------------------------------------------------------
# 5. LTM short-circuit on Q4
# ---------------------------------------------------------------------------


class TestLtmQ4ShortCircuit(unittest.IsolatedAsyncioTestCase):
    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_empty_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_ltm_q4_returns_directly(self, mock_resolve, mock_facts, mock_subs) -> None:
        """When MRP is Q4/FY, LTM should return it directly without DerivedValue."""
        mock_resolve.return_value = ("0005555555", "Q4 CORP")
        mock_facts.return_value = _facts(
            5555555,
            "Q4 CORP",
            gaap={
                "Revenues": _concept_block(
                    [
                        _entry(
                            50_000_000_000,
                            "2024-01-01",
                            "2025-01-01",
                            2025,
                            "FY",
                            "10-K",
                            "0005555555-25-000001",
                            "2025-03-01",
                        ),
                        # Q4 is the most recent 10-Q
                        _entry(
                            15_000_000_000,
                            "2024-10-01",
                            "2025-01-01",
                            2025,
                            "Q4",
                            "10-Q",
                            "0005555555-25-000005",
                            "2025-02-01",
                        ),
                    ]
                )
            },
        )

        result = await financials("Q4C", "revenue", period="ltm")
        revenue = result.metrics["revenue"]
        self.assertIsNotNone(revenue)
        # Should NOT be a DerivedValue since Q4 short-circuits
        self.assertNotIsInstance(revenue, DerivedValue)
        self.assertEqual(revenue.value, 15_000_000_000)


# ---------------------------------------------------------------------------
# 6. EBITDA (derived of derived components)
# ---------------------------------------------------------------------------


class TestEbitda(unittest.IsolatedAsyncioTestCase):
    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_empty_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_ebitda_sum(self, mock_resolve, mock_facts, mock_subs) -> None:
        """EBITDA = operating_income + depreciation_amortization."""
        mock_resolve.return_value = ("0004444444", "EBITDA CORP")
        mock_facts.return_value = _facts(
            4444444,
            "EBITDA CORP",
            gaap={
                "OperatingIncomeLoss": _concept_block(
                    [
                        _entry(
                            5_000_000_000,
                            "2024-01-01",
                            "2025-01-01",
                            2025,
                            "FY",
                            "10-K",
                            "0004444444-25-000001",
                            "2025-03-01",
                        ),
                    ]
                ),
                "DepreciationDepletionAndAmortization": _concept_block(
                    [
                        _entry(
                            2_000_000_000,
                            "2024-01-01",
                            "2025-01-01",
                            2025,
                            "FY",
                            "10-K",
                            "0004444444-25-000001",
                            "2025-03-01",
                        ),
                    ]
                ),
            },
        )

        result = await financials("EBC", "ebitda", period="lfy")
        ebitda = result.metrics["ebitda"]
        self.assertIsNotNone(ebitda)
        self.assertIsInstance(ebitda, DerivedValue)
        self.assertEqual(ebitda.value, 7_000_000_000)


# ---------------------------------------------------------------------------
# 7. Division by zero in ratio
# ---------------------------------------------------------------------------


class TestDivisionByZero(unittest.IsolatedAsyncioTestCase):
    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_empty_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_gross_margin_zero_revenue(self, mock_resolve, mock_facts, mock_subs) -> None:
        """gross_margin with revenue=0 should return None, not crash."""
        mock_resolve.return_value = ("0003333333", "ZERO REV CORP")
        mock_facts.return_value = _facts(
            3333333,
            "ZERO REV CORP",
            gaap={
                "Revenues": _concept_block(
                    [
                        _entry(
                            0,
                            "2024-01-01",
                            "2025-01-01",
                            2025,
                            "FY",
                            "10-K",
                            "0003333333-25-000001",
                            "2025-03-01",
                        ),
                    ]
                ),
                "GrossProfit": _concept_block(
                    [
                        _entry(
                            0,
                            "2024-01-01",
                            "2025-01-01",
                            2025,
                            "FY",
                            "10-K",
                            "0003333333-25-000001",
                            "2025-03-01",
                        ),
                    ]
                ),
            },
        )

        result = await financials("ZRC", "gross_margin", period="lfy")
        self.assertIsNone(result.metrics["gross_margin"])


# ---------------------------------------------------------------------------
# 8. Negative value formatting
# ---------------------------------------------------------------------------


class TestNegativeFormatting(unittest.TestCase):
    def test_negative_currency(self) -> None:
        """Negative monetary values should format correctly."""
        result = _format_currency(-2_500_000_000, "USD")
        self.assertIn("-", result)
        self.assertIn("2.5B", result)

    def test_negative_margin(self) -> None:
        """Negative margin should display as negative percentage."""
        cited = CitedValue(
            value=-0.15,
            unit="pure",
            metric="net_margin",
            concept="net_margin",
            period_end=date(2025, 1, 1),
            fiscal_year=2025,
            fiscal_period="FY",
            form_type="10-K",
            filed=date(2025, 3, 1),
            accession="0003333333-25-000001",
            cik="0003333333",
            company="LOSS CORP",
        )
        formatted = _format_value(cited)
        self.assertEqual(formatted, "-15.0%")

    def test_negative_net_income(self) -> None:
        """Negative net income should format with negative sign."""
        cited = CitedValue(
            value=-500_000_000,
            unit="USD",
            metric="net_income",
            concept="NetIncomeLoss",
            period_end=date(2025, 1, 1),
            fiscal_year=2025,
            fiscal_period="FY",
            form_type="10-K",
            filed=date(2025, 3, 1),
            accession="0003333333-25-000001",
            cik="0003333333",
            company="LOSS CORP",
        )
        formatted = _format_value(cited)
        self.assertIn("-", formatted)
        self.assertIn("500M", formatted)


# ---------------------------------------------------------------------------
# 9. Lean JSON with LTM
# ---------------------------------------------------------------------------


class TestLeanJsonLtm(unittest.IsolatedAsyncioTestCase):
    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_empty_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_ltm_lean_has_components_and_formula(self, mock_resolve, mock_facts, _ms) -> None:
        """LTM lean JSON should inline components and show formula."""
        mock_resolve.return_value = ("0002222222", "LTM LEAN CORP")
        mock_facts.return_value = _facts(
            2222222,
            "LTM LEAN CORP",
            gaap={
                "Revenues": _concept_block(
                    [
                        _entry(
                            100_000_000_000,
                            "2024-01-01",
                            "2025-01-01",
                            2025,
                            "FY",
                            "10-K",
                            "0002222222-25-000001",
                            "2025-03-01",
                        ),
                        _entry(
                            20_000_000_000,
                            "2024-01-01",
                            "2024-04-01",
                            2025,
                            "Q1",
                            "10-Q",
                            "0002222222-24-000010",
                            "2024-05-15",
                        ),
                        _entry(
                            30_000_000_000,
                            "2025-01-01",
                            "2025-04-01",
                            2026,
                            "Q1",
                            "10-Q",
                            "0002222222-25-000020",
                            "2025-05-15",
                        ),
                    ]
                )
            },
        )

        result = await financials("LLC", "revenue", period="ltm")
        d = result.to_lean_dict()
        revenue = d["metrics"]["revenue"]
        self.assertEqual(revenue["formula"], "mrp + lfy - mrp_prior")
        self.assertIn("ltm_components", revenue)
        self.assertIn("mrp", revenue["ltm_components"])
        self.assertIn("lfy", revenue["ltm_components"])
        self.assertIn("mrp_prior", revenue["ltm_components"])


# ---------------------------------------------------------------------------
# 10. Comps with mixed currencies
# ---------------------------------------------------------------------------


class TestMixedCurrencyComps(unittest.IsolatedAsyncioTestCase):
    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_empty_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_usd_and_eur_side_by_side(self, mock_resolve, mock_facts, mock_subs) -> None:
        """USD and EUR companies in comps should each format with correct symbol."""
        # For this test, we test the formatting function directly
        usd_cited = CitedValue(
            value=10_000_000_000,
            unit="USD",
            metric="revenue",
            concept="Revenues",
            period_end=date(2025, 1, 1),
            fiscal_year=2025,
            fiscal_period="FY",
            form_type="10-K",
            filed=date(2025, 3, 1),
            accession="0001111111-25-000001",
            cik="0001111111",
            company="US CORP",
        )
        eur_cited = CitedValue(
            value=8_000_000_000,
            unit="EUR",
            metric="revenue",
            concept="Revenue",
            period_end=date(2025, 1, 1),
            fiscal_year=2025,
            fiscal_period="FY",
            form_type="20-F",
            filed=date(2025, 4, 1),
            accession="0002222222-25-000001",
            cik="0002222222",
            company="EU CORP",
        )
        usd_fmt = _format_value(usd_cited)
        eur_fmt = _format_value(eur_cited)
        self.assertIn("$", usd_fmt)
        self.assertIn("\u20ac", eur_fmt)
        self.assertIn("10.0B", usd_fmt)
        self.assertIn("8.0B", eur_fmt)


# ---------------------------------------------------------------------------
# 11. Annual series with year gaps
# ---------------------------------------------------------------------------


class TestAnnualSeriesGaps(unittest.IsolatedAsyncioTestCase):
    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_empty_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_annual_gap_returns_available(self, mock_resolve, mock_facts, mock_subs) -> None:
        """annual:3 with FY2020 and FY2022 (no 2021) should return 2, not 3."""
        mock_resolve.return_value = ("0001010101", "GAP CORP")
        mock_facts.return_value = _facts(
            1010101,
            "GAP CORP",
            gaap={
                "Revenues": _concept_block(
                    [
                        _entry(
                            20_000_000_000,
                            "2021-01-01",
                            "2022-01-01",
                            2022,
                            "FY",
                            "10-K",
                            "0001010101-22-000001",
                            "2022-03-01",
                        ),
                        _entry(
                            15_000_000_000,
                            "2019-01-01",
                            "2020-01-01",
                            2020,
                            "FY",
                            "10-K",
                            "0001010101-20-000001",
                            "2020-03-01",
                        ),
                    ]
                )
            },
        )

        result = await financials("GAP", "revenue", period="annual:3")
        revenue = result.metrics["revenue"]
        self.assertIsInstance(revenue, list)
        self.assertEqual(len(revenue), 2)
        self.assertEqual(revenue[0].fiscal_year, 2022)
        self.assertEqual(revenue[1].fiscal_year, 2020)


# ---------------------------------------------------------------------------
# 12. 20-F + IFRS full path
# ---------------------------------------------------------------------------


class TestIfrsFull(unittest.IsolatedAsyncioTestCase):
    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_empty_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_20f_ifrs_revenue(self, mock_resolve, mock_facts, mock_subs) -> None:
        """Non-US filer (20-F) with ifrs-full data should resolve correctly."""
        mock_resolve.return_value = ("0000123456", "FOREIGN CORP")
        mock_facts.return_value = _facts(
            123456,
            "FOREIGN CORP",
            ifrs={
                "Revenue": _concept_block(
                    [
                        _entry(
                            5_000_000_000,
                            "2024-01-01",
                            "2025-01-01",
                            2025,
                            "FY",
                            "20-F",
                            "0000123456-25-000001",
                            "2025-04-15",
                            "EUR",
                        ),
                    ],
                    unit="EUR",
                ),
            },
        )

        result = await financials("FC", "revenue", period="lfy")
        revenue = result.metrics["revenue"]
        self.assertIsNotNone(revenue)
        self.assertEqual(revenue.value, 5_000_000_000)
        self.assertEqual(revenue.unit, "EUR")
        self.assertEqual(revenue.concept, "Revenue")


# ---------------------------------------------------------------------------
# 13. Filing deduplication
# ---------------------------------------------------------------------------


class TestFilingDeduplication(unittest.IsolatedAsyncioTestCase):
    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_empty_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_five_metrics_one_filing(self, mock_resolve, mock_facts, mock_subs) -> None:
        """5 metrics from 1 accession: filings table should have exactly 1 entry."""
        accn = "0001234567-25-000001"
        mock_resolve.return_value = ("0001234567", "DEDUP CORP")
        mock_facts.return_value = _facts(
            1234567,
            "DEDUP CORP",
            gaap={
                "Revenues": _concept_block(
                    [
                        _entry(
                            10_000_000_000,
                            "2024-01-01",
                            "2025-01-01",
                            2025,
                            "FY",
                            "10-K",
                            accn,
                            "2025-03-01",
                        ),
                    ]
                ),
                "GrossProfit": _concept_block(
                    [
                        _entry(
                            6_000_000_000,
                            "2024-01-01",
                            "2025-01-01",
                            2025,
                            "FY",
                            "10-K",
                            accn,
                            "2025-03-01",
                        ),
                    ]
                ),
                "NetIncomeLoss": _concept_block(
                    [
                        _entry(
                            3_000_000_000,
                            "2024-01-01",
                            "2025-01-01",
                            2025,
                            "FY",
                            "10-K",
                            accn,
                            "2025-03-01",
                        ),
                    ]
                ),
                "OperatingIncomeLoss": _concept_block(
                    [
                        _entry(
                            4_000_000_000,
                            "2024-01-01",
                            "2025-01-01",
                            2025,
                            "FY",
                            "10-K",
                            accn,
                            "2025-03-01",
                        ),
                    ]
                ),
                "EarningsPerShareDiluted": _concept_block(
                    [
                        _entry(
                            2.50, "2024-01-01", "2025-01-01", 2025, "FY", "10-K", accn, "2025-03-01"
                        ),
                    ],
                    unit="USD/shares",
                ),
            },
        )

        result = await financials(
            "DDC",
            ["revenue", "gross_profit", "net_income", "operating_income", "eps_diluted"],
            period="lfy",
        )
        d = result.to_lean_dict()
        self.assertEqual(len(d["filings"]), 1)
        self.assertIn(accn, d["filings"])


# ---------------------------------------------------------------------------
# 14. Formatting boundaries
# ---------------------------------------------------------------------------


class TestFormattingBoundaries(unittest.TestCase):
    def test_exact_billion(self) -> None:
        self.assertEqual(_format_currency(1_000_000_000, "USD"), "$1.0B")

    def test_just_under_billion(self) -> None:
        result = _format_currency(999_999_999, "USD")
        self.assertIn("M", result)

    def test_exact_million(self) -> None:
        self.assertEqual(_format_currency(1_000_000, "USD"), "$1M")

    def test_just_under_million(self) -> None:
        result = _format_currency(999_999, "USD")
        self.assertIn("K", result)

    def test_exact_thousand(self) -> None:
        self.assertEqual(_format_currency(1_000, "USD"), "$1K")

    def test_just_under_thousand(self) -> None:
        result = _format_currency(999, "USD")
        self.assertEqual(result, "$999")

    def test_zero(self) -> None:
        self.assertEqual(_format_currency(0, "USD"), "$0")

    def test_eps_formatting(self) -> None:
        cited = CitedValue(
            value=1.19,
            unit="USD/shares",
            metric="eps_diluted",
            concept="EarningsPerShareDiluted",
            period_end=date(2025, 1, 1),
            fiscal_year=2025,
            fiscal_period="FY",
            form_type="10-K",
            filed=date(2025, 3, 1),
            accession="0001045810-25-000001",
            cik="0001045810",
            company="TEST CORP",
        )
        self.assertEqual(_format_value(cited), "$1.19")

    def test_shares_billion(self) -> None:
        cited = CitedValue(
            value=24_000_000_000,
            unit="shares",
            metric="shares_outstanding",
            concept="CommonStockSharesOutstanding",
            period_end=date(2025, 1, 1),
            fiscal_year=2025,
            fiscal_period="FY",
            form_type="10-K",
            filed=date(2025, 3, 1),
            accession="0001045810-25-000001",
            cik="0001045810",
            company="TEST CORP",
        )
        result = _format_value(cited)
        self.assertIn("24.0B", result)

    def test_na_value(self) -> None:
        cited = CitedValue(
            value=None,
            unit="USD",
            metric="revenue",
            concept="Revenues",
            period_end=date(2025, 1, 1),
            fiscal_year=2025,
            fiscal_period="FY",
            form_type="10-K",
            filed=date(2025, 3, 1),
            accession="0001045810-25-000001",
            cik="0001045810",
            company="TEST CORP",
        )
        self.assertEqual(_format_value(cited), "N/A")

    def test_unknown_three_letter_currency(self) -> None:
        """Three-letter currency codes not in the map should still format as monetary."""
        result = _format_currency(5_000_000_000, "CHF")
        self.assertIn("5.0B", result)


if __name__ == "__main__":
    unittest.main()
