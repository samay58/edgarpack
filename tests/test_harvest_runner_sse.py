"""Tests for the SSE (A-share) lane of the harvest runner."""

from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from edgarpack.china.acquire import CninfoAnnualReportRef
from edgarpack.harvest.planner import HarvestItem, HarvestPlan
from edgarpack.harvest.registry import PackRegistry
from edgarpack.harvest.runner import run_harvest
from edgarpack.pack.build import PackResult

_STOCK_CODE = "688696"
_COMPANY_NAME = "Chengdu XGIMI Technology Co., Ltd."


def _sse_item(stock_code: str = _STOCK_CODE, ticker: str | None = None) -> HarvestItem:
    return HarvestItem(
        cik=None,
        ticker=ticker or stock_code,
        company_name=_COMPANY_NAME,
        accession=None,
        form_type="ANNUAL-REPORT",
        filing_date="",
        primary_document=None,
        already_built=False,
        market="SSE",
        stock_code=stock_code,
    )


def _plan(items: list[HarvestItem]) -> HarvestPlan:
    return HarvestPlan(
        items=items,
        skipped=[],
        errors=[],
        total_filings=len(items),
        new_filings=len(items),
        already_built=0,
    )


def _selected(filing_date: date = date(2026, 3, 20)) -> CninfoAnnualReportRef:
    return CninfoAnnualReportRef(
        stock_code=_STOCK_CODE,
        company_name=_COMPANY_NAME,
        title="2025 Annual Report",
        filing_date=filing_date,
        source_url="https://static.cninfo.com.cn/report.pdf",
    )


def _pack_result(out_dir: Path) -> PackResult:
    pack_dir = out_dir / _STOCK_CODE / "2026-annual"
    pack_dir.mkdir(parents=True, exist_ok=True)
    return PackResult(
        output_dir=pack_dir,
        filing_meta={"company_name": _COMPANY_NAME},
        sections_count=12,
        tokens_total=45000,
        warnings=[],
        artifacts=[],
    )


@pytest.mark.asyncio
async def test_sse_happy_path_registers_market_and_stock_code(tmp_path):
    registry = PackRegistry(tmp_path / "registry.db")
    plan = _plan([_sse_item()])

    with patch(
        "edgarpack.harvest.runner.find_latest_annual_report",
        return_value=_selected(),
    ):
        with patch(
            "edgarpack.harvest.runner.build_sse_pack",
            new=AsyncMock(return_value=_pack_result(tmp_path / "packs")),
        ):
            summary = await run_harvest(plan, out_dir=tmp_path / "packs", registry=registry)

    assert summary["built"] == 1
    assert summary["failed"] == 0

    records = registry.list_packs(limit=None)
    assert len(records) == 1
    assert records[0].market == "SSE"
    assert records[0].stock_code == _STOCK_CODE
    assert records[0].filing_date == "2026-03-20"
    assert records[0].cik != ""

    registry.close()


@pytest.mark.asyncio
async def test_sse_cninfo_lookup_error_logs_and_continues(tmp_path):
    registry = PackRegistry(tmp_path / "registry.db")
    bad_item = _sse_item(stock_code="000001")
    good_item = _sse_item(stock_code=_STOCK_CODE)
    plan = _plan([bad_item, good_item])

    def fake_find(stock_code: str) -> CninfoAnnualReportRef:
        if stock_code == "000001":
            raise LookupError("No full annual report found on CNINFO for 000001")
        return _selected()

    with patch(
        "edgarpack.harvest.runner.find_latest_annual_report",
        side_effect=fake_find,
    ):
        with patch(
            "edgarpack.harvest.runner.build_sse_pack",
            new=AsyncMock(return_value=_pack_result(tmp_path / "packs")),
        ):
            summary = await run_harvest(plan, out_dir=tmp_path / "packs", registry=registry)

    # The bad filer fails but the good one still builds: a single CNINFO
    # LookupError must not abort the rest of the SSE lane.
    assert summary["built"] == 1
    assert summary["failed"] == 1

    errors = registry.get_errors(limit=10)
    assert any(e["ticker"] == "000001" for e in errors)
    assert any("No full annual report" in e["error"] for e in errors)

    registry.close()


@pytest.mark.asyncio
async def test_sse_already_registered_filing_date_is_skipped_without_build(tmp_path):
    registry = PackRegistry(tmp_path / "registry.db")
    registry.register(
        accession=f"SSE:{_STOCK_CODE}:2026-03-20",
        cik=f"SSE:{_STOCK_CODE}",
        ticker=_STOCK_CODE,
        company_name=_COMPANY_NAME,
        form_type="ANNUAL-REPORT",
        filing_date="2026-03-20",
        sections_count=12,
        tokens_total=45000,
        pack_dir=str(tmp_path / "packs" / _STOCK_CODE / "existing"),
        market="SSE",
        stock_code=_STOCK_CODE,
    )

    plan = _plan([_sse_item()])
    build_mock = AsyncMock()

    with patch(
        "edgarpack.harvest.runner.find_latest_annual_report",
        return_value=_selected(),
    ):
        with patch("edgarpack.harvest.runner.build_sse_pack", new=build_mock):
            summary = await run_harvest(plan, out_dir=tmp_path / "packs", registry=registry)

    build_mock.assert_not_called()
    assert summary["built"] == 0
    assert summary["skipped"] == 1

    registry.close()
