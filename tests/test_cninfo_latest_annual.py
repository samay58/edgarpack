from __future__ import annotations

from argparse import Namespace
from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest


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


def test_cninfo_latest_annual_excludes_english_edition():
    from edgarpack.china.acquire import latest_annual_from_cninfo_payload

    payload = {
        "announcements": [
            {
                "secCode": "000858",
                "secName": "五粮液",
                "announcementTitle": "2025年度报告（英文版）",
                "announcementTime": "2026-06-01",
                "adjunctUrl": "finalpage/2026-06-01/en.PDF",
            },
            {
                "secCode": "000858",
                "secName": "五粮液",
                "announcementTitle": "2024年年度报告",
                "announcementTime": "2025-04-22",
                "adjunctUrl": "finalpage/2025-04-22/zh.PDF",
            },
        ]
    }

    ref = latest_annual_from_cninfo_payload(payload, stock_code="000858")

    assert ref is not None
    assert ref.title == "2024年年度报告"
    assert ref.filing_date == date(2025, 4, 22)


def test_cninfo_latest_annual_prefers_chinese_edition_on_same_date_tie():
    from edgarpack.china.acquire import latest_annual_from_cninfo_payload

    payload = {
        "announcements": [
            {
                "secCode": "000858",
                "secName": "五粮液",
                "announcementTitle": "2024年度报告（英文）",
                "announcementTime": "2025-04-22",
                "adjunctUrl": "finalpage/2025-04-22/en.PDF",
            },
            {
                "secCode": "000858",
                "secName": "五粮液",
                "announcementTitle": "2024年年度报告",
                "announcementTime": "2025-04-22",
                "adjunctUrl": "finalpage/2025-04-22/zh.PDF",
            },
        ]
    }

    ref = latest_annual_from_cninfo_payload(payload, stock_code="000858")

    assert ref is not None
    assert ref.title == "2024年年度报告"


def test_cninfo_query_uses_stock_param_when_org_id_provided():
    from edgarpack.china.acquire.cninfo import _cninfo_annual_query_data

    data = _cninfo_annual_query_data("000858", org_id="gssz0000858")

    assert data["stock"] == "000858,gssz0000858"
    assert data["searchkey"] == ""
    assert data["column"] == "szse"
    assert data["plate"] == "sz"


def test_resolve_cninfo_org_id_returns_match_from_topsearch_payload():
    from edgarpack.china.acquire.cninfo import _resolve_cninfo_org_id

    def fake_poster(stock_code: str) -> list[dict[str, str]]:
        assert stock_code == "000858"
        return [
            {
                "code": "000858",
                "orgId": "gssz0000858",
                "zwjc": "五粮液",
                "category": "A股",
            }
        ]

    assert _resolve_cninfo_org_id("000858", poster=fake_poster) == "gssz0000858"


def test_resolve_cninfo_org_id_returns_none_when_no_match():
    from edgarpack.china.acquire.cninfo import _resolve_cninfo_org_id

    assert _resolve_cninfo_org_id("999999", poster=lambda _code: []) is None


def test_resolve_cninfo_org_id_returns_none_on_poster_failure(caplog):
    from edgarpack.china.acquire.cninfo import _resolve_cninfo_org_id

    def failing_poster(_stock_code: str) -> list[dict[str, str]]:
        raise RuntimeError("network unreachable")

    with caplog.at_level("WARNING"):
        result = _resolve_cninfo_org_id("000858", poster=failing_poster)

    assert result is None
    assert "orgId resolution failed" in caplog.text


def test_fetch_cninfo_announcements_uses_stock_param_when_org_id_resolves(monkeypatch):
    from edgarpack.china.acquire import cninfo

    monkeypatch.setattr(cninfo, "_resolve_cninfo_org_id", lambda _code: "gssz0000858")
    captured: dict[str, Any] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, list[Any]]:
            return {"announcements": []}

    class FakeClient:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *_args: Any) -> bool:
            return False

        def post(self, _url: str, headers: Any = None, data: Any = None) -> FakeResponse:
            captured["data"] = data
            return FakeResponse()

    import httpx

    monkeypatch.setattr(httpx, "Client", FakeClient)

    cninfo.fetch_cninfo_announcements("000858")

    assert captured["data"]["stock"] == "000858,gssz0000858"
    assert captured["data"]["searchkey"] == ""


def test_fetch_cninfo_announcements_falls_back_to_searchkey_when_org_id_resolution_fails(
    monkeypatch,
):
    from edgarpack.china.acquire import cninfo

    monkeypatch.setattr(cninfo, "_resolve_cninfo_org_id", lambda _code: None)
    captured: dict[str, Any] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, list[Any]]:
            return {"announcements": []}

    class FakeClient:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *_args: Any) -> bool:
            return False

        def post(self, _url: str, headers: Any = None, data: Any = None) -> FakeResponse:
            captured["data"] = data
            return FakeResponse()

    import httpx

    monkeypatch.setattr(httpx, "Client", FakeClient)

    cninfo.fetch_cninfo_announcements("688696")

    assert captured["data"]["stock"] == ""
    assert captured["data"]["searchkey"] == "688696"


def test_find_latest_annual_report_rejects_stale_selection():
    from edgarpack.china.acquire.cninfo import find_latest_annual_report

    payload = {
        "announcements": [
            {
                "secCode": "000858",
                "secName": "五粮液",
                "announcementTitle": "2025年年度报告摘要",
                "announcementTime": "2026-04-01",
                "adjunctUrl": "finalpage/2026-04-01/summary.PDF",
            },
            {
                "secCode": "000858",
                "secName": "五粮液",
                "announcementTitle": "2005年年度报告",
                "announcementTime": "2006-04-01",
                "adjunctUrl": "finalpage/2006-04-01/1223192484.PDF",
            },
        ]
    }

    with pytest.raises(LookupError, match="stale"):
        find_latest_annual_report("000858", fetcher=lambda _code: payload)


def test_find_latest_annual_report_accepts_fresh_selection():
    from edgarpack.china.acquire.cninfo import find_latest_annual_report

    payload = {
        "announcements": [
            {
                "secCode": "688696",
                "secName": "XGIMI",
                "announcementTitle": "2024年年度报告",
                "announcementTime": 1745270000000,
                "adjunctUrl": "finalpage/2025-04-22/1223192484.PDF",
            },
        ]
    }

    ref = find_latest_annual_report("688696", fetcher=lambda _code: payload)

    assert ref.filing_date == date(2025, 4, 22)
