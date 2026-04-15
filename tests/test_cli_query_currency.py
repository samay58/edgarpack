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



def test_query_hkex_ticker_exits_with_not_yet_supported_message():
    result = _run("0700.HK", "revenue")
    assert result.returncode == 2
    err = result.stderr.lower()
    assert "hkex" in err or "hong kong" in err
    assert "not yet" in err or "unsupported" in err or "pending" in err


def test_query_unknown_company_exits_with_suggestion():
    result = _run("ZZZZZ", "revenue")
    assert result.returncode == 2
    assert "unknown" in result.stderr.lower() or "did you mean" in result.stderr.lower()
