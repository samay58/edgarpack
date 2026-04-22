"""Tests for the canonical numeric formatter shared by query/comps and compare."""

from __future__ import annotations

from edgarpack.query.formatting import format_number


class TestScaleAndPrecision:
    def test_small_currency_gets_two_decimals(self) -> None:
        assert format_number(3.62, "USD") == "$3.62"

    def test_small_eur_gets_two_decimals(self) -> None:
        assert format_number(42.5, "EUR") == "€42.50"

    def test_billions_one_decimal(self) -> None:
        assert format_number(5_900_000_000, "USD") == "$5.9B"

    def test_millions_integer_strips_trailing_zero(self) -> None:
        assert format_number(474_000_000, "count") == "474M"

    def test_millions_fractional_keeps_one_decimal(self) -> None:
        assert format_number(474_300_000, "count") == "474.3M"

    def test_thousands(self) -> None:
        assert format_number(12_500, "USD") == "$12.5K"

    def test_below_thousand_no_scale(self) -> None:
        assert format_number(532, "USD") == "$532"

    def test_zero_currency(self) -> None:
        assert format_number(0, "USD") == "$0"

    def test_none_value(self) -> None:
        assert format_number(None, "USD") == "N/A"


class TestNegatives:
    def test_negative_currency_uses_parens(self) -> None:
        assert format_number(-532_000_000, "USD") == "($532M)"

    def test_negative_small_currency_uses_parens(self) -> None:
        assert format_number(-0.43, "USD") == "($0.43)"

    def test_negative_percent_uses_parens(self) -> None:
        assert format_number(-0.6, "pure") == "(60.0%)"

    def test_negative_count_keeps_minus(self) -> None:
        assert format_number(-500, "count") == "-500"


class TestUnits:
    def test_pure_is_percent_one_decimal(self) -> None:
        assert format_number(0.125, "pure") == "12.5%"

    def test_usd_per_share(self) -> None:
        assert format_number(3.62, "USD/shares") == "$3.62"

    def test_unknown_three_letter_treated_as_currency(self) -> None:
        assert format_number(1_000_000_000, "CHF") == "CHF 1.0B"

    def test_shares_unit(self) -> None:
        assert format_number(2_500_000_000, "shares") == "2.5B"

    def test_headcount_unit(self) -> None:
        assert format_number(12_345, "headcount") == "12.3K"


class TestSymbolTable:
    def test_currency_symbols_exposed(self) -> None:
        from edgarpack.query.formatting import _CURRENCY_SYMBOLS

        assert _CURRENCY_SYMBOLS["USD"] == "$"
        assert _CURRENCY_SYMBOLS["EUR"] == "€"
        assert _CURRENCY_SYMBOLS["GBP"] == "£"
        assert _CURRENCY_SYMBOLS["JPY"] == "¥"
