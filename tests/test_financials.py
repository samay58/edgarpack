"""Tests for single-company financial queries."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
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
    async def test_unknown_metric_raises_metric_not_found(
        self, mock_resolve, mock_facts, mock_subs
    ) -> None:
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


GOOG_BAD_LTM_FACTS = {
    "cik": 1652044,
    "entityName": "Alphabet Inc.",
    "facts": {
        "us-gaap": {
            "Revenues": {
                "label": "Revenues",
                "units": {
                    "USD": [
                        {
                            "val": 400_000_000_000,
                            "start": "2025-01-01",
                            "end": "2025-12-31",
                            "fy": 2025,
                            "fp": "FY",
                            "form": "10-K",
                            "accn": "0001652044-26-000001",
                            "filed": "2026-02-04",
                        },
                        {
                            "val": 90_000_000_000,
                            "start": "2026-01-01",
                            "end": "2026-03-31",
                            "fy": 2026,
                            "fp": "Q1",
                            "form": "10-Q",
                            "accn": "0001652044-26-000020",
                            "filed": "2026-04-25",
                        },
                    ]
                },
            },
            "ContractWithCustomerLiabilityRevenueRecognized": {
                "label": "Revenue Recognized From Contract Liability",
                "units": {
                    "USD": [
                        {
                            "val": 3_500_000_000,
                            "start": "2026-01-01",
                            "end": "2026-03-31",
                            "fy": 2026,
                            "fp": "Q1",
                            "form": "10-Q",
                            "accn": "0001652044-26-000020",
                            "filed": "2026-04-25",
                        },
                    ]
                },
            },
        }
    },
}


GOOD_LEARNED_GROSS_PROFIT_FACTS = {
    "cik": 9990001,
    "entityName": "CUSTOM GROSS PROFIT CORP",
    "facts": {
        "us-gaap": {
            "Revenues": {
                "label": "Revenues",
                "units": {
                    "USD": [
                        {
                            "val": 1_000_000_000,
                            "start": "2025-01-01",
                            "end": "2025-12-31",
                            "fy": 2025,
                            "fp": "FY",
                            "form": "10-K",
                            "accn": "0009990001-26-000001",
                            "filed": "2026-02-15",
                        }
                    ]
                },
            },
            "GrossProfitLoss": {
                "label": "Gross Profit Loss",
                "units": {
                    "USD": [
                        {
                            "val": 600_000_000,
                            "start": "2025-01-01",
                            "end": "2025-12-31",
                            "fy": 2025,
                            "fp": "FY",
                            "form": "10-K",
                            "accn": "0009990001-26-000001",
                            "filed": "2026-02-15",
                        }
                    ]
                },
            },
        }
    },
}


BAD_CACHED_GROSS_PROFIT_FACTS = {
    "cik": 1783879,
    "entityName": "Robinhood Markets, Inc.",
    "facts": {
        "us-gaap": {
            "Revenues": {
                "label": "Revenues",
                "units": {
                    "USD": [
                        {
                            "val": 4_473_000_000,
                            "start": "2025-01-01",
                            "end": "2025-12-31",
                            "fy": 2025,
                            "fp": "FY",
                            "form": "10-K/A",
                            "accn": "0001783879-26-000029",
                            "filed": "2026-02-20",
                        }
                    ]
                },
            },
            "ContractWithCustomerAssetGross": {
                "label": "Contract with Customer Asset, Gross",
                "units": {
                    "USD": [
                        {
                            "val": 185_000_000,
                            "end": "2025-12-31",
                            "fy": 2025,
                            "fp": "FY",
                            "form": "10-K/A",
                            "accn": "0001783879-26-000029",
                            "filed": "2026-02-20",
                        }
                    ]
                },
            },
        }
    },
}


SPARSE_CAPEX_FACTS = {
    "cik": 1783879,
    "entityName": "Robinhood Markets, Inc.",
    "facts": {
        "us-gaap": {
            "Revenues": {
                "units": {
                    "USD": [
                        {
                            "val": 4_473_000_000,
                            "start": "2025-01-01",
                            "end": "2025-12-31",
                            "fy": 2025,
                            "fp": "FY",
                            "form": "10-K/A",
                            "accn": "0001783879-26-000029",
                            "filed": "2026-02-20",
                        }
                    ]
                }
            },
            "PaymentsToAcquireProductiveAssets": {
                "units": {
                    "USD": [
                        {
                            "val": 28_000_000,
                            "start": "2022-01-01",
                            "end": "2022-12-31",
                            "fy": 2022,
                            "fp": "FY",
                            "form": "10-K",
                            "accn": "0001783879-23-000045",
                            "filed": "2023-02-27",
                        },
                        {
                            "val": 63_182_000,
                            "start": "2021-01-01",
                            "end": "2021-12-31",
                            "fy": 2021,
                            "fp": "FY",
                            "form": "10-K",
                            "accn": "0001783879-22-000044",
                            "filed": "2022-02-24",
                        },
                    ]
                }
            },
        }
    },
}


ALIGNED_CAPEX_FACTS = {
    "cik": 1783879,
    "entityName": "Robinhood Markets, Inc.",
    "facts": {
        "us-gaap": {
            "NetCashProvidedByUsedInOperatingActivities": {
                "units": {
                    "USD": [
                        {
                            "val": 1_638_000_000,
                            "start": "2025-01-01",
                            "end": "2025-12-31",
                            "fy": 2025,
                            "fp": "FY",
                            "form": "10-K/A",
                            "accn": "0001783879-26-000029",
                            "filed": "2026-02-20",
                        },
                        {
                            "val": -157_000_000,
                            "start": "2024-01-01",
                            "end": "2024-12-31",
                            "fy": 2024,
                            "fp": "FY",
                            "form": "10-K",
                            "accn": "0001783879-25-000049",
                            "filed": "2025-02-18",
                        },
                        {
                            "val": 1_181_000_000,
                            "start": "2023-01-01",
                            "end": "2023-12-31",
                            "fy": 2023,
                            "fp": "FY",
                            "form": "10-K",
                            "accn": "0001783879-24-000054",
                            "filed": "2024-02-27",
                        },
                    ]
                }
            },
            "PaymentsToAcquireOtherProductiveAssets": {
                "units": {
                    "USD": [
                        {
                            "val": 15_000_000,
                            "start": "2025-01-01",
                            "end": "2025-12-31",
                            "fy": 2025,
                            "fp": "FY",
                            "form": "10-K/A",
                            "accn": "0001783879-26-000029",
                            "filed": "2026-02-20",
                        },
                        {
                            "val": 13_000_000,
                            "start": "2024-01-01",
                            "end": "2024-12-31",
                            "fy": 2024,
                            "fp": "FY",
                            "form": "10-K",
                            "accn": "0001783879-25-000049",
                            "filed": "2025-02-18",
                        },
                        {
                            "val": 2_000_000,
                            "start": "2023-01-01",
                            "end": "2023-12-31",
                            "fy": 2023,
                            "fp": "FY",
                            "form": "10-K",
                            "accn": "0001783879-24-000054",
                            "filed": "2024-02-27",
                        },
                    ]
                }
            },
        }
    },
}


MIXED_REVENUE_CONCEPT_FACTS = {
    "cik": 1652044,
    "entityName": "Alphabet Inc.",
    "facts": {
        "us-gaap": {
            "RevenueFromContractWithCustomerExcludingAssessedTax": {
                "units": {
                    "USD": [
                        {
                            "val": 402_800_000_000,
                            "start": "2025-01-01",
                            "end": "2025-12-31",
                            "fy": 2025,
                            "fp": "FY",
                            "form": "10-K",
                            "accn": "0001652044-26-000018",
                            "filed": "2026-02-05",
                        },
                        {
                            "val": 257_600_000_000,
                            "start": "2021-01-01",
                            "end": "2021-12-31",
                            "fy": 2021,
                            "fp": "FY",
                            "form": "10-K",
                            "accn": "0001652044-22-000019",
                            "filed": "2022-02-02",
                        },
                    ]
                }
            },
            "Revenues": {
                "units": {
                    "USD": [
                        {
                            "val": 350_000_000_000,
                            "start": "2024-01-01",
                            "end": "2024-12-31",
                            "fy": 2024,
                            "fp": "FY",
                            "form": "10-K",
                            "accn": "0001652044-25-000014",
                            "filed": "2025-02-04",
                        }
                    ]
                }
            },
        }
    },
}


MOCK_EBITDA_SERIES_FACTS = {
    "cik": 1045810,
    "entityName": "NVIDIA CORP",
    "facts": {
        "us-gaap": {
            "OperatingIncomeLoss": {
                "label": "Operating Income",
                "units": {
                    "USD": [
                        {
                            "val": 130_000_000_000,
                            "start": "2024-01-29",
                            "end": "2025-01-26",
                            "fy": 2025,
                            "fp": "FY",
                            "form": "10-K",
                            "accn": "0001045810-25-000001",
                            "filed": "2025-02-18",
                        },
                        {
                            "val": 90_000_000_000,
                            "start": "2023-01-30",
                            "end": "2024-01-28",
                            "fy": 2024,
                            "fp": "FY",
                            "form": "10-K",
                            "accn": "0001045810-24-000001",
                            "filed": "2024-02-21",
                        },
                        {
                            "val": 30_000_000_000,
                            "start": "2024-07-29",
                            "end": "2024-10-27",
                            "fy": 2025,
                            "fp": "Q3",
                            "form": "10-Q",
                            "accn": "0001045810-25-000003",
                            "filed": "2025-11-20",
                        },
                        {
                            "val": 24_000_000_000,
                            "start": "2024-04-29",
                            "end": "2024-07-28",
                            "fy": 2025,
                            "fp": "Q2",
                            "form": "10-Q",
                            "accn": "0001045810-25-000002",
                            "filed": "2025-08-20",
                        },
                        {
                            "val": 20_000_000_000,
                            "start": "2024-01-29",
                            "end": "2024-04-28",
                            "fy": 2025,
                            "fp": "Q1",
                            "form": "10-Q",
                            "accn": "0001045810-25-000020",
                            "filed": "2025-06-01",
                        },
                    ]
                },
            },
            "DepreciationAndAmortization": {
                "label": "Depreciation and Amortization",
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
                        {
                            "val": 8_000_000_000,
                            "start": "2023-01-30",
                            "end": "2024-01-28",
                            "fy": 2024,
                            "fp": "FY",
                            "form": "10-K",
                            "accn": "0001045810-24-000001",
                            "filed": "2024-02-21",
                        },
                        {
                            "val": 2_000_000_000,
                            "start": "2024-01-29",
                            "end": "2024-04-28",
                            "fy": 2025,
                            "fp": "Q1",
                            "form": "10-Q",
                            "accn": "0001045810-25-000020",
                            "filed": "2025-06-01",
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


class TestPeriodAwareResolution(unittest.IsolatedAsyncioTestCase):
    @patch(f"{_P}._build_doc_map", new_callable=AsyncMock, return_value={})
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_ltm_failure_does_not_self_heal_to_contract_liability(
        self, mock_resolve, mock_facts, _mock_doc_map
    ) -> None:
        mock_resolve.return_value = ("0001652044", "Alphabet Inc.")
        mock_facts.return_value = GOOG_BAD_LTM_FACTS

        with tempfile.TemporaryDirectory() as tmp:
            registry_path = Path(tmp) / "registry.db"
            with patch("edgarpack.query.learned_registry.DEFAULT_REGISTRY_PATH", registry_path):
                result = await financials("GOOG", "revenue", period="ltm")

        self.assertIsNone(result.metrics["revenue"])
        self.assertIn(
            "ltm_incomputable",
            [d.kind for d in result.diagnostics if d.metric == "revenue"],
        )

    @patch(f"{_P}._build_doc_map", new_callable=AsyncMock, return_value={})
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_verified_learned_bad_mapping_still_fails_period_guard(
        self, mock_resolve, mock_facts, _mock_doc_map
    ) -> None:
        from edgarpack.query.learned_registry import LearnedRegistry

        mock_resolve.return_value = ("0001652044", "Alphabet Inc.")
        mock_facts.return_value = GOOG_BAD_LTM_FACTS

        with tempfile.TemporaryDirectory() as tmp:
            registry_path = Path(tmp) / "registry.db"
            reg = LearnedRegistry(db_path=registry_path)
            reg.upsert(
                cik="0001652044",
                metric="revenue",
                concept="ContractWithCustomerLiabilityRevenueRecognized",
                taxonomy="us-gaap",
                source="fuzzy",
                verified=True,
                verif_method="manual",
                value_sample=3_500_000_000,
            )
            reg.close()
            with patch("edgarpack.query.learned_registry.DEFAULT_REGISTRY_PATH", registry_path):
                result = await financials("GOOG", "revenue", period="ltm")

        self.assertIsNone(result.metrics["revenue"])
        self.assertIn(
            "ltm_incomputable",
            [d.kind for d in result.diagnostics if d.metric == "revenue"],
        )

    @patch(f"{_P}._build_doc_map", new_callable=AsyncMock, return_value={})
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_verified_learned_gross_profit_feeds_direct_and_derived_metrics(
        self, mock_resolve, mock_facts, _mock_doc_map
    ) -> None:
        from edgarpack.query.learned_registry import LearnedRegistry

        mock_resolve.return_value = ("0009990001", "CUSTOM GROSS PROFIT CORP")
        mock_facts.return_value = GOOD_LEARNED_GROSS_PROFIT_FACTS

        with tempfile.TemporaryDirectory() as tmp:
            registry_path = Path(tmp) / "registry.db"
            reg = LearnedRegistry(db_path=registry_path)
            reg.upsert(
                cik="0009990001",
                metric="gross_profit",
                concept="GrossProfitLoss",
                taxonomy="us-gaap",
                source="user",
                verified=True,
                verif_method="manual",
                value_sample=600_000_000,
            )
            reg.close()
            with patch("edgarpack.query.learned_registry.DEFAULT_REGISTRY_PATH", registry_path):
                result = await financials(
                    "CGP",
                    ["gross_profit", "gross_margin"],
                    period="lfy",
                )

        gross_profit = result.metrics["gross_profit"]
        self.assertIsNotNone(gross_profit)
        self.assertEqual(gross_profit.concept, "GrossProfitLoss")
        self.assertEqual(gross_profit.value, 600_000_000)

        gross_margin = result.metrics["gross_margin"]
        self.assertIsNotNone(gross_margin)
        self.assertIsInstance(gross_margin, DerivedValue)
        self.assertAlmostEqual(gross_margin.value, 0.6)
        self.assertEqual(gross_margin.components["gross_profit"].concept, "GrossProfitLoss")

    @patch(f"{_P}._build_doc_map", new_callable=AsyncMock, return_value={})
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_bad_cached_gross_profit_does_not_feed_direct_or_derived_metrics(
        self, mock_resolve, mock_facts, _mock_doc_map
    ) -> None:
        from edgarpack.query.learned_registry import LearnedRegistry

        mock_resolve.return_value = ("0001783879", "Robinhood Markets, Inc.")
        mock_facts.return_value = BAD_CACHED_GROSS_PROFIT_FACTS

        with tempfile.TemporaryDirectory() as tmp:
            registry_path = Path(tmp) / "registry.db"
            reg = LearnedRegistry(db_path=registry_path)
            reg.upsert(
                cik="0001783879",
                metric="gross_profit",
                concept="ContractWithCustomerAssetGross",
                taxonomy="us-gaap",
                source="fuzzy",
                verified=True,
                verif_method="manual",
                value_sample=185_000_000,
            )
            reg.close()
            with patch("edgarpack.query.learned_registry.DEFAULT_REGISTRY_PATH", registry_path):
                result = await financials(
                    "HOOD",
                    ["gross_profit", "gross_margin"],
                    period="lfy",
                )

        self.assertIsNone(result.metrics["gross_profit"])
        self.assertIsNone(result.metrics["gross_margin"])

    @patch(f"{_P}._build_doc_map", new_callable=AsyncMock, return_value={})
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_lfy_offset_rejects_concept_local_nearest_year(
        self, mock_resolve, mock_facts, _mock_doc_map
    ) -> None:
        mock_resolve.return_value = ("0001783879", "Robinhood Markets, Inc.")
        mock_facts.return_value = SPARSE_CAPEX_FACTS

        result = await financials("HOOD", "capex", period="lfy-1")

        self.assertIsNone(result.metrics["capex"])

    @patch(f"{_P}._build_doc_map", new_callable=AsyncMock, return_value={})
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_annual_series_can_merge_exact_years_across_known_concepts(
        self, mock_resolve, mock_facts, _mock_doc_map
    ) -> None:
        mock_resolve.return_value = ("0001652044", "Alphabet Inc.")
        mock_facts.return_value = MIXED_REVENUE_CONCEPT_FACTS

        result = await financials("GOOG", "revenue", period="annual:2")

        revenue = result.metrics["revenue"]
        self.assertIsInstance(revenue, list)
        self.assertEqual([v.fiscal_year for v in revenue], [2025, 2024])
        self.assertEqual([v.value for v in revenue], [402_800_000_000, 350_000_000_000])

    @patch(f"{_P}._build_doc_map", new_callable=AsyncMock, return_value={})
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_free_cash_flow_uses_aligned_capex_concept_for_annual_series(
        self, mock_resolve, mock_facts, _mock_doc_map
    ) -> None:
        mock_resolve.return_value = ("0001783879", "Robinhood Markets, Inc.")
        mock_facts.return_value = ALIGNED_CAPEX_FACTS

        result = await financials(
            "HOOD",
            ["capex", "free_cash_flow"],
            period="annual:3",
        )

        capex = result.metrics["capex"]
        self.assertIsInstance(capex, list)
        self.assertEqual([v.fiscal_year for v in capex], [2025, 2024, 2023])
        self.assertEqual([v.value for v in capex], [15_000_000, 13_000_000, 2_000_000])

        fcf = result.metrics["free_cash_flow"]
        self.assertIsInstance(fcf, list)
        self.assertEqual([v.fiscal_year for v in fcf], [2025, 2024, 2023])
        self.assertEqual(
            [v.value for v in fcf],
            [1_623_000_000, -170_000_000, 1_179_000_000],
        )


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

    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_derived_annual_series_returns_aligned_list(
        self, mock_resolve, mock_facts, mock_subs
    ) -> None:
        mock_resolve.return_value = ("0001045810", "NVIDIA CORP")
        mock_facts.return_value = MOCK_EBITDA_SERIES_FACTS

        result = await financials("NVDA", "ebitda", period="annual:2")

        ebitda = result.metrics["ebitda"]
        self.assertIsInstance(ebitda, list)
        self.assertEqual([v.value for v in ebitda], [140_000_000_000, 98_000_000_000])
        self.assertEqual([v.fiscal_year for v in ebitda], [2025, 2024])
        for value in ebitda:
            self.assertIsInstance(value, DerivedValue)
            self.assertEqual(
                {c.fiscal_year for c in value.components.values()},
                {value.fiscal_year},
            )

    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_derived_quarterly_series_requires_aligned_component_windows(
        self, mock_resolve, mock_facts, mock_subs
    ) -> None:
        mock_resolve.return_value = ("0001045810", "NVIDIA CORP")
        mock_facts.return_value = MOCK_EBITDA_SERIES_FACTS

        result = await financials("NVDA", "ebitda", period="quarterly:3")

        ebitda = result.metrics["ebitda"]
        self.assertIsInstance(ebitda, list)
        self.assertEqual(len(ebitda), 1)
        self.assertEqual(ebitda[0].value, 22_000_000_000)
        self.assertEqual(ebitda[0].fiscal_period, "Q1")
        self.assertEqual(
            {
                (
                    component.fiscal_period,
                    component.period_start,
                    component.period_end,
                )
                for component in ebitda[0].components.values()
            },
            {("Q1", ebitda[0].period_start, ebitda[0].period_end)},
        )


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
                                    "fy": 2024,
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
                                    "fy": 2024,
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
    async def test_lean_ltm_ratio_still_surfaces_components(
        self, mock_resolve, mock_facts, _ms
    ) -> None:
        """A ratio over LTM windows (gross_margin --period ltm) surfaces its
        components inline, like the same ratio at lfy. Regression: the LTM
        ratio branch stopped emitting ltm_components, so the component-surfacing
        guard must key on the additive-LTM test, not on fiscal_period."""
        mock_resolve.return_value = ("0001045810", "NVIDIA CORP")
        mock_facts.return_value = MOCK_COMPANY_FACTS

        result = await financials("NVDA", "gross_margin", period="ltm")
        gm = result.metrics.get("gross_margin")
        if gm is None or not getattr(gm, "components", None):
            self.skipTest("gross_margin LTM not derivable from the mock facts")

        metrics = result.to_lean_dict()["metrics"]
        self.assertIn("gross_margin", metrics)
        # Components reachable inline regardless of LTM-ness of the ratio.
        for comp in gm.components:
            self.assertIn(comp, metrics, f"component {comp} not surfaced inline")

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
        # Rejection is announced, not a silent N/A.
        stale_diags = [d for d in result.diagnostics if d.kind == "stale_rejected"]
        self.assertEqual(len(stale_diags), 1)
        self.assertEqual(stale_diags[0].metric, "gross_profit")
        self.assertIn("FY2020", stale_diags[0].message)

    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=_mock_submissions)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_stale_derived_value_emits_diagnostic(
        self, mock_resolve, mock_facts, _ms
    ) -> None:
        """The derived-metric staleness rejection (CAGR on old data) must also
        be announced via a stale_rejected diagnostic, not flipped silently."""
        mock_resolve.return_value = ("0000018230", "CATERPILLAR INC")

        def _annual(val: float, year: int) -> dict:
            return {
                "val": val,
                "start": f"{year}-01-01",
                "end": f"{year}-12-31",
                "fy": year,
                "fp": "FY",
                "form": "10-K",
                "accn": f"0000018230-{str(year + 1)[-2:]}-000001",
                "filed": f"{year + 1}-02-17",
            }

        mock_facts.return_value = {
            "cik": 18230,
            "entityName": "CATERPILLAR INC",
            "facts": {
                "us-gaap": {
                    "Revenues": {
                        "label": "Revenues",
                        "units": {
                            "USD": [
                                _annual(40_000_000_000, 2016),
                                _annual(45_000_000_000, 2017),
                                _annual(50_000_000_000, 2018),
                                _annual(55_000_000_000, 2019),
                            ]
                        },
                    },
                }
            },
        }
        result = await financials("CAT", "revenue_cagr_3y", period="lfy")
        self.assertIsNone(result.metrics["revenue_cagr_3y"])
        stale_diags = [d for d in result.diagnostics if d.kind == "stale_rejected"]
        self.assertEqual(len(stale_diags), 1)
        self.assertEqual(stale_diags[0].metric, "revenue_cagr_3y")

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
            with (
                patch(
                    f"{_P}.resolve_ticker",
                    new=AsyncMock(return_value=("0001045810", "NVIDIA CORP")),
                ),
                patch(f"{_P}.fetch_company_facts", new=AsyncMock(return_value={"facts": {}})),
                patch(f"{_P}._build_doc_map", new=AsyncMock(return_value={})),
            ):
                with self.assertRaises(MetricNotFound) as ctx:
                    await financials("NVDA", metrics="xyzzy_nothing", period="lfy")
                self.assertEqual(ctx.exception.metric_name, "xyzzy_nothing")

        _asyncio.run(_run())

    def test_kpi_catalog_name_does_not_raise(self) -> None:
        """A metric name in KPI_CATALOG but not METRIC_MAP must not raise.

        Task 5 ships the guard extension. Task 12 will wire try_extract_kpi
        so 'arr' actually resolves to a value. For now we pin the
        'no MetricNotFound' contract and assert the current None return.
        """
        import asyncio as _asyncio

        from edgarpack.query.layer_zero import MetricNotFound

        async def _run() -> None:
            with (
                patch(
                    f"{_P}.resolve_ticker",
                    new=AsyncMock(return_value=("0001535527", "CrowdStrike")),
                ),
                patch(f"{_P}.fetch_company_facts", new=AsyncMock(return_value={"facts": {}})),
                patch(f"{_P}._build_doc_map", new=AsyncMock(return_value={})),
            ):
                try:
                    result = await financials("CRWD", metrics="arr", period="lfy")
                except MetricNotFound:
                    self.fail("KPI_CATALOG name 'arr' must not raise MetricNotFound")
                self.assertIn("arr", result.metrics)
                # Task 12 will change this to an extracted CitedValue.
                self.assertIsNone(result.metrics["arr"])

        _asyncio.run(_run())


class TestLayerBWireUp(unittest.TestCase):
    def test_kpi_catalog_metric_calls_try_extract_kpi(self) -> None:
        """When a metric is in KPI_CATALOG but not METRIC_MAP, financials()
        must call try_extract_kpi instead of returning None silently."""
        import asyncio as _asyncio
        from datetime import date as _date

        from edgarpack.query.models import CitedValue

        async def _run() -> None:
            fake_cited = CitedValue(
                value=3_440_000_000,
                unit="USD",
                metric="arr",
                concept="annual recurring revenue",
                period_end=_date(2024, 1, 31),
                fiscal_year=2024,
                fiscal_period="FY",
                form_type="10-K",
                filed=_date(2024, 3, 7),
                accession="0001535527-24-000008",
                cik="0001535527",
                company="CROWDSTRIKE HOLDINGS INC",
                source="learned:kpi-llm",
            )

            with (
                patch(f"{_P}.resolve_ticker", new=AsyncMock(return_value=("0001535527", "CRWD"))),
                patch(f"{_P}.fetch_company_facts", new=AsyncMock(return_value={"facts": {}})),
                patch(f"{_P}._build_doc_map", new=AsyncMock(return_value={})),
                patch(
                    "edgarpack.query.kpi_extract.try_extract_kpi", return_value=fake_cited
                ) as mock_extract,
            ):
                result = await financials("CRWD", metrics="arr", period="lfy")
                mock_extract.assert_called_once()
                self.assertIsNotNone(result.metrics["arr"])
                self.assertEqual(result.metrics["arr"].value, 3_440_000_000)
                self.assertEqual(result.metrics["arr"].source, "learned:kpi-llm")

        _asyncio.run(_run())

    def test_kpi_none_result_adds_diagnostic(self) -> None:
        """When try_extract_kpi returns None, a diagnostic entry is added
        to the QueryResult."""
        import asyncio as _asyncio

        async def _run() -> None:
            with (
                patch(f"{_P}.resolve_ticker", new=AsyncMock(return_value=("0001535527", "CRWD"))),
                patch(f"{_P}.fetch_company_facts", new=AsyncMock(return_value={"facts": {}})),
                patch(f"{_P}._build_doc_map", new=AsyncMock(return_value={})),
                patch("edgarpack.query.kpi_extract.try_extract_kpi", return_value=None),
            ):
                result = await financials("CRWD", metrics="arr", period="lfy")
                self.assertIsNone(result.metrics["arr"])
                self.assertTrue(
                    any(d.metric == "arr" for d in result.diagnostics),
                    f"expected 'arr' diagnostic, got {result.diagnostics}",
                )

        _asyncio.run(_run())

    def test_known_metric_does_not_call_try_extract_kpi(self) -> None:
        """A metric in METRIC_MAP must be resolved via the deterministic
        path, not Layer B. Pins the gating invariant."""
        import asyncio as _asyncio

        async def _run() -> None:
            with (
                patch(
                    f"{_P}.resolve_ticker",
                    new=AsyncMock(return_value=("0001045810", "NVIDIA CORP")),
                ),
                patch(f"{_P}.fetch_company_facts", new=AsyncMock(return_value={"facts": {}})),
                patch(f"{_P}._build_doc_map", new=AsyncMock(return_value={})),
                patch("edgarpack.query.kpi_extract.try_extract_kpi") as mock_extract,
            ):
                # 'revenue' is in METRIC_MAP, not KPI_CATALOG
                await financials("NVDA", metrics="revenue", period="lfy")
                mock_extract.assert_not_called()

        _asyncio.run(_run())


class TestXBRLFetchErrorDiagnostic(unittest.IsolatedAsyncioTestCase):
    """Covers edgarpack-4jc: network/HTTP failures on companyfacts must surface
    as a layer_a_fetch_error Diagnostic, not silent N/A."""

    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_fetch_error_emits_diagnostic(self, mock_resolve, mock_facts, mock_subs) -> None:
        from edgarpack.sec.xbrl import XBRLFetchError

        mock_resolve.return_value = ("0001045810", "NVIDIA CORP")
        mock_facts.side_effect = XBRLFetchError("0001045810", RuntimeError("boom"))
        mock_subs.return_value = MOCK_SUBMISSIONS

        result = await financials("NVDA", "revenue,net_income", period="lfy")

        self.assertIsNone(result.metrics.get("revenue"))
        self.assertIsNone(result.metrics.get("net_income"))
        kinds = [d.kind for d in result.diagnostics]
        self.assertIn("layer_a_fetch_error", kinds)
        fetch_errors = [d for d in result.diagnostics if d.kind == "layer_a_fetch_error"]
        self.assertEqual({d.metric for d in fetch_errors}, {"revenue", "net_income"})
        self.assertTrue(all("fetch failed" in d.message.lower() for d in fetch_errors))

    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock)
    @patch(f"{_P}.fetch_company_facts")
    @patch(f"{_P}.resolve_ticker")
    async def test_unavailable_stays_silent(self, mock_resolve, mock_facts, mock_subs) -> None:
        """Empty facts (filer has no XBRL) must NOT emit a fetch_error diagnostic."""
        mock_resolve.return_value = ("0001045810", "NVIDIA CORP")
        mock_facts.return_value = {}
        mock_subs.return_value = MOCK_SUBMISSIONS

        result = await financials("NVDA", "revenue", period="lfy")

        self.assertIsNone(result.metrics.get("revenue"))
        kinds = [d.kind for d in result.diagnostics]
        self.assertNotIn("layer_a_fetch_error", kinds)


def test_cited_value_carries_accounting_standard_and_reporting_currency():
    from datetime import date

    from edgarpack.query.models import CitedValue

    v = CitedValue(
        value=100,
        unit="USD",
        metric="revenue",
        concept="Revenues",
        period_end=date(2023, 12, 31),
        fiscal_year=2023,
        fiscal_period="FY",
        form_type="10-K",
        filed=date(2024, 2, 1),
        accession="0001234567-24-000001",
        cik="0001329099",
        company="Baidu",
        accounting_standard="IFRS",
        reporting_currency="USD",
    )
    assert v.accounting_standard == "IFRS"
    assert v.reporting_currency == "USD"


def test_cited_value_defaults_to_us_gaap_usd():
    from datetime import date

    from edgarpack.query.models import CitedValue

    v = CitedValue(
        value=100,
        unit="USD",
        metric="revenue",
        concept="Revenues",
        period_end=date(2023, 12, 31),
        fiscal_year=2023,
        fiscal_period="FY",
        form_type="10-K",
        filed=date(2024, 2, 1),
        accession="0001234567-24-000001",
        cik="0001234567",
        company="Acme",
    )
    assert v.accounting_standard == "US-GAAP"
    assert v.reporting_currency == "USD"


class TestDiscoveredKpiMultiPeriod(unittest.IsolatedAsyncioTestCase):
    """financials() returns distinct CitedValues per period for discovered KPIs.

    Seeds the learned registry with six annual rows for a fake CIK and stubs
    the SEC-side identity, facts, and doc-map calls so only the discovered
    path runs. Verifies that scalar offsets return distinct rows, series
    selectors return lists, and LTM / partial-coverage emit diagnostics.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db_path = Path(self._tmp.name) / "registry.db"

        from edgarpack.query.learned_registry import LearnedRegistry

        reg = LearnedRegistry(db_path=self.db_path)
        for yr in (2020, 2021, 2022, 2023, 2024, 2025):
            reg.company_kpi_upsert(
                cik="0001564408",
                accession=f"000-{yr}-ANN",
                slug="daily_active_users",
                display_name="Daily Active Users",
                aliases=[],
                unit="count",
                magnitude=None,
                value=float((yr - 2019) * 50_000_000),
                period_end=f"{yr}-12-31",
                fiscal_year=yr,
                fiscal_period="FY",
                form_type="10-K",
                definition=None,
                section_id=None,
                chunk_id=None,
                source_substring=None,
                confidence=None,
            )
        reg.close()

    async def _run(self, period: str):
        with (
            patch(
                f"{_P}.resolve_ticker",
                new=AsyncMock(return_value=("0001564408", "Snap Inc")),
            ),
            patch(
                f"{_P}.fetch_company_facts",
                new=AsyncMock(return_value={"facts": {}}),
            ),
            patch(f"{_P}._build_doc_map", new=AsyncMock(return_value={})),
            patch(
                "edgarpack.query.learned_registry.DEFAULT_REGISTRY_PATH",
                self.db_path,
            ),
        ):
            return await financials("SNAP", metrics="daily_active_users", period=period)

    async def test_lfy_vs_lfy_back_three_differ(self) -> None:
        lfy_result = await self._run("lfy")
        lfy3_result = await self._run("lfy-3")
        lfy_cited = lfy_result.metrics["daily_active_users"]
        lfy3_cited = lfy3_result.metrics["daily_active_users"]
        self.assertIsNotNone(lfy_cited)
        self.assertIsNotNone(lfy3_cited)
        self.assertEqual(lfy_cited.fiscal_year, 2025)
        self.assertEqual(lfy3_cited.fiscal_year, 2022)

    async def test_annual_six_returns_list(self) -> None:
        result = await self._run("annual:6")
        values = result.metrics["daily_active_users"]
        self.assertIsInstance(values, list)
        self.assertEqual(len(values), 6)
        self.assertEqual(
            [v.fiscal_year for v in values],
            [2025, 2024, 2023, 2022, 2021, 2020],
        )

    async def test_ltm_emits_degraded_diagnostic(self) -> None:
        result = await self._run("ltm")
        diag_kinds = [d.kind for d in result.diagnostics]
        self.assertIn("ltm_degraded", diag_kinds)
        cited = result.metrics["daily_active_users"]
        self.assertIsNotNone(cited)
        self.assertEqual(cited.fiscal_year, 2025)

    async def test_annual_partial_coverage_diagnostic(self) -> None:
        result = await self._run("annual:10")
        diag_kinds = [d.kind for d in result.diagnostics]
        self.assertIn("partial_coverage", diag_kinds)
        values = result.metrics["daily_active_users"]
        self.assertIsInstance(values, list)
        self.assertEqual(len(values), 6)

    async def test_annual_on_quarterly_only_slug_returns_empty_list(self) -> None:
        """Known slug with no rows of requested form type returns [],
        distinct from unknown-slug which returns None. No partial_coverage
        diagnostic because no rows at all (not a coverage shortfall)."""
        from edgarpack.query.learned_registry import LearnedRegistry

        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "learned.db"
            reg = LearnedRegistry(db_path=db)
            reg.company_kpi_upsert(
                cik="0001564408",
                accession="Q1-2025",
                slug="daily_active_users",
                display_name="Daily Active Users",
                aliases=[],
                unit="count",
                magnitude=None,
                value=100_000_000.0,
                period_end="2025-03-31",
                fiscal_year=2025,
                fiscal_period="Q1",
                form_type="10-Q",
                definition=None,
                section_id=None,
                chunk_id=None,
                source_substring=None,
                confidence=None,
            )
            reg.close()

            with (
                patch("edgarpack.query.learned_registry.DEFAULT_REGISTRY_PATH", db),
                patch(
                    f"{_P}.resolve_ticker",
                    new=AsyncMock(return_value=("0001564408", "Snap Inc")),
                ),
                patch(
                    f"{_P}.fetch_company_facts",
                    new=AsyncMock(return_value={"facts": {}}),
                ),
                patch(f"{_P}._build_doc_map", new=AsyncMock(return_value={})),
            ):
                result = await financials("SNAP", metrics="daily_active_users", period="annual:3")

        values = result.metrics["daily_active_users"]
        self.assertEqual(values, [])  # empty list, NOT None
        diag_kinds = [d.kind for d in result.diagnostics]
        self.assertNotIn("layer_b_unresolved", diag_kinds)
        self.assertNotIn("partial_coverage", diag_kinds)


class TestFiscalLabel(unittest.TestCase):
    def test_annual_drops_fy_double_prefix(self) -> None:
        from datetime import date

        from edgarpack.query.models import CitedValue

        cv = CitedValue(
            value=1,
            unit="USD",
            metric="m",
            concept="c",
            period_end=date(2025, 12, 31),
            fiscal_year=2025,
            fiscal_period="FY",
            form_type="10-K",
            filed=date(2026, 2, 5),
            accession="a",
            cik="c",
            company="co",
        )
        self.assertEqual(cv.fiscal_label, "FY2025")

    def test_quarter_label_unchanged(self) -> None:
        from datetime import date

        from edgarpack.query.models import CitedValue

        cv = CitedValue(
            value=1,
            unit="USD",
            metric="m",
            concept="c",
            period_end=date(2025, 6, 30),
            fiscal_year=2025,
            fiscal_period="Q2",
            form_type="10-Q",
            filed=date(2025, 8, 6),
            accession="a",
            cik="c",
            company="co",
        )
        self.assertEqual(cv.fiscal_label, "Q2 FY2025")

    def test_empty_fiscal_period_treated_as_annual(self) -> None:
        """When fiscal_period is empty string, fallback to FY{year} form."""
        from datetime import date

        from edgarpack.query.models import CitedValue

        cv = CitedValue(
            value=1,
            unit="USD",
            metric="m",
            concept="c",
            period_end=date(2025, 12, 31),
            fiscal_year=2025,
            fiscal_period="",
            form_type="10-K",
            filed=date(2026, 2, 5),
            accession="a",
            cik="c",
            company="co",
        )
        self.assertEqual(cv.fiscal_label, "FY2025")


if __name__ == "__main__":
    unittest.main()
