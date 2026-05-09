"""End-to-end integration: edgarpack query on an S-1 filer returns snapshot
values labeled as s1_snapshot. 10-K rows win for overlapping periods."""

from __future__ import annotations

import importlib
import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from edgarpack.query.financials import financials
from edgarpack.query.models import DerivedValue, QueryResult
from edgarpack.query.s1_financials import (
    SCHEMA_VERSION,
    default_registration_query_metrics,
    source_sha256_for_pack,
)

# Ensure the real module object is cached before any test runs
importlib.import_module("edgarpack.query.financials")


def _seed_s1_pack(
    packs_root: Path,
    cik: str = "0002021728",
    accession: str = "0001628280-24-041596",
    *,
    revenue_cents: int = 7828700000,
    filing_date: str = "2024-09-30",
    fiscal_year: int = 2024,
    period_end: str = "2024-12-31",
    is_pro_forma: bool = False,
    extra_metric: str | None = None,
    extra_cents: int = 0,
    extra_facts: list[dict[str, object]] | None = None,
) -> None:
    pack = packs_root / cik / accession
    pack.mkdir(parents=True, exist_ok=True)
    (pack / "manifest.json").write_text(
        json.dumps(
            {
                "filing": {
                    "accession": accession,
                    "form_type": "S-1",
                    "filing_date": filing_date,
                    "cik": cik,
                    "company_name": "Cerebras Systems Inc",
                }
            }
        )
    )
    (pack / "filing.full.md").write_text(
        "# Selected Financial Data\n\nRevenue 78,287\n", encoding="utf-8"
    )
    facts = [
        {
            "accession": accession,
            "fiscal_year": fiscal_year,
            "period_end": period_end,
            "metric": "revenue",
            "value_cents": revenue_cents,
            "currency": "USD",
            "is_audited": not is_pro_forma,
            "is_pro_forma": is_pro_forma,
            "pro_forma_note": ("assumes IPO price $32.50" if is_pro_forma else None),
        }
    ]
    if extra_metric:
        facts.append(
            {
                "accession": accession,
                "fiscal_year": fiscal_year,
                "period_end": period_end,
                "metric": extra_metric,
                "value_cents": extra_cents,
                "currency": "USD",
                "is_audited": True,
                "is_pro_forma": False,
                "pro_forma_note": None,
            }
        )
    facts.extend(extra_facts or [])
    (pack / "s1_financials.json").write_text(
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "accession": accession,
                "extracted_at": "2026-04-22T00:00:00Z",
                "extraction_status": "ok",
                "source_sha256": source_sha256_for_pack(pack),
                "model": "claude-haiku-4-5-20251001",
                "facts": facts,
            }
        )
    )


def _write_s1_pack_without_snapshot(
    packs_root: Path,
    *,
    cik: str = "0002021728",
    accession: str,
    filing_date: str,
    markdown: str,
) -> Path:
    pack = packs_root / cik / accession
    pack.mkdir(parents=True, exist_ok=True)
    (pack / "manifest.json").write_text(
        json.dumps(
            {
                "filing": {
                    "accession": accession,
                    "form_type": "S-1",
                    "filing_date": filing_date,
                    "cik": cik,
                    "company_name": "Cerebras Systems Inc",
                }
            }
        )
    )
    (pack / "filing.full.md").write_text(markdown, encoding="utf-8")
    return pack


@pytest.mark.asyncio
async def test_financials_returns_s1_snapshot_when_periodic_empty(tmp_path):
    _seed_s1_pack(tmp_path)

    import sys

    fin_module = sys.modules["edgarpack.query.financials"]

    async def fake_fetch(cik, force=False):  # noqa: ARG001
        return {"facts": {}}

    async def fake_resolve_ticker(company, force=False):  # noqa: ARG001
        from edgarpack.errors import UnknownCompany

        raise UnknownCompany("not in map")

    async def fake_resolve_by_name(name):  # noqa: ARG001
        return "0002021728", "Cerebras Systems Inc."

    with patch.object(fin_module, "fetch_company_facts", side_effect=fake_fetch):
        with patch.object(fin_module, "resolve_ticker", side_effect=fake_resolve_ticker):
            with patch(
                "edgarpack.sec.tickers.resolve_company_by_name",
                side_effect=fake_resolve_by_name,
            ):
                result = await financials(
                    company="Cerebras Systems",
                    metrics=["revenue"],
                    period="lfy",
                    pack_root=tmp_path,
                )

    assert isinstance(result, QueryResult)
    row = result.metrics.get("revenue")
    assert row is not None
    assert row.source == "s1_snapshot"
    assert row.form_type == "S-1"
    assert row.accession == "0001628280-24-041596"
    assert row.filed == date(2024, 9, 30)
    assert row.value == 78287000.0


@pytest.mark.asyncio
async def test_financials_uses_registration_defaults_when_metrics_omitted(tmp_path):
    _seed_s1_pack(
        tmp_path,
        accession="0001628280-26-032523",
        revenue_cents=88_671_900_000,
        filing_date="2026-05-08",
        fiscal_year=2025,
        period_end="2025-12-31",
        extra_facts=[
            {
                "accession": "0001628280-26-032523",
                "fiscal_year": 2025,
                "period_end": "2025-12-31",
                "metric": "adjusted_ebitda",
                "value_cents": 21_810_000_000,
                "currency": "USD",
                "is_audited": True,
                "is_pro_forma": False,
                "pro_forma_note": None,
                "source_text": "Adjusted EBITDA was $218.1 million.",
            }
        ],
    )

    import sys

    fin_module = sys.modules["edgarpack.query.financials"]

    async def fake_fetch(cik, force=False):  # noqa: ARG001
        return {"facts": {}}

    async def fake_resolve_ticker(company, force=False):  # noqa: ARG001
        from edgarpack.errors import UnknownCompany

        raise UnknownCompany("not in map")

    async def fake_resolve_by_name(name):  # noqa: ARG001
        return "0002021728", "Cerebras Systems Inc."

    with patch.object(fin_module, "fetch_company_facts", side_effect=fake_fetch):
        with patch.object(fin_module, "resolve_ticker", side_effect=fake_resolve_ticker):
            with patch(
                "edgarpack.sec.tickers.resolve_company_by_name",
                side_effect=fake_resolve_by_name,
            ):
                result = await financials(
                    company="Cerebras Systems",
                    metrics=None,
                    period="lfy",
                    pack_root=tmp_path,
                )

    assert list(result.metrics) == default_registration_query_metrics()
    assert "cost_of_revenue" not in result.metrics
    assert result.metrics["revenue"] is not None
    assert result.metrics["adjusted_ebitda"] is not None
    assert result.metrics["adjusted_ebitda"].source == "s1_snapshot"


@pytest.mark.asyncio
async def test_financials_maps_public_net_income_to_s1_net_income_loss(tmp_path):
    _seed_s1_pack(
        tmp_path,
        accession="0001628280-26-025762",
        revenue_cents=50_999_100_000,
        filing_date="2026-04-17",
        fiscal_year=2025,
        period_end="2025-12-31",
        extra_facts=[
            {
                "accession": "0001628280-26-025762",
                "fiscal_year": 2025,
                "period_end": "2025-12-31",
                "metric": "net_income_loss",
                "value_cents": 23_782_700_000,
                "currency": "USD",
                "is_audited": True,
                "is_pro_forma": False,
                "pro_forma_note": None,
            }
        ],
    )

    import sys

    fin_module = sys.modules["edgarpack.query.financials"]

    async def fake_fetch(cik, force=False):  # noqa: ARG001
        return {"facts": {}}

    async def fake_resolve_ticker(company, force=False):  # noqa: ARG001
        return "0002021728", "Cerebras Systems Inc."

    with patch.object(fin_module, "fetch_company_facts", side_effect=fake_fetch):
        with patch.object(fin_module, "resolve_ticker", side_effect=fake_resolve_ticker):
            result = await financials(
                company="CRBS",
                metrics=["net_income"],
                period="lfy",
                pack_root=tmp_path,
            )

    row = result.metrics.get("net_income")
    assert row is not None
    assert row.metric == "net_income"
    assert row.concept == "NetIncomeLoss"
    assert row.value == 237827000.0
    assert row.source == "s1_snapshot"


@pytest.mark.asyncio
async def test_financials_accepts_capital_expenditures_alias_for_s1_capex(tmp_path):
    _seed_s1_pack(
        tmp_path,
        accession="0001628280-26-025762",
        revenue_cents=50_999_100_000,
        filing_date="2026-04-17",
        fiscal_year=2025,
        period_end="2025-12-31",
        extra_facts=[
            {
                "accession": "0001628280-26-025762",
                "fiscal_year": 2025,
                "period_end": "2025-12-31",
                "metric": "capex",
                "value_cents": 38_273_900_000,
                "currency": "USD",
                "is_audited": True,
                "is_pro_forma": False,
                "pro_forma_note": None,
            }
        ],
    )

    import sys

    fin_module = sys.modules["edgarpack.query.financials"]

    async def fake_fetch(cik, force=False):  # noqa: ARG001
        return {"facts": {}}

    async def fake_resolve_ticker(company, force=False):  # noqa: ARG001
        return "0002021728", "Cerebras Systems Inc."

    with patch.object(fin_module, "fetch_company_facts", side_effect=fake_fetch):
        with patch.object(fin_module, "resolve_ticker", side_effect=fake_resolve_ticker):
            result = await financials(
                company="CRBS",
                metrics=["capital_expenditures"],
                period="lfy",
                pack_root=tmp_path,
            )

    row = result.metrics.get("capex")
    assert row is not None
    assert row.metric == "capex"
    assert row.concept == "PaymentsToAcquirePropertyPlantAndEquipment"
    assert row.value == 382739000.0


@pytest.mark.asyncio
async def test_financials_computes_s1_free_cash_flow_from_components(tmp_path):
    _seed_s1_pack(
        tmp_path,
        accession="0001628280-26-025762",
        revenue_cents=50_999_100_000,
        filing_date="2026-04-17",
        fiscal_year=2025,
        period_end="2025-12-31",
        extra_facts=[
            {
                "accession": "0001628280-26-025762",
                "fiscal_year": 2025,
                "period_end": "2025-12-31",
                "metric": "operating_cash_flow",
                "value_cents": -1_005_000_000,
                "currency": "USD",
                "is_audited": True,
                "is_pro_forma": False,
                "pro_forma_note": None,
            },
            {
                "accession": "0001628280-26-025762",
                "fiscal_year": 2025,
                "period_end": "2025-12-31",
                "metric": "capex",
                "value_cents": 38_273_900_000,
                "currency": "USD",
                "is_audited": True,
                "is_pro_forma": False,
                "pro_forma_note": None,
            },
        ],
    )

    import sys

    fin_module = sys.modules["edgarpack.query.financials"]

    async def fake_fetch(cik, force=False):  # noqa: ARG001
        return {"facts": {}}

    async def fake_resolve_ticker(company, force=False):  # noqa: ARG001
        return "0002021728", "Cerebras Systems Inc."

    with patch.object(fin_module, "fetch_company_facts", side_effect=fake_fetch):
        with patch.object(fin_module, "resolve_ticker", side_effect=fake_resolve_ticker):
            result = await financials(
                company="CRBS",
                metrics=["free_cash_flow"],
                period="lfy",
                pack_root=tmp_path,
            )

    row = result.metrics.get("free_cash_flow")
    assert isinstance(row, DerivedValue)
    assert row.source == "s1_snapshot"
    assert row.value == -392789000.0
    assert set(row.components) == {"operating_cash_flow", "capex"}


@pytest.mark.asyncio
async def test_financials_prefers_10k_over_s1_for_overlapping_period(tmp_path):
    _seed_s1_pack(tmp_path, revenue_cents=7828700000)

    import sys

    fin_module = sys.modules["edgarpack.query.financials"]

    async def fake_fetch(cik, force=False):  # noqa: ARG001
        return {
            "facts": {
                "us-gaap": {
                    "Revenues": {
                        "units": {
                            "USD": [
                                {
                                    "val": 80000000,
                                    "form": "10-K",
                                    "fy": 2024,
                                    "fp": "FY",
                                    "start": "2024-01-01",
                                    "end": "2024-12-31",
                                    "filed": "2025-02-01",
                                    "accn": "0002021728-25-000001",
                                }
                            ]
                        }
                    }
                }
            }
        }

    async def fake_resolve_ticker(company, force=False):  # noqa: ARG001
        return "0002021728", "Cerebras Systems Inc."

    with patch.object(fin_module, "fetch_company_facts", side_effect=fake_fetch):
        with patch.object(fin_module, "resolve_ticker", side_effect=fake_resolve_ticker):
            result = await financials(
                company="CRBS",
                metrics=["revenue"],
                period="lfy",
                pack_root=tmp_path,
            )

    row = result.metrics.get("revenue")
    assert row is not None
    assert row.source != "s1_snapshot"
    assert row.value == 80000000


@pytest.mark.asyncio
async def test_financials_pro_forma_period_returns_pro_forma_row_only(tmp_path):
    _seed_s1_pack(tmp_path, extra_metric="cash_and_equivalents", extra_cents=20991200000)
    pack = tmp_path / "0002021728" / "0001628280-24-041596"
    cache = json.loads((pack / "s1_financials.json").read_text())
    cache["facts"].append(
        {
            "accession": "0001628280-24-041596",
            "fiscal_year": 2024,
            "period_end": "2024-12-31",
            "metric": "cash_and_equivalents",
            "value_cents": 110341200000,
            "currency": "USD",
            "is_audited": False,
            "is_pro_forma": True,
            "pro_forma_note": "assumes IPO price $32.50, midpoint",
        }
    )
    (pack / "s1_financials.json").write_text(json.dumps(cache))

    import sys

    fin_module = sys.modules["edgarpack.query.financials"]

    async def fake_fetch(cik, force=False):  # noqa: ARG001
        return {"facts": {}}

    async def fake_resolve_ticker(company, force=False):  # noqa: ARG001
        return "0002021728", "Cerebras Systems Inc."

    with patch.object(fin_module, "fetch_company_facts", side_effect=fake_fetch):
        with patch.object(fin_module, "resolve_ticker", side_effect=fake_resolve_ticker):
            result = await financials(
                company="CRBS",
                metrics=["cash_and_equivalents"],
                period="pro-forma",
                pack_root=tmp_path,
            )

    row = result.metrics.get("cash_and_equivalents")
    assert row is not None
    assert row.is_pro_forma is True
    assert row.pro_forma_note == "assumes IPO price $32.50, midpoint"
    assert row.source == "s1_pro_forma"


@pytest.mark.asyncio
async def test_financials_extracts_newest_s1_before_using_old_cached_snapshot(
    tmp_path, monkeypatch
):
    _seed_s1_pack(
        tmp_path,
        accession="0001628280-24-041596",
        revenue_cents=7874400000,
        filing_date="2024-09-30",
        fiscal_year=2023,
        period_end="2023-12-31",
    )
    _write_s1_pack_without_snapshot(
        tmp_path,
        accession="0001628280-26-025762",
        filing_date="2026-04-17",
        markdown=(
            "Summary Consolidated Financial Data\n\n"
            "> 2025 / 2024\n"
            "> (in thousands, except per share amounts) / "
            "(in thousands, except per share amounts)\n"
            "> Total revenue ... $509,991 / $290,252\n"
        ),
    )

    async def should_not_call_llm(_section):
        raise AssertionError("latest Cerebras summary table should parse deterministically")

    monkeypatch.setattr("edgarpack.query.s1_financials._call_haiku_extract", should_not_call_llm)

    import sys

    fin_module = sys.modules["edgarpack.query.financials"]

    async def fake_fetch(cik, force=False):  # noqa: ARG001
        return {"facts": {}}

    async def fake_resolve_ticker(company, force=False):  # noqa: ARG001
        return "0002021728", "Cerebras Systems Inc."

    with patch.object(fin_module, "fetch_company_facts", side_effect=fake_fetch):
        with patch.object(fin_module, "resolve_ticker", side_effect=fake_resolve_ticker):
            result = await financials(
                company="CRBS",
                metrics=["revenue"],
                period="lfy",
                pack_root=tmp_path,
            )

    row = result.metrics.get("revenue")
    assert row is not None
    assert row.accession == "0001628280-26-025762"
    assert row.fiscal_year == 2025
    assert row.filed == date(2026, 4, 17)
    assert row.value == 509991000.0


@pytest.mark.asyncio
async def test_financials_does_not_fallback_to_old_s1_when_newest_snapshot_empty(tmp_path):
    _seed_s1_pack(
        tmp_path,
        accession="0001628280-24-041596",
        revenue_cents=7874400000,
        filing_date="2024-09-30",
        fiscal_year=2023,
        period_end="2023-12-31",
    )
    _write_s1_pack_without_snapshot(
        tmp_path,
        accession="0001628280-26-025762",
        filing_date="2026-04-17",
        markdown="# Risk Factors\n\nNo financial table here.",
    )

    import sys

    fin_module = sys.modules["edgarpack.query.financials"]

    async def fake_fetch(cik, force=False):  # noqa: ARG001
        return {"facts": {}}

    async def fake_resolve_ticker(company, force=False):  # noqa: ARG001
        return "0002021728", "Cerebras Systems Inc."

    with patch.object(fin_module, "fetch_company_facts", side_effect=fake_fetch):
        with patch.object(fin_module, "resolve_ticker", side_effect=fake_resolve_ticker):
            result = await financials(
                company="CRBS",
                metrics=["revenue"],
                period="lfy",
                pack_root=tmp_path,
            )

    assert result.metrics.get("revenue") is None
