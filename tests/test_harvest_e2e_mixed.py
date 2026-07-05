"""End-to-end mocked harvest over a universe with one SEC and one SSE filer."""

from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from edgarpack.china.acquire import CninfoAnnualReportRef
from edgarpack.harvest.planner import plan_harvest
from edgarpack.harvest.registry import PackRegistry
from edgarpack.harvest.runner import run_harvest
from edgarpack.harvest.universe import CompanySpec, UniverseConfig
from edgarpack.pack.build import PackResult
from edgarpack.sec.submissions import FilingMeta


def _sec_filing() -> FilingMeta:
    return FilingMeta(
        cik="0001045810",
        accession="0001045810-25-000042",
        form_type="10-K",
        filing_date=date(2025, 2, 26),
        primary_document="main.htm",
        company_name="NVIDIA CORP",
    )


def _sec_pack_result(out_dir: Path) -> PackResult:
    pack_dir = out_dir / "0001045810" / "0001045810-25-000042"
    pack_dir.mkdir(parents=True, exist_ok=True)
    return PackResult(
        output_dir=pack_dir,
        filing_meta={"company_name": "NVIDIA CORP"},
        sections_count=22,
        tokens_total=156000,
        warnings=[],
        artifacts=[],
    )


def _sse_pack_result(out_dir: Path) -> PackResult:
    pack_dir = out_dir / "688696" / "2026-annual"
    pack_dir.mkdir(parents=True, exist_ok=True)
    return PackResult(
        output_dir=pack_dir,
        filing_meta={"company_name": "Chengdu XGIMI Technology Co., Ltd."},
        sections_count=12,
        tokens_total=45000,
        warnings=[],
        artifacts=[],
    )


@pytest.mark.asyncio
async def test_mixed_universe_builds_and_registers_both_lanes(tmp_path):
    universe = UniverseConfig(
        companies=[
            CompanySpec(ticker="NVDA", forms_10k=1, forms_10q=0, forms_8k=0),
            CompanySpec(
                ticker="688696",
                name="Chengdu XGIMI Technology Co., Ltd.",
                listing="SSE",
                stock_code="688696",
            ),
        ]
    )
    registry = PackRegistry(tmp_path / "registry.db")
    out_dir = tmp_path / "packs"

    async def fake_resolve(spec):
        return "0001045810", "NVIDIA CORP"

    async def fake_list_filings(cik, form_type=None, limit=10, force=False):
        if form_type == "10-K":
            return [_sec_filing()]
        return []

    selected = CninfoAnnualReportRef(
        stock_code="688696",
        company_name="Chengdu XGIMI Technology Co., Ltd.",
        title="2025 Annual Report",
        filing_date=date(2026, 3, 20),
        source_url="https://static.cninfo.com.cn/report.pdf",
    )

    with (
        patch("edgarpack.harvest.planner.resolve_filer", new=fake_resolve),
        patch("edgarpack.harvest.planner.list_filings", new=fake_list_filings),
    ):
        plan = await plan_harvest(universe, registry)

    assert plan.errors == []
    assert len(plan.items) == 2

    with (
        patch(
            "edgarpack.harvest.runner.build_pack",
            new=AsyncMock(return_value=_sec_pack_result(out_dir)),
        ),
        patch(
            "edgarpack.harvest.runner.find_latest_annual_report",
            return_value=selected,
        ),
        patch(
            "edgarpack.harvest.runner.build_sse_pack",
            new=AsyncMock(return_value=_sse_pack_result(out_dir)),
        ),
    ):
        summary = await run_harvest(plan, out_dir=out_dir, registry=registry)

    assert summary["built"] == 2
    assert summary["failed"] == 0

    sec_record = registry.lookup("0001045810-25-000042")
    assert sec_record is not None
    assert sec_record.market is None

    sse_record = registry.lookup("SSE:688696:2026-03-20")
    assert sse_record is not None
    assert sse_record.market == "SSE"
    assert sse_record.stock_code == "688696"

    registry.close()
