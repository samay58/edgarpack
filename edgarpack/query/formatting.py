"""Canonical numeric formatter used by query.comps and compare.

Single source of truth for scale (B/M/K), precision, and finance-style
negative parentheses across every output surface that renders values to
users.
"""

from __future__ import annotations

_CURRENCY_SYMBOLS: dict[str, str] = {
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "JPY": "¥",
    "HKD": "HK$",
    "CNY": "¥",
}

_COUNT_UNITS = frozenset({"count", "shares", "headcount"})


def _scale_value(abs_val: float) -> tuple[float, str, int]:
    """Return (scaled_value, suffix, decimals) for a magnitude pick.

    Small-value bump: abs_val < 100 returns (abs_val, "", 2).
    abs_val in [100, 1000) returns (abs_val, "", 0).
    Otherwise scales at 1K/1M/1B with 1 decimal.
    """
    if abs_val == 0:
        return (0.0, "", 0)
    if abs_val < 100:
        return (abs_val, "", 2)
    if abs_val < 1_000:
        return (abs_val, "", 0)
    if abs_val < 1_000_000:
        return (abs_val / 1_000, "K", 1)
    if abs_val < 1_000_000_000:
        return (abs_val / 1_000_000, "M", 1)
    return (abs_val / 1_000_000_000, "B", 1)


def _render_number(
    abs_val: float, decimals: int, suffix: str, *, strip_trailing_zero: bool = False
) -> str:
    """Render a positive magnitude with decimals, optionally stripping a lone .0.

    Trailing ``.0`` is stripped only when ``strip_trailing_zero=True`` or when the
    suffix is ``K``/``M`` (billions keep one decimal for readability).
    """
    if decimals == 0:
        return f"{abs_val:,.0f}{suffix}"
    text = f"{abs_val:,.{decimals}f}"
    should_strip = strip_trailing_zero or suffix in ("K", "M")
    if should_strip and decimals == 1 and text.endswith(".0"):
        text = text[:-2]
    return f"{text}{suffix}"


def format_number(value: float | None, unit: str) -> str:
    """Canonical formatter for numeric values with unit-aware scale and precision.

    Rules:
      - None -> "N/A".
      - unit == "pure" -> percent with 1 decimal; negatives in parens.
      - unit == "USD/shares" -> "$X.XX" with 2 decimals; negatives in parens.
      - unit in {"count", "shares", "headcount"} -> scale with 1 decimal
        (trailing .0 stripped), negatives keep minus sign.
      - unit in _CURRENCY_SYMBOLS or any 3-letter alpha code -> scale with
        1 decimal (small-value bump to 2 decimals when abs<100), negatives
        in parens. Symbol prefixed (or code + space for unknown codes).
      - unknown unit -> plain comma thousands with 2 decimals.
    """
    if value is None:
        return "N/A"

    if unit == "pure":
        pct = value * 100.0
        rendered = f"{abs(pct):.1f}%"
        return f"({rendered})" if value < 0 else rendered

    if unit == "USD/shares":
        rendered = f"${abs(value):,.2f}"
        return f"({rendered})" if value < 0 else rendered

    if unit in _COUNT_UNITS:
        abs_val = abs(value)
        scaled, suffix, decimals = _scale_value(abs_val)
        rendered = _render_number(scaled, decimals, suffix, strip_trailing_zero=True)
        return f"-{rendered}" if value < 0 else rendered

    is_currency = unit in _CURRENCY_SYMBOLS or (len(unit) == 3 and unit.isalpha())
    if is_currency:
        symbol = _CURRENCY_SYMBOLS.get(unit)
        prefix = symbol if symbol is not None else f"{unit} "
        abs_val = abs(value)
        scaled, suffix, decimals = _scale_value(abs_val)
        rendered = f"{prefix}{_render_number(scaled, decimals, suffix)}"
        return f"({rendered})" if value < 0 else rendered

    return f"{value:,.2f}"


__all__ = ["format_number", "_CURRENCY_SYMBOLS"]
