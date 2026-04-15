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
