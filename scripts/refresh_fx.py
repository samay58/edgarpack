"""Refresh data/fx_rates.csv from FRED.

Fetches DEXCHUS (CNY/USD) and DEXHKUS (HKD/USD) daily series, aggregates
into monthly period-average and month-end spot values, writes CSV.

Usage: .venv/bin/python scripts/refresh_fx.py
"""

from __future__ import annotations

import csv
import datetime as dt
import sys
from pathlib import Path
from statistics import mean

import httpx

FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
SERIES = {"CNY/USD": "DEXCHUS", "HKD/USD": "DEXHKUS"}
OUT = Path(__file__).resolve().parents[1] / "data" / "fx_rates.csv"


def _fetch_series(series: str) -> dict[dt.date, float]:
    url = FRED_CSV.format(series=series)
    resp = httpx.get(url, timeout=30, follow_redirects=True)
    resp.raise_for_status()
    rows = resp.text.splitlines()[1:]
    out: dict[dt.date, float] = {}
    for line in rows:
        parts = line.split(",")
        if len(parts) < 2:
            continue
        date_s, val_s = parts[0], parts[1]
        if val_s == "." or not val_s:
            continue
        try:
            per_usd = float(val_s)
        except ValueError:
            continue
        rate_to_usd = 1.0 / per_usd
        out[dt.date.fromisoformat(date_s)] = rate_to_usd
    return out


def _monthly(daily: dict[dt.date, float]) -> list[tuple[dt.date, float, float]]:
    buckets: dict[tuple[int, int], list[tuple[dt.date, float]]] = {}
    for d, v in daily.items():
        buckets.setdefault((d.year, d.month), []).append((d, v))
    out: list[tuple[dt.date, float, float]] = []
    for (_y, _m), pairs in sorted(buckets.items()):
        pairs.sort()
        month_end = pairs[-1][0]
        spot = pairs[-1][1]
        avg = mean(v for _, v in pairs)
        out.append((month_end, spot, avg))
    return out


def _usd_identity_rows(start_year: int, end_year: int) -> list[tuple[dt.date, float, float]]:
    rows: list[tuple[dt.date, float, float]] = []
    for y in range(start_year, end_year + 1):
        for m in range(1, 13):
            if m == 12:
                last = dt.date(y, 12, 31)
            else:
                last = dt.date(y, m + 1, 1) - dt.timedelta(days=1)
            rows.append((last, 1.0, 1.0))
    return rows


def main() -> int:
    all_rows: list[dict[str, str]] = []
    min_year = 9999
    max_year = 0
    for pair, series in SERIES.items():
        print(f"Fetching {series} ({pair})...", file=sys.stderr)
        daily = _fetch_series(series)
        monthly = _monthly(daily)
        for month_end, spot, avg in monthly:
            min_year = min(min_year, month_end.year)
            max_year = max(max_year, month_end.year)
            all_rows.append(
                {
                    "ccy_pair": pair,
                    "month_end_date": month_end.isoformat(),
                    "spot_end": f"{spot:.6f}",
                    "period_average": f"{avg:.6f}",
                }
            )
    for month_end, spot, avg in _usd_identity_rows(min_year, max_year):
        all_rows.append(
            {
                "ccy_pair": "USD/USD",
                "month_end_date": month_end.isoformat(),
                "spot_end": f"{spot:.6f}",
                "period_average": f"{avg:.6f}",
            }
        )

    all_rows.sort(key=lambda r: (r["ccy_pair"], r["month_end_date"]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["ccy_pair", "month_end_date", "spot_end", "period_average"],
        )
        w.writeheader()
        w.writerows(all_rows)
    print(f"Wrote {len(all_rows)} rows to {OUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
