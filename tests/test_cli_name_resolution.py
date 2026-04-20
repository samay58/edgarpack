"""CLI-level tests for company-name resolution.

Covers the positional ``company`` argument plumbing on ``build``,
``company-llms``, and ``list``, plus the deprecated ``--cik`` path. All
downstream calls are mocked so the tests exercise only argument handling
and the resolver glue.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from edgarpack import cli

MOCK_TICKERS = {
    "0": {"cik_str": "320193", "ticker": "AAPL", "title": "Apple Inc"},
    "1": {"cik_str": "1045810", "ticker": "NVDA", "title": "NVIDIA CORP"},
}


@pytest.fixture
def mock_ticker_cache():
    """Stub the SEC ticker cache so resolve_company sees MOCK_TICKERS."""
    with (
        patch("edgarpack.sec.tickers.DiskCache") as mock_cache_cls,
        patch("edgarpack.sec.tickers.get_client"),
    ):
        cache_instance = mock_cache_cls.return_value
        cache_instance.get.return_value = json.dumps(MOCK_TICKERS).encode()
        yield


def _build_args(*, company=None, cik=None, form="10-K", accession=None):
    return SimpleNamespace(
        company=company,
        cik=cik,
        accession=accession,
        form=form,
        out="./packs",
        with_chunks=False,
        with_xbrl=False,
        force=False,
    )


def _list_args(*, company=None, cik=None, form=None, limit=5):
    return SimpleNamespace(company=company, cik=cik, form=form, limit=limit)


def _llms_args(*, company=None, cik=None, out="./packs"):
    return SimpleNamespace(company=company, cik=cik, out=out)


def _stub_build_result(tmp_path, company_name):
    return SimpleNamespace(
        output_dir=tmp_path,
        filing_meta={
            "company_name": company_name,
            "form_type": "10-K",
            "filing_date": "2024-01-01",
        },
        sections_count=10,
        tokens_total=1000,
        warnings=[],
    )


def test_build_accepts_ticker_positional(mock_ticker_cache, capsys, tmp_path):
    """Ticker positional resolves to CIK before dispatching to build_pack."""
    stub_result = _stub_build_result(tmp_path, "Apple Inc")
    mock_build = AsyncMock(return_value=stub_result)
    with patch("edgarpack.pack.build.build_pack", new=mock_build):
        rc = cli._cmd_build(_build_args(company="AAPL"))
    assert rc == 0
    assert mock_build.called
    assert mock_build.call_args.kwargs["cik"] == "0000320193"


def test_build_accepts_company_name_positional(mock_ticker_cache, tmp_path):
    """'NVIDIA' (bare name) resolves to NVDA's CIK via suffix stripping."""
    stub_result = _stub_build_result(tmp_path, "NVIDIA CORP")
    mock_build = AsyncMock(return_value=stub_result)
    with patch("edgarpack.pack.build.build_pack", new=mock_build):
        rc = cli._cmd_build(_build_args(company="NVIDIA"))
    assert rc == 0
    assert mock_build.call_args.kwargs["cik"] == "0001045810"


def test_build_deprecated_cik_flag_still_works(mock_ticker_cache, capsys, tmp_path):
    stub_result = _stub_build_result(tmp_path, "Apple Inc")
    mock_build = AsyncMock(return_value=stub_result)
    with patch("edgarpack.pack.build.build_pack", new=mock_build):
        rc = cli._cmd_build(_build_args(cik="0000320193"))
    err = capsys.readouterr().err
    assert rc == 0
    assert mock_build.called
    assert "deprecated" in err.lower()


def test_build_rejects_both_positional_and_cik(mock_ticker_cache, capsys):
    rc = cli._cmd_build(_build_args(company="AAPL", cik="0000320193"))
    assert rc == 2
    assert "not both" in capsys.readouterr().err.lower()


def test_build_requires_company_or_cik(mock_ticker_cache, capsys):
    rc = cli._cmd_build(_build_args())
    assert rc == 2
    assert "required" in capsys.readouterr().err.lower()


def test_build_surfaces_unknown_company_error(mock_ticker_cache, capsys):
    rc = cli._cmd_build(_build_args(company="Zzzzz Holdings"))
    err = capsys.readouterr().err
    assert rc == 2
    assert err.lower().startswith("error: unknown")


def test_list_accepts_company_name(mock_ticker_cache, capsys):
    """list command resolves positional company before calling list_filings."""
    with patch(
        "edgarpack.sec.submissions.list_filings",
        new=AsyncMock(return_value=[]),
    ) as mock_list:
        rc = cli._cmd_list(_list_args(company="NVIDIA"))
    assert rc == 0
    assert mock_list.called
    assert mock_list.call_args.args[0] == "0001045810"


def test_company_llms_accepts_company_name(mock_ticker_cache):
    with patch(
        "edgarpack.pack.build.build_company_llms",
        new=AsyncMock(return_value="/tmp/path.txt"),
    ) as mock_llms:
        rc = cli._cmd_company_llms(_llms_args(company="Apple Inc"))
    assert rc == 0
    assert mock_llms.called
    assert mock_llms.call_args.args[0] == "0000320193"


def test_query_accepts_company_name(mock_ticker_cache, capsys):
    """query command passes the original string to financials(), which now
    handles name resolution internally via resolve_ticker -> resolve_company."""
    stub_result = SimpleNamespace(
        company="NVIDIA CORP",
        cik="0001045810",
        metrics={},
        diagnostics=[],
        to_lean_dict=lambda: {"metrics": {}, "citations": {}, "calculations": {}},
        to_cited_dict=lambda: {},
    )
    query_args = SimpleNamespace(
        company="NVIDIA",
        metrics="revenue",
        period="lfy",
        output_format="json",
        force=False,
        strict=False,
        currency="native",
        audit=False,
        show_links="primary",
        citations="inline",
    )
    with patch(
        "edgarpack.query.financials.financials",
        new=AsyncMock(return_value=stub_result),
    ) as mock_fin:
        rc = cli._cmd_query(query_args)
    assert rc == 0
    assert mock_fin.called
    # CLI forwards the user's raw input; financials() resolves internally.
    assert mock_fin.call_args.kwargs.get("company") == "NVIDIA"
