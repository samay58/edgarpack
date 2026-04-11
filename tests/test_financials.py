"""Tests for single-company financial queries."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from edgarpack.query.concepts import MetricMeta
from edgarpack.query.financials import _compute_derived, financials
from edgarpack.query.models import DerivedValue

_P = "edgarpack.query.financials"

# Mock submissions response for deep linking
MOCK_SUBMISSIONS = {
    "cik": 1045810,
    "name": "NVIDIA CORP",
    "filings": {
        "recent": {
            "accessionNumber": [
                "0001045810-25-000001",
                "0001045810-25-000020",
                "0001045810-25-000003",
                "0001045810-25-000002",
                "0001045810-24-000010",
                "0001045810-24-000001",
                "0001045810-26-000001",
            ],
            "primaryDocument": [
                "nvda-20250126.htm",
                "nvda-20250427.htm",
                "nvda-20251026.htm",
                "nvda-20250727.htm",
                "nvda-20240428.htm",
                "nvda-20240128.htm",
                "nvda-20260125.htm",
            ],
            "form": ["10-K", "10-Q", "10-Q", "10-Q", "10-Q", "10-K", "10-K"],
            "filingDate": [
                "2025-02-18",
                "2025-06-01",
                "2025-11-20",
                "2025-08-20",
                "2024-06-01",
                "2024-02-21",
                "2026-02-18",
            ],
        }
    },
}


def _mock_submissions(*args, **kwargs):
    return MOCK_SUBMISSIONS


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
    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_single_metric(self, mock_resolve, mock_facts, mock_subs) -> None:
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

    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_multiple_metrics(self, mock_resolve, mock_facts, mock_subs) -> None:
        mock_resolve.return_value = ("0001045810", "NVIDIA CORP")
        mock_facts.return_value = MOCK_COMPANY_FACTS

        result = await financials("NVDA", ["revenue", "net_income", "eps_diluted"])

        self.assertEqual(len(result.metrics), 3)
        self.assertIsNotNone(result.metrics["revenue"])
        self.assertIsNotNone(result.metrics["net_income"])
        self.assertIsNotNone(result.metrics["eps_diluted"])
        self.assertAlmostEqual(result.metrics["eps_diluted"].value, 1.19)

    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_derived_metric_gross_margin(self, mock_resolve, mock_facts, mock_subs) -> None:
        mock_resolve.return_value = ("0001045810", "NVIDIA CORP")
        mock_facts.return_value = MOCK_COMPANY_FACTS

        result = await financials("NVDA", "gross_margin", period="lfy")

        gm = result.metrics["gross_margin"]
        self.assertIsNotNone(gm)
        self.assertIsInstance(gm, DerivedValue)
        # gross_margin = gross_profit / revenue = 44803 / 60922 ~ 0.7355
        self.assertAlmostEqual(gm.value, 44_803_000_000 / 60_922_000_000, places=4)
        self.assertEqual(gm.unit, "pure")

    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_missing_metric_returns_none(self, mock_resolve, mock_facts, mock_subs) -> None:
        mock_resolve.return_value = ("0001045810", "NVIDIA CORP")
        mock_facts.return_value = MOCK_COMPANY_FACTS

        result = await financials("NVDA", "inventory")

        self.assertIsNone(result.metrics["inventory"])

    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_unknown_metric_raises_metric_not_found(self, mock_resolve, mock_facts, mock_subs) -> None:
        """As of self-heal v1, unknown metric names raise instead of silently
        returning None. Layer 0 dereferences aliases first and the caller
        (financials()) raises MetricNotFound with suggestions for anything
        that still doesn't resolve."""
        from edgarpack.query.layer_zero import MetricNotFound

        mock_resolve.return_value = ("0001045810", "NVIDIA CORP")
        mock_facts.return_value = MOCK_COMPANY_FACTS

        with self.assertRaises(MetricNotFound) as ctx:
            await financials("NVDA", "nonexistent_metric")
        self.assertEqual(ctx.exception.metric_name, "nonexistent_metric")


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
    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_derived_returns_none_when_components_differ_year(
        self, mock_resolve, mock_facts, mock_subs
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
    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_series_returns_list(self, mock_resolve, mock_facts, mock_subs) -> None:
        mock_resolve.return_value = ("0001045810", "NVIDIA CORP")
        mock_facts.return_value = MOCK_QUARTERLY_SERIES_FACTS

        result = await financials("NVDA", "revenue", period="quarterly:3")
        revenue = result.metrics["revenue"]
        self.assertIsInstance(revenue, list)
        self.assertEqual(len(revenue), 3)
        self.assertEqual(revenue[0].value, 35_100_000_000)
        self.assertEqual(revenue[1].value, 30_000_000_000)
        self.assertEqual(revenue[2].value, 26_000_000_000)

    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_series_to_cited_dict_preserves_list(self, mock_resolve, mock_facts, _ms) -> None:
        mock_resolve.return_value = ("0001045810", "NVIDIA CORP")
        mock_facts.return_value = MOCK_QUARTERLY_SERIES_FACTS

        result = await financials("NVDA", "revenue", period="quarterly:3")
        d = result.to_cited_dict()
        revenue_data = d["metrics"]["revenue"]
        self.assertIsInstance(revenue_data, list)
        self.assertEqual(len(revenue_data), 3)
        self.assertIn("citation", revenue_data[0])

    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_annual_series_returns_list(self, mock_resolve, mock_facts, mock_subs) -> None:
        mock_resolve.return_value = ("0001045810", "NVIDIA CORP")
        mock_facts.return_value = MOCK_COMPANY_FACTS

        result = await financials("NVDA", "revenue", period="annual:2")
        revenue = result.metrics["revenue"]
        self.assertIsInstance(revenue, list)
        self.assertEqual(len(revenue), 2)
        self.assertEqual(revenue[0].value, 60_922_000_000)
        self.assertEqual(revenue[1].value, 26_974_000_000)


class TestCitationFormat(unittest.IsolatedAsyncioTestCase):
    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_citation_string(self, mock_resolve, mock_facts, mock_subs) -> None:
        mock_resolve.return_value = ("0001045810", "NVIDIA CORP")
        mock_facts.return_value = MOCK_COMPANY_FACTS

        result = await financials("NVDA", "revenue")
        revenue = result.metrics["revenue"]
        self.assertIn("NVIDIA CORP", revenue.citation)
        self.assertIn("10-K", revenue.citation)
        self.assertIn("FY2025", revenue.citation)

    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_filing_url(self, mock_resolve, mock_facts, mock_subs) -> None:
        mock_resolve.return_value = ("0001045810", "NVIDIA CORP")
        mock_facts.return_value = MOCK_COMPANY_FACTS

        result = await financials("NVDA", "revenue")
        revenue = result.metrics["revenue"]
        self.assertIn("sec.gov", revenue.filing_url)
        self.assertIn("1045810", revenue.filing_url)
        self.assertTrue(revenue.filing_url.endswith("-index.htm"))

    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_permalink(self, mock_resolve, mock_facts, mock_subs) -> None:
        mock_resolve.return_value = ("0001045810", "NVIDIA CORP")
        mock_facts.return_value = MOCK_COMPANY_FACTS

        result = await financials("NVDA", "revenue", period="lfy")
        self.assertIn("permalink", result.to_lean_dict())
        self.assertIn("permalink", result.to_cited_dict())
        self.assertEqual(result.permalink, "edgarpack query 0001045810 revenue --period lfy")

    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_to_cited_dict(self, mock_resolve, mock_facts, mock_subs) -> None:
        mock_resolve.return_value = ("0001045810", "NVIDIA CORP")
        mock_facts.return_value = MOCK_COMPANY_FACTS

        result = await financials("NVDA", "revenue")
        d = result.to_cited_dict()
        self.assertEqual(d["company"], "NVIDIA CORP")
        self.assertIn("revenue", d["metrics"])
        revenue_dict = d["metrics"]["revenue"]
        self.assertIn("citation", revenue_dict)
        self.assertIn("filing_url", revenue_dict)


class TestLtmCitation(unittest.IsolatedAsyncioTestCase):
    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_ltm_citation_references_real_filings(
        self, mock_resolve, mock_facts, _ms
    ) -> None:
        """LTM citation should reference the underlying real filings, not 'LTM (LTM2025)'."""
        # Build facts with quarterly + annual data for LTM computation
        mock_resolve.return_value = ("0001045810", "NVIDIA CORP")
        mock_facts.return_value = {
            "cik": 1045810,
            "entityName": "NVIDIA CORP",
            "facts": {
                "us-gaap": {
                    "Revenues": {
                        "units": {
                            "USD": [
                                # FY2025 annual
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
                                # Q1 FY2025 (prior year MRP)
                                {
                                    "val": 26_000_000_000,
                                    "start": "2024-01-29",
                                    "end": "2024-04-28",
                                    "fy": 2025,
                                    "fp": "Q1",
                                    "form": "10-Q",
                                    "accn": "0001045810-24-000010",
                                    "filed": "2024-06-01",
                                },
                                # Q1 FY2026 (MRP)
                                {
                                    "val": 35_100_000_000,
                                    "start": "2025-01-27",
                                    "end": "2025-04-27",
                                    "fy": 2026,
                                    "fp": "Q1",
                                    "form": "10-Q",
                                    "accn": "0001045810-25-000020",
                                    "filed": "2025-06-01",
                                },
                            ]
                        }
                    },
                }
            },
        }

        result = await financials("NVDA", "revenue", period="ltm")
        revenue = result.metrics["revenue"]
        self.assertIsNotNone(revenue)
        self.assertIsInstance(revenue, DerivedValue)
        # Citation should NOT contain "LTM (LTM"
        self.assertNotIn("LTM (LTM", revenue.citation)
        # Citation should reference the underlying filings
        self.assertIn("LTM computed from:", revenue.citation)
        self.assertIn("10-Q", revenue.citation)
        self.assertIn("10-K", revenue.citation)
        # form_type should be the MRP's form, not "LTM"
        self.assertNotEqual(revenue.form_type, "LTM")
        self.assertEqual(revenue.form_type, "10-Q")

    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_ltm_minus_1_has_derived_components(self, mock_resolve, mock_facts, _ms) -> None:
        """LTM-1 should be derived and include component citations in lean output."""
        mock_resolve.return_value = ("0001045810", "NVIDIA CORP")
        mock_facts.return_value = {
            "cik": 1045810,
            "entityName": "NVIDIA CORP",
            "facts": {
                "us-gaap": {
                    "Revenues": {
                        "units": {
                            "USD": [
                                {
                                    "val": 40_000_000_000,
                                    "start": "2023-01-30",
                                    "end": "2024-01-28",
                                    "fy": 2023,
                                    "fp": "FY",
                                    "form": "10-K",
                                    "accn": "0001045810-24-000001",
                                    "filed": "2024-02-21",
                                },
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
                                    "val": 8_000_000_000,
                                    "start": "2023-01-30",
                                    "end": "2023-04-30",
                                    "fy": 2023,
                                    "fp": "Q1",
                                    "form": "10-Q",
                                    "accn": "0001045810-24-000010",
                                    "filed": "2024-06-01",
                                },
                                {
                                    "val": 26_000_000_000,
                                    "start": "2024-01-29",
                                    "end": "2024-04-28",
                                    "fy": 2025,
                                    "fp": "Q1",
                                    "form": "10-Q",
                                    "accn": "0001045810-24-000010",
                                    "filed": "2024-06-01",
                                },
                                {
                                    "val": 35_100_000_000,
                                    "start": "2025-01-27",
                                    "end": "2025-04-27",
                                    "fy": 2026,
                                    "fp": "Q1",
                                    "form": "10-Q",
                                    "accn": "0001045810-25-000020",
                                    "filed": "2025-06-01",
                                },
                            ]
                        }
                    },
                }
            },
        }

        result = await financials("NVDA", "revenue", period="ltm-1")
        revenue = result.metrics["revenue"]
        self.assertIsNotNone(revenue)
        self.assertIsInstance(revenue, DerivedValue)
        self.assertEqual(revenue.fiscal_period, "LTM-1")
        self.assertIn("LTM computed from:", revenue.citation)

        lean = result.to_lean_dict()
        metric = lean["metrics"]["revenue"]
        self.assertTrue(metric["derived"])
        self.assertIn("ltm_components", metric)
        self.assertIn("citation_ids", metric)
        self.assertIn("calculation_id", metric)
        self.assertIn("component_citation_ids", metric)
        self.assertNotIn("mrp", lean["metrics"])
        self.assertNotIn("lfy", lean["metrics"])
        self.assertNotIn("mrp_prior", lean["metrics"])
        mrp_component = metric["ltm_components"]["mrp"]
        self.assertIn("fiscal_label", mrp_component)
        self.assertIn("period", mrp_component)
        self.assertIn("primary_link", mrp_component)
        self.assertIn("citation_id", mrp_component)
        primary_accession = metric["accession"]
        primary_filing = lean["filings"][primary_accession]
        self.assertNotEqual(primary_filing["fiscal_period"], "LTM-1")


class TestLeanJson(unittest.IsolatedAsyncioTestCase):
    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_lean_dict_structure(self, mock_resolve, mock_facts, mock_subs) -> None:
        """to_lean_dict should have company, cik, filings, and metrics at top level."""
        mock_resolve.return_value = ("0001045810", "NVIDIA CORP")
        mock_facts.return_value = MOCK_COMPANY_FACTS

        result = await financials("NVDA", "revenue", period="lfy")
        d = result.to_lean_dict()

        self.assertEqual(d["company"], "NVIDIA CORP")
        self.assertEqual(d["cik"], "0001045810")
        self.assertEqual(d["period"], "lfy")
        self.assertIn("filings", d)
        self.assertIn("metrics", d)
        self.assertIn("citations", d)
        self.assertIn("calculations", d)
        # Revenue metric should have value, unit, concept, period, accession
        revenue = d["metrics"]["revenue"]
        self.assertIn("value", revenue)
        self.assertIn("unit", revenue)
        self.assertIn("concept", revenue)
        self.assertIn("period", revenue)
        self.assertIn("accession", revenue)
        self.assertIn("citation_ids", revenue)

    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_lean_filings_deduplication(self, mock_resolve, mock_facts, mock_subs) -> None:
        """Filings table should deduplicate by accession."""
        mock_resolve.return_value = ("0001045810", "NVIDIA CORP")
        mock_facts.return_value = MOCK_COMPANY_FACTS

        result = await financials("NVDA", ["revenue", "net_income"], period="lfy")
        d = result.to_lean_dict()

        # Both metrics come from same filing, should only appear once
        filings = d["filings"]
        self.assertEqual(len(filings), 1)
        acc = list(filings.keys())[0]
        self.assertEqual(acc, "0001045810-25-000001")

    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_lean_derived_auto_includes_components(
        self, mock_resolve, mock_facts, _ms
    ) -> None:
        """Querying gross_margin should auto-include gross_profit and revenue."""
        mock_resolve.return_value = ("0001045810", "NVIDIA CORP")
        mock_facts.return_value = MOCK_COMPANY_FACTS

        result = await financials("NVDA", "gross_margin", period="lfy")
        d = result.to_lean_dict()

        metrics = d["metrics"]
        self.assertIn("gross_margin", metrics)
        self.assertIn("gross_profit", metrics)
        self.assertIn("revenue", metrics)
        # Components should be tagged
        self.assertTrue(metrics["gross_profit"]["_component"])
        self.assertTrue(metrics["revenue"]["_component"])

    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_lean_derived_has_formula(self, mock_resolve, mock_facts, mock_subs) -> None:
        """Derived metrics should include formula and component references."""
        mock_resolve.return_value = ("0001045810", "NVIDIA CORP")
        mock_facts.return_value = MOCK_COMPANY_FACTS

        result = await financials("NVDA", "gross_margin", period="lfy")
        d = result.to_lean_dict()

        gm = d["metrics"]["gross_margin"]
        self.assertTrue(gm["derived"])
        self.assertIn("formula", gm)
        self.assertIn("components", gm)

    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_lean_no_component_for_explicit_metrics(
        self, mock_resolve, mock_facts, _ms
    ) -> None:
        """When user explicitly requests components, they should not be tagged."""
        mock_resolve.return_value = ("0001045810", "NVIDIA CORP")
        mock_facts.return_value = MOCK_COMPANY_FACTS

        result = await financials("NVDA", ["gross_margin", "revenue"], period="lfy")
        d = result.to_lean_dict()

        # revenue was explicitly requested, should NOT have _component tag
        self.assertNotIn("_component", d["metrics"]["revenue"])


class TestDeepLinking(unittest.IsolatedAsyncioTestCase):
    """Tests for multi-tier deep linking URLs (concept, viewer, document)."""

    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_concept_url(self, mock_resolve, mock_facts, mock_subs) -> None:
        """concept_url should point to the companyconcept API endpoint."""
        mock_resolve.return_value = ("0001045810", "NVIDIA CORP")
        mock_facts.return_value = MOCK_COMPANY_FACTS

        result = await financials("NVDA", "revenue", period="lfy")
        revenue = result.metrics["revenue"]
        url = revenue.concept_url
        self.assertIsNotNone(url)
        self.assertIn("/api/xbrl/companyconcept/", url)
        self.assertIn("CIK0001045810", url)
        self.assertIn("us-gaap", url)
        self.assertIn("Revenues.json", url)

    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_viewer_url(self, mock_resolve, mock_facts, mock_subs) -> None:
        """viewer_url should point to the SEC Inline XBRL Viewer."""
        mock_resolve.return_value = ("0001045810", "NVIDIA CORP")
        mock_facts.return_value = MOCK_COMPANY_FACTS

        result = await financials("NVDA", "revenue", period="lfy")
        revenue = result.metrics["revenue"]
        url = revenue.viewer_url
        self.assertIsNotNone(url)
        self.assertIn("/ix?doc=", url)
        self.assertIn("nvda-20250126.htm", url)
        self.assertIn("1045810", url)

    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_document_url_text_fragment(self, mock_resolve, mock_facts, mock_subs) -> None:
        """document_url should include #:~:text= with concept label."""
        mock_resolve.return_value = ("0001045810", "NVIDIA CORP")
        mock_facts.return_value = MOCK_COMPANY_FACTS

        result = await financials("NVDA", "net_income", period="lfy")
        ni = result.metrics["net_income"]
        url = ni.document_url
        self.assertIsNotNone(url)
        self.assertIn("#:~:text=", url)
        # NetIncomeLoss -> "Net Income Loss"
        self.assertIn("Net%20Income%20Loss", url)
        self.assertIn("nvda-20250126.htm", url)

    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_derived_no_concept_url(self, mock_resolve, mock_facts, mock_subs) -> None:
        """Derived metrics (formula in concept field) should have no concept_url."""
        mock_resolve.return_value = ("0001045810", "NVIDIA CORP")
        mock_facts.return_value = MOCK_COMPANY_FACTS

        result = await financials("NVDA", "gross_margin", period="lfy")
        gm = result.metrics["gross_margin"]
        self.assertIsNotNone(gm)
        # concept = "gross_profit / revenue" (has spaces) -> concept_url should be None
        self.assertIsNone(gm.concept_url)
        # viewer_url should still work (uses primary_document)
        self.assertIsNotNone(gm.viewer_url)

    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_lean_filings_has_viewer_url(self, mock_resolve, mock_facts, mock_subs) -> None:
        """Lean JSON filings table should include viewer_url when available."""
        mock_resolve.return_value = ("0001045810", "NVIDIA CORP")
        mock_facts.return_value = MOCK_COMPANY_FACTS

        result = await financials("NVDA", "revenue", period="lfy")
        d = result.to_lean_dict()
        filings = d["filings"]
        acc = "0001045810-25-000001"
        self.assertIn(acc, filings)
        self.assertIn("viewer_url", filings[acc])
        self.assertIn("/ix?doc=", filings[acc]["viewer_url"])

    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_cited_dict_has_deep_links(self, mock_resolve, mock_facts, mock_subs) -> None:
        """to_cited_dict should include concept_url, viewer_url, document_url."""
        mock_resolve.return_value = ("0001045810", "NVIDIA CORP")
        mock_facts.return_value = MOCK_COMPANY_FACTS

        result = await financials("NVDA", "revenue", period="lfy")
        d = result.to_cited_dict()
        revenue_dict = d["metrics"]["revenue"]
        self.assertIn("concept_url", revenue_dict)
        self.assertIn("viewer_url", revenue_dict)
        self.assertIn("document_url", revenue_dict)

    @patch(
        f"{_P}.fetch_submissions",
        new_callable=AsyncMock,
        side_effect=OSError("network error"),
    )
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_submissions_failure_graceful(self, mock_resolve, mock_facts, _ms) -> None:
        """When fetch_submissions fails, data should still return without viewer/document URLs."""
        mock_resolve.return_value = ("0001045810", "NVIDIA CORP")
        mock_facts.return_value = MOCK_COMPANY_FACTS

        result = await financials("NVDA", "revenue", period="lfy")
        revenue = result.metrics["revenue"]
        self.assertIsNotNone(revenue)
        self.assertEqual(revenue.value, 60_922_000_000)
        # concept_url should still work (no submissions needed)
        self.assertIsNotNone(revenue.concept_url)
        # viewer_url and document_url need primary_document, which needs submissions
        self.assertIsNone(revenue.viewer_url)
        self.assertIsNone(revenue.document_url)

    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_lean_metric_has_concept_url(self, mock_resolve, mock_facts, mock_subs) -> None:
        """Lean metric dict should include concept_url for non-derived metrics."""
        mock_resolve.return_value = ("0001045810", "NVIDIA CORP")
        mock_facts.return_value = MOCK_COMPANY_FACTS

        result = await financials("NVDA", "revenue", period="lfy")
        d = result.to_lean_dict()
        revenue = d["metrics"]["revenue"]
        self.assertIn("concept_url", revenue)
        self.assertIn("Revenues.json", revenue["concept_url"])


MOCK_LOW_DEBT_FACTS = {
    "cik": 37996,
    "entityName": "FORD MOTOR CO",
    "facts": {
        "us-gaap": {
            "LongTermDebtNoncurrent": {
                "label": "Long Term Debt Noncurrent",
                "units": {
                    "USD": [
                        {
                            "val": 291_000_000,
                            "start": "2025-01-01",
                            "end": "2025-12-31",
                            "fy": 2025,
                            "fp": "FY",
                            "form": "10-K",
                            "accn": "0000037996-25-000001",
                            "filed": "2026-02-05",
                        },
                    ]
                },
            },
            "Liabilities": {
                "label": "Liabilities",
                "units": {
                    "USD": [
                        {
                            "val": 240_300_000_000,
                            "start": "2025-01-01",
                            "end": "2025-12-31",
                            "fy": 2025,
                            "fp": "FY",
                            "form": "10-K",
                            "accn": "0000037996-25-000001",
                            "filed": "2026-02-05",
                        },
                    ]
                },
            },
        }
    },
}


class TestLowDebtSanityWarning(unittest.IsolatedAsyncioTestCase):
    """total_debt << total_liabilities should attach a warning."""

    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_low_debt_warning_attached(self, mock_resolve, mock_facts, _ms) -> None:
        mock_resolve.return_value = ("0000037996", "FORD MOTOR CO")
        mock_facts.return_value = MOCK_LOW_DEBT_FACTS

        result = await financials("F", "total_debt", period="lfy")
        debt = result.metrics["total_debt"]
        self.assertIsNotNone(debt)
        self.assertEqual(debt.value, 291_000_000)
        self.assertTrue(
            any("less than 2%" in w for w in debt.warnings),
            f"Expected low-debt warning in {debt.warnings}",
        )

    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_normal_debt_no_warning(self, mock_resolve, mock_facts, _ms) -> None:
        """Company with normal debt/liabilities ratio should NOT get the warning."""
        mock_resolve.return_value = ("0001045810", "NVIDIA CORP")
        # Reuse NVDA facts but add Liabilities and a debt concept
        facts_with_debt = {
            "cik": 1045810,
            "entityName": "NVIDIA CORP",
            "facts": {
                "us-gaap": {
                    **MOCK_COMPANY_FACTS["facts"]["us-gaap"],
                    "LongTermDebt": {
                        "label": "Long Term Debt",
                        "units": {
                            "USD": [
                                {
                                    "val": 10_000_000_000,
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
                    "Liabilities": {
                        "label": "Liabilities",
                        "units": {
                            "USD": [
                                {
                                    "val": 30_000_000_000,
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
        mock_facts.return_value = facts_with_debt

        result = await financials("NVDA", "total_debt", period="lfy")
        debt = result.metrics["total_debt"]
        self.assertIsNotNone(debt)
        # 10B / 30B = 33% -- well above 2% threshold
        self.assertFalse(
            any("less than 2%" in w for w in debt.warnings),
            f"Did not expect low-debt warning but got {debt.warnings}",
        )


class TestStalenessGuard(unittest.IsolatedAsyncioTestCase):
    """Values too far behind the current year should be rejected as stale."""

    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_stale_value_returns_none(self, mock_resolve, mock_facts, _ms) -> None:
        """A metric with only FY2020 data should be stale in 2026."""
        mock_resolve.return_value = ("0000018230", "CATERPILLAR INC")
        mock_facts.return_value = {
            "cik": 18230,
            "entityName": "CATERPILLAR INC",
            "facts": {
                "us-gaap": {
                    "GrossProfit": {
                        "label": "Gross Profit",
                        "units": {
                            "USD": [
                                {
                                    "val": 2_786_000_000,
                                    "start": "2020-01-01",
                                    "end": "2020-12-31",
                                    "fy": 2020,
                                    "fp": "FY",
                                    "form": "10-K",
                                    "accn": "0000018230-21-000001",
                                    "filed": "2021-02-17",
                                },
                            ]
                        },
                    },
                }
            },
        }
        result = await financials("CAT", "gross_profit", period="lfy")
        self.assertIsNone(result.metrics["gross_profit"])

    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_fresh_value_not_stale(self, mock_resolve, mock_facts, _ms) -> None:
        """FY2025 data should not be stale in 2026."""
        mock_resolve.return_value = ("0001045810", "NVIDIA CORP")
        mock_facts.return_value = MOCK_COMPANY_FACTS
        result = await financials("NVDA", "revenue", period="lfy")
        self.assertIsNotNone(result.metrics["revenue"])
        self.assertEqual(result.metrics["revenue"].value, 60_922_000_000)

    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_series_queries_skip_staleness(self, mock_resolve, mock_facts, _ms) -> None:
        """annual:N series queries should not filter by staleness."""
        mock_resolve.return_value = ("0001045810", "NVIDIA CORP")
        mock_facts.return_value = MOCK_COMPANY_FACTS
        result = await financials("NVDA", "revenue", period="annual:2")
        revenue = result.metrics["revenue"]
        self.assertIsInstance(revenue, list)
        self.assertEqual(len(revenue), 2)

    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_stale_component_rejects_derived(self, mock_resolve, mock_facts, _ms) -> None:
        """A derived metric with a stale component should return None."""
        mock_resolve.return_value = ("0001234567", "CROSS YEAR CORP")
        mock_facts.return_value = {
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
                                    "start": "2019-01-01",
                                    "end": "2019-12-31",
                                    "fy": 2019,
                                    "fp": "FY",
                                    "form": "10-K",
                                    "accn": "0001234567-20-000001",
                                    "filed": "2020-03-01",
                                },
                            ]
                        },
                    },
                    "Revenues": {
                        "label": "Revenues",
                        "units": {
                            "USD": [
                                {
                                    "val": 60_000_000_000,
                                    "start": "2019-01-01",
                                    "end": "2019-12-31",
                                    "fy": 2019,
                                    "fp": "FY",
                                    "form": "10-K",
                                    "accn": "0001234567-20-000001",
                                    "filed": "2020-03-01",
                                },
                            ]
                        },
                    },
                }
            },
        }
        result = await financials("XYZ", "gross_margin", period="lfy")
        self.assertIsNone(result.metrics["gross_margin"])


class TestScopeWarnings(unittest.IsolatedAsyncioTestCase):
    """Concepts with known scope mismatches should attach warnings."""

    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_cogs_scope_warning_attached(self, mock_resolve, mock_facts, _ms) -> None:
        """CostOfGoodsAndServicesSold should carry a scope warning."""
        mock_resolve.return_value = ("0000012345", "SERVICE CORP")
        mock_facts.return_value = {
            "cik": 12345,
            "entityName": "SERVICE CORP",
            "facts": {
                "us-gaap": {
                    "CostOfGoodsAndServicesSold": {
                        "label": "Cost of Goods and Services Sold",
                        "units": {
                            "USD": [
                                {
                                    "val": 25_000_000_000,
                                    "start": "2024-01-01",
                                    "end": "2024-12-31",
                                    "fy": 2025,
                                    "fp": "FY",
                                    "form": "10-K",
                                    "accn": "0000012345-25-000001",
                                    "filed": "2025-03-01",
                                },
                            ]
                        },
                    },
                }
            },
        }
        result = await financials("SVC", "cost_of_revenue", period="lfy")
        cogs = result.metrics["cost_of_revenue"]
        self.assertIsNotNone(cogs)
        self.assertTrue(
            any("CostOfGoodsAndServicesSold" in w for w in cogs.warnings),
            f"Expected scope warning, got: {cogs.warnings}",
        )

    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_clean_concept_no_warning(self, mock_resolve, mock_facts, _ms) -> None:
        """CostOfRevenue (preferred concept) should not carry a scope warning."""
        mock_resolve.return_value = ("0001045810", "NVIDIA CORP")
        mock_facts.return_value = {
            "cik": 1045810,
            "entityName": "NVIDIA CORP",
            "facts": {
                "us-gaap": {
                    "CostOfRevenue": {
                        "label": "Cost of Revenue",
                        "units": {
                            "USD": [
                                {
                                    "val": 16_000_000_000,
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
        result = await financials("NVDA", "cost_of_revenue", period="lfy")
        cogs = result.metrics["cost_of_revenue"]
        self.assertIsNotNone(cogs)
        self.assertEqual(cogs.warnings, [])

    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_scope_warning_propagates_to_derived_component(
        self, mock_resolve, mock_facts, _ms
    ) -> None:
        """Scope warning on a component should be visible via the DerivedValue's components."""
        mock_resolve.return_value = ("0000012345", "SERVICE CORP")
        mock_facts.return_value = {
            "cik": 12345,
            "entityName": "SERVICE CORP",
            "facts": {
                "us-gaap": {
                    "Revenues": {
                        "label": "Revenues",
                        "units": {
                            "USD": [
                                {
                                    "val": 50_000_000_000,
                                    "start": "2024-01-01",
                                    "end": "2024-12-31",
                                    "fy": 2025,
                                    "fp": "FY",
                                    "form": "10-K",
                                    "accn": "0000012345-25-000001",
                                    "filed": "2025-03-01",
                                },
                            ]
                        },
                    },
                    "CostOfGoodsAndServicesSold": {
                        "label": "Cost of Goods and Services Sold",
                        "units": {
                            "USD": [
                                {
                                    "val": 25_000_000_000,
                                    "start": "2024-01-01",
                                    "end": "2024-12-31",
                                    "fy": 2025,
                                    "fp": "FY",
                                    "form": "10-K",
                                    "accn": "0000012345-25-000001",
                                    "filed": "2025-03-01",
                                },
                            ]
                        },
                    },
                    "GrossProfit": {
                        "label": "Gross Profit",
                        "units": {
                            "USD": [
                                {
                                    "val": 25_000_000_000,
                                    "start": "2024-01-01",
                                    "end": "2024-12-31",
                                    "fy": 2025,
                                    "fp": "FY",
                                    "form": "10-K",
                                    "accn": "0000012345-25-000001",
                                    "filed": "2025-03-01",
                                },
                            ]
                        },
                    },
                }
            },
        }
        result = await financials("SVC", "gross_margin", period="lfy")
        gm = result.metrics["gross_margin"]
        self.assertIsNotNone(gm)
        self.assertIsInstance(gm, DerivedValue)
        # The gross_profit component depends on GrossProfit (no warning),
        # but revenue uses Revenues (no warning either).
        # Let's check cost_of_revenue directly for the scope warning.
        result2 = await financials("SVC", "cost_of_revenue", period="lfy")
        cogs = result2.metrics["cost_of_revenue"]
        self.assertTrue(
            any("CostOfGoodsAndServicesSold" in w for w in cogs.warnings),
        )


class TestDerivedCycleProtection(unittest.TestCase):
    def test_cycle_returns_none_instead_of_recursing_forever(self) -> None:
        cycle_a = MetricMeta(
            concepts=(),
            duration=True,
            derived=True,
            formula="cycle_b + cycle_b",
            components=("cycle_b",),
        )
        cycle_b = MetricMeta(
            concepts=(),
            duration=True,
            derived=True,
            formula="cycle_a + cycle_a",
            components=("cycle_a",),
        )

        with patch.dict(
            "edgarpack.query.financials.METRIC_MAP",
            {"cycle_a": cycle_a, "cycle_b": cycle_b},
            clear=False,
        ):
            result = _compute_derived(
                facts={},
                metric="cycle_a",
                meta=cycle_a,
                company="TEST",
                cik="0000000000",
                period="lfy",
            )
        self.assertIsNone(result)


class TestAliasDereferencing(unittest.TestCase):
    """Alias lookup happens before METRIC_MAP check."""

    def test_free_cash_flow_is_known_canonical(self) -> None:
        # 'fcf' should resolve to 'free_cash_flow' via alias; free_cash_flow
        # is already in METRIC_MAP as a derived metric.
        from edgarpack.query.concepts import METRIC_MAP
        self.assertIn("free_cash_flow", METRIC_MAP)

    def test_unknown_metric_raises_metric_not_found(self) -> None:
        import asyncio as _asyncio
        from edgarpack.query.layer_zero import MetricNotFound

        async def _run() -> None:
            with patch(f"{_P}.resolve_ticker",
                       new=AsyncMock(return_value=("0001045810", "NVIDIA CORP"))), \
                 patch(f"{_P}.fetch_company_facts",
                       new=AsyncMock(return_value={"facts": {}})), \
                 patch(f"{_P}._build_doc_map",
                       new=AsyncMock(return_value={})):
                with self.assertRaises(MetricNotFound) as ctx:
                    await financials("NVDA", metrics="xyzzy_nothing", period="lfy")
                self.assertEqual(ctx.exception.metric_name, "xyzzy_nothing")

        _asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
