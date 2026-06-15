"""Canonical numeric formatter used by query.comps and compare.

Single source of truth for scale (B/M/K), precision, and finance-style
negative parentheses across every output surface that renders values to
users.
"""

from __future__ import annotations

import math
from typing import Any

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
      - None or non-finite (NaN, +/-inf) -> "N/A".
      - unit == "pure" -> percent with 1 decimal; negatives in parens.
      - unit == "USD/shares" -> "$X.XX" with 2 decimals; negatives in parens.
      - unit in {"count", "shares", "headcount"} -> scale with 1 decimal
        (trailing .0 stripped), negatives keep minus sign.
      - unit in _CURRENCY_SYMBOLS or any 3-letter alpha code -> scale with
        1 decimal (small-value bump to 2 decimals when abs<100), negatives
        in parens. Symbol prefixed (or code + space for unknown codes).
      - unit is a 3-letter alpha code not in _CURRENCY_SYMBOLS -> treated as
        an ISO-4217 currency code ("CHF 1.2B"). This is a heuristic and will
        false-positive on non-currency 3-letter tokens like "bps" or "foo".
        Callers that need a different rendering for such tokens should route
        through an explicit unit branch.
      - unknown unit (empty string, non-alpha token, or 4+ chars) -> plain
        comma thousands with 2 decimals. Negatives keep the minus sign; no
        parens in this fallback path (no unit to anchor the finance style).

    Unit matching is case-sensitive; callers must pass uppercase ISO codes
    (e.g., "USD" not "usd"). Internal callers receive unit from
    ``CitedValue.unit``, which upstream already normalizes to uppercase.
    """
    if value is None:
        return "N/A"
    if not math.isfinite(value):
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


def format_citation_marker(cited: Any) -> str:  # noqa: ANN401 (duck-typed on CitedValue)
    """Inline citation marker for table renderings.

    - Registration snapshot rows:   [S-1, 24-041596] or [F-1, 26-071170]
    - Registration pro-forma rows:  [S-1 pro-forma, 26-025762] *
    - Everything else:     empty string (periodic filings already have
      their own citation machinery via cited.filing_url etc.).

    Accession is rendered in short year-suffix form: take everything from
    the first dash of the 10-digit CIK prefix onward.
    """
    source = getattr(cited, "source", "") or ""
    accession = getattr(cited, "accession", "") or ""
    if source not in ("s1_snapshot", "s1_pro_forma"):
        return ""
    parts = accession.split("-", 1)
    short = parts[1] if len(parts) == 2 else accession
    form_label = str(getattr(cited, "form_type", "") or "S-1").upper()
    if source == "s1_pro_forma":
        return f"[{form_label} pro-forma, {short}] *"
    return f"[{form_label}, {short}]"


__all__ = ["format_number", "format_citation_marker", "_CURRENCY_SYMBOLS"]
