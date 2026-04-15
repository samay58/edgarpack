"""FX rate table loader."""

from __future__ import annotations

import csv
import datetime as dt
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MonthlyRate:
    ccy_pair: str
    month_end: dt.date
    spot_end: float
    period_average: float


@dataclass(frozen=True)
class RateTable:
    rows: tuple[MonthlyRate, ...]

    def for_pair(self, ccy_pair: str) -> tuple[MonthlyRate, ...]:
        return tuple(r for r in self.rows if r.ccy_pair == ccy_pair)


def load_rates(path: Path) -> RateTable:
    with path.open() as f:
        reader = csv.DictReader(f)
        rows = [
            MonthlyRate(
                ccy_pair=r["ccy_pair"],
                month_end=dt.date.fromisoformat(r["month_end_date"]),
                spot_end=float(r["spot_end"]),
                period_average=float(r["period_average"]),
            )
            for r in reader
        ]
    return RateTable(rows=tuple(rows))
