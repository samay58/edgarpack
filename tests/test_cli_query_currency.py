import subprocess
import sys
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

from edgarpack.cli import main
from edgarpack.query.currency import format_cited_currency
from edgarpack.query.models import CitedValue


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "edgarpack.cli", "query", *args],
        capture_output=True,
        text=True,
        cwd=Path.cwd(),
    )


def _run_cmd(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "edgarpack.cli", *args],
        capture_output=True,
        text=True,
        cwd=Path.cwd(),
    )


def test_query_help_advertises_currency_flag():
    result = _run("--help")
    assert result.returncode == 0
    assert "--currency" in result.stdout
    assert "native" in result.stdout
    assert "usd" in result.stdout
    assert "both" in result.stdout


def test_query_rejects_unknown_currency_choice():
    result = _run("BIDU", "revenue", "--currency", "wat")
    assert result.returncode != 0
    assert "invalid choice" in result.stderr.lower() or "invalid" in result.stderr.lower()


def test_query_china_currency_both_shows_usd_native_and_fx():
    result = _run("zhipu", "revenue", "--currency", "both")

    assert result.returncode == 0, result.stderr
    assert "$43.4M" in result.stdout
    assert "native: ¥312.4M" in result.stdout
    assert "FX: data/fx_rates.csv CNY/USD 2024-12-31 average" in result.stdout


def test_query_china_currency_native_omits_usd_conversion():
    result = _run("zhipu", "revenue", "--currency", "native")

    assert result.returncode == 0, result.stderr
    # Bilingual metric cell (Phase 3 english-surface): the fixture's matched
    # extraction label is the English "revenue" caption from a bilingual
    # HKEX filing, so it renders as its own parenthetical, same as any other
    # China-path matched_label.
    assert "Revenue: ¥312.4M" in result.stdout
    assert "$43.4M" not in result.stdout
    assert "FX:" not in result.stdout


def test_query_china_currency_usd_keeps_native_provenance():
    result = _run("zhipu", "revenue", "--currency", "usd")

    assert result.returncode == 0, result.stderr
    assert "Revenue: $43.4M" in result.stdout
    assert "native: ¥312.4M" in result.stdout
    assert "FX: data/fx_rates.csv CNY/USD 2024-12-31 average" in result.stdout


def test_currency_formatter_does_not_treat_share_counts_as_dollars():
    cited = CitedValue(
        value=24_500_000_000,
        unit="shares",
        metric="shares_diluted",
        concept="WeightedAverageNumberOfDilutedSharesOutstanding",
        period_end=date(2026, 1, 25),
        fiscal_year=2026,
        fiscal_period="FY",
        form_type="10-K",
        filed=date(2026, 2, 25),
        accession="0001045810-26-000021",
        cik="0001045810",
        company="NVIDIA CORP",
        reporting_currency="USD",
    )

    assert format_cited_currency(cited, mode="both", metric="shares_diluted") == "24.5B"


def test_which_help_advertises_currency_flag():
    result = _run_cmd("which", "--help")

    assert result.returncode == 0
    assert "--currency" in result.stdout
    assert "native" in result.stdout
    assert "usd" in result.stdout
    assert "both" in result.stdout


def test_which_china_currency_usd_keeps_native_provenance():
    result = _run_cmd("which", "zhipu", "--currency", "usd")

    assert result.returncode == 0, result.stderr
    assert "$43.4M" in result.stdout
    assert "native: ¥312.4M" in result.stdout
    assert "FX: data/fx_rates.csv CNY/USD 2024-12-31 average" in result.stdout


def test_query_unknown_company_falls_through_to_sec(capsys):
    """Unknown-to-universe tickers must pass through to the SEC ticker
    resolver rather than hard-bailing at the universe gate. The SEC
    resolver returns 'Unknown ticker' for genuinely unknown symbols."""
    with patch(
        "edgarpack.query.financials.financials",
        new=AsyncMock(side_effect=ValueError("Unknown ticker: ZZZZZ")),
    ):
        rc = main(["query", "ZZZZZ", "revenue"])

    assert rc == 2
    stderr = capsys.readouterr().err.lower()
    assert "unknown" in stderr
    # Regression guard: must not suggest Chinese aliases for a SEC-shaped ticker.
    assert "alibaba" not in stderr
    assert "baidu" not in stderr
