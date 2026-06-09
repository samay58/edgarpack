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

[[companies]]
ticker = "688696"
name = "Chengdu XGIMI Technology Co., Ltd."
listing = "SSE"
aliases = ["xgimi", "chengdu xgimi technology co., ltd."]
stock_code = "688696"
alt_tickers = ["XGIMI"]
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


def test_resolve_sse_stock_code_routes_to_sse(identity):
    r = resolve(identity, ticker="688696", company=None)
    assert r.listing == "SSE"
    assert r.source == "SSE"
    assert r.stock_code == "688696"
    assert r.hk_stock_code is None


def test_resolve_sse_aliases_route_to_sse(identity):
    by_alias = resolve(identity, ticker=None, company="xgimi")
    by_name = resolve(identity, ticker=None, company="Chengdu XGIMI Technology Co., Ltd.")
    by_alt = resolve(identity, ticker="XGIMI", company=None)
    for r in (by_alias, by_name, by_alt):
        assert r.source == "SSE"
        assert r.stock_code == "688696"


def test_resolve_unknown_ticker_raises_with_suggestions(identity):
    with pytest.raises(UnknownCompany) as excinfo:
        resolve(identity, ticker="ZZZZ", company=None)
    assert "Did you mean:" in str(excinfo.value)


def test_resolve_requires_one_of_ticker_or_company(identity):
    with pytest.raises(ValueError):
        resolve(identity, ticker=None, company=None)


def test_private_name_only_company_resolves_by_alias(tmp_path):
    cfg = tmp_path / "u.toml"
    cfg.write_text(
        """
[[companies]]
name = "Shenzhen Shuye Innovative Technology Co., Ltd."
listing = "PRIVATE"
aliases = ["laifen", "shenzhen shuye"]
"""
    )
    index = load_identity(cfg)

    r = resolve(index, ticker=None, company="laifen")

    assert r.private is True
    assert r.ticker == "Shenzhen Shuye Innovative Technology Co., Ltd."
    assert r.listing == "PRIVATE"


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

    r = resolve(index, ticker="688696", company=None)
    assert r.source == "SSE"
    assert r.stock_code == "688696"


def test_live_universe_laifen_routes_to_private():
    from pathlib import Path

    index = load_identity(Path("universe.toml"))
    r = resolve(index, ticker=None, company="laifen")
    assert r.private is True
    assert r.ticker == "Shenzhen Shuye Innovative Technology Co., Ltd."


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
        ("xgimi", "688696"),
        ("tsmc", "TSM"),
        ("brk", "BRK-B"),
    ]:
        r = resolve(index, ticker=None, company=alias)
        assert r.ticker == expected


def test_live_universe_sec_aliases_route_to_primary_tickers():
    from pathlib import Path

    index = load_identity(Path("universe.toml"))

    tsm = resolve(index, ticker=None, company="TSMC")
    assert tsm.source == "SEC"
    assert tsm.ticker == "TSM"
    assert tsm.cik == "0001046179"

    brk = resolve(index, ticker=None, company="BRK")
    assert brk.source == "SEC"
    assert brk.ticker == "BRK-B"
    assert brk.cik == "0001067983"


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


def test_duplicate_ticker_raises_at_load_time(tmp_path):
    cfg = tmp_path / "u.toml"
    cfg.write_text(
        """
[[companies]]
ticker = "DUP"
listing = "NYSE"
cik = "0000000001"

[[companies]]
ticker = "DUP"
listing = "NASDAQ"
cik = "0000000002"
"""
    )
    with pytest.raises(AmbiguousCompany, match="DUP"):
        load_identity(cfg)


def test_resolved_cik_is_zero_padded(tmp_path):
    cfg = tmp_path / "u.toml"
    cfg.write_text(
        """
[[companies]]
ticker = "PAD"
listing = "NYSE"
cik = "320193"
"""
    )
    index = load_identity(cfg)
    assert index.by_ticker["PAD"].cik == "0000320193"
