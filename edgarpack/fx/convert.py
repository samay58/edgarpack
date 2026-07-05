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


def _months_in_range(period_start: dt.date, period_end: dt.date) -> list[tuple[int, int]]:
    if period_start > period_end:
        raise RateNotFound(
            f"period_start {period_start.isoformat()} is after period_end {period_end.isoformat()}"
        )
    months: list[tuple[int, int]] = []
    year, month = period_start.year, period_start.month
    while (year, month) <= (period_end.year, period_end.month):
        months.append((year, month))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


def _average_over_period(
    rows: tuple[MonthlyRate, ...], period_start: dt.date, period_end: dt.date
) -> tuple[float, str]:
    """Average the monthly period_average rows across the period, start to end inclusive.

    Fails closed (RateNotFound) if any month in the range has no row, so a
    partial average is never mistaken for the period average.
    """
    by_month = {(r.month_end.year, r.month_end.month): r for r in rows}
    months = _months_in_range(period_start, period_end)
    matched: list[MonthlyRate] = []
    for year, month in months:
        row = by_month.get((year, month))
        if row is None:
            raise RateNotFound(
                f"No rate row for month {year:04d}-{month:02d}, required for period "
                f"average {period_start.isoformat()}..{period_end.isoformat()}"
            )
        matched.append(row)
    mean_rate = sum(r.period_average for r in matched) / len(matched)
    span = f"{matched[0].month_end.isoformat()}..{matched[-1].month_end.isoformat()}"
    return mean_rate, f"average of {len(matched)} month(s) {span}"


def convert(
    value: Decimal,
    from_ccy: str,
    to_ccy: str,
    as_of: dt.date,
    convention: Convention,
    rates: RateTable,
    period_end: dt.date | None = None,
    period_start: dt.date | None = None,
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

    if convention == "average" and period_start is not None and period_end is not None:
        rate, span_label = _average_over_period(rows, period_start, period_end)
        converted = float(value) * rate
        source = f"{pair} {span_label} (average)"
        return ConvertedValue(
            converted_value=converted,
            rate_used=rate,
            from_ccy=from_ccy,
            to_ccy=to_ccy,
            as_of=as_of,
            convention=convention,
            rate_source_row=source,
        )

    # Legacy single-month sample: used when the caller has no period_start to
    # give (e.g. a caller that only tracks a period end). Kept so existing
    # callers that supply only period_end do not regress; callers should
    # migrate to passing period_start for a true period average.
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
