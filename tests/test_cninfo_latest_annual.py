from __future__ import annotations

from argparse import Namespace
from datetime import date
from types import SimpleNamespace


def test_cninfo_latest_annual_filters_summary_and_builds_static_url():
    from edgarpack.china.acquire import latest_annual_from_cninfo_payload

    payload = {
        "announcements": [
            {
                "secCode": "688696",
                "secName": "XGIMI",
                "announcementTitle": "2024年年度报告摘要",
                "announcementTime": 1745270000000,
                "adjunctUrl": "finalpage/2025-04-22/summary.PDF",
            },
            {
                "secCode": "688696",
                "secName": "XGIMI",
                "announcementTitle": "2024年年度报告",
                "announcementTime": 1745270000000,
                "adjunctUrl": "finalpage/2025-04-22/1223192484.PDF",
            },
        ]
    }

    ref = latest_annual_from_cninfo_payload(payload, stock_code="688696")

    assert ref is not None
    assert ref.stock_code == "688696"
    assert ref.company_name == "XGIMI"
    assert ref.filing_date == date(2025, 4, 22)
    assert ref.source_url == "https://static.cninfo.com.cn/finalpage/2025-04-22/1223192484.PDF"


def test_cninfo_latest_annual_accepts_full_text_title_and_prefers_newest():
    from edgarpack.china.acquire import latest_annual_from_cninfo_payload

    payload = {
        "announcements": [
            {
                "secCode": "688696",
                "secName": "<em>极米科技</em>",
                "announcementTitle": "2024年年度报告",
                "adjunctUrl": "finalpage/2025-04-22/1223192484.PDF",
            },
            {
                "secCode": "688696",
                "secName": "<em>极米科技</em>",
                "announcementTitle": "2025年年度报告全文",
                "adjunctUrl": "finalpage/2026-03-31/1225055991.PDF",
            },
        ]
    }

    ref = latest_annual_from_cninfo_payload(payload, stock_code="688696")

    assert ref is not None
    assert ref.title == "2025年年度报告全文"
    assert ref.company_name == "极米科技"
    assert ref.filing_date == date(2026, 3, 31)
    assert ref.source_url == "https://static.cninfo.com.cn/finalpage/2026-03-31/1225055991.PDF"


def test_cninfo_query_uses_searchkey_for_sse_stock_without_org_id():
    from edgarpack.china.acquire.cninfo import _cninfo_annual_query_data

    data = _cninfo_annual_query_data("688696")

    assert data["column"] == "sse"
    assert data["plate"] == "sh"
    assert data["stock"] == ""
    assert data["searchkey"] == "688696"
    assert data["category"] == "category_ndbg_szsh"


def test_build_sse_latest_annual_uses_cninfo_selection(monkeypatch, tmp_path, capsys):
    from edgarpack import cli
    from edgarpack.china.acquire import CninfoAnnualReportRef

    selected = CninfoAnnualReportRef(
        stock_code="688696",
        company_name="Chengdu XGIMI Technology Co., Ltd.",
        title="2024年年度报告",
        filing_date=date(2025, 4, 22),
        source_url="https://static.cninfo.com.cn/finalpage/2025-04-22/1223192484.PDF",
    )
    calls = {}

    async def fake_build_sse_pack(**kwargs):
        calls.update(kwargs)
        return SimpleNamespace(
            output_dir=tmp_path / "packs" / "sse" / "688696" / "688696_2025-04-22",
            filing_meta={
                "company_name": kwargs["company_name"],
                "form_type": "ANNUAL-REPORT",
                "filing_date": str(kwargs["filing_date"]),
            },
            sections_count=4,
            tokens_total=1234,
            warnings=[],
        )

    monkeypatch.setattr(cli, "_find_latest_sse_annual_report", lambda *_args, **_kwargs: selected)
    monkeypatch.setattr("edgarpack.pack.build.build_sse_pack", fake_build_sse_pack)

    rc = cli._cmd_build_sse(
        Namespace(
            target="xgimi",
            latest_annual=True,
            url=None,
            stock_code=None,
            company=None,
            filing_date=None,
            out=tmp_path / "packs",
            pdf=None,
            with_chunks=False,
            translate=False,
            translate_model="deepseek-ai/DeepSeek-V3",
            form_type="auto",
            force=False,
        )
    )

    assert rc == 0
    assert calls["url"] == selected.source_url
    assert calls["stock_code"] == "688696"
    assert calls["company_name"] == "Chengdu XGIMI Technology Co., Ltd."
    assert calls["filing_date"] == date(2025, 4, 22)
    assert calls["form_type"] == "annual-report"
    out = capsys.readouterr().out
    assert "Selected annual report" in out
    assert "1223192484.PDF" in out


def test_build_sse_latest_annual_accepts_raw_stock_code(monkeypatch, tmp_path, capsys):
    from edgarpack import cli
    from edgarpack.china.acquire import CninfoAnnualReportRef

    selected = CninfoAnnualReportRef(
        stock_code="688775",
        company_name="Insta360",
        title="2024年年度报告",
        filing_date=date(2025, 4, 22),
        source_url="https://static.cninfo.com.cn/finalpage/2025-04-22/688775.pdf",
    )
    calls = {}

    async def fake_build_sse_pack(**kwargs):
        calls.update(kwargs)
        return SimpleNamespace(
            output_dir=tmp_path / "packs" / "sse" / "688775" / "688775_2025-04-22",
            filing_meta={
                "company_name": kwargs["company_name"],
                "form_type": "ANNUAL-REPORT",
                "filing_date": str(kwargs["filing_date"]),
            },
            sections_count=4,
            tokens_total=1234,
            warnings=[],
        )

    monkeypatch.setattr(cli, "_find_latest_sse_annual_report", lambda *_args, **_kwargs: selected)
    monkeypatch.setattr("edgarpack.pack.build.build_sse_pack", fake_build_sse_pack)

    rc = cli._cmd_build_sse(
        Namespace(
            target="688775",
            latest_annual=True,
            url=None,
            stock_code=None,
            company=None,
            filing_date=None,
            out=tmp_path / "packs",
            pdf=None,
            with_chunks=False,
            translate=False,
            translate_model="deepseek-ai/DeepSeek-V3",
            form_type="auto",
            force=False,
        )
    )

    assert rc == 0
    assert calls["stock_code"] == "688775"
    assert calls["company_name"] == "Insta360"
    assert calls["url"] == selected.source_url
    out = capsys.readouterr().out
    assert "Selected annual report" in out
    assert "Stock Code: 688775" in out
