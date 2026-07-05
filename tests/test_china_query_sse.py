"""Smoke tests for SSE annual-report pack query paths."""

from __future__ import annotations

import asyncio
import json

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


def test_raw_a_share_code_query_uses_china_pack_path(tmp_path):
    pack_root = tmp_path / "packs"
    pack_dir = pack_root / "sse" / "688775" / "688775_2025-04-22"
    pack_dir.mkdir(parents=True)
    (pack_dir / "manifest.json").write_text(
        json.dumps(
            {
                "filing": {
                    "company_name": "Insta360",
                    "filing_date": "2025-04-22",
                    "form_type": "ANNUAL-REPORT",
                    "stock_code": "688775",
                    "exchange": "SSE",
                }
            }
        ),
        encoding="utf-8",
    )
    (pack_dir / "facts.json").write_text(
        json.dumps(
            {
                "source": "SSE",
                "exchange": "SSE",
                "stock_code": "688775",
                "company": "Insta360",
                "facts": {
                    "cas": {
                        "Revenue": {
                            "label": "Revenue",
                            "units": {
                                "CNY": [
                                    {
                                        "start": "2024-01-01",
                                        "end": "2024-12-31",
                                        "fy": 2024,
                                        "fp": "FY",
                                        "form": "ANNUAL-REPORT",
                                        "accn": "688775_2025-04-22",
                                        "filed": "2025-04-22",
                                        "source_url": "https://static.cninfo.com.cn/finalpage/2025-04-22/688775.PDF",
                                        "source_document": "optional/source.pdf",
                                        "section_id": "annual_s02_company_profile_key_financials",
                                        "matched_label": "营业收入",
                                        "extraction_method": "regex:annual_table",
                                        "val": 123_456_789.0,
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
        financials(company="688775", metrics="revenue", period="lfy", pack_root=pack_root)
    )

    assert result.metrics["revenue"].value == 123_456_789.0
    assert result.metrics["revenue"].reporting_currency == "CNY"
    assert result.metrics["revenue"].primary_link.startswith("https://static.cninfo.com.cn/")


def test_unknown_a_share_like_code_reports_missing_china_pack(tmp_path):
    with pytest.raises(FileNotFoundError, match="No SSE pack found for 688999"):
        asyncio.run(
            financials(
                company="688999",
                metrics="revenue",
                period="lfy",
                pack_root=tmp_path / "packs",
            )
        )


def test_sse_provenance_threads_form_and_filed_into_json_full(tmp_path):
    """A fact point missing its own form/filed inherits both from the pack
    manifest's filing.form_type / filing.filing_date, not just filed alone."""
    pack_root = tmp_path / "packs"
    pack_dir = pack_root / "sse" / "601988" / "601988_2025-03-28"
    pack_dir.mkdir(parents=True)
    (pack_dir / "manifest.json").write_text(
        json.dumps(
            {
                "filing": {
                    "company_name": "China Merchants Bank",
                    "filing_date": "2025-03-28",
                    "form_type": "ANNUAL-REPORT",
                    "stock_code": "601988",
                    "exchange": "SSE",
                }
            }
        ),
        encoding="utf-8",
    )
    (pack_dir / "facts.json").write_text(
        json.dumps(
            {
                "source": "SSE",
                "exchange": "SSE",
                "stock_code": "601988",
                "company": "China Merchants Bank",
                "facts": {
                    "cas": {
                        "Revenue": {
                            "label": "Revenue",
                            "units": {
                                "CNY": [
                                    {
                                        "start": "2024-01-01",
                                        "end": "2024-12-31",
                                        "fy": 2024,
                                        "fp": "FY",
                                        "accn": "601988_2025-03-28",
                                        "extraction_method": "regex:annual_table",
                                        "val": 1000.0,
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
        financials(company="601988", metrics="revenue", period="lfy", pack_root=pack_root)
    )
    revenue = result.metrics["revenue"]

    assert revenue.form_type == "ANNUAL-REPORT"
    assert revenue.filed is not None
    assert revenue.filed.isoformat() == "2025-03-28"

    payload = revenue.to_cited_dict()
    assert payload["form_type"] == "ANNUAL-REPORT"
    assert payload["filed"] == "2025-03-28"


def test_known_sse_without_pack_gives_build_next_step(tmp_path):
    with pytest.raises(FileNotFoundError) as excinfo:
        asyncio.run(
            financials(
                company="688696",
                metrics="revenue",
                period="lfy",
                pack_root=tmp_path / "packs",
            )
        )

    message = str(excinfo.value)
    assert "No SSE pack found for 688696" in message
    assert "edgarpack build-sse 688696 --latest-annual --with-chunks" in message
