from __future__ import annotations

import asyncio
import datetime as dt
import json
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from .query.models import CitedValue

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

# Signed percent (e.g. "+12%", "-3%"): YoY growth and period-over-period deltas.
_GROWTH_METRICS: frozenset[str] = frozenset({"revenue_growth_yoy", "gross_margin_trend"})

# Unsigned percent (e.g. "45%"): ratios and intensity metrics.
_RATIO_METRICS: frozenset[str] = frozenset(
    {
        "r_and_d_intensity",
        "gross_margin",
        "operating_margin",
        "net_margin",
        "ebitda_margin",
        "fcf_margin",
    }
)

_PER_EMPLOYEE_METRICS: frozenset[str] = frozenset({"revenue_per_employee"})


def _convention_for(metric: str) -> str:
    if metric in _BALANCE_SHEET_METRICS:
        return "spot"
    return "average"


def _load_rates():
    from .fx import load_rates

    return load_rates(Path("data/fx_rates.csv"))


def _convert_to_usd(
    value: float, from_ccy: str, metric: str, fy: int, rates
) -> tuple[float, float] | None:
    from .fx import RateNotFound, convert

    if from_ccy == "USD":
        return float(value), 1.0
    convention = _convention_for(metric)
    as_of = dt.date(fy, 12, 31)
    try:
        result = convert(
            value=Decimal(str(value)),
            from_ccy=from_ccy,
            to_ccy="USD",
            as_of=as_of,
            convention=convention,
            rates=rates,
            period_end=as_of if convention == "average" else None,
        )
    except (RateNotFound, NotImplementedError):
        return None
    return result.converted_value, result.rate_used


@dataclass(frozen=True)
class CompanyColumn:
    ticker: str
    company: str
    period: str
    reporting_currency: str
    metrics: dict[str, dict[str, Any]]


def _flatten(value: CitedValue | list[CitedValue] | None) -> CitedValue | None:
    if value is None:
        return None
    if isinstance(value, list):
        return value[0] if value else None
    return value


async def _fetch_one(name: str, metrics: str | None, period: str) -> CompanyColumn:
    from .query.financials import financials

    result = await financials(company=name, metrics=metrics, period=period)
    flattened: dict[str, CitedValue] = {}
    for k, v in result.metrics.items():
        cv = _flatten(v)
        if cv is not None:
            flattened[k] = cv

    if flattened:
        # Prefer a sample that actually names a reporting currency. Headcount
        # and dimensionless ratios (reporting_currency="pure") would otherwise
        # hijack the column footer.
        sample = next(
            (
                cv
                for cv in flattened.values()
                if cv.reporting_currency and cv.reporting_currency not in ("headcount", "pure")
            ),
            next(iter(flattened.values())),
        )
        period_label = f"FY{sample.fiscal_year}"
        currency = sample.reporting_currency or "USD"
        if currency in ("headcount", "pure"):
            currency = "USD"
        company = sample.company or result.company
    else:
        period_label = "n/a"
        currency = "USD"
        company = result.company

    rates = None
    metrics_dict: dict[str, dict[str, Any]] = {}
    for m, cv in flattened.items():
        entry: dict[str, Any] = {
            "value": cv.value,
            "currency": cv.reporting_currency or "",
            "extraction_method": cv.source or "",
        }
        if m in _GROWTH_METRICS:
            entry["growth"] = float(cv.value)
        elif m in _RATIO_METRICS:
            entry["ratio"] = float(cv.value)
        elif m in _PER_EMPLOYEE_METRICS:
            # revenue / headcount in the native reporting currency. Convert
            # to USD using the revenue convention (average over the year).
            if cv.reporting_currency and cv.reporting_currency != "USD":
                if rates is None:
                    rates = _load_rates()
                conv = _convert_to_usd(
                    cv.value, cv.reporting_currency, "revenue", cv.fiscal_year, rates
                )
                if conv is not None:
                    entry["per_employee_usd"] = conv[0]
                    entry["fx_rate"] = conv[1]
            else:
                entry["per_employee_usd"] = float(cv.value)
                entry["fx_rate"] = 1.0
        elif cv.unit == "headcount":
            entry["headcount"] = int(cv.value)
        elif cv.reporting_currency and cv.reporting_currency != "USD":
            if rates is None:
                rates = _load_rates()
            conv = _convert_to_usd(cv.value, cv.reporting_currency, m, cv.fiscal_year, rates)
            if conv is not None:
                entry["usd_value"] = conv[0]
                entry["fx_rate"] = conv[1]
        else:
            entry["usd_value"] = float(cv.value)
            entry["fx_rate"] = 1.0
        metrics_dict[m] = entry
    return CompanyColumn(
        ticker=name,
        company=company,
        period=period_label,
        reporting_currency=currency,
        metrics=metrics_dict,
    )


async def _gather(names: list[str], metrics: str | None, period: str) -> list[CompanyColumn]:
    cols: list[CompanyColumn] = []
    for n in names:
        cols.append(await _fetch_one(n, metrics, period))
    return cols


def _abbrev_usd(val: float) -> str:
    if val is None:
        return "n/a"
    absval = abs(val)
    sign = "-" if val < 0 else ""
    if absval >= 1_000_000_000:
        return f"{sign}${absval / 1_000_000_000:,.1f}B"
    if absval >= 1_000_000:
        return f"{sign}${absval / 1_000_000:,.1f}M"
    if absval >= 1_000:
        return f"{sign}${absval / 1_000:,.1f}K"
    return f"{sign}${absval:,.0f}"


def _format_value(v: dict[str, Any] | None) -> str:
    if v is None or v.get("value") is None:
        return "n/a"
    if "growth" in (v or {}):
        pct = v["growth"] * 100
        return f"{pct:+.0f}%" if abs(pct) >= 10 else f"{pct:+.1f}%"
    if "ratio" in (v or {}):
        return f"{v['ratio'] * 100:.0f}%"
    if "per_employee_usd" in (v or {}):
        return f"${int(v['per_employee_usd']):,}"
    if "headcount" in (v or {}):
        return f"{int(v['headcount']):,}"
    val = v["value"]
    cur = v.get("currency", "")
    usd = v.get("usd_value")
    if usd is not None and cur != "USD":
        return f"{_abbrev_usd(usd)} (native: {float(val):,.0f} {cur})"
    if usd is not None:
        return _abbrev_usd(usd)
    try:
        return f"{float(val):,.0f} {cur}".strip()
    except (TypeError, ValueError):
        return f"{val} {cur}".strip()


def _format_table(columns: list[CompanyColumn], metric_keys: list[str]) -> str:
    headers = ["metric"] + [c.ticker for c in columns]
    rows: list[list[str]] = []
    for m in metric_keys:
        row = [m]
        for c in columns:
            row.append(_format_value(c.metrics.get(m)))
        rows.append(row)

    widths = [max(len(str(r[i])) for r in [headers] + rows) for i in range(len(headers))]
    lines: list[str] = []
    lines.append("  ".join(headers[i].ljust(widths[i]) for i in range(len(headers))))
    lines.append("  ".join("-" * widths[i] for i in range(len(headers))))
    for row in rows:
        lines.append("  ".join(str(row[i]).ljust(widths[i]) for i in range(len(headers))))
    lines.append("")
    for c in columns:
        lines.append(f"  {c.ticker}: {c.company}, {c.period}, reported in {c.reporting_currency}")
    return "\n".join(lines)


def _format_markdown(columns: list[CompanyColumn], metric_keys: list[str]) -> str:
    headers = ["metric"] + [c.ticker for c in columns]
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for m in metric_keys:
        row = [m] + [_format_value(c.metrics.get(m)) for c in columns]
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    for c in columns:
        lines.append(f"_{c.ticker}: {c.company}, {c.period}, {c.reporting_currency}_")
    return "\n".join(lines)


def _format_json(columns: list[CompanyColumn]) -> str:
    return json.dumps(
        {
            "companies": [
                {
                    "ticker": c.ticker,
                    "company": c.company,
                    "period": c.period,
                    "reporting_currency": c.reporting_currency,
                    "metrics": c.metrics,
                }
                for c in columns
            ]
        },
        indent=2,
        default=str,
    )


def cmd_compare(args: Any) -> int:
    from pathlib import Path

    from .identity import AmbiguousCompany, UnknownCompany, load_identity, resolve

    universe_path = Path("universe.toml")
    if universe_path.exists():
        try:
            idx = load_identity(universe_path)
        except Exception as e:
            print(f"Error: failed to load universe: {e}", file=sys.stderr)
            return 1

        for name in args.companies:
            try:
                resolve(idx, ticker=name, company=None)
            except UnknownCompany:
                try:
                    resolve(idx, ticker=None, company=name)
                except UnknownCompany:
                    # Unknown in universe falls through to SEC ticker lookup
                    # inside _gather(); do not hard-bail here.
                    continue
                except AmbiguousCompany as e:
                    print(f"Error: {e}", file=sys.stderr)
                    return 2
            except AmbiguousCompany as e:
                print(f"Error: {e}", file=sys.stderr)
                return 2

    metrics = args.metrics or "revenue,gross_profit,net_income,cash_and_equivalents"
    period = getattr(args, "period", None) or "lfy"

    try:
        columns = asyncio.run(_gather(args.companies, metrics, period))
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    except ValueError as e:
        msg = str(e)
        print(f"Error: {msg}", file=sys.stderr)
        return 2 if msg.lower().startswith("unknown ticker") else 1

    metric_keys = [m.strip() for m in metrics.split(",")]

    fmt = getattr(args, "compare_format", None) or "table"
    if fmt == "json":
        print(_format_json(columns))
    elif fmt == "markdown":
        print(_format_markdown(columns, metric_keys))
    else:
        print(_format_table(columns, metric_keys))
    return 0
