"""Identity resolution for China query parity (edgarpack-2yg)."""

import pytest

from edgarpack.identity import (
    AmbiguousCompany,
    ResolvedCompany,
    UnknownCompany,
    load_identity,
    resolve,
)


@pytest.fixture
def identity(tmp_path):
    cfg = tmp_path / "u.toml"
    cfg.write_text(
        """
[[companies]]
ticker = "BIDU"
listing = "NASDAQ"
cik = "0001329099"
forms_20f = 3
aliases = ["baidu"]

[[companies]]
ticker = "0700.HK"
listing = "HKEX"
aliases = ["tencent", "tencent holdings"]
hk_stock_code = "00700"

[[companies]]
ticker = "BABA"
listing = "NYSE"
cik = "0001577552"
forms_20f = 3
aliases = ["alibaba", "alibaba group"]
alt_tickers = ["9988.HK"]
"""
    )
    return load_identity(cfg)


def test_resolve_us_ticker_routes_to_sec(identity):
    r = resolve(identity, ticker="BIDU", company=None)
    assert isinstance(r, ResolvedCompany)
    assert r.ticker == "BIDU"
    assert r.listing == "NASDAQ"
    assert r.source == "SEC"
    assert r.cik == "0001329099"
    assert r.private is False


def test_resolve_hk_suffix_ticker_routes_to_hkex(identity):
    r = resolve(identity, ticker="0700.HK", company=None)
    assert r.listing == "HKEX"
    assert r.source == "HKEX"
    assert r.hk_stock_code == "00700"


def test_resolve_alt_ticker_routes_to_alt_listing(identity):
    r = resolve(identity, ticker="9988.HK", company=None)
    assert r.source == "HKEX"
    assert r.ticker == "9988.HK"


def test_resolve_company_alias_picks_primary_listing(identity):
    r = resolve(identity, ticker=None, company="tencent")
    assert r.ticker == "0700.HK"
    assert r.source == "HKEX"


def test_resolve_unknown_ticker_raises_with_suggestions(identity):
    with pytest.raises(UnknownCompany) as excinfo:
        resolve(identity, ticker="ZZZZ", company=None)
    assert "BIDU" in str(excinfo.value) or "BABA" in str(excinfo.value)


def test_resolve_requires_one_of_ticker_or_company(identity):
    with pytest.raises(ValueError):
        resolve(identity, ticker=None, company=None)


def test_ambiguous_alias_raises_at_load_time(tmp_path):
    cfg = tmp_path / "u.toml"
    cfg.write_text(
        """
[[companies]]
ticker = "BIDU"
aliases = ["baidu"]

[[companies]]
ticker = "0700.HK"
aliases = ["baidu"]
"""
    )
    with pytest.raises(AmbiguousCompany) as excinfo:
        load_identity(cfg)
    assert "baidu" in str(excinfo.value).lower()
