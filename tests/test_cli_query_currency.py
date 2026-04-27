import subprocess
import sys
from pathlib import Path


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
    assert "$42.9M" in result.stdout
    assert "native: ¥312.4M" in result.stdout
    assert "FX: data/fx_rates.csv CNY/USD 2024-12-31 average" in result.stdout


def test_query_china_currency_native_omits_usd_conversion():
    result = _run("zhipu", "revenue", "--currency", "native")

    assert result.returncode == 0, result.stderr
    assert "Revenue: ¥312.4M" in result.stdout
    assert "$42.9M" not in result.stdout
    assert "FX:" not in result.stdout


def test_query_china_currency_usd_keeps_native_provenance():
    result = _run("zhipu", "revenue", "--currency", "usd")

    assert result.returncode == 0, result.stderr
    assert "Revenue: $42.9M" in result.stdout
    assert "native: ¥312.4M" in result.stdout
    assert "FX: data/fx_rates.csv CNY/USD 2024-12-31 average" in result.stdout


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
    assert "$42.9M" in result.stdout
    assert "native: ¥312.4M" in result.stdout
    assert "FX: data/fx_rates.csv CNY/USD 2024-12-31 average" in result.stdout


def test_query_unknown_company_falls_through_to_sec():
    """Unknown-to-universe tickers must pass through to the SEC ticker
    resolver rather than hard-bailing at the universe gate. The SEC
    resolver returns 'Unknown ticker' for genuinely unknown symbols."""
    result = _run("ZZZZZ", "revenue")
    assert result.returncode in (1, 2)
    stderr = result.stderr.lower()
    assert "unknown" in stderr
    # Regression guard: must not suggest Chinese aliases for a SEC-shaped ticker.
    assert "alibaba" not in stderr
    assert "baidu" not in stderr
