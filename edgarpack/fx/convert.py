"""Convert values between currencies using bundled monthly rates.

Follows ASC 830 conventions: spot-at-period-end for balance sheet,
period-average for income statement.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from .rates import MonthlyRate, RateTable

Convention = Literal["spot", "average"]


class RateNotFound(ValueError):  # noqa: N818
    pass


@dataclass(frozen=True)
class ConvertedValue:
    converted_value: float
    rate_used: float
    from_ccy: str
    to_ccy: str
    as_of: dt.date
    convention: Convention
    rate_source_row: str


def _find_row(rows: tuple[MonthlyRate, ...], as_of: dt.date) -> MonthlyRate:
    candidates = [
        r for r in rows if r.month_end.year == as_of.year and r.month_end.month == as_of.month
    ]
    if candidates:
        return candidates[0]
    raise RateNotFound(f"No rate row for month of {as_of.isoformat()}")


def convert(
    value: Decimal,
    from_ccy: str,
    to_ccy: str,
    as_of: dt.date,
    convention: Convention,
    rates: RateTable,
    period_end: dt.date | None = None,
) -> ConvertedValue:
    if from_ccy == to_ccy:
        return ConvertedValue(
            converted_value=float(value),
            rate_used=1.0,
            from_ccy=from_ccy,
            to_ccy=to_ccy,
            as_of=as_of,
            convention=convention,
            rate_source_row=f"identity {from_ccy}",
        )

    if to_ccy != "USD":
        raise NotImplementedError("v1 only supports conversion to USD")

    pair = f"{from_ccy}/USD"
    rows = rates.for_pair(pair)
    if not rows:
        raise RateNotFound(f"No rates loaded for pair {pair}")

    lookup_date = period_end if convention == "average" and period_end else as_of
    row = _find_row(rows, lookup_date)
    rate = row.spot_end if convention == "spot" else row.period_average
    converted = float(value) * rate
    source = f"{pair} {row.month_end.isoformat()} ({convention})"
    return ConvertedValue(
        converted_value=converted,
        rate_used=rate,
        from_ccy=from_ccy,
        to_ccy=to_ccy,
        as_of=as_of,
        convention=convention,
        rate_source_row=source,
    )
