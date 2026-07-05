"""Tests for the harvest planner's SSE (A-share) lane."""

from unittest.mock import patch

import pytest

from edgarpack.harvest.planner import plan_harvest
from edgarpack.harvest.registry import PackRegistry
from edgarpack.harvest.universe import CompanySpec, UniverseConfig


async def _fail_resolve(_spec):
    raise AssertionError("SSE entries must not hit SEC filer resolution")


@pytest.mark.asyncio
async def test_sse_entry_yields_annual_report_plan_item(tmp_path):
    spec = CompanySpec(
        ticker="688696",
        name="Chengdu XGIMI Technology Co., Ltd.",
        listing="SSE",
        stock_code="688696",
    )
    cfg = UniverseConfig(companies=[spec])
    registry = PackRegistry(tmp_path / "registry.db")

    with patch("edgarpack.harvest.planner.resolve_filer", new=_fail_resolve):
        plan = await plan_harvest(cfg, registry)

    assert plan.errors == []
    assert len(plan.items) == 1
    item = plan.items[0]
    assert item.form_type == "ANNUAL-REPORT"
    assert item.market == "SSE"
    assert item.stock_code == "688696"
    assert item.cik is None
    assert item.accession is None


@pytest.mark.asyncio
async def test_sse_entry_without_stock_code_becomes_plan_error(tmp_path):
    spec = CompanySpec(ticker="600000", name="Malformed A-Share Entry", listing="SSE")
    cfg = UniverseConfig(companies=[spec])
    registry = PackRegistry(tmp_path / "registry.db")

    with patch("edgarpack.harvest.planner.resolve_filer", new=_fail_resolve):
        plan = await plan_harvest(cfg, registry)

    assert plan.items == []
    assert len(plan.errors) == 1
    assert plan.errors[0].ticker == "600000"
    assert "stock_code" in plan.errors[0].error
