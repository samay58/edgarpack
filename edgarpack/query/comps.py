"""Cross-company comparison queries."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from .financials import financials
from .models import CitedValue, QueryResult


async def comps(
    companies: list[str],
    metrics: list[str],
    period: str = "lfy",
    force: bool = False,
) -> dict[str, QueryResult]:
    """Query financial metrics for multiple companies in parallel.

    Args:
        companies: List of ticker symbols or CIK numbers.
        metrics: List of metric names.
        period: Period selector.
        force: Bypass cache.

    Returns:
        Dict keyed by company identifier, values are QueryResult.
    """
    tasks = [financials(company=c, metrics=metrics, period=period, force=force) for c in companies]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    output: dict[str, QueryResult] = {}
    for company, result in zip(companies, results):
        if isinstance(result, BaseException):
            # Return empty result for failed companies
            output[company] = QueryResult(
                company=company,
                cik="",
                metrics={m: None for m in metrics},
            )
        else:
            output[company] = result

    return output


def format_comps_table(
    results: dict[str, QueryResult],
    metrics: list[str],
) -> str:
    """Render comparison results as a human-readable table.

    Returns:
        Formatted string with table and citations footer.
    """
    # Build header
    header_parts = ["Company"]
    for m in metrics:
        header_parts.append(m.replace("_", " ").title())

    # Calculate column widths
    rows: list[list[str]] = []
    citations: list[str] = []
    citation_set: set[str] = set()

    for company, qr in results.items():
        row = [qr.company or company]
        for m in metrics:
            cited = qr.metrics.get(m)
            if cited is None or cited.value is None:
                row.append("N/A")
            else:
                row.append(_format_value(cited))
                cite = cited.citation
                if cite not in citation_set:
                    citation_set.add(cite)
                    citations.append(cite)
        rows.append(row)

    # Compute column widths
    all_rows = [header_parts] + rows
    col_widths = [max(len(row[i]) for row in all_rows) for i in range(len(header_parts))]

    # Format table
    lines = []

    # Header
    header_line = "  ".join(header_parts[i].ljust(col_widths[i]) for i in range(len(header_parts)))
    lines.append(header_line)
    lines.append("  ".join("-" * w for w in col_widths))

    # Rows
    for row in rows:
        line = "  ".join(
            row[i].rjust(col_widths[i]) if i > 0 else row[i].ljust(col_widths[i])
            for i in range(len(row))
        )
        lines.append(line)

    # Citations footer
    if citations:
        lines.append("")
        lines.append("Sources:")
        for cite in citations:
            lines.append(f"  - {cite}")

    return "\n".join(lines)


def comps_to_json(results: dict[str, QueryResult]) -> str:
    """Serialize comparison results to JSON with citations on every value."""
    output: dict[str, Any] = {}
    for company, qr in results.items():
        output[company] = qr.to_cited_dict()
    return json.dumps(output, indent=2, sort_keys=True, default=str)


def comps_to_lean_json(
    results: dict[str, QueryResult],
    metrics: list[str],
    period: str = "lfy",
) -> str:
    """Serialize comparison results to lean JSON format."""
    companies: dict[str, object] = {}
    for company, qr in results.items():
        companies[company] = qr.to_lean_dict()

    output: dict[str, object] = {
        "period": period,
        "requested_metrics": metrics,
        "companies": companies,
    }
    return json.dumps(output, indent=2, sort_keys=True, default=str)


_CURRENCY_SYMBOLS: dict[str, str] = {
    "USD": "$",
    "EUR": "\u20ac",
    "GBP": "\u00a3",
    "JPY": "\u00a5",
}


def _format_currency(val: float, unit: str) -> str:
    """Format a monetary value with currency symbol and B/M/K scaling."""
    symbol = _CURRENCY_SYMBOLS.get(unit, "")
    prefix = f"{symbol}" if symbol else f"{unit} "
    abs_val = abs(val)
    if abs_val >= 1_000_000_000:
        return f"{prefix}{val / 1_000_000_000:,.1f}B"
    elif abs_val >= 1_000_000:
        return f"{prefix}{val / 1_000_000:,.0f}M"
    elif abs_val >= 1_000:
        return f"{prefix}{val / 1_000:,.0f}K"
    else:
        return f"{prefix}{val:,.0f}"


def _format_value(cited: CitedValue) -> str:
    """Format a CitedValue for human display."""
    if cited.value is None:
        return "N/A"

    val = cited.value

    if cited.unit == "pure":
        # Ratio: display as percentage
        return f"{val * 100:.1f}%"
    elif cited.unit == "USD/shares":
        return f"${val:.2f}"
    elif cited.unit in _CURRENCY_SYMBOLS or cited.unit == "USD":
        return _format_currency(val, cited.unit)
    elif cited.unit == "shares":
        abs_val = abs(val)
        if abs_val >= 1_000_000_000:
            return f"{val / 1_000_000_000:,.1f}B"
        elif abs_val >= 1_000_000:
            return f"{val / 1_000_000:,.0f}M"
        else:
            return f"{val:,.0f}"
    else:
        # Unknown currency: treat as monetary with unit prefix
        if len(cited.unit) == 3 and cited.unit.isalpha():
            return _format_currency(val, cited.unit)
        return f"{val:,.2f}"
