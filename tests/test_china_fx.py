"""FX convention tests."""

import datetime as dt
from decimal import Decimal
from pathlib import Path

import pytest

from edgarpack.fx import ConvertedValue, RateNotFound, convert, load_rates


@pytest.fixture(scope="module")
def rates():
    return load_rates(Path("data/fx_rates.csv"))


def test_spot_convention_uses_month_end_spot(rates):
    result = convert(
        value=Decimal("1576000000000"),
        from_ccy="CNY",
        to_ccy="USD",
        as_of=dt.date(2023, 12, 31),
        convention="spot",
        rates=rates,
    )
    assert isinstance(result, ConvertedValue)
    assert 0.138 <= result.rate_used <= 0.145
    assert 215_000_000_000 <= result.converted_value <= 228_000_000_000
    assert result.convention == "spot"
    assert "2023-12" in result.rate_source_row


def test_average_convention_uses_period_average(rates):
    result = convert(
        value=Decimal("609015000000"),
        from_ccy="CNY",
        to_ccy="USD",
        as_of=dt.date(2023, 12, 31),
        convention="average",
        period_end=dt.date(2023, 12, 31),
        rates=rates,
    )
    assert 0.139 <= result.rate_used <= 0.145
    assert 84_000_000_000 <= result.converted_value <= 89_000_000_000


def test_hkd_to_usd_conversion(rates):
    result = convert(
        value=Decimal("1000000000"),
        from_ccy="HKD",
        to_ccy="USD",
        as_of=dt.date(2023, 12, 31),
        convention="spot",
        rates=rates,
    )
    assert 0.125 <= result.rate_used <= 0.130


def test_usd_to_usd_is_identity(rates):
    result = convert(
        value=Decimal("123456789"),
        from_ccy="USD",
        to_ccy="USD",
        as_of=dt.date(2023, 6, 30),
        convention="spot",
        rates=rates,
    )
    assert result.rate_used == 1.0
    assert result.converted_value == 123456789.0


def test_missing_rate_raises(rates):
    with pytest.raises(RateNotFound):
        convert(
            value=Decimal("100"),
            from_ccy="CNY",
            to_ccy="USD",
            as_of=dt.date(1950, 1, 1),
            convention="spot",
            rates=rates,
        )


def test_converted_value_carries_provenance(rates):
    result = convert(
        value=Decimal("100"),
        from_ccy="CNY",
        to_ccy="USD",
        as_of=dt.date(2023, 12, 31),
        convention="spot",
        rates=rates,
    )
    assert result.from_ccy == "CNY"
    assert result.to_ccy == "USD"
    assert result.as_of == dt.date(2023, 12, 31)
    assert result.rate_source_row  # non-empty
