"""Identity resolution tests."""

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


def test_live_universe_resolves_all_six_public_targets():
    from pathlib import Path

    index = load_identity(Path("universe.toml"))

    for ticker in ["BIDU", "PDD", "BABA", "JD"]:
        r = resolve(index, ticker=ticker, company=None)
        assert r.source == "SEC", f"{ticker} should route to SEC"
        assert r.private is False

    for ticker in ["0700.HK", "3690.HK", "9988.HK", "9618.HK"]:
        r = resolve(index, ticker=ticker, company=None)
        assert r.source == "HKEX", f"{ticker} should route to HKEX"
        assert r.private is False


def test_live_universe_resolves_every_alias():
    from pathlib import Path

    index = load_identity(Path("universe.toml"))
    for alias, expected in [
        ("baidu", "BIDU"),
        ("pinduoduo", "PDD"),
        ("alibaba", "BABA"),
        ("jd.com", "JD"),
        ("tencent", "0700.HK"),
        ("meituan", "3690.HK"),
    ]:
        r = resolve(index, ticker=None, company=alias)
        assert r.ticker == expected


def test_minimax_routes_to_hkex():
    from pathlib import Path

    from edgarpack.identity import load_identity, resolve

    index = load_identity(Path("universe.toml"))
    r = resolve(index, ticker=None, company="minimax")
    assert r.source == "HKEX"
    assert r.private is False
    assert r.hk_stock_code == "00100"


def test_zhipu_routes_to_hkex():
    from pathlib import Path

    from edgarpack.identity import load_identity, resolve

    index = load_identity(Path("universe.toml"))
    r = resolve(index, ticker=None, company="zhipu")
    assert r.source == "HKEX"
    assert r.private is False
    assert r.hk_stock_code == "02513"


def test_zhipu_alias_z_ai_resolves():
    from pathlib import Path

    from edgarpack.identity import load_identity, resolve

    index = load_identity(Path("universe.toml"))
    r = resolve(index, ticker=None, company="z.ai")
    assert r.ticker == "2513.HK"
