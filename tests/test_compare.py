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


def test_compare_header_states_period_and_resolved_fy():
    """Output must always lead with the requested period and the resolved
    fiscal year(s). No silent defaults."""
    r = _run("minimax", "zhipu", "--metrics", "revenue", "--format", "table")
    out = r.stdout
    # First non-empty line is the period header.
    first_line = next(line for line in out.splitlines() if line.strip())
    assert first_line.startswith("Period: lfy")
    assert "FY2024" in first_line


def test_compare_json_includes_period_request():
    """JSON output must carry the requested period as a top-level field."""
    import json as _json

    r = _run("minimax", "zhipu", "--metrics", "revenue", "--period", "annual:3", "--format", "json")
    data = _json.loads(r.stdout)
    assert data["period_request"] == "annual:3"


def test_compare_header_flags_mismatched_fiscal_years():
    """When companies resolve lfy/lfy-N to different fiscal years the
    header must surface the divergence, not paper over it."""
    r = _run("NVDA", "AMD", "--metrics", "revenue", "--period", "lfy-1", "--format", "table")
    out = r.stdout
    first_line = next(line for line in out.splitlines() if line.strip())
    # NVIDIA's fiscal year ends January; AMD's ends December. lfy-1 resolves
    # to different calendar fiscal years, which the header must call out.
    assert "fiscal years differ" in first_line
    assert "NVDA=" in first_line
    assert "AMD=" in first_line


def test_gather_fetches_concurrently():
    """Covers edgarpack-r9a: _gather must fan out with asyncio.gather so
    N tickers hit the pipeline in parallel, not sequentially."""
    import asyncio
    import unittest.mock as _mock

    from edgarpack import compare as _compare

    max_in_flight = 0
    in_flight = 0

    async def _fake_fetch_one(name, metrics, period, *, strict=False):
        nonlocal in_flight, max_in_flight
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        # Yield so sibling tasks can start before we finish.
        await asyncio.sleep(0.02)
        in_flight -= 1
        col = _compare.CompanyColumn(
            ticker=name,
            company=name,
            period="FY2024",
            reporting_currency="USD",
            metrics={},
        )
        return col, []

    with _mock.patch.object(_compare, "_fetch_one", side_effect=_fake_fetch_one):
        cols, _ = asyncio.run(
            _compare._gather(["A", "B", "C", "D"], "revenue", "lfy", strict=False)
        )

    assert len(cols) == 4
    assert max_in_flight >= 2, (
        f"expected concurrent fan-out, saw max {max_in_flight} tasks in flight (sequential path?)"
    )


# Format-layer behavior after Task 3 delegation to format_number.


def test_format_value_abbrev_usd_large_value():
    from edgarpack.compare import _format_value

    v = {"value": 5_900_000_000, "currency": "USD", "usd_value": 5_900_000_000}
    assert _format_value(v) == "$5.9B"


def test_format_value_abbrev_usd_negative_parens():
    from edgarpack.compare import _format_value

    v = {"value": -532_000_000, "currency": "USD", "usd_value": -532_000_000}
    assert _format_value(v) == "($532M)"


def test_format_value_native_with_usd_conversion():
    from edgarpack.compare import _format_value

    v = {"value": 28_262_000_000, "currency": "EUR", "usd_value": 30_000_000_000}
    # USD portion scales at B with .0 preserved (B-suffix currency keeps decimals).
    # Native EUR: 28.262B -> "€28.3B".
    assert _format_value(v) == "$30.0B (native: €28.3B)"


def test_compare_currency_native_respects_flag():
    r = _run(
        "minimax",
        "zhipu",
        "--metrics",
        "revenue",
        "--currency",
        "native",
        "--format",
        "table",
    )

    assert r.returncode == 0, r.stderr
    assert "¥312.4M" in r.stdout
    assert "$42.9M" not in r.stdout
    assert "FX:" not in r.stdout


def test_compare_currency_usd_shows_native_fx_provenance():
    r = _run(
        "minimax",
        "zhipu",
        "--metrics",
        "revenue",
        "--currency",
        "usd",
        "--format",
        "table",
    )

    assert r.returncode == 0, r.stderr
    assert "$42.9M" in r.stdout
    assert "native: ¥312.4M" in r.stdout
    assert "FX: data/fx_rates.csv CNY/USD 2024-12-31 average" in r.stdout


def test_format_value_ratio_uses_pure_formatter():
    from edgarpack.compare import _format_value

    v = {"value": 0.125, "ratio": 0.125, "currency": "USD"}
    assert _format_value(v) == "12.5%"


def test_format_value_per_employee_usd_small_gets_two_decimals():
    from edgarpack.compare import _format_value

    # 42.5 is under the $100 small-value threshold -> 2 decimals.
    v = {"value": 42.5, "per_employee_usd": 42.5}
    assert _format_value(v) == "$42.50"


def test_format_value_headcount_renders_with_scale():
    from edgarpack.compare import _format_value

    v = {"value": 12_345, "headcount": 12_345}
    assert _format_value(v) == "12.3K"


def test_format_value_none_value_returns_na():
    from edgarpack.compare import _format_value

    assert _format_value(None) == "n/a"
    assert _format_value({"value": None}) == "n/a"


def test_bare_value_empty_currency_renders_two_decimals() -> None:
    """Empty-currency path routes through format_number's unknown-unit
    fallback: plain comma thousands with 2 decimals. This is a behavior
    change from the pre-refactor _format_value which used .0f (no
    decimals). Pinned explicitly so a future change surfaces the intent."""
    from edgarpack.compare import _format_value

    v = {"value": 12_345.0, "currency": ""}
    assert _format_value(v) == "12,345.00"
