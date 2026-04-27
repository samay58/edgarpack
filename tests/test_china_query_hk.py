"""Smoke tests for HKEX pack query paths.

Numeric regression coverage lives in tests/test_china_query_eval.py
(driven by tests/eval/china_golden.yaml). This file asserts structural
and metadata invariants only: currency flags, accounting standard flags,
ticker-form resolution, multi-metric queries, and failure modes.
"""

import asyncio
import json
from pathlib import Path

import pytest

from edgarpack.query.financials import financials


def test_minimax_query_returns_revenue_with_hkfrs_metadata():
    result = asyncio.run(financials(company="minimax", metrics="revenue", period="lfy"))
    assert result is not None
    revenue = result.metrics.get("revenue")
    assert revenue is not None, f"No revenue in {list(result.metrics.keys())}"
    assert revenue.reporting_currency == "USD"
    assert revenue.accounting_standard == "HKFRS"
    assert revenue.fiscal_year == 2024


def test_zhipu_query_returns_net_income_with_cny_metadata():
    result = asyncio.run(financials(company="zhipu", metrics="net_income", period="lfy"))
    ni = result.metrics.get("net_income")
    assert ni is not None
    assert ni.reporting_currency == "CNY"
    assert ni.accounting_standard == "HKFRS"


def test_minimax_ticker_form_resolves():
    result = asyncio.run(
        financials(company="00100.HK", metrics="cash_and_equivalents", period="lfy")
    )
    cash = result.metrics.get("cash_and_equivalents")
    assert cash is not None
    assert cash.reporting_currency == "USD"


def test_minimax_full_query_returns_multiple_metrics():
    result = asyncio.run(financials(company="minimax", metrics=None, period="lfy"))
    metrics = set(result.metrics.keys())
    assert {"revenue", "net_income", "cash_and_equivalents"} <= metrics


def test_minimax_r_and_d_alias_resolves_to_canonical_metric():
    result = asyncio.run(financials(company="minimax", metrics="r_and_d_expense", period="lfy"))

    assert list(result.metrics.keys()) == ["rd_expense"]
    rd = result.metrics["rd_expense"]
    assert rd is not None
    assert rd.value == 188_979_000
    assert rd.reporting_currency == "USD"


def test_minimax_query_preserves_non_sec_source_provenance():
    result = asyncio.run(financials(company="minimax", metrics="revenue", period="lfy"))
    revenue = result.metrics["revenue"]

    assert revenue.primary_link_type == "source_path"
    assert revenue.primary_link.endswith("tests/fixtures/china_packs/minimax_2024/source.pdf")
    assert Path(revenue.source_path).exists()
    assert revenue.source_document == "source.pdf"
    assert revenue.filed.isoformat() == "2024-12-31"
    assert revenue.source == "regex"
    assert revenue.section_id == "hkex_income_statement"
    assert "sec.gov" not in revenue.primary_link


def test_hkex_annual_pack_uses_local_pdf_and_announcement_date(tmp_path):
    pack_dir = tmp_path / "packs" / "hk" / "00700" / "2023"
    pack_dir.mkdir(parents=True)
    (pack_dir / "00700_2023.pdf").write_bytes(b"%PDF-1.4\n")
    (pack_dir / "manifest.json").write_text(
        json.dumps(
            {
                "source": "HKEX",
                "stock_code": "00700",
                "fiscal_year": 2023,
                "company": "Tencent Holdings",
                "reporting_currency": "CNY",
                "accounting_standard": "HKFRS",
                "pdf_url": "https://www1.hkexnews.hk/listedco/listconews/sehk/2024/0326/2024032600840.pdf",
                "announcement_date": "26/03/2024",
            }
        ),
        encoding="utf-8",
    )
    (pack_dir / "facts.json").write_text(
        json.dumps(
            {
                "source": "HKEX",
                "stock_code": "00700",
                "company": "Tencent Holdings",
                "facts": {
                    "hkfrs": {
                        "Revenue": {
                            "label": "Revenue",
                            "units": {
                                "CNY": [
                                    {
                                        "start": "2023-01-01",
                                        "end": "2023-12-31",
                                        "val": 609_015_000_000,
                                        "fy": 2023,
                                        "fp": "FY",
                                        "form": "Annual Report",
                                        "accn": "00700_2023",
                                        "section_id": "hkex_income_statement",
                                        "extraction_method": "regex",
                                    }
                                ]
                            },
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    result = asyncio.run(
        financials(
            company="0700.HK",
            metrics="revenue",
            period="lfy",
            pack_root=tmp_path / "packs",
        )
    )

    revenue = result.metrics["revenue"]
    assert revenue.filed.isoformat() == "2024-03-26"
    assert revenue.source_url.startswith("https://www1.hkexnews.hk/")
    assert revenue.source_document == "00700_2023.pdf"
    assert revenue.source_path.endswith("00700_2023.pdf")
    assert "sec.gov" not in revenue.primary_link


def test_unknown_hkex_company_raises():
    with pytest.raises(Exception):
        asyncio.run(financials(company="00999.HK", metrics="revenue", period="lfy"))
