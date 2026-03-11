"""Live SEC integration coverage for useful audit and parser workflows.

Skipped by default. Requires:
    export EDGARPACK_USER_AGENT="Your Name your.email@example.com"

Useful runs:
    pytest tests/test_live_sec_integration.py -q --run-live-sec
    pytest tests/test_live_sec_integration.py -q --run-live-sec --live-sec-full
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from edgarpack.pack.build import build_pack
from edgarpack.query.comps import comps, comps_to_lean_json, format_comps_table
from edgarpack.query.financials import financials
from edgarpack.query.models import DerivedValue

pytestmark = [
    pytest.mark.live_sec,
    pytest.mark.slow,
    pytest.mark.usefixtures("_require_live_sec"),
]


@dataclass(frozen=True)
class PackBuildCase:
    ticker: str
    cik: str
    form_type: str


_LARGE_CAP_CASES: tuple[tuple[str, str], ...] = (
    ("AAPL", "0000320193"),
    ("MSFT", "0000789019"),
    ("NVDA", "0001045810"),
    ("AMD", "0000002488"),
    ("AMZN", "0001018724"),
    ("META", "0001326801"),
    ("GOOGL", "0001652044"),
    ("ORCL", "0001341439"),
    ("CSCO", "0000858877"),
    ("INTC", "0000050863"),
)

FULL_PACK_CASES: tuple[PackBuildCase, ...] = tuple(
    PackBuildCase(ticker=ticker, cik=cik, form_type=form_type)
    for ticker, cik in _LARGE_CAP_CASES
    for form_type in ("10-K", "10-Q", "8-K")
)

SMOKE_PACK_CASES: tuple[PackBuildCase, ...] = (
    PackBuildCase(ticker="AAPL", cik="0000320193", form_type="10-K"),
    PackBuildCase(ticker="NVDA", cik="0001045810", form_type="10-Q"),
    PackBuildCase(ticker="MSFT", cik="0000789019", form_type="8-K"),
    PackBuildCase(ticker="AMZN", cik="0001018724", form_type="10-K"),
    PackBuildCase(ticker="META", cik="0001326801", form_type="10-Q"),
    PackBuildCase(ticker="ORCL", cik="0001341439", form_type="8-K"),
)


def _case_id(case: PackBuildCase) -> str:
    return f"{case.ticker}-{case.form_type.lower()}"


def _assert_pack_result(case: PackBuildCase, output_dir: Path) -> None:
    manifest_path = output_dir / "manifest.json"
    llms_path = output_dir / "llms.txt"
    filing_path = output_dir / "filing.full.md"
    sections_dir = output_dir / "sections"

    assert manifest_path.exists(), f"manifest missing for {case.ticker} {case.form_type}"
    assert llms_path.exists(), f"llms.txt missing for {case.ticker} {case.form_type}"
    assert filing_path.exists(), f"filing.full.md missing for {case.ticker} {case.form_type}"
    assert sections_dir.exists(), f"sections dir missing for {case.ticker} {case.form_type}"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    filing_meta = manifest.get("filing", {})
    sections = manifest.get("sections", [])
    artifacts = manifest.get("artifacts", {})

    assert str(filing_meta.get("cik", "")).zfill(10) == case.cik
    assert str(filing_meta.get("form_type", "")).startswith(case.form_type)
    assert sections, f"no sections emitted for {case.ticker} {case.form_type}"
    assert "filing.full.md" in artifacts
    assert "llms.txt" in artifacts
    assert len(list(sections_dir.glob("*.md"))) == len(sections)
    assert filing_path.read_text(encoding="utf-8").strip()


@pytest.mark.asyncio
@pytest.mark.parametrize("ticker", ["AAPL", "MSFT", "NVDA", "AMD"])
async def test_live_financials_lean_json_has_audit_surface(ticker: str) -> None:
    result = await financials(
        ticker,
        ["revenue", "net_income", "gross_margin"],
        period="lfy",
    )

    assert result.company
    assert result.cik
    assert result.permalink.startswith("edgarpack query ")

    revenue = result.metrics["revenue"]
    net_income = result.metrics["net_income"]
    gross_margin = result.metrics["gross_margin"]

    assert revenue is not None, f"missing live revenue for {ticker}"
    assert net_income is not None, f"missing live net income for {ticker}"
    assert gross_margin is not None, f"missing live gross margin for {ticker}"
    assert isinstance(gross_margin, DerivedValue)

    lean = result.to_lean_dict()
    metrics = lean["metrics"]
    citations = lean["citations"]
    calculations = lean["calculations"]

    revenue_payload = metrics["revenue"]
    assert revenue_payload["citation_ids"]
    revenue_citation_id = revenue_payload["citation_ids"][0]
    revenue_citation = citations[revenue_citation_id]
    assert revenue_citation["primary_link_type"] in {"anchor_url", "viewer_url", "filing_url"}
    assert revenue_citation["primary_link"]

    gross_margin_payload = metrics["gross_margin"]
    calc_id = gross_margin_payload["calculation_id"]
    assert calc_id in calculations
    assert gross_margin_payload["component_citation_ids"]

    calc = calculations[calc_id]
    assert calc["kind"] == "derived"
    assert calc["formula"] == "gross_profit / revenue"
    assert len(calc["components"]) >= 2
    for component in calc["components"]:
        assert component["citation_id"] in citations
        assert component["primary_link"]


@pytest.mark.asyncio
async def test_live_comps_output_exposes_citations_and_calculations() -> None:
    results = await comps(
        companies=["NVDA", "AMD"],
        metrics=["revenue", "gross_margin"],
        period="ltm",
    )

    table = format_comps_table(
        results,
        ["revenue", "gross_margin"],
        citations_mode="inline",
        show_links="primary",
        audit=True,
        terminal_width=120,
    )
    assert "NVIDIA" in table
    assert "ADVANCED MICRO DEVICES" in table
    assert "Citations:" in table
    assert "Calculations:" in table
    assert "[C" in table

    payload = json.loads(comps_to_lean_json(results, ["revenue", "gross_margin"], period="ltm"))
    assert payload["period"] == "ltm"
    for company in ("NVDA", "AMD"):
        company_payload = payload["companies"][company]
        assert company_payload["citations"]
        assert company_payload["calculations"]
        assert company_payload["metrics"]["gross_margin"]["calculation_id"]


@pytest.mark.asyncio
@pytest.mark.parametrize("case", SMOKE_PACK_CASES, ids=_case_id)
async def test_build_pack_smoke_real_filings(case: PackBuildCase, tmp_path: Path) -> None:
    result = await build_pack(
        cik=case.cik,
        form_type=case.form_type,
        out_dir=tmp_path,
        with_chunks=False,
        with_xbrl=False,
        force=False,
    )

    assert result.sections_count > 0
    assert result.tokens_total > 0
    _assert_pack_result(case, result.output_dir)


@pytest.mark.asyncio
@pytest.mark.usefixtures("_require_live_sec_full")
@pytest.mark.parametrize("case", FULL_PACK_CASES, ids=_case_id)
async def test_build_pack_real_filing_matrix(case: PackBuildCase, tmp_path: Path) -> None:
    result = await build_pack(
        cik=case.cik,
        form_type=case.form_type,
        out_dir=tmp_path,
        with_chunks=False,
        with_xbrl=False,
        force=False,
    )

    assert result.sections_count > 0
    assert result.tokens_total > 0
    _assert_pack_result(case, result.output_dir)
