"""Tests for harvest universe loading."""

import tempfile
from pathlib import Path

from edgarpack.harvest.universe import CompanySpec, UniverseConfig, load_universe


def test_load_universe_basic():
    """Load a minimal universe.toml."""
    content = """
[defaults]
forms_10k = 3
forms_10q = 6
forms_8k = 2

[[companies]]
ticker = "NVDA"

[[companies]]
ticker = "AMD"
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write(content)
        f.flush()
        config = load_universe(Path(f.name))

    assert config.defaults_10k == 3
    assert config.defaults_10q == 6
    assert config.defaults_8k == 2
    assert len(config.companies) == 2
    assert config.companies[0].ticker == "NVDA"
    assert config.companies[1].ticker == "AMD"


def test_load_universe_with_overrides():
    """Per-company overrides take precedence over defaults."""
    content = """
[defaults]
forms_10k = 2
forms_10q = 4
forms_8k = 5

[[companies]]
ticker = "TSM"
cik = "0001046179"
forms_10q = 0
forms_20f = 2
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write(content)
        f.flush()
        config = load_universe(Path(f.name))

    spec = config.companies[0]
    assert spec.ticker == "TSM"
    assert spec.cik == "0001046179"
    assert spec.forms_10q == 0
    assert spec.forms_20f == 2

    counts = config.form_counts(spec)
    assert "10-K" in counts
    assert counts["10-K"] == 2
    assert "10-Q" not in counts  # 0 means excluded
    assert "20-F" in counts
    assert counts["20-F"] == 2
    assert "8-K" in counts
    assert counts["8-K"] == 5


def test_form_counts_defaults():
    """Default form counts apply when not overridden."""
    config = UniverseConfig(
        defaults_10k=2,
        defaults_10q=4,
        defaults_8k=5,
        companies=[CompanySpec(ticker="NVDA")],
    )
    counts = config.form_counts(config.companies[0])
    assert counts == {"10-K": 2, "10-Q": 4, "8-K": 5}


def test_form_counts_zero_excludes():
    """Setting a form count to 0 excludes it."""
    config = UniverseConfig(
        defaults_10k=2,
        defaults_10q=4,
        defaults_8k=5,
        companies=[CompanySpec(ticker="NVDA", forms_8k=0)],
    )
    counts = config.form_counts(config.companies[0])
    assert "8-K" not in counts
    assert counts == {"10-K": 2, "10-Q": 4}


def test_form_counts_private_company_has_no_sec_fetch_plan():
    config = UniverseConfig(
        defaults_10k=2,
        defaults_10q=4,
        defaults_8k=5,
        companies=[
            CompanySpec(
                name="Shenzhen Shuye Innovative Technology Co., Ltd.",
                listing="PRIVATE",
            )
        ],
    )

    assert config.form_counts(config.companies[0]) == {}


def test_company_spec_accepts_hk_listing_fields(tmp_path):
    cfg = tmp_path / "u.toml"
    cfg.write_text(
        """
[[companies]]
ticker = "0700.HK"
listing = "HKEX"
aliases = ["tencent", "tencent holdings"]
hk_stock_code = "00700"
"""
    )
    from edgarpack.harvest.universe import load_universe

    universe = load_universe(cfg)
    spec = universe.companies[0]
    assert spec.ticker == "0700.HK"
    assert spec.listing == "HKEX"
    assert spec.aliases == ["tencent", "tencent holdings"]
    assert spec.hk_stock_code == "00700"


def test_company_spec_accepts_alt_tickers_for_dual_listed(tmp_path):
    cfg = tmp_path / "u.toml"
    cfg.write_text(
        """
[[companies]]
ticker = "BABA"
listing = "NYSE"
aliases = ["alibaba"]
alt_tickers = ["9988.HK"]
"""
    )
    from edgarpack.harvest.universe import load_universe

    universe = load_universe(cfg)
    spec = universe.companies[0]
    assert spec.alt_tickers == ["9988.HK"]


def test_company_spec_listing_defaults_to_none_for_legacy_entries(tmp_path):
    cfg = tmp_path / "u.toml"
    cfg.write_text(
        """
[[companies]]
ticker = "NVDA"
"""
    )
    from edgarpack.harvest.universe import load_universe

    universe = load_universe(cfg)
    spec = universe.companies[0]
    assert spec.listing is None
    assert spec.aliases == []
    assert spec.alt_tickers == []
    assert spec.hk_stock_code is None
