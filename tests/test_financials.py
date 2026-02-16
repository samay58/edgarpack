"""Tests for single-company financial queries."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from edgarpack.query.financials import financials
from edgarpack.query.models import DerivedValue

# Mock companyfacts response
MOCK_COMPANY_FACTS = {
    "cik": 1045810,
    "entityName": "NVIDIA CORP",
    "facts": {
        "us-gaap": {
            "Revenues": {
                "label": "Revenues",
                "units": {
                    "USD": [
                        {
                            "val": 60_922_000_000,
                            "start": "2024-01-29",
                            "end": "2025-01-26",
                            "fy": 2025,
                            "fp": "FY",
                            "form": "10-K",
                            "accn": "0001045810-25-000001",
                            "filed": "2025-02-18",
                        },
                        {
                            "val": 26_974_000_000,
                            "start": "2023-01-30",
                            "end": "2024-01-28",
                            "fy": 2024,
                            "fp": "FY",
                            "form": "10-K",
                            "accn": "0001045810-24-000001",
                            "filed": "2024-02-21",
                        },
                    ]
                },
            },
            "GrossProfit": {
                "label": "Gross Profit",
                "units": {
                    "USD": [
                        {
                            "val": 44_803_000_000,
                            "start": "2024-01-29",
                            "end": "2025-01-26",
                            "fy": 2025,
                            "fp": "FY",
                            "form": "10-K",
                            "accn": "0001045810-25-000001",
                            "filed": "2025-02-18",
                        },
                    ]
                },
            },
            "NetIncomeLoss": {
                "label": "Net Income",
                "units": {
                    "USD": [
                        {
                            "val": 29_760_000_000,
                            "start": "2024-01-29",
                            "end": "2025-01-26",
                            "fy": 2025,
                            "fp": "FY",
                            "form": "10-K",
                            "accn": "0001045810-25-000001",
                            "filed": "2025-02-18",
                        },
                    ]
                },
            },
            "EarningsPerShareDiluted": {
                "label": "EPS Diluted",
                "units": {
                    "USD/shares": [
                        {
                            "val": 1.19,
                            "start": "2024-01-29",
                            "end": "2025-01-26",
                            "fy": 2025,
                            "fp": "FY",
                            "form": "10-K",
                            "accn": "0001045810-25-000001",
                            "filed": "2025-02-18",
                        },
                    ]
                },
            },
        }
    },
}


class TestFinancials(unittest.IsolatedAsyncioTestCase):
    @patch("edgarpack.query.financials.fetch_company_facts")
    @patch("edgarpack.query.financials.resolve_ticker")
    async def test_single_metric(self, mock_resolve, mock_facts) -> None:
        mock_resolve.return_value = ("0001045810", "NVIDIA CORP")
        mock_facts.return_value = MOCK_COMPANY_FACTS

        result = await financials("NVDA", "revenue", period="lfy")

        self.assertEqual(result.company, "NVIDIA CORP")
        self.assertEqual(result.cik, "0001045810")
        self.assertIn("revenue", result.metrics)

        revenue = result.metrics["revenue"]
        self.assertIsNotNone(revenue)
        self.assertEqual(revenue.value, 60_922_000_000)
        self.assertEqual(revenue.fiscal_year, 2025)
        self.assertEqual(revenue.concept, "Revenues")

    @patch("edgarpack.query.financials.fetch_company_facts")
    @patch("edgarpack.query.financials.resolve_ticker")
    async def test_multiple_metrics(self, mock_resolve, mock_facts) -> None:
        mock_resolve.return_value = ("0001045810", "NVIDIA CORP")
        mock_facts.return_value = MOCK_COMPANY_FACTS

        result = await financials("NVDA", ["revenue", "net_income", "eps_diluted"])

        self.assertEqual(len(result.metrics), 3)
        self.assertIsNotNone(result.metrics["revenue"])
        self.assertIsNotNone(result.metrics["net_income"])
        self.assertIsNotNone(result.metrics["eps_diluted"])
        self.assertAlmostEqual(result.metrics["eps_diluted"].value, 1.19)

    @patch("edgarpack.query.financials.fetch_company_facts")
    @patch("edgarpack.query.financials.resolve_ticker")
    async def test_derived_metric_gross_margin(self, mock_resolve, mock_facts) -> None:
        mock_resolve.return_value = ("0001045810", "NVIDIA CORP")
        mock_facts.return_value = MOCK_COMPANY_FACTS

        result = await financials("NVDA", "gross_margin", period="lfy")

        gm = result.metrics["gross_margin"]
        self.assertIsNotNone(gm)
        self.assertIsInstance(gm, DerivedValue)
        # gross_margin = gross_profit / revenue = 44803 / 60922 ~ 0.7355
        self.assertAlmostEqual(gm.value, 44_803_000_000 / 60_922_000_000, places=4)
        self.assertEqual(gm.unit, "pure")

    @patch("edgarpack.query.financials.fetch_company_facts")
    @patch("edgarpack.query.financials.resolve_ticker")
    async def test_missing_metric_returns_none(self, mock_resolve, mock_facts) -> None:
        mock_resolve.return_value = ("0001045810", "NVIDIA CORP")
        mock_facts.return_value = MOCK_COMPANY_FACTS

        result = await financials("NVDA", "inventory")

        self.assertIsNone(result.metrics["inventory"])

    @patch("edgarpack.query.financials.fetch_company_facts")
    @patch("edgarpack.query.financials.resolve_ticker")
    async def test_unknown_metric_returns_none(self, mock_resolve, mock_facts) -> None:
        mock_resolve.return_value = ("0001045810", "NVIDIA CORP")
        mock_facts.return_value = MOCK_COMPANY_FACTS

        result = await financials("NVDA", "nonexistent_metric")

        self.assertIsNone(result.metrics["nonexistent_metric"])


MOCK_CROSS_YEAR_FACTS = {
    "cik": 1234567,
    "entityName": "CROSS YEAR CORP",
    "facts": {
        "us-gaap": {
            "GrossProfit": {
                "label": "Gross Profit",
                "units": {
                    "USD": [
                        {
                            "val": 50_000_000_000,
                            "start": "2024-01-01",
                            "end": "2025-01-01",
                            "fy": 2025,
                            "fp": "FY",
                            "form": "10-K",
                            "accn": "0001234567-25-000001",
                            "filed": "2025-03-01",
                        },
                    ]
                },
            },
            # Revenue concept only has FY2018 data (stale)
            "Revenues": {
                "label": "Revenues",
                "units": {
                    "USD": [
                        {
                            "val": 10_000_000_000,
                            "start": "2017-01-01",
                            "end": "2018-01-01",
                            "fy": 2018,
                            "fp": "FY",
                            "form": "10-K",
                            "accn": "0001234567-18-000001",
                            "filed": "2018-03-01",
                        },
                    ]
                },
            },
            # Revenue concept with fresh data (FY2025)
            "RevenueFromContractWithCustomerExcludingAssessedTax": {
                "label": "Revenue",
                "units": {
                    "USD": [
                        {
                            "val": 60_000_000_000,
                            "start": "2024-01-01",
                            "end": "2025-01-01",
                            "fy": 2025,
                            "fp": "FY",
                            "form": "10-K",
                            "accn": "0001234567-25-000001",
                            "filed": "2025-03-01",
                        },
                    ]
                },
            },
        }
    },
}

MOCK_QUARTERLY_SERIES_FACTS = {
    "cik": 1045810,
    "entityName": "NVIDIA CORP",
    "facts": {
        "us-gaap": {
            "Revenues": {
                "label": "Revenues",
                "units": {
                    "USD": [
                        {
                            "val": 35_100_000_000,
                            "start": "2025-10-27",
                            "end": "2026-01-25",
                            "fy": 2026,
                            "fp": "Q4",
                            "form": "10-K",
                            "accn": "0001045810-26-000001",
                            "filed": "2026-02-18",
                        },
                        {
                            "val": 30_000_000_000,
                            "start": "2025-07-28",
                            "end": "2025-10-26",
                            "fy": 2026,
                            "fp": "Q3",
                            "form": "10-Q",
                            "accn": "0001045810-25-000003",
                            "filed": "2025-11-20",
                        },
                        {
                            "val": 26_000_000_000,
                            "start": "2025-04-28",
                            "end": "2025-07-27",
                            "fy": 2026,
                            "fp": "Q2",
                            "form": "10-Q",
                            "accn": "0001045810-25-000002",
                            "filed": "2025-08-20",
                        },
                    ]
                },
            },
        }
    },
}


class TestCrossYearValidation(unittest.IsolatedAsyncioTestCase):
    @patch("edgarpack.query.financials.fetch_company_facts")
    @patch("edgarpack.query.financials.resolve_ticker")
    async def test_derived_returns_none_when_components_differ_year(
        self, mock_resolve, mock_facts
    ) -> None:
        """gross_margin should be None when gross_profit is FY2025 but revenue is FY2018."""
        mock_resolve.return_value = ("0001234567", "CROSS YEAR CORP")
        # Use facts where Revenues only has FY2018 AND the newer concept is absent
        # so that resolve_concept picks Revenues (the only one available)
        stale_only_facts = {
            "cik": 1234567,
            "entityName": "CROSS YEAR CORP",
            "facts": {
                "us-gaap": {
                    "GrossProfit": MOCK_CROSS_YEAR_FACTS["facts"]["us-gaap"]["GrossProfit"],
                    "Revenues": MOCK_CROSS_YEAR_FACTS["facts"]["us-gaap"]["Revenues"],
                }
            },
        }
        mock_facts.return_value = stale_only_facts

        result = await financials("XYZ", "gross_margin", period="lfy")
        self.assertIsNone(result.metrics["gross_margin"])


class TestSeriesOutput(unittest.IsolatedAsyncioTestCase):
    @patch("edgarpack.query.financials.fetch_company_facts")
    @patch("edgarpack.query.financials.resolve_ticker")
    async def test_series_returns_list(self, mock_resolve, mock_facts) -> None:
        mock_resolve.return_value = ("0001045810", "NVIDIA CORP")
        mock_facts.return_value = MOCK_QUARTERLY_SERIES_FACTS

        result = await financials("NVDA", "revenue", period="quarterly:3")
        revenue = result.metrics["revenue"]
        self.assertIsInstance(revenue, list)
        self.assertEqual(len(revenue), 3)
        self.assertEqual(revenue[0].value, 35_100_000_000)
        self.assertEqual(revenue[1].value, 30_000_000_000)
        self.assertEqual(revenue[2].value, 26_000_000_000)

    @patch("edgarpack.query.financials.fetch_company_facts")
    @patch("edgarpack.query.financials.resolve_ticker")
    async def test_series_to_cited_dict_preserves_list(self, mock_resolve, mock_facts) -> None:
        mock_resolve.return_value = ("0001045810", "NVIDIA CORP")
        mock_facts.return_value = MOCK_QUARTERLY_SERIES_FACTS

        result = await financials("NVDA", "revenue", period="quarterly:3")
        d = result.to_cited_dict()
        revenue_data = d["metrics"]["revenue"]
        self.assertIsInstance(revenue_data, list)
        self.assertEqual(len(revenue_data), 3)
        self.assertIn("citation", revenue_data[0])

    @patch("edgarpack.query.financials.fetch_company_facts")
    @patch("edgarpack.query.financials.resolve_ticker")
    async def test_annual_series_returns_list(self, mock_resolve, mock_facts) -> None:
        mock_resolve.return_value = ("0001045810", "NVIDIA CORP")
        mock_facts.return_value = MOCK_COMPANY_FACTS

        result = await financials("NVDA", "revenue", period="annual:2")
        revenue = result.metrics["revenue"]
        self.assertIsInstance(revenue, list)
        self.assertEqual(len(revenue), 2)
        self.assertEqual(revenue[0].value, 60_922_000_000)
        self.assertEqual(revenue[1].value, 26_974_000_000)


class TestCitationFormat(unittest.IsolatedAsyncioTestCase):
    @patch("edgarpack.query.financials.fetch_company_facts")
    @patch("edgarpack.query.financials.resolve_ticker")
    async def test_citation_string(self, mock_resolve, mock_facts) -> None:
        mock_resolve.return_value = ("0001045810", "NVIDIA CORP")
        mock_facts.return_value = MOCK_COMPANY_FACTS

        result = await financials("NVDA", "revenue")
        revenue = result.metrics["revenue"]
        self.assertIn("NVIDIA CORP", revenue.citation)
        self.assertIn("10-K", revenue.citation)
        self.assertIn("FY2025", revenue.citation)

    @patch("edgarpack.query.financials.fetch_company_facts")
    @patch("edgarpack.query.financials.resolve_ticker")
    async def test_filing_url(self, mock_resolve, mock_facts) -> None:
        mock_resolve.return_value = ("0001045810", "NVIDIA CORP")
        mock_facts.return_value = MOCK_COMPANY_FACTS

        result = await financials("NVDA", "revenue")
        revenue = result.metrics["revenue"]
        self.assertIn("sec.gov", revenue.filing_url)
        self.assertIn("1045810", revenue.filing_url)

    @patch("edgarpack.query.financials.fetch_company_facts")
    @patch("edgarpack.query.financials.resolve_ticker")
    async def test_to_cited_dict(self, mock_resolve, mock_facts) -> None:
        mock_resolve.return_value = ("0001045810", "NVIDIA CORP")
        mock_facts.return_value = MOCK_COMPANY_FACTS

        result = await financials("NVDA", "revenue")
        d = result.to_cited_dict()
        self.assertEqual(d["company"], "NVIDIA CORP")
        self.assertIn("revenue", d["metrics"])
        revenue_dict = d["metrics"]["revenue"]
        self.assertIn("citation", revenue_dict)
        self.assertIn("filing_url", revenue_dict)


if __name__ == "__main__":
    unittest.main()
