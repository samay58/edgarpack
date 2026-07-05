"""Live HKEX integration coverage for the acquisition flow.

Skipped by default. Useful runs:
    pytest tests/test_live_hk_integration.py -q --run-live-hk
"""

from __future__ import annotations

import pytest

from edgarpack.hk.acquire import list_annual_reports, resolve_stock_id, warm_up

pytestmark = [
    pytest.mark.live_hk,
    pytest.mark.slow,
    pytest.mark.usefixtures("_require_live_hk"),
]


def test_resolve_and_list_annual_reports_for_tencent() -> None:
    import httpx

    with httpx.Client(
        headers={"User-Agent": "edgarpack/0.1 (+https://github.com) live-test"},
        follow_redirects=True,
        timeout=30.0,
    ) as client:
        warm_up(client)
        match = resolve_stock_id(client, "0700")
        assert match.code == "00700"

        rows = list_annual_reports(client, match.stock_id)
        assert len(rows) > 0
