from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .fx import RateTable
from .query.citations import CitationRegistry, calculation_summary, citation_summary
from .query.formatting import format_number
from .query.models import CitedValue, DerivedValue

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
    values: dict[str, CitedValue] = field(default_factory=dict)
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
            values=flattened,
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


def _format_value(
    v: dict[str, Any] | None,
    *,
    currency_mode: str = "both",
    marker: str = "",
) -> str:
    if v is None or v.get("value") is None:
        return "n/a"
    # Growth is a signed delta (e.g., "+5%", "-3%"), not a finance-negative.
    # Keep the signed +/- formatter; don't route through format_number
    # which would wrap negatives in parens.
    if "growth" in (v or {}):
        pct = v["growth"] * 100
        text = f"{pct:+.0f}%" if abs(pct) >= 10 else f"{pct:+.1f}%"
        return f"{text} {marker}".rstrip()
    if "ratio" in (v or {}):
        text = format_number(v["ratio"], "pure")
        return f"{text} {marker}".rstrip()
    if "per_employee_usd" in (v or {}):
        if currency_mode == "native":
            text = format_number(float(v["value"]), v.get("currency", ""))
            return f"{text} {marker}".rstrip()
        native = format_number(float(v["value"]), v.get("currency", ""))
        suffix = f"; {v['fx_provenance']}" if v.get("fx_provenance") else ""
        if v.get("currency") and v.get("currency") != "USD":
            usd_text = format_number(float(v["per_employee_usd"]), "USD")
            text = f"{usd_text} (native: {native}{suffix})"
            return f"{text} {marker}".rstrip()
        text = format_number(float(v["per_employee_usd"]), "USD")
        return f"{text} {marker}".rstrip()
    if "headcount" in (v or {}):
        text = format_number(float(v["headcount"]), "headcount")
        return f"{text} {marker}".rstrip()
    val = v["value"]
    cur = v.get("currency", "")
    usd = v.get("usd_value")
    if usd is not None and cur != "USD":
        native = format_number(float(val), cur)
        if currency_mode == "native":
            return f"{native} {marker}".rstrip()
        suffix = f"; {v['fx_provenance']}" if v.get("fx_provenance") else ""
        text = f"{format_number(float(usd), 'USD')} (native: {native}{suffix})"
        return f"{text} {marker}".rstrip()
    if usd is not None:
        text = format_number(float(usd), "USD")
        return f"{text} {marker}".rstrip()
    if cur:
        text = format_number(float(val), cur)
        return f"{text} {marker}".rstrip()
    text = format_number(float(val), "")
    return f"{text} {marker}".rstrip()


def _citation_context(
    columns: list[CompanyColumn],
    metric_keys: list[str] | None = None,
) -> tuple[CitationRegistry, dict[tuple[int, str], str]]:
    registry = CitationRegistry()
    markers: dict[tuple[int, str], str] = {}
    for column_idx, column in enumerate(columns):
        keys = metric_keys or list(column.metrics)
        for metric in keys:
            item = column.values.get(metric)
            if item is None:
                continue
            markers[(column_idx, metric)] = registry.marker_for(metric, item)
    return registry, markers


def _source_lines(registry: CitationRegistry, *, markdown: bool = False) -> list[str]:
    lines: list[str] = []
    if not registry.calculations and not registry.citations:
        return lines
    if markdown:
        lines.append("**Sources**")
        for calc_id, record in registry.calculations.items():
            lines.append(f"- {calculation_summary(calc_id, record)}")
        for citation_id, record in registry.citations.items():
            lines.append(f"- {citation_summary(citation_id, record)}")
    else:
        lines.append("sources:")
        for calc_id, record in registry.calculations.items():
            lines.append(f"  {calculation_summary(calc_id, record)}")
        for citation_id, record in registry.citations.items():
            lines.append(f"  {citation_summary(citation_id, record)}")
    return lines


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
    registry, markers = _citation_context(columns, metric_keys)
    headers = ["metric"] + [c.ticker for c in columns]
    rows: list[list[str]] = []
    for m in metric_keys:
        row = [m]
        for idx, c in enumerate(columns):
            row.append(
                _format_value(
                    c.metrics.get(m),
                    currency_mode=currency_mode,
                    marker=markers.get((idx, m), ""),
                )
            )
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
    source_lines = _source_lines(registry)
    if source_lines:
        lines.append("")
        lines.extend(source_lines)
    return "\n".join(lines)


def _format_markdown(
    columns: list[CompanyColumn],
    metric_keys: list[str],
    period_request: str,
    *,
    currency_mode: str = "both",
) -> str:
    registry, markers = _citation_context(columns, metric_keys)
    headers = ["metric"] + [c.ticker for c in columns]
    lines: list[str] = [f"**{_period_header(period_request, columns)}**", ""]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for m in metric_keys:
        row = [
            m,
            *[
                _format_value(
                    c.metrics.get(m),
                    currency_mode=currency_mode,
                    marker=markers.get((idx, m), ""),
                )
                for idx, c in enumerate(columns)
            ],
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
    source_lines = _source_lines(registry, markdown=True)
    if source_lines:
        lines.append("")
        lines.extend(source_lines)
    return "\n".join(lines)


def _format_json(columns: list[CompanyColumn], period_request: str) -> str:
    registry, markers = _citation_context(columns)

    def _metric_payload(column_idx: int, metric: str, entry: dict[str, Any]) -> dict[str, Any]:
        payload = dict(entry)
        item = columns[column_idx].values.get(metric)
        marker = markers.get((column_idx, metric))
        if item is None or marker is None:
            return payload
        marker_id = marker.strip("[]")
        payload["marker"] = marker
        if isinstance(item, DerivedValue):
            calculation = registry.calculations.get(marker_id, {})
            payload["calculation_id"] = marker_id
            result_citation_id = calculation.get("result_citation_id")
            if result_citation_id:
                payload["result_citation_id"] = result_citation_id
            component_citation_ids = calculation.get("component_citation_ids")
            if component_citation_ids:
                payload["component_citation_ids"] = component_citation_ids
        else:
            payload["citation_ids"] = [marker_id]
        return payload

    return json.dumps(
        {
            "period_request": period_request,
            "companies": [
                {
                    "ticker": c.ticker,
                    "company": c.company,
                    "period": c.period,
                    "reporting_currency": c.reporting_currency,
                    "metrics": {
                        metric: _metric_payload(column_idx, metric, entry)
                        for metric, entry in c.metrics.items()
                    },
                    **({"diagnostics": c.diagnostics} if c.diagnostics else {}),
                }
                for column_idx, c in enumerate(columns)
            ],
            "citations": registry.citations,
            "calculations": registry.calculations,
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
