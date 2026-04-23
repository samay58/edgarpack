"""Live-SEC + live-Anthropic smoke test for Cerebras S-1 financial extraction.

Gated on `--run-slow --run-live-sec` plus ANTHROPIC_API_KEY environment
variable. Skips silently otherwise so the fast suite stays offline.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.slow,
    pytest.mark.live_sec,
    pytest.mark.usefixtures("_require_slow", "_require_live_sec"),
]


@pytest.mark.asyncio
async def test_cerebras_2024_s1_yields_revenue_in_expected_band():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")

    pack = Path("packs/0002021728/0001628280-24-041596")
    if not pack.exists():
        pytest.skip("pack not built: run `edgarpack harvest --universe cerebras.toml` first")

    from edgarpack.query.s1_financials import (
        extract_or_load_snapshot,
        pick_snapshot_fact,
    )

    result = await extract_or_load_snapshot(pack, force=True)
    assert result.extraction_status == "ok", f"extraction failed: {result.extraction_status}"

    revenue = pick_snapshot_fact(result.facts, metric="revenue", period="lfy")
    assert revenue is not None, "no revenue fact extracted from Cerebras 2024 S-1"
    # Cerebras's 2024 S-1 reported FY2024 revenue in the $70M-$120M range
    # (filed with reference to 2024 audited statements). Wide band because
    # the LLM may extract either the full-year or interim figure.
    assert 70_000_000 <= revenue.value_cents // 100 <= 120_000_000, (
        f"unexpected Cerebras revenue: ${revenue.value_cents // 100:,}"
    )
