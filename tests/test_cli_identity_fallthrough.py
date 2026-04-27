"""Regression tests for CLI identity resolution (edgarpack-n8e).

The China Lens identity resolver is an *additive* routing layer. Any ticker
not registered in universe.toml must fall through to the SEC ticker
resolver unchanged. Failing closed breaks the 'query any public ticker'
core workflow.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from edgarpack import cli


def _args(company: str) -> SimpleNamespace:
    return SimpleNamespace(
        company=company,
        metrics="revenue",
        period="lfy",
        force=False,
        output_format="table",
        currency="native",
        strict=False,
    )


def test_unknown_ticker_reaches_financials_entrypoint():
    """GSAT (not in universe.toml) must reach financials()."""
    with patch("edgarpack.query.financials.financials") as mock_fin:
        mock_fin.side_effect = ValueError("Unknown ticker: GSAT")
        rc = cli._cmd_query(_args("GSAT"))
    assert mock_fin.called, "financials() was not reached; CLI hard-gated on universe"
    passed_company = mock_fin.call_args.kwargs.get("company") or mock_fin.call_args.args[0]
    assert passed_company == "GSAT"
    assert rc == 2


def test_hkex_ticker_still_routes_through_financials():
    """Universe-registered HKEX ticker must still reach financials()
    (which internally dispatches to the pack path)."""
    with patch("edgarpack.query.financials.financials") as mock_fin:
        # Build a minimal QueryResult-like stub to let the render path run.
        mock_fin.side_effect = ValueError("stub")
        rc = cli._cmd_query(_args("minimax"))
    assert mock_fin.called
    assert rc in (1, 2)


def test_sse_code_still_routes_through_financials_not_sec_gate():
    """Universe-registered A-share codes must reach the China pack query path."""
    with patch("edgarpack.query.financials.financials") as mock_fin:
        mock_fin.side_effect = ValueError("stub")
        rc = cli._cmd_query(_args("688696"))
    assert mock_fin.called
    passed_company = mock_fin.call_args.kwargs.get("company") or mock_fin.call_args.args[0]
    assert passed_company == "688696"
    assert rc in (1, 2)


def test_ambiguous_alias_still_bails_cleanly(capsys):
    """A real alias collision must surface as exit 2 with a clear message."""
    from edgarpack.identity import AmbiguousCompany

    with patch("edgarpack.identity.resolve") as mock_resolve:
        mock_resolve.side_effect = AmbiguousCompany("Alias 'foo' claimed by A and B")
        rc = cli._cmd_query(_args("foo"))
    captured = capsys.readouterr()
    assert rc == 2
    assert "claimed" in captured.err.lower()
