"""The ltm/mrq selectors reject a window far older than the company's newest data."""

from __future__ import annotations

from datetime import date

from edgarpack.query.financials import _reject_stale_window
from edgarpack.query.models import CitedValue, Diagnostic


def _facts(latest_end: str) -> dict:
    row = {
        "val": 1,
        "start": "2026-07-01",
        "end": latest_end,
        "fy": 2026,
        "fp": "Q3",
        "form": "10-Q",
        "accn": "a",
        "filed": "2026-10-29",
    }
    typo = {**row, "start": "2206-07-01", "end": "2206-09-30"}  # mistyped context date
    # A dividend declared after quarter end: an instant dated past the period.
    event = {**row, "start": None, "end": "2026-10-20"}
    return {"us-gaap": {"Revenues": {"units": {"USD": [row, typo, event]}}}}


def _cited(period_end: date) -> CitedValue:
    return CitedValue(
        value=1.0,
        unit="USD",
        metric="revenue",
        concept="Old",
        period_start=None,
        period_end=period_end,
        fiscal_year=period_end.year,
        fiscal_period="LTM",
        form_type="10-Q",
        filed=period_end,
        accession="x",
        cik="1",
        company="C",
    )


def test_ltm_1_from_an_abandoned_concept_is_rejected() -> None:
    diagnostics: list[Diagnostic] = []
    stale = _cited(date(2024, 3, 31))  # GOOGL: old revenue tag stops in 2024
    out = _reject_stale_window(
        stale, _facts("2026-09-30"), "revenue", "Old", "ltm-1", 0, diagnostics
    )
    assert out is None
    assert [d.kind for d in diagnostics] == ["period_mismatch"]


def test_window_one_year_back_for_ltm_1_is_kept() -> None:
    diagnostics: list[Diagnostic] = []
    ok = _cited(date(2025, 9, 30))
    assert (
        _reject_stale_window(ok, _facts("2026-09-30"), "revenue", "c", "ltm-1", 0, diagnostics)
        is ok
    )
    # A derived component asking for the prior year (offset -1) is allowed the same reach.
    assert (
        _reject_stale_window(ok, _facts("2026-09-30"), "revenue", "c", "ltm", -1, diagnostics) is ok
    )
    assert diagnostics == []


def test_one_quarter_old_ltm_is_rejected() -> None:
    """ORCL: `Revenues` stops at FY-end May 2026 while the company reports through
    August; the fallback concept must answer instead."""
    diagnostics: list[Diagnostic] = []
    lagging = _cited(date(2026, 6, 30))
    assert (
        _reject_stale_window(lagging, _facts("2026-09-30"), "revenue", "c", "ltm", 0, diagnostics)
        is None
    )


def test_subsequent_event_dates_do_not_move_the_anchor() -> None:
    ok = _cited(date(2026, 9, 30))
    assert _reject_stale_window(ok, _facts("2026-09-30"), "revenue", "c", "mrq", 0, []) is ok


def test_mrq_after_a_10k_keeps_the_last_reported_quarter() -> None:
    """AAPL right after its 10-K: the year ends in September, but the newest
    standalone quarter on file ends in June. That is still the MRQ."""
    facts = _facts("2026-06-27")
    annual = {
        "val": 1,
        "start": "2025-09-28",
        "end": "2026-09-26",
        "fy": 2026,
        "fp": "FY",
        "form": "10-K",
        "accn": "k",
        "filed": "2026-11-03",
    }
    facts["us-gaap"]["Revenues"]["units"]["USD"].append(annual)
    june = _cited(date(2026, 6, 27))
    assert _reject_stale_window(june, facts, "revenue", "c", "mrq", 0, []) is june
    # The LTM, though, must not stop at June once the full year is filed.
    assert _reject_stale_window(june, facts, "revenue", "c", "ltm", 0, []) is None


def test_per_share_ltm_keeps_its_disclosed_annual_fallback() -> None:
    annual = _cited(date(2025, 12, 31))
    assert (
        _reject_stale_window(annual, _facts("2026-09-30"), "eps_diluted", "c", "ltm", 0, [])
        is annual
    )


def test_other_periods_are_untouched() -> None:
    old = _cited(date(2020, 12, 31))
    assert _reject_stale_window(old, _facts("2026-09-30"), "revenue", "c", "lfy-5", 0, []) is old
