from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass
from typing import Any

from .query.models import CitedValue


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
        sample = next(iter(flattened.values()))
        period_label = f"FY{sample.fiscal_year}"
        currency = sample.reporting_currency or "USD"
        company = sample.company or result.company
    else:
        period_label = "n/a"
        currency = "USD"
        company = result.company

    metrics_dict = {
        m: {
            "value": cv.value,
            "currency": cv.reporting_currency or "",
            "extraction_method": cv.source or "",
        }
        for m, cv in flattened.items()
    }
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


def _format_value(v: dict[str, Any] | None) -> str:
    if v is None or v.get("value") is None:
        return "n/a"
    val = v["value"]
    cur = v.get("currency", "")
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

    widths = [
        max(len(str(r[i])) for r in [headers] + rows) for i in range(len(headers))
    ]
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

    try:
        idx = load_identity(Path("universe.toml"))
    except Exception as e:
        print(f"Error: failed to load universe: {e}", file=sys.stderr)
        return 1

    for name in args.companies:
        try:
            resolve(idx, ticker=name, company=None)
        except UnknownCompany:
            try:
                resolve(idx, ticker=None, company=name)
            except (UnknownCompany, AmbiguousCompany) as e:
                print(f"Error: {e}", file=sys.stderr)
                return 2

    metrics = args.metrics or "revenue,gross_profit,net_income,cash_and_equivalents"
    period = getattr(args, "period", None) or "lfy"

    try:
        columns = asyncio.run(_gather(args.companies, metrics, period))
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    metric_keys = [m.strip() for m in metrics.split(",")]

    fmt = getattr(args, "compare_format", None) or "table"
    if fmt == "json":
        print(_format_json(columns))
    elif fmt == "markdown":
        print(_format_markdown(columns, metric_keys))
    else:
        print(_format_table(columns, metric_keys))
    return 0
