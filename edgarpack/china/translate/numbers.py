"""Deterministic Chinese number/unit tagging and conversion.

This is the single most dangerous failure mode in translation: a wan/yi
error is a 10,000x magnitude mistake. Numbers are NEVER delegated to an LLM.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Multiplier map for Chinese units
_UNIT_MULTIPLIERS: dict[str, float] = {
    "万亿": 1_000_000_000_000,
    "亿": 100_000_000,
    "万": 10_000,
}

# Currency labels
_CURRENCY_LABELS: dict[str, str] = {
    "人民币": "RMB",
    "元": "RMB",
    "美元": "USD",
    "港元": "HKD",
    "欧元": "EUR",
    "日元": "JPY",
}

# Pattern for Chinese financial numbers:
#   optional negative, digits with optional commas and decimals, optional unit, optional currency
_NUM_PATTERN = re.compile(
    r"(?P<neg>-|负)?"
    r"(?P<digits>[\d,]+(?:\.\d+)?)"
    r"(?:\s|<br>)*(?P<unit>万亿|亿|万)?"
    r"(?:\s|<br>)*(?P<currency>人民币|元|美元|港元|欧元|日元|股|份|%|百分点)?"
)


@dataclass(frozen=True)
class NumberTag:
    placeholder: str
    original: str
    value: float
    unit: str
    currency: str
    converted: str


def _parse_digits(s: str) -> float:
    return float(s.replace(",", ""))


def _format_large_number(value: float) -> str:
    """Format a number with appropriate magnitude suffix."""
    abs_val = abs(value)
    sign = "-" if value < 0 else ""
    if abs_val >= 1_000_000_000_000:
        return f"{sign}{abs_val / 1_000_000_000_000:.2f} trillion"
    if abs_val >= 1_000_000_000:
        return f"{sign}{abs_val / 1_000_000_000:.2f} billion"
    if abs_val >= 1_000_000:
        return f"{sign}{abs_val / 1_000_000:.2f} million"
    if abs_val >= 1_000:
        return f"{sign}{abs_val:,.2f}"
    if abs_val == int(abs_val):
        return f"{sign}{int(abs_val)}"
    return f"{sign}{abs_val:.2f}"


def convert_number(digits_str: str, unit: str, currency: str, negative: bool = False) -> str:
    """Convert a Chinese number+unit to English representation.

    Args:
        digits_str: Raw digit string (may contain commas).
        unit: Chinese unit (万, 亿, 万亿, or empty).
        currency: Chinese currency label or suffix.
        negative: Whether the number is negative.

    Returns:
        English string like "RMB 12.35 million".
    """
    raw_val = _parse_digits(digits_str)
    multiplier = _UNIT_MULTIPLIERS.get(unit, 1.0)
    value = raw_val * multiplier
    if negative:
        value = -value

    formatted = _format_large_number(value)

    # Currency prefix
    cur_en = _CURRENCY_LABELS.get(currency, "")
    suffix = currency if currency in ("%", "百分点", "股", "份") else ""

    if suffix == "百分点":
        return f"{formatted} percentage points"
    if suffix == "%":
        return f"{formatted}{suffix}"
    if suffix == "股":
        return f"{formatted} shares"
    if suffix == "份":
        return f"{formatted} units"
    if cur_en:
        return f"{cur_en} {formatted}"
    if unit:
        return formatted
    return digits_str


def tag_numbers(text_zh: str) -> tuple[str, list[NumberTag]]:
    """Replace Chinese numbers with placeholders for safe LLM translation.

    Returns the tagged text and a list of NumberTag objects for later restoration.
    """
    tags: list[NumberTag] = []
    counter = 0

    def _replace(m: re.Match[str]) -> str:
        nonlocal counter
        unit = m.group("unit") or ""
        currency = m.group("currency") or ""
        # Skip bare numbers without Chinese unit/currency context
        if not unit and not currency:
            return m.group(0)
        # Skip percentage-only matches (just digits + %)
        if currency == "%" and not unit:
            return m.group(0)

        neg = bool(m.group("neg"))
        digits = m.group("digits")
        converted = convert_number(digits, unit, currency, negative=neg)

        counter += 1
        placeholder = f"<<NUM_{counter:03d}>>"
        tag = NumberTag(
            placeholder=placeholder,
            original=m.group(0),
            value=_parse_digits(digits) * _UNIT_MULTIPLIERS.get(unit, 1.0) * (-1 if neg else 1),
            unit=unit,
            currency=currency,
            converted=converted,
        )
        tags.append(tag)
        return placeholder

    tagged = _NUM_PATTERN.sub(_replace, text_zh)
    return tagged, tags


def restore_numbers(text_en: str, tags: list[NumberTag]) -> str:
    """Replace placeholders in translated text with converted English values."""
    result = text_en
    for tag in tags:
        result = result.replace(tag.placeholder, tag.converted)
    return result
