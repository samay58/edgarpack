"""Tests for the harvest planner's handling of the registration-form family."""

from datetime import date
from unittest.mock import patch

import pytest

from edgarpack.harvest.planner import plan_harvest
from edgarpack.harvest.registry import PackRegistry
from edgarpack.harvest.universe import CompanySpec, UniverseConfig
from edgarpack.sec.submissions import FilingMeta


def _filing(accession: str, form: str, filing_date: str) -> FilingMeta:
    return FilingMeta(
        cik="0002021728",
        accession=accession,
        form_type=form,
        filing_date=date.fromisoformat(filing_date),
        primary_document="main.htm",
        company_name="Cerebras Systems Inc",
    )


@pytest.mark.asyncio
async def test_planner_expands_registration_sentinel(tmp_path):
    spec = CompanySpec(name="Cerebras Systems", forms_s1=4)
    cfg = UniverseConfig(companies=[spec])

    canned: dict[str, list[FilingMeta]] = {
        "S-1": [_filing("0000001-25-000001", "S-1", "2025-09-30")],
        "S-1/A": [
            _filing("0000001-25-000002", "S-1/A", "2025-10-15"),
            _filing("0000001-25-000003", "S-1/A", "2025-11-01"),
        ],
        "424B4": [_filing("0000001-25-000004", "424B4", "2025-12-01")],
    }

    async def fake_list_filings(cik, form_type=None, limit=10, force=False):
        return canned.get(form_type, [])

    async def fake_resolve(spec):
        return "0002021728", "Cerebras Systems Inc"

    registry = PackRegistry(tmp_path / "registry.db")
    with patch("edgarpack.harvest.planner.list_filings", new=fake_list_filings):
        with patch("edgarpack.harvest.planner.resolve_filer", new=fake_resolve):
            plan = await plan_harvest(cfg, registry)

    accessions = {item.accession for item in plan.items}
    assert len(plan.items) == 4
    assert accessions == {
        "0000001-25-000001",
        "0000001-25-000002",
        "0000001-25-000003",
        "0000001-25-000004",
    }


@pytest.mark.asyncio
async def test_planner_registration_caps_at_budget(tmp_path):
    spec = CompanySpec(name="Example IPO Corp", forms_s1=2)
    cfg = UniverseConfig(companies=[spec])

    canned = {
        "S-1": [_filing("A-1", "S-1", "2025-01-01")],
        "S-1/A": [
            _filing("A-2", "S-1/A", "2025-02-01"),
            _filing("A-3", "S-1/A", "2025-03-01"),
            _filing("A-4", "S-1/A", "2025-04-01"),
        ],
    }

    async def fake_list_filings(cik, form_type=None, limit=10, force=False):
        return canned.get(form_type, [])

    async def fake_resolve(spec):
        return "0001234567", "Example IPO Corp"

    registry = PackRegistry(tmp_path / "registry.db")
    with patch("edgarpack.harvest.planner.list_filings", new=fake_list_filings):
        with patch("edgarpack.harvest.planner.resolve_filer", new=fake_resolve):
            plan = await plan_harvest(cfg, registry)

    assert {i.accession for i in plan.items} == {"A-3", "A-4"}


@pytest.mark.asyncio
async def test_planner_does_not_fetch_periodic_forms_for_pre_ipo(tmp_path):
    spec = CompanySpec(name="Cerebras Systems", forms_s1=1)
    cfg = UniverseConfig(companies=[spec])

    calls: list[str] = []

    async def fake_list_filings(cik, form_type=None, limit=10, force=False):
        calls.append(form_type or "")
        if form_type == "S-1":
            return [_filing("X-1", "S-1", "2025-09-30")]
        return []

    async def fake_resolve(spec):
        return "0002021728", "Cerebras Systems Inc"

    registry = PackRegistry(tmp_path / "registry.db")
    with patch("edgarpack.harvest.planner.list_filings", new=fake_list_filings):
        with patch("edgarpack.harvest.planner.resolve_filer", new=fake_resolve):
            await plan_harvest(cfg, registry)

    assert "10-K" not in calls
    assert "10-Q" not in calls
    assert "8-K" not in calls


@pytest.mark.asyncio
async def test_planner_skips_private_company_before_sec_resolution(tmp_path):
    spec = CompanySpec(
        name="Shenzhen Shuye Innovative Technology Co., Ltd.",
        listing="PRIVATE",
    )
    cfg = UniverseConfig(companies=[spec])

    async def fail_resolve(_spec):
        raise AssertionError("private companies should not hit SEC resolution")

    registry = PackRegistry(tmp_path / "registry.db")
    with patch("edgarpack.harvest.planner.resolve_filer", new=fail_resolve):
        plan = await plan_harvest(cfg, registry)

    assert plan.items == []
    assert plan.skipped == []
    assert plan.errors == []
