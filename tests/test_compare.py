import json
import subprocess
import sys
from pathlib import Path


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "edgarpack.cli", "compare", *args],
        capture_output=True,
        text=True,
        cwd=Path.cwd(),
    )


def test_compare_help_lists_flags():
    r = _run("--help")
    assert r.returncode == 0
    out = r.stdout.lower()
    assert "companies" in out
    assert "--metrics" in out
    assert "--format" in out


def test_compare_three_lab_companies_table():
    r = _run("minimax", "zhipu", "--metrics", "revenue,net_income", "--format", "table")
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert "minimax" in out.lower()
    assert "zhipu" in out.lower()
    assert "revenue" in out.lower()
    assert "net_income" in out.lower()


def test_compare_json_format_parses():
    r = _run("minimax", "zhipu", "--metrics", "revenue", "--format", "json")
    assert r.returncode == 0, r.stderr
    parsed = json.loads(r.stdout)
    assert "companies" in parsed
    assert len(parsed["companies"]) == 2
    tickers = {c["ticker"] for c in parsed["companies"]}
    assert {"minimax", "zhipu"} == tickers


def test_compare_markdown_format_emits_table_syntax():
    r = _run("minimax", "zhipu", "--metrics", "revenue", "--format", "markdown")
    assert r.returncode == 0, r.stderr
    assert "|" in r.stdout
    assert "---" in r.stdout


def test_compare_unknown_company_exits_2():
    r = _run("minimax", "ZZZZZZ", "--metrics", "revenue")
    assert r.returncode == 2
    assert "unknown" in r.stderr.lower() or "no" in r.stderr.lower()


def test_compare_emits_currency_in_output():
    r = _run("minimax", "zhipu", "--metrics", "revenue", "--format", "table")
    out = r.stdout
    assert "USD" in out or "$" in out
    assert "CNY" in out or "RMB" in out or "¥" in out


def test_compare_footer_never_reports_non_currency_unit():
    """Regression: non-currency units (headcount, pure) must not leak into
    the 'reported in ...' footer when mixed with real currencies or when
    queried in isolation."""
    r = _run(
        "minimax",
        "zhipu",
        "--metrics",
        "revenue,headcount,r_and_d_intensity,revenue_growth_yoy",
        "--format",
        "table",
    )
    out = r.stdout
    assert "reported in headcount" not in out
    assert "reported in pure" not in out
    # Real currencies still appear on the footer for non-headcount metrics.
    assert "reported in USD" in out or "reported in CNY" in out


def test_compare_headcount_only_falls_back_to_usd():
    """When every metric is non-currency the footer defaults to USD rather
    than showing a unit sentinel."""
    r = _run("minimax", "zhipu", "--metrics", "headcount", "--format", "table")
    out = r.stdout
    assert "reported in headcount" not in out
    assert "reported in USD" in out
