"""Tests for cross-company comparison queries."""

from __future__ import annotations

import json
import unittest
from unittest.mock import AsyncMock, patch

from edgarpack.query.comps import comps, comps_to_json, format_comps_table
from edgarpack.query.models import CitedValue, QueryResult

_P = "edgarpack.query.financials"

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

COMPS_SUBMISSIONS = {
    "0001045810": {
        "cik": 1045810,
        "name": "NVIDIA CORP",
        "filings": {
            "recent": {
                "accessionNumber": ["0001045810-25-000001"],
                "primaryDocument": ["nvda-20250126.htm"],
                "form": ["10-K"],
                "filingDate": ["2025-02-18"],
            }
        },
    },
    "0000002488": {
        "cik": 2488,
        "name": "ADVANCED MICRO DEVICES INC",
        "filings": {
            "recent": {
                "accessionNumber": ["0000002488-25-000001"],
                "primaryDocument": ["amd-20241228.htm"],
                "form": ["10-K"],
                "filingDate": ["2025-02-05"],
            }
        },
    },
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


async def mock_fetch_submissions(cik, force=False):
    empty = {
        "filings": {
            "recent": {
                "accessionNumber": [],
                "primaryDocument": [],
                "form": [],
                "filingDate": [],
            }
        }
    }
    return COMPS_SUBMISSIONS.get(cik, empty)


class TestComps(unittest.IsolatedAsyncioTestCase):
    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=mock_fetch_submissions)
    @patch(f"{_P}.fetch_company_facts", side_effect=mock_fetch_facts)
    @patch(f"{_P}.resolve_ticker", side_effect=mock_resolve_ticker)
    async def test_multi_company_parallel(self, mock_resolve, mock_facts, mock_subs) -> None:
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

    @patch(f"{_P}.fetch_submissions", new_callable=AsyncMock, side_effect=mock_fetch_submissions)
    @patch(f"{_P}.fetch_company_facts", side_effect=mock_fetch_facts)
    @patch(f"{_P}.resolve_ticker", side_effect=mock_resolve_ticker)
    async def test_failed_company_returns_empty(self, mock_resolve, mock_facts, mock_subs) -> None:
        # Make AMD fail
        async def _resolve_with_amd_failure(c: str, force: bool = False):
            if c.upper() == "AMD":
                raise ValueError("fail")
            return await mock_resolve_ticker(c, force)

        mock_resolve.side_effect = _resolve_with_amd_failure

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
        self.assertIn("Citations:", table)
        self.assertIn("[C1]", table)


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


class TestCurrencyFormatting(unittest.TestCase):
    def test_eur_formatting(self) -> None:
        from datetime import date

        from edgarpack.query.comps import _format_value

        cited = CitedValue(
            value=28_262_000_000,
            unit="EUR",
            metric="revenue",
            concept="Revenue",
            period_end=date(2024, 12, 31),
            fiscal_year=2024,
            fiscal_period="FY",
            form_type="20-F",
            filed=date(2025, 2, 15),
            accession="0000000001-25-000001",
            cik="0000000001",
            company="ASML HOLDING NV",
        )
        formatted = _format_value(cited)
        self.assertIn("\u20ac", formatted)
        self.assertIn("B", formatted)

    def test_gbp_formatting(self) -> None:
        from datetime import date

        from edgarpack.query.comps import _format_value

        cited = CitedValue(
            value=5_000_000_000,
            unit="GBP",
            metric="revenue",
            concept="Revenue",
            period_end=date(2024, 12, 31),
            fiscal_year=2024,
            fiscal_period="FY",
            form_type="20-F",
            filed=date(2025, 2, 15),
            accession="0000000001-25-000001",
            cik="0000000001",
            company="TEST CO",
        )
        formatted = _format_value(cited)
        self.assertIn("\u00a3", formatted)

    def test_unknown_currency_uses_prefix(self) -> None:
        from datetime import date

        from edgarpack.query.comps import _format_value

        cited = CitedValue(
            value=1_000_000_000,
            unit="CHF",
            metric="revenue",
            concept="Revenue",
            period_end=date(2024, 12, 31),
            fiscal_year=2024,
            fiscal_period="FY",
            form_type="20-F",
            filed=date(2025, 2, 15),
            accession="0000000001-25-000001",
            cik="0000000001",
            company="TEST CO",
        )
        formatted = _format_value(cited)
        self.assertIn("CHF", formatted)
        self.assertIn("B", formatted)

    def test_arpu_renders_with_two_decimals(self) -> None:
        from datetime import date

        from edgarpack.query.comps import _format_value

        cited = CitedValue(
            value=3.62,
            unit="USD",
            metric="average_revenue_per_user",
            concept="Average Revenue Per User",
            period_end=date(2025, 12, 31),
            fiscal_year=2025,
            fiscal_period="FY",
            form_type="10-K",
            filed=date(2026, 2, 5),
            accession="0001564408-26-000013",
            cik="0001564408",
            company="Snap Inc",
        )
        self.assertEqual(_format_value(cited), "$3.62")

    def test_count_unit_renders_474m(self) -> None:
        from datetime import date

        from edgarpack.query.comps import _format_value

        cited = CitedValue(
            value=474_000_000,
            unit="count",
            metric="daily_active_users",
            concept="Daily Active Users",
            period_end=date(2025, 12, 31),
            fiscal_year=2025,
            fiscal_period="FY",
            form_type="10-K",
            filed=date(2026, 2, 5),
            accession="0001564408-26-000013",
            cik="0001564408",
            company="Snap Inc",
        )
        self.assertEqual(_format_value(cited), "474M")

    def test_negative_currency_uses_parens(self) -> None:
        from datetime import date

        from edgarpack.query.comps import _format_value

        cited = CitedValue(
            value=-532_000_000,
            unit="USD",
            metric="operating_income",
            concept="OperatingIncomeLoss",
            period_end=date(2025, 12, 31),
            fiscal_year=2025,
            fiscal_period="FY",
            form_type="10-K",
            filed=date(2026, 2, 5),
            accession="0001564408-26-000013",
            cik="0001564408",
            company="Snap Inc",
        )
        self.assertEqual(_format_value(cited), "($532M)")

    def test_empty_unit_does_not_route_to_percent(self) -> None:
        """Empty unit preserves the pre-refactor fallback (plain 2-decimal),
        not percent formatting."""
        from datetime import date

        from edgarpack.query.comps import _format_value

        cited = CitedValue(
            value=12.5,
            unit="",
            metric="unknown",
            concept="Unknown",
            period_end=date(2025, 12, 31),
            fiscal_year=2025,
            fiscal_period="FY",
            form_type="10-K",
            filed=date(2026, 2, 5),
            accession="a",
            cik="c",
            company="co",
        )
        self.assertEqual(_format_value(cited), "12.50")


class TestCompsLeanJson(unittest.TestCase):
    def test_lean_json_structure(self) -> None:
        from datetime import date

        from edgarpack.query.comps import comps_to_lean_json

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
                period="lfy",
                metrics={"revenue": cited},
            ),
        }

        json_str = comps_to_lean_json(results, ["revenue"], "lfy")
        parsed = json.loads(json_str)
        self.assertIn("period", parsed)
        self.assertIn("requested_metrics", parsed)
        self.assertIn("companies", parsed)
        self.assertIn("NVDA", parsed["companies"])
        nvda = parsed["companies"]["NVDA"]
        self.assertIn("filings", nvda)
        self.assertIn("metrics", nvda)


class TestPermalinkDisplayToken(unittest.TestCase):
    def test_build_permalink_uses_display_token(self) -> None:
        from edgarpack.query.comps import _build_permalink

        link = _build_permalink(
            cik="0001564408",
            company="Snap Inc",
            metrics=["revenue"],
            periods=["lfy"],
            display_token="snap",
        )
        self.assertEqual(link, "edgarpack query snap revenue --period lfy")

    def test_build_permalink_falls_back_to_cik(self) -> None:
        from edgarpack.query.comps import _build_permalink

        link = _build_permalink(
            cik="0001564408",
            company="Snap Inc",
            metrics=["revenue"],
            periods=["lfy"],
            display_token=None,
        )
        self.assertEqual(link, "edgarpack query 0001564408 revenue --period lfy")

    def test_build_permalink_falls_back_to_company_when_cik_empty(self) -> None:
        from edgarpack.query.comps import _build_permalink

        link = _build_permalink(
            cik="",
            company="Snap Inc",
            metrics=["revenue"],
            periods=["lfy"],
            display_token=None,
        )
        self.assertEqual(link, "edgarpack query Snap Inc revenue --period lfy")


class TestQueryResultPermalinkDisplayToken(unittest.TestCase):
    def test_permalink_prefers_display_token(self) -> None:
        from edgarpack.query.models import QueryResult

        qr = QueryResult(
            company="Snap Inc",
            cik="0001564408",
            period="lfy",
            metrics={"revenue": None},
            display_token="snap",
        )
        self.assertEqual(
            qr.permalink,
            "edgarpack query snap revenue --period lfy",
        )

    def test_permalink_falls_back_to_cik(self) -> None:
        from edgarpack.query.models import QueryResult

        qr = QueryResult(
            company="Snap Inc",
            cik="0001564408",
            period="lfy",
            metrics={"revenue": None},
        )
        self.assertEqual(
            qr.permalink,
            "edgarpack query 0001564408 revenue --period lfy",
        )


if __name__ == "__main__":
    unittest.main()
