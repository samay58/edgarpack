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

    def test_hkd_multichar_prefix(self) -> None:
        # "HK$" is the only multi-char prefix in _CURRENCY_SYMBOLS. Trailing
        # .0 is stripped for K/M suffixes per _render_number's rule.
        assert format_number(1_000, "HKD") == "HK$1K"


class TestHelpers:
    def test_scale_value_zero_short_circuit(self) -> None:
        from edgarpack.query.formatting import _scale_value

        assert _scale_value(0.0) == (0.0, "", 0)

    def test_scale_value_small_value_bump(self) -> None:
        from edgarpack.query.formatting import _scale_value

        assert _scale_value(99.99) == (99.99, "", 2)

    def test_scale_value_hundreds_no_scale(self) -> None:
        from edgarpack.query.formatting import _scale_value

        assert _scale_value(100.0) == (100.0, "", 0)

    def test_scale_value_k_threshold(self) -> None:
        from edgarpack.query.formatting import _scale_value

        scaled, suffix, decimals = _scale_value(1_000.0)
        assert (scaled, suffix, decimals) == (1.0, "K", 1)

    def test_scale_value_m_threshold(self) -> None:
        from edgarpack.query.formatting import _scale_value

        scaled, suffix, decimals = _scale_value(1_000_000.0)
        assert (scaled, suffix, decimals) == (1.0, "M", 1)

    def test_scale_value_b_threshold(self) -> None:
        from edgarpack.query.formatting import _scale_value

        scaled, suffix, decimals = _scale_value(1_000_000_000.0)
        assert (scaled, suffix, decimals) == (1.0, "B", 1)

    def test_scale_value_trillion_still_in_b_bucket(self) -> None:
        from edgarpack.query.formatting import _scale_value

        scaled, suffix, decimals = _scale_value(1_000_000_000_000.0)
        assert (scaled, suffix, decimals) == (1_000.0, "B", 1)


class TestFallback:
    def test_empty_unit_renders_as_plain_number(self) -> None:
        assert format_number(12.5, "") == "12.50"

    def test_empty_unit_zero(self) -> None:
        assert format_number(0, "") == "0.00"

    def test_bps_four_letter_hits_fallback(self) -> None:
        """Non-3-letter-alpha units are treated as unknown (not currency)."""
        # "bps" IS 3-letter alpha, so it currently hits the currency branch.
        # Use a non-3-letter token to exercise the fallback:
        assert format_number(12.5, "ratio") == "12.50"

    def test_bps_three_letter_alpha_currently_treated_as_currency(self) -> None:
        """Documents the current 3-letter-alpha heuristic: 'bps' is rendered
        as if it were a currency code. This is a known false positive of
        the 3-letter alpha fallback. If you need 'bps' to render differently,
        add it to _COUNT_UNITS or extend the unit branching."""
        assert format_number(1234, "bps") == "bps 1.2K"


class TestEdgeCases:
    def test_nan_returns_na(self) -> None:
        assert format_number(float("nan"), "USD") == "N/A"

    def test_inf_returns_na(self) -> None:
        assert format_number(float("inf"), "USD") == "N/A"
