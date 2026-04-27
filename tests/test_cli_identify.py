from __future__ import annotations

from unittest.mock import patch

from edgarpack.cli import main


def test_identify_sse_alias_shows_a_share_next_step(capsys):
    rc = main(["identify", "xgimi"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "Status: public A-share / SSE" in out
    assert "Stock Code: 688696" in out
    assert "edgarpack build-sse xgimi --latest-annual" in out


def test_identify_unknown_a_share_code_does_not_try_sec(capsys):
    with patch("edgarpack.sec.tickers.resolve_company") as mock_resolve:
        rc = main(["identify", "688999"])

    assert rc == 0
    mock_resolve.assert_not_called()
    out = capsys.readouterr().out
    assert "Status: unknown China A-share code" in out
    assert "No SEC fallback attempted" in out


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

