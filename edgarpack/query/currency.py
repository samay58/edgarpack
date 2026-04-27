"""Currency display helpers for investor-facing query surfaces."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Literal

from ..fx import RateNotFound, RateTable, convert, load_rates
from .formatting import format_number
from .models import CitedValue

CurrencyMode = Literal["native", "usd", "both"]
_NON_CURRENCY_UNITS: frozenset[str] = frozenset({"count", "shares", "headcount", "pure"})

_BALANCE_SHEET_METRICS: frozenset[str] = frozenset(
    {
        "total_assets",
        "total_liabilities",
        "total_equity",
        "cash_and_equivalents",
        "total_debt",
        "shares_outstanding_basic",
        "shares_outstanding_diluted",
    }
)


@dataclass(frozen=True)
class FxDisplay:
    usd_value: float
    native_value: float
    native_currency: str
    rate_used: float
    convention: str
    as_of: dt.date
    source_label: str = "data/fx_rates.csv"

    @property
    def provenance(self) -> str:
        return (
            f"FX: {self.source_label} {self.native_currency}/USD "
            f"{self.as_of.isoformat()} {self.convention} {self.rate_used:.4f}"
        )


def fx_rates_path() -> Path:
    """Return the repo-local default FX table independent of the shell cwd."""
    return Path(__file__).resolve().parents[2] / "data" / "fx_rates.csv"


def load_default_rates() -> RateTable:
    return load_rates(fx_rates_path())


def convention_for_metric(metric: str) -> str:
    if metric in _BALANCE_SHEET_METRICS:
        return "spot"
    return "average"


def _currency_from_unit(unit: str) -> str:
    if unit in _NON_CURRENCY_UNITS:
        return ""
    if "/" in unit:
        prefix = unit.split("/", 1)[0]
        if len(prefix) == 3 and prefix.isalpha():
            return prefix
    if len(unit) == 3 and unit.isalpha():
        return unit
    return ""


def _display_currency(cited: CitedValue) -> str:
    unit = (cited.unit or "").strip()
    unit_currency = _currency_from_unit(unit)
    if unit_currency:
        return unit_currency

    currency = (cited.reporting_currency or "").strip()
    if currency and currency not in _NON_CURRENCY_UNITS:
        return currency
    return ""


def _native_unit(cited: CitedValue, native_currency: str) -> str:
    unit = cited.unit or native_currency
    if unit == native_currency:
        return native_currency
    return unit


def is_currency_value(cited: CitedValue) -> bool:
    if cited.value is None:
        return False
    if cited.unit in _NON_CURRENCY_UNITS:
        return False
    return bool(_display_currency(cited))


def convert_cited_to_usd(
    cited: CitedValue,
    *,
    metric: str | None = None,
    rates: RateTable | None = None,
) -> FxDisplay | None:
    if cited.value is None or not is_currency_value(cited):
        return None

    native_currency = _display_currency(cited)
    if native_currency == "USD":
        return FxDisplay(
            usd_value=float(cited.value),
            native_value=float(cited.value),
            native_currency="USD",
            rate_used=1.0,
            convention="native",
            as_of=cited.period_end,
        )

    convention = convention_for_metric(metric or cited.metric)
    rates = load_default_rates() if rates is None else rates
    try:
        result = convert(
            value=Decimal(str(cited.value)),
            from_ccy=native_currency,
            to_ccy="USD",
            as_of=cited.period_end,
            convention=convention,  # type: ignore[arg-type]
            rates=rates,
            period_end=cited.period_end if convention == "average" else None,
        )
    except (RateNotFound, NotImplementedError):
        return None

    return FxDisplay(
        usd_value=result.converted_value,
        native_value=float(cited.value),
        native_currency=native_currency,
        rate_used=result.rate_used,
        convention=convention,
        as_of=cited.period_end,
    )


def format_cited_currency(
    cited: CitedValue,
    *,
    mode: CurrencyMode = "both",
    metric: str | None = None,
    rates: RateTable | None = None,
) -> str:
    """Format a cited value with explicit USD/native/FX provenance controls."""
    if cited.value is None:
        return "N/A"
    if not is_currency_value(cited):
        return format_number(cited.value, cited.unit or "")

    native_currency = _display_currency(cited)
    native_text = format_number(float(cited.value), _native_unit(cited, native_currency))
    fx = convert_cited_to_usd(cited, metric=metric, rates=rates)
    if mode == "native" or fx is None:
        return native_text

    usd_text = format_number(fx.usd_value, "USD")
    if native_currency == "USD":
        return usd_text
    return f"{usd_text} (native: {native_text}; {fx.provenance})"
