"""Direct convert() tests for the period-average fix.

Uses a small synthetic rates table (not data/fx_rates.csv) so every
expectation is hand-computable: convention="average" must average the
monthly period_average rows across the whole period, start to end
inclusive, not sample a single month.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from edgarpack.fx.convert import RateNotFound, convert
from edgarpack.fx.rates import MonthlyRate, RateTable
from edgarpack.query.currency import convert_cited_to_usd
from edgarpack.query.models import CitedValue

_MONTHLY_AVERAGE = {
    1: 0.90,
    2: 0.95,
    3: 1.00,
    4: 1.10,
    5: 1.20,
    6: 1.15,
    7: 1.05,
    8: 1.25,
    9: 1.30,
    10: 1.40,
    11: 1.35,
    12: 1.50,
}


def _synthetic_rates(skip_months: frozenset[int] = frozenset()) -> RateTable:
    rows = [
        MonthlyRate(
            ccy_pair="XXX/USD",
            month_end=dt.date(2021, month, 28),
            spot_end=avg,
            period_average=avg,
        )
        for month, avg in _MONTHLY_AVERAGE.items()
        if month not in skip_months
    ]
    return RateTable(rows=tuple(rows))


def test_average_over_calendar_fiscal_year():
    # Hand-computed: mean of all 12 monthly averages = 1.1791666...
    rates = _synthetic_rates()
    result = convert(
        value=Decimal("1000000"),
        from_ccy="XXX",
        to_ccy="USD",
        as_of=dt.date(2021, 12, 31),
        convention="average",
        rates=rates,
        period_start=dt.date(2021, 1, 1),
        period_end=dt.date(2021, 12, 31),
    )
    expected_rate = sum(_MONTHLY_AVERAGE.values()) / 12
    assert result.rate_used == pytest.approx(expected_rate)
    assert result.converted_value == pytest.approx(1_000_000 * expected_rate)
    assert "12 month" in result.rate_source_row


def test_average_over_partial_year_period():
    # Hand-computed: mean of Apr through Sep = (1.10+1.20+1.15+1.05+1.25+1.30)/6 = 1.175
    rates = _synthetic_rates()
    result = convert(
        value=Decimal("500000"),
        from_ccy="XXX",
        to_ccy="USD",
        as_of=dt.date(2021, 9, 30),
        convention="average",
        rates=rates,
        period_start=dt.date(2021, 4, 1),
        period_end=dt.date(2021, 9, 30),
    )
    apr_to_sep = [_MONTHLY_AVERAGE[m] for m in range(4, 10)]
    expected_rate = sum(apr_to_sep) / len(apr_to_sep)
    assert expected_rate == pytest.approx(1.175)
    assert result.rate_used == pytest.approx(1.175)
    assert result.converted_value == pytest.approx(500_000 * 1.175)
    assert "6 month" in result.rate_source_row


def test_average_over_single_month_equals_that_months_average():
    # A single-month period must equal that month's own average, matching
    # the pre-fix single-month sampling for the degenerate one-month case.
    rates = _synthetic_rates()
    result = convert(
        value=Decimal("100"),
        from_ccy="XXX",
        to_ccy="USD",
        as_of=dt.date(2021, 4, 30),
        convention="average",
        rates=rates,
        period_start=dt.date(2021, 4, 1),
        period_end=dt.date(2021, 4, 30),
    )
    assert result.rate_used == pytest.approx(_MONTHLY_AVERAGE[4])
    assert result.converted_value == pytest.approx(100 * _MONTHLY_AVERAGE[4])


def test_missing_month_inside_period_fails_closed():
    # July is missing from the table. A fiscal-year average spanning July
    # must raise, never silently average the other 11 months.
    rates = _synthetic_rates(skip_months=frozenset({7}))
    with pytest.raises(RateNotFound):
        convert(
            value=Decimal("1000000"),
            from_ccy="XXX",
            to_ccy="USD",
            as_of=dt.date(2021, 12, 31),
            convention="average",
            rates=rates,
            period_start=dt.date(2021, 1, 1),
            period_end=dt.date(2021, 12, 31),
        )


def _flow_cited_value() -> CitedValue:
    return CitedValue(
        value=1_000_000,
        unit="XXX",
        metric="revenue",
        concept="Revenues",
        period_start=dt.date(2021, 1, 1),
        period_end=dt.date(2021, 12, 31),
        fiscal_year=2021,
        fiscal_period="FY",
        form_type="10-K",
        filed=dt.date(2022, 2, 1),
        accession="0000000000-22-000001",
        cik="0000000000",
        company="Test Co",
    )


def test_convert_cited_to_usd_uses_period_average_not_end_month():
    # Regression for fx-production-wiring: convert_cited_to_usd is the sole
    # production caller of convert() and must pass period_start through for
    # "average" convention, so a flow value spanning a full fiscal year
    # converts at the multi-month mean, not sampled off the end-month rate.
    rates = _synthetic_rates()
    cited = _flow_cited_value()

    fx = convert_cited_to_usd(cited, rates=rates)

    assert fx is not None
    expected_rate = sum(_MONTHLY_AVERAGE.values()) / 12
    end_month_rate = _MONTHLY_AVERAGE[12]
    assert fx.rate_used == pytest.approx(expected_rate)
    assert fx.rate_used != pytest.approx(end_month_rate)
    assert fx.usd_value == pytest.approx(1_000_000 * expected_rate)
