"""Live-SEC end-to-end smoke test for the new-filer pipeline.

Gated on --run-slow and --run-live-sec to avoid beating on SEC during fast test
runs. Requires EDGARPACK_USER_AGENT to be set in the environment.

Run with:
    pytest tests/test_cerebras_s1_smoke.py --run-slow --run-live-sec -v
"""

from __future__ import annotations

import pytest

from edgarpack.harvest.planner import plan_harvest
from edgarpack.harvest.registry import PackRegistry
from edgarpack.harvest.universe import CompanySpec, UniverseConfig
from edgarpack.sec.submissions import is_registration_form

pytestmark = [
    pytest.mark.slow,
    pytest.mark.live_sec,
    pytest.mark.usefixtures("_require_slow", "_require_live_sec"),
]


@pytest.mark.asyncio
async def test_cerebras_name_resolution_and_plan(tmp_path):
    spec = CompanySpec(name="Cerebras Systems", forms_s1=4)
    cfg = UniverseConfig(companies=[spec])
    registry = PackRegistry(tmp_path / "registry.db")
    plan = await plan_harvest(cfg, registry)

    assert plan.total_filings >= 1

    for item in plan.items:
        assert is_registration_form(item.form_type), item.form_type

    forms = {item.form_type for item in plan.items}
    assert any(f.startswith("S-1") for f in forms), f"no S-1 in plan: {forms}"


@pytest.mark.asyncio
async def test_cerebras_by_cik_fallback(tmp_path):
    """If name resolution is ambiguous, supplying CIK directly must work."""
    spec = CompanySpec(cik="0002021728", forms_s1=2)
    cfg = UniverseConfig(companies=[spec])
    registry = PackRegistry(tmp_path / "registry.db")
    plan = await plan_harvest(cfg, registry)
    assert plan.total_filings >= 1
