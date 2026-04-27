from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from edgarpack.cli import main


def test_identify_sse_alias_shows_a_share_next_step(capsys):
    rc = main(["identify", "xgimi"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "Status: public A-share / SSE" in out
    assert "Stock Code: 688696" in out
    assert "edgarpack build-sse xgimi --latest-annual" in out


def test_identify_a_share_code_verifies_via_cninfo(capsys):
    selected = SimpleNamespace(company_name="Insta360", stock_code="688775")
    with (
        patch("edgarpack.cli._find_latest_sse_annual_report", return_value=selected) as mock_find,
        patch("edgarpack.sec.tickers.resolve_company") as mock_resolve,
    ):
        rc = main(["identify", "688775"])

    assert rc == 0
    mock_find.assert_called_once_with("688775")
    mock_resolve.assert_not_called()
    out = capsys.readouterr().out
    assert "Status: public A-share / SSE" in out
    assert "Insta360" in out
    assert "Stock Code: 688775" in out
    assert "edgarpack build-sse 688775 --latest-annual --with-chunks" in out


def test_identify_unknown_a_share_code_does_not_try_sec(capsys):
    with (
        patch("edgarpack.cli._find_latest_sse_annual_report", side_effect=LookupError("missing")),
        patch("edgarpack.sec.tickers.resolve_company") as mock_resolve,
    ):
        rc = main(["identify", "688999"])

    assert rc == 0
    mock_resolve.assert_not_called()
    out = capsys.readouterr().out
    assert "Status: unknown China A-share code" in out
    assert "No SEC fallback attempted" in out


def test_identify_laifen_uses_private_universe_entry_without_sec(capsys):
    with (
        patch("edgarpack.sec.tickers.resolve_company") as mock_resolve,
        patch("edgarpack.sec.tickers.resolve_company_by_name") as mock_resolve_name,
    ):
        rc = main(["identify", "laifen"])

    assert rc == 0
    mock_resolve.assert_not_called()
    mock_resolve_name.assert_not_called()
    out = capsys.readouterr().out
    assert "Shenzhen Shuye Innovative Technology Co., Ltd." in out
    assert "Status: private company" in out
    assert "No public filing workflow is available" in out


def test_identify_private_name_only_company_from_universe(tmp_path, monkeypatch, capsys):
    (tmp_path / "universe.toml").write_text(
        """
[[companies]]
name = "Shenzhen Shuye Innovative Technology Co., Ltd."
listing = "PRIVATE"
aliases = ["laifen", "shenzhen shuye"]
"""
    )
    monkeypatch.chdir(tmp_path)

    rc = main(["identify", "laifen"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "Status: private company" in out
    assert "No public filing workflow is available" in out
