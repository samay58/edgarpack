"""Tests for cross-company comparison queries."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from edgarpack.query.comps import comps, comps_to_json, format_comps_table
from edgarpack.query.models import CitedValue, QueryResult

# Minimal mock data for two companies
NVDA_FACTS = {
    "cik": 1045810,
    "entityName": "NVIDIA CORP",
    "facts": {
        "us-gaap": {
            "Revenues": {
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
                    ]
                }
            },
            "NetIncomeLoss": {
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
                }
            },
        }
    },
}

AMD_FACTS = {
    "cik": 2488,
    "entityName": "ADVANCED MICRO DEVICES INC",
    "facts": {
        "us-gaap": {
            "Revenues": {
                "units": {
                    "USD": [
                        {
                            "val": 22_680_000_000,
                            "start": "2024-01-01",
                            "end": "2024-12-28",
                            "fy": 2024,
                            "fp": "FY",
                            "form": "10-K",
                            "accn": "0000002488-25-000001",
                            "filed": "2025-02-05",
                        },
                    ]
                }
            },
            "NetIncomeLoss": {
                "units": {
                    "USD": [
                        {
                            "val": 1_641_000_000,
                            "start": "2024-01-01",
                            "end": "2024-12-28",
                            "fy": 2024,
                            "fp": "FY",
                            "form": "10-K",
                            "accn": "0000002488-25-000001",
                            "filed": "2025-02-05",
                        },
                    ]
                }
            },
        }
    },
}

TICKER_MAP = {
    "NVDA": ("0001045810", "NVIDIA CORP"),
    "AMD": ("0000002488", "ADVANCED MICRO DEVICES INC"),
}


async def mock_resolve_ticker(company, force=False):
    key = company.upper()
    if key in TICKER_MAP:
        return TICKER_MAP[key]
    raise ValueError(f"Unknown: {company}")


async def mock_fetch_facts(cik, force=False):
    if cik == "0001045810":
        return NVDA_FACTS
    elif cik == "0000002488":
        return AMD_FACTS
    return {}


class TestComps(unittest.IsolatedAsyncioTestCase):
    @patch("edgarpack.query.financials.fetch_company_facts", side_effect=mock_fetch_facts)
    @patch("edgarpack.query.financials.resolve_ticker", side_effect=mock_resolve_ticker)
    async def test_multi_company_parallel(self, mock_resolve, mock_facts) -> None:
        results = await comps(
            companies=["NVDA", "AMD"],
            metrics=["revenue", "net_income"],
            period="lfy",
        )

        self.assertIn("NVDA", results)
        self.assertIn("AMD", results)

        nvda = results["NVDA"]
        self.assertEqual(nvda.company, "NVIDIA CORP")
        self.assertIsNotNone(nvda.metrics["revenue"])
        self.assertEqual(nvda.metrics["revenue"].value, 60_922_000_000)

        amd = results["AMD"]
        self.assertEqual(amd.company, "ADVANCED MICRO DEVICES INC")
        self.assertIsNotNone(amd.metrics["revenue"])
        self.assertEqual(amd.metrics["revenue"].value, 22_680_000_000)

    @patch("edgarpack.query.financials.fetch_company_facts", side_effect=mock_fetch_facts)
    @patch("edgarpack.query.financials.resolve_ticker", side_effect=mock_resolve_ticker)
    async def test_failed_company_returns_empty(self, mock_resolve, mock_facts) -> None:
        # Make AMD fail
        mock_resolve.side_effect = lambda c, force=False: (
            mock_resolve_ticker(c, force)
            if c.upper() != "AMD"
            else (_ for _ in ()).throw(ValueError("fail"))
        )

        results = await comps(
            companies=["NVDA", "AMD"],
            metrics=["revenue"],
            period="lfy",
        )

        self.assertIn("NVDA", results)
        self.assertIn("AMD", results)
        self.assertIsNone(results["AMD"].metrics["revenue"])


class TestFormatCompsTable(unittest.TestCase):
    def test_table_formatting(self) -> None:
        from datetime import date

        cited = CitedValue(
            value=60_922_000_000,
            unit="USD",
            metric="revenue",
            concept="Revenues",
            period_end=date(2025, 1, 26),
            fiscal_year=2025,
            fiscal_period="FY",
            form_type="10-K",
            filed=date(2025, 2, 18),
            accession="0001045810-25-000001",
            cik="0001045810",
            company="NVIDIA CORP",
        )

        results = {
            "NVDA": QueryResult(
                company="NVIDIA CORP",
                cik="0001045810",
                metrics={"revenue": cited},
            ),
        }

        table = format_comps_table(results, ["revenue"])
        self.assertIn("NVIDIA CORP", table)
        self.assertIn("Revenue", table)
        self.assertIn("Sources:", table)


class TestCompsToJson(unittest.TestCase):
    def test_json_output_valid(self) -> None:
        from datetime import date

        cited = CitedValue(
            value=60_922_000_000,
            unit="USD",
            metric="revenue",
            concept="Revenues",
            period_end=date(2025, 1, 26),
            fiscal_year=2025,
            fiscal_period="FY",
            form_type="10-K",
            filed=date(2025, 2, 18),
            accession="0001045810-25-000001",
            cik="0001045810",
            company="NVIDIA CORP",
        )

        results = {
            "NVDA": QueryResult(
                company="NVIDIA CORP",
                cik="0001045810",
                metrics={"revenue": cited},
            ),
        }

        json_str = comps_to_json(results)
        parsed = json.loads(json_str)
        self.assertIn("NVDA", parsed)
        self.assertIn("revenue", parsed["NVDA"]["metrics"])
        self.assertIn("citation", parsed["NVDA"]["metrics"]["revenue"])


if __name__ == "__main__":
    unittest.main()
