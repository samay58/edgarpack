from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .fx import RateTable
from .query.formatting import format_number
from .query.models import CitedValue

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


def _load_rates() -> RateTable:
    from .query.currency import load_default_rates

    return load_default_rates()


@dataclass(frozen=True)
class CompanyColumn:
    ticker: str
    company: str
    period: str
    reporting_currency: str
    metrics: dict[str, dict[str, Any]]
    diagnostics: list[dict[str, str]] | None = None


def _flatten(value: CitedValue | list[CitedValue] | None) -> CitedValue | None:
    if value is None:
        return None
    if isinstance(value, list):
        return value[0] if value else None
    return value


async def _fetch_one(
    name: str, metrics: str | None, period: str, *, strict: bool = False
) -> tuple[CompanyColumn, list[str]]:
    """Fetch one column. Returns (column, strict_rejected_metrics).

    When `strict` is True, any CitedValue whose source is not 'hardcoded'
    is filtered out before column construction; its metric name appears
    in the returned rejected list so the CLI can surface the rejection.
    """
    from .query.financials import financials

    result = await financials(company=name, metrics=metrics, period=period)

    strict_rejected: list[str] = []
    if strict:
        from .query.strict import apply_strict

        strict_rejected = apply_strict(result)

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
        raw_value = cv.value
        if raw_value is None:
            metrics_dict[m] = entry
            continue
        if m in _GROWTH_METRICS:
            entry["growth"] = float(raw_value)
        elif m in _RATIO_METRICS:
            entry["ratio"] = float(raw_value)
        elif m in _PER_EMPLOYEE_METRICS:
            # revenue / headcount in the native reporting currency. Convert
            # to USD using the revenue convention (average over the year).
            if cv.reporting_currency and cv.reporting_currency != "USD":
                from .query.currency import convert_cited_to_usd

                if rates is None:
                    rates = _load_rates()
                conv = convert_cited_to_usd(cv, metric="revenue", rates=rates)
                if conv is not None:
                    entry["per_employee_usd"] = conv.usd_value
                    entry["fx_rate"] = conv.rate_used
                    entry["fx_convention"] = conv.convention
                    entry["fx_as_of"] = conv.as_of.isoformat()
                    entry["fx_provenance"] = conv.provenance
            else:
                entry["per_employee_usd"] = float(raw_value)
                entry["fx_rate"] = 1.0
        elif cv.unit == "headcount":
            entry["headcount"] = int(raw_value)
        elif cv.reporting_currency and cv.reporting_currency != "USD":
            from .query.currency import convert_cited_to_usd

            if rates is None:
                rates = _load_rates()
            conv = convert_cited_to_usd(cv, metric=m, rates=rates)
            if conv is not None:
                entry["usd_value"] = conv.usd_value
                entry["fx_rate"] = conv.rate_used
                entry["fx_convention"] = conv.convention
                entry["fx_as_of"] = conv.as_of.isoformat()
                entry["fx_provenance"] = conv.provenance
        else:
            entry["usd_value"] = float(raw_value)
            entry["fx_rate"] = 1.0
        metrics_dict[m] = entry
    diagnostics_out: list[dict[str, str]] = [
        {"metric": d.metric, "kind": d.kind, "message": d.message} for d in result.diagnostics
    ]

    return (
        CompanyColumn(
            ticker=name,
            company=company,
            period=period_label,
            reporting_currency=currency,
            metrics=metrics_dict,
            diagnostics=diagnostics_out or None,
        ),
        strict_rejected,
    )


async def _gather(
    names: list[str], metrics: str | None, period: str, *, strict: bool = False
) -> tuple[list[CompanyColumn], dict[str, list[str]]]:
    """Fetch one column per name concurrently.

    Uses asyncio.gather so N tickers hit the SEC / HKEX pipelines in
    parallel instead of serially. Failed fetches (AmbiguousCompany,
    unknown ticker, etc.) propagate as before; one bad ticker still
    sinks the whole command, matching the pre-parallel semantics.
    """
    results = await asyncio.gather(*(_fetch_one(n, metrics, period, strict=strict) for n in names))
    cols: list[CompanyColumn] = []
    rejected_by_company: dict[str, list[str]] = {}
    for n, (col, rejected) in zip(names, results, strict=True):
        cols.append(col)
        if rejected:
            rejected_by_company[n] = rejected
    return cols, rejected_by_company


def _format_value(v: dict[str, Any] | None, *, currency_mode: str = "both") -> str:
    if v is None or v.get("value") is None:
        return "n/a"
    # Growth is a signed delta (e.g., "+5%", "-3%"), not a finance-negative.
    # Keep the signed +/- formatter; don't route through format_number
    # which would wrap negatives in parens.
    if "growth" in (v or {}):
        pct = v["growth"] * 100
        return f"{pct:+.0f}%" if abs(pct) >= 10 else f"{pct:+.1f}%"
    if "ratio" in (v or {}):
        return format_number(v["ratio"], "pure")
    if "per_employee_usd" in (v or {}):
        if currency_mode == "native":
            return format_number(float(v["value"]), v.get("currency", ""))
        native = format_number(float(v["value"]), v.get("currency", ""))
        suffix = f"; {v['fx_provenance']}" if v.get("fx_provenance") else ""
        if v.get("currency") and v.get("currency") != "USD":
            usd_text = format_number(float(v["per_employee_usd"]), "USD")
            return f"{usd_text} (native: {native}{suffix})"
        return format_number(float(v["per_employee_usd"]), "USD")
    if "headcount" in (v or {}):
        return format_number(float(v["headcount"]), "headcount")
    val = v["value"]
    cur = v.get("currency", "")
    usd = v.get("usd_value")
    if usd is not None and cur != "USD":
        native = format_number(float(val), cur)
        if currency_mode == "native":
            return native
        suffix = f"; {v['fx_provenance']}" if v.get("fx_provenance") else ""
        return f"{format_number(float(usd), 'USD')} (native: {native}{suffix})"
    if usd is not None:
        return format_number(float(usd), "USD")
    if cur:
        return format_number(float(val), cur)
    return format_number(float(val), "")


def _period_header(period_request: str, columns: list[CompanyColumn]) -> str:
    """One-line period statement. Shows the requested period and resolved
    fiscal years; flags mismatch when companies don't line up."""
    resolved = [c.period for c in columns if c.period != "n/a"]
    unique = list(dict.fromkeys(resolved))
    if not unique:
        return f"Period: {period_request}"
    if len(unique) == 1:
        return f"Period: {period_request} ({unique[0]})"
    pairs = ", ".join(f"{c.ticker}={c.period}" for c in columns)
    return f"Period: {period_request}; fiscal years differ: {pairs}"


def _diagnostics_lines(columns: list[CompanyColumn]) -> list[str]:
    """Render a flat warnings block so mislabeled LTM values never hide silently."""
    lines: list[str] = []
    for c in columns:
        if not c.diagnostics:
            continue
        for d in c.diagnostics:
            lines.append(f"  ! {c.ticker}.{d.get('metric', '?')}: {d.get('message', '')}")
    if lines:
        lines.insert(0, "warnings:")
    return lines


def _format_table(
    columns: list[CompanyColumn],
    metric_keys: list[str],
    period_request: str,
    *,
    currency_mode: str = "both",
) -> str:
    headers = ["metric"] + [c.ticker for c in columns]
    rows: list[list[str]] = []
    for m in metric_keys:
        row = [m]
        for c in columns:
            row.append(_format_value(c.metrics.get(m), currency_mode=currency_mode))
        rows.append(row)

    widths = [max(len(str(r[i])) for r in [headers] + rows) for i in range(len(headers))]
    lines: list[str] = [_period_header(period_request, columns), ""]
    lines.append("  ".join(headers[i].ljust(widths[i]) for i in range(len(headers))))
    lines.append("  ".join("-" * widths[i] for i in range(len(headers))))
    for row in rows:
        lines.append("  ".join(str(row[i]).ljust(widths[i]) for i in range(len(headers))))
    lines.append("")
    for c in columns:
        lines.append(f"  {c.ticker}: {c.company}, {c.period}, reported in {c.reporting_currency}")
    diag_lines = _diagnostics_lines(columns)
    if diag_lines:
        lines.append("")
        lines.extend(diag_lines)
    return "\n".join(lines)


def _format_markdown(
    columns: list[CompanyColumn],
    metric_keys: list[str],
    period_request: str,
    *,
    currency_mode: str = "both",
) -> str:
    headers = ["metric"] + [c.ticker for c in columns]
    lines: list[str] = [f"**{_period_header(period_request, columns)}**", ""]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for m in metric_keys:
        row = [
            m,
            *[_format_value(c.metrics.get(m), currency_mode=currency_mode) for c in columns],
        ]
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    for c in columns:
        lines.append(f"_{c.ticker}: {c.company}, {c.period}, {c.reporting_currency}_")
    diag_lines = _diagnostics_lines(columns)
    if diag_lines:
        lines.append("")
        lines.append(f"**{diag_lines[0]}**")
        for line in diag_lines[1:]:
            lines.append(f"- {line.strip().lstrip('!').strip()}")
    return "\n".join(lines)


def _format_json(columns: list[CompanyColumn], period_request: str) -> str:
    return json.dumps(
        {
            "period_request": period_request,
            "companies": [
                {
                    "ticker": c.ticker,
                    "company": c.company,
                    "period": c.period,
                    "reporting_currency": c.reporting_currency,
                    "metrics": c.metrics,
                    **({"diagnostics": c.diagnostics} if c.diagnostics else {}),
                }
                for c in columns
            ],
        },
        indent=2,
        default=str,
    )


def cmd_compare(args: Any) -> int:
    from .identity import AmbiguousCompany, UnknownCompany, load_identity, resolve

    universe_path = Path("universe.toml")
    if universe_path.exists():
        try:
            idx = load_identity(universe_path)
        except AmbiguousCompany as e:
            print(f"Error: {e}", file=sys.stderr)
            return 2
        except Exception as e:
            print(f"Error: failed to load universe: {e}", file=sys.stderr)
            return 2

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

    strict_flag = bool(getattr(args, "strict", False))
    try:
        columns, strict_rejected = asyncio.run(
            _gather(args.companies, metrics, period, strict=strict_flag)
        )
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    except AmbiguousCompany as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    except ValueError as e:
        msg = str(e)
        print(f"Error: {msg}", file=sys.stderr)
        lower = msg.lower()
        if lower.startswith(("unknown ticker", "unknown company", "ambiguous company")):
            return 2
        return 1

    metric_keys = [m.strip() for m in metrics.split(",")]

    fmt = getattr(args, "compare_format", None) or "table"
    currency_mode = getattr(args, "currency", "both")
    if fmt == "json":
        import json as _json

        payload = _json.loads(_format_json(columns, period))
        if strict_flag and strict_rejected:
            payload["strict_rejected"] = strict_rejected
        print(_json.dumps(payload, indent=2, default=str))
    elif fmt == "markdown":
        print(_format_markdown(columns, metric_keys, period, currency_mode=currency_mode))
        if strict_flag and strict_rejected:
            flat = sorted({m for v in strict_rejected.values() for m in v})
            print("")
            print(f"_Strict mode: rejected learned values for: {', '.join(flat)}_")
    else:
        print(_format_table(columns, metric_keys, period, currency_mode=currency_mode))
        if strict_flag and strict_rejected:
            flat = sorted({m for v in strict_rejected.values() for m in v})
            print("")
            print(f"Strict mode: rejected learned values for: {', '.join(flat)}")
            print("Use `edgarpack learned list` to inspect, or re-run without --strict.")
    return 0
