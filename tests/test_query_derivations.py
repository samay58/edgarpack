"""Multi-year YoY derivation regression tests.

Exercises revenue_growth_yoy, gross_margin_trend, r_and_d_intensity, and
revenue_per_employee against the regenerated MiniMax and Zhipu fixtures.
"""

from __future__ import annotations

import asyncio

from edgarpack.query.financials import financials


def test_minimax_revenue_growth_yoy_present():
    res = asyncio.run(financials(company="minimax", metrics="revenue_growth_yoy", period="lfy"))
    val = res.metrics.get("revenue_growth_yoy")
    assert val is not None
    # MiniMax FY23 revenue 3,460k -> FY24 revenue 30,523k: ~7.8x growth.
    assert val.value > 0.5


def test_zhipu_revenue_growth_yoy_present():
    res = asyncio.run(financials(company="zhipu", metrics="revenue_growth_yoy", period="lfy"))
    val = res.metrics.get("revenue_growth_yoy")
    assert val is not None
    # Zhipu FY23 -> FY24: 124,538 -> 312,414 = +150.8%.
    assert 1.0 <= val.value <= 2.0


def test_minimax_rd_intensity_reasonable():
    res = asyncio.run(financials(company="minimax", metrics="r_and_d_intensity", period="lfy"))
    val = res.metrics.get("r_and_d_intensity")
    assert val is not None
    # MiniMax FY24: R&D 188,979 / revenue 30,523 ~ 6.2x.
    assert val.value > 1.0


def test_zhipu_rd_intensity_reasonable():
    res = asyncio.run(financials(company="zhipu", metrics="r_and_d_intensity", period="lfy"))
    val = res.metrics.get("r_and_d_intensity")
    assert val is not None
    # Zhipu FY24: R&D 2,195,436 / revenue 312,414 ~ 7.0x (pre-revenue AI lab).
    assert val.value > 1.0


def test_minimax_revenue_per_employee_present():
    res = asyncio.run(financials(company="minimax", metrics="revenue_per_employee", period="lfy"))
    val = res.metrics.get("revenue_per_employee")
    assert val is not None
    # Native USD, MiniMax ~30M / 385 employees ~ 79k / employee.
    assert val.value > 1_000


def test_zhipu_revenue_per_employee_present():
    res = asyncio.run(financials(company="zhipu", metrics="revenue_per_employee", period="lfy"))
    val = res.metrics.get("revenue_per_employee")
    assert val is not None
    # Native CNY, Zhipu ~312M / 883 employees ~ 353k CNY / employee.
    assert val.value > 100_000


def test_gross_margin_trend_shifts_across_years():
    # Both MiniMax and Zhipu should have distinct FY24 and FY23 gross margins.
    res = asyncio.run(financials(company="zhipu", metrics="gross_margin_trend", period="lfy"))
    val = res.metrics.get("gross_margin_trend")
    assert val is not None
    # Should not be 0 (which would indicate the offset did not propagate).
    assert abs(val.value) > 1e-6


def test_sec_revenue_per_employee_resolves_after_text_scan_fallback():
    """When headcount only populates via the 10-K text-scan fallback (i.e.
    the filer omits dei:EntityNumberOfEmployees from XBRL), derived metrics
    that depend on headcount must still compute. Regression: they used to
    be n/a because the derivation ran before the fallback populated the
    value."""
    res = asyncio.run(
        financials(company="NVDA", metrics="revenue_per_employee,headcount", period="lfy")
    )
    hc = res.metrics.get("headcount")
    rpe = res.metrics.get("revenue_per_employee")
    assert hc is not None, "headcount must populate via text-scan fallback"
    assert rpe is not None, "revenue_per_employee must follow once headcount resolves"
    # NVIDIA reports ~30k-50k employees and ~$100B-$300B revenue, so
    # per-employee revenue is in the low millions.
    assert 500_000 < rpe.value < 20_000_000
