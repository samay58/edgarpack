"""Live HKEX build coverage: one real Tencent (0700) end-to-end build.

Skipped by default. Run with:
    pytest tests/test_live_hk_build.py -q --run-live-hk

Asserts sectioning and manifest metadata only. Facts correctness is the
hk-extract-fixes packet's responsibility.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.live_hk,
    pytest.mark.slow,
    pytest.mark.usefixtures("_require_live_hk"),
]


def test_build_hk_tencent_income_statement_contains_real_statement(tmp_path: Path) -> None:
    import httpx

    from edgarpack.cli import _acquire_hk_filing
    from edgarpack.hk.adapter import build_hk_pack

    client = httpx.Client(
        headers={"User-Agent": "edgarpack/0.1 (+https://github.com) live-test"},
        follow_redirects=True,
        timeout=120.0,
    )
    try:
        ref, company_name, dual_codes = _acquire_hk_filing(client, "0700")
        pack = build_hk_pack(
            ref,
            tmp_path / "pack",
            company_name=company_name,
            dual_counter_codes=dual_codes,
            client=client,
        )
    finally:
        client.close()

    income = (pack.path / "sections" / "hkex_income_statement.md").read_text()
    assert "Consolidated Income Statement" in income
    assert "Revenue" in income

    manifest = json.loads((pack.path / "manifest.json").read_text())
    assert manifest["stock_code"] == "00700"
    assert manifest["reporting_currency"] == "CNY"
    # Corrected from the legacy _COMPANY_META dict's HKFRS: the filing states IFRS.
    assert manifest["accounting_standard"] == "IFRS"
