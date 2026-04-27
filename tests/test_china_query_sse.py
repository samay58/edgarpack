"""Smoke tests for SSE annual-report pack query paths."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

import pytest

from edgarpack.query.financials import financials


def _write_xgimi_pack(pack_root):
    pack_dir = pack_root / "sse" / "688696" / "688696_2025-04-22"
    pack_dir.mkdir(parents=True)
    (pack_dir / "manifest.json").write_text(
        json.dumps(
            {
                "filing": {
                    "company_name": "Chengdu XGIMI Technology Co., Ltd.",
                    "filing_date": "2025-04-22",
                    "form_type": "ANNUAL-REPORT",
                    "stock_code": "688696",
                    "exchange": "SSE",
                }
            }
        ),
        encoding="utf-8",
    )
    point_base = {
        "start": "2024-01-01",
        "end": "2024-12-31",
        "fy": 2024,
        "fp": "FY",
        "form": "ANNUAL-REPORT",
        "accn": "688696_2025-04-22",
        "filed": "2025-04-22",
        "source_url": "https://static.cninfo.com.cn/finalpage/2025-04-22/1223192484.PDF",
        "source_document": "optional/source.pdf",
        "section_id": "annual_s02_company_profile_key_financials",
        "matched_label": "营业收入",
        "extraction_method": "regex:annual_table",
    }
    payload = {
        "source": "SSE",
        "exchange": "SSE",
        "stock_code": "688696",
        "company": "Chengdu XGIMI Technology Co., Ltd.",
        "source_url": point_base["source_url"],
        "facts": {
            "cas": {
                "Revenue": {
                    "label": "Revenue",
                    "units": {"CNY": [{**point_base, "val": 3_404_605_307.88}]},
                },
                "ProfitLoss": {
                    "label": "Net income attributable to shareholders",
                    "units": {
                        "CNY": [
                            {
                                **point_base,
                                "val": 120_142_895.56,
                                "matched_label": "归属于上市公司股东的净利润",
                            }
                        ]
                    },
                },
                "NetCashProvidedByUsedInOperatingActivities": {
                    "label": "Net cash from operating activities",
                    "units": {
                        "CNY": [
                            {
                                **point_base,
                                "val": 230_241_355.89,
                                "matched_label": "经营活动产生的现金流量净额",
                            }
                        ]
                    },
                },
                "ResearchAndDevelopmentIntensity": {
                    "label": "R&D intensity",
                    "units": {
                        "pure": [
                            {
                                **point_base,
                                "val": 0.108,
                                "matched_label": "研发投入占营业收入的比例",
                            }
                        ]
                    },
                },
            }
        },
    }
    (pack_dir / "facts.json").write_text(json.dumps(payload), encoding="utf-8")
    return pack_dir


def test_xgimi_sse_query_returns_cas_values_with_source_links(tmp_path):
    _write_xgimi_pack(tmp_path / "packs")

    result = asyncio.run(
        financials(
            company="688696",
            metrics="revenue,net_income,operating_cash_flow,r_and_d_intensity",
            period="lfy",
            pack_root=tmp_path / "packs",
        )
    )

    revenue = result.metrics["revenue"]
    net_income = result.metrics["net_income"]
    operating_cash_flow = result.metrics["operating_cash_flow"]
    r_and_d = result.metrics["r_and_d_intensity"]

    assert revenue.value == 3_404_605_307.88
    assert revenue.reporting_currency == "CNY"
    assert revenue.accounting_standard == "CAS"
    assert revenue.primary_link_type == "source_url"
    assert revenue.primary_link.startswith("https://static.cninfo.com.cn/")
    assert revenue.section_id == "annual_s02_company_profile_key_financials"
    assert net_income.value == 120_142_895.56
    assert operating_cash_flow.value == 230_241_355.89
    assert r_and_d.unit == "pure"
    assert r_and_d.value == pytest.approx(0.108)


def test_xgimi_alias_query_routes_to_sse_pack(tmp_path):
    _write_xgimi_pack(tmp_path / "packs")

    result = asyncio.run(
        financials(company="XGIMI", metrics="revenue", period="lfy", pack_root=tmp_path / "packs")
    )

    assert result.metrics["revenue"].value == 3_404_605_307.88


def test_unknown_a_share_like_code_does_not_fall_back_to_sec():
    with patch("edgarpack.query.financials.resolve_ticker") as mock_resolve:
        with pytest.raises(ValueError, match="China A-share code"):
            asyncio.run(financials(company="688999", metrics="revenue", period="lfy"))

    mock_resolve.assert_not_called()
