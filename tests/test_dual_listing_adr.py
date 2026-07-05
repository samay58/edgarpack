"""Tests for the dual-listing-adr packet: one universe.toml entry carrying
SEC + HKEX (+ SSE) identity simultaneously, --venue routing, and the
identify "Listings" block.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from edgarpack import cli
from edgarpack.identity import (
    VenueNotAvailable,
    load_identity,
    resolve,
    select_venue,
    ticker_for_venue,
)

# ---------------------------------------------------------------------------
# Loader: coexisting identifiers on one ResolvedCompany
# ---------------------------------------------------------------------------


@pytest.fixture
def dual_identity(tmp_path):
    cfg = tmp_path / "u.toml"
    cfg.write_text(
        """
[[companies]]
cik = "1234567"
hk_stock_code = "00999"
stock_code = "300999"
listing = "SEC"
alt_tickers = ["ABCD", "9999.HK"]
aliases = ["tripleco"]
"""
    )
    return load_identity(cfg)


def test_loader_preserves_all_three_identifiers_on_one_company(dual_identity):
    r = resolve(dual_identity, ticker="ABCD", company=None)
    assert r.cik == "0001234567"
    assert r.hk_stock_code == "00999"
    assert r.stock_code == "300999"


def test_loader_does_not_blend_hk_code_into_absent_stock_code(tmp_path):
    """Regression: stock_code (SSE identity) must never silently pick up
    hk_stock_code's value just because stock_code itself was left unset."""
    cfg = tmp_path / "u.toml"
    cfg.write_text(
        """
[[companies]]
cik = "1234567"
hk_stock_code = "00999"
listing = "SEC"
alt_tickers = ["ABCD"]
"""
    )
    index = load_identity(cfg)
    r = resolve(index, ticker="ABCD", company=None)
    assert r.hk_stock_code == "00999"
    assert r.stock_code is None


# ---------------------------------------------------------------------------
# Real universe.toml: Alibaba / JD / BYD pilot entries
# ---------------------------------------------------------------------------


@pytest.fixture
def universe_index():
    return load_identity(Path("universe.toml"))


def test_alibaba_resolves_via_every_identifier(universe_index):
    by_ticker = resolve(universe_index, ticker="BABA", company=None)
    by_hk_ticker = resolve(universe_index, ticker="9988.HK", company=None)
    by_alias = resolve(universe_index, ticker=None, company="alibaba")
    by_cik = resolve(universe_index, ticker="1577552", company=None)

    for r in (by_ticker, by_hk_ticker, by_alias, by_cik):
        assert r.cik == "0001577552"
        assert r.hk_stock_code == "09988"


def test_alibaba_default_venue_is_sec(universe_index):
    r = resolve(universe_index, ticker=None, company="alibaba")
    assert r.source == "SEC"


def test_byd_default_venue_is_sse(universe_index):
    r = resolve(universe_index, ticker=None, company="byd")
    assert r.source == "SSE"
    assert r.stock_code == "002594"
    assert r.hk_stock_code == "01211"
    assert r.cik is None


def test_select_venue_hkex_on_alibaba_scopes_to_hkex_only(universe_index):
    resolved = resolve(universe_index, ticker="BABA", company=None)
    routed = select_venue(resolved, "hkex")
    assert routed.source == "HKEX"
    assert routed.hk_stock_code == "09988"
    assert routed.cik is None
    assert routed.stock_code is None


def test_select_venue_sec_on_byd_raises_teaching_error(universe_index):
    resolved = resolve(universe_index, ticker=None, company="byd")
    with pytest.raises(VenueNotAvailable) as excinfo:
        select_venue(resolved, "sec")
    msg = str(excinfo.value)
    assert "does not file with the sec" in msg.lower()
    assert "sse (002594" in msg
    assert "hkex (01211" in msg


def test_ticker_for_venue_finds_alt_ticker_for_each_venue(universe_index):
    resolved = resolve(universe_index, ticker=None, company="alibaba")
    assert ticker_for_venue(universe_index, resolved, "sec") == "BABA"
    assert ticker_for_venue(universe_index, resolved, "hkex") == "9988.HK"

    byd = resolve(universe_index, ticker=None, company="byd")
    assert ticker_for_venue(universe_index, byd, "sse") == "002594"
    assert ticker_for_venue(universe_index, byd, "hkex") == "1211.HK"


# ---------------------------------------------------------------------------
# identify: multi-listing block
# ---------------------------------------------------------------------------


def test_identify_alibaba_shows_listings_line_with_default_marked(capsys):
    rc = cli.main(["identify", "BABA"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Listings: SEC 20-F (CIK 0001577552, ADR: BABA) [default] | HKEX 09988" in out


def test_identify_byd_shows_listings_line_sse_default(capsys):
    rc = cli.main(["identify", "byd"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Listings: SSE 002594 [default] | HKEX 01211" in out


def test_identify_single_listing_filer_output_is_unchanged(capsys):
    rc = cli.main(["identify", "BIDU"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Listings:" not in out
    assert out == (
        "baidu\n"
        "Status: public SEC filer\n"
        "Ticker: BIDU\n"
        "CIK: 0001329099\n"
        "Next: edgarpack query BIDU revenue --period lfy\n"
    )


# ---------------------------------------------------------------------------
# query --venue routing
# ---------------------------------------------------------------------------


def _query_args(**overrides):
    base = dict(
        company="BABA",
        metrics="revenue",
        period="lfy",
        output_format="json",
        force=False,
        strict=False,
        currency="native",
        audit=False,
        show_links="primary",
        citations="inline",
        venue=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_query_venue_hkex_substitutes_the_hk_alt_ticker():
    stub_result = SimpleNamespace(
        company="9988.HK",
        cik="",
        metrics={"revenue": None},
        diagnostics=[],
        to_lean_dict=lambda: {"metrics": {}, "citations": {}, "calculations": {}},
        to_cited_dict=lambda: {},
    )
    with patch(
        "edgarpack.query.financials.financials",
        new=AsyncMock(return_value=stub_result),
    ) as mock_fin:
        rc = cli._cmd_query(_query_args(venue="hkex"))
    assert rc == 0
    assert mock_fin.call_args.kwargs.get("company") == "9988.HK"
    # display_token stays the user's original input, not the substituted one.
    assert mock_fin.call_args.kwargs.get("display_token") == "BABA"


def test_query_venue_sec_on_byd_returns_teaching_error_without_calling_financials(
    capsys,
):
    with patch(
        "edgarpack.query.financials.financials",
        new=AsyncMock(),
    ) as mock_fin:
        rc = cli._cmd_query(_query_args(company="byd", venue="sec"))
    assert rc == 2
    assert not mock_fin.called
    err = capsys.readouterr().err
    assert "does not file with the sec" in err.lower()
    assert "sse (002594" in err
    assert "hkex (01211" in err
