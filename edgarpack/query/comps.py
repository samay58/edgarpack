"""Cross-company comparison queries."""

from __future__ import annotations

import asyncio
import json
import textwrap
from typing import Any

from .citations import CitationRegistry, calculation_summary, citation_summary
from .financials import financials
from .formatting import format_number
from .models import CitedValue, DerivedValue, QueryResult
from .periods import parse_period_spec


async def comps(
    companies: list[str],
    metrics: list[str],
    period: str = "lfy",
    force: bool = False,
) -> dict[str, QueryResult]:
    """Query financial metrics for multiple companies in parallel.

    Args:
        companies: List of tickers, CIKs, or company names. Each entry is
            passed through ``financials()``, which resolves all three shapes
            via the SEC ticker list.
        metrics: List of metric names.
        period: Period selector (see ``financials`` for the accepted forms).
        force: Bypass the on-disk cache for SEC lookups.

    Returns:
        Dict keyed by the caller's input string. Failed lookups yield a
        ``QueryResult`` with empty metrics rather than raising.
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


def _register_citation(
    cited: CitedValue,
    citation_ids: dict[str, str],
    citation_records: dict[str, dict[str, object]],
) -> str:
    """Backward-compatible wrapper around the shared citation registry."""
    registry = CitationRegistry(citation_ids=citation_ids, citations=citation_records)
    return registry.register_citation(cited)


def _register_calculation(
    metric_name: str,
    item: DerivedValue,
    citation_ids: dict[str, str],
    citation_records: dict[str, dict[str, object]],
    calc_ids: dict[str, str],
    calc_records: dict[str, dict[str, object]],
    formula_records: dict[tuple[str, str], dict[str, object]] | None = None,
) -> str:
    """Backward-compatible wrapper around the shared citation registry."""
    registry = CitationRegistry(
        citation_ids=citation_ids,
        citations=citation_records,
        calculation_ids=calc_ids,
        calculations=calc_records,
        formula_records=formula_records,
    )
    return registry.register_calculation(metric_name, item)


def expand_comps_periods(spec: str) -> list[str]:
    """Parse a comps period spec into scalar columns.

    ``query`` can ask ``financials()`` for ``annual:N`` directly because it
    renders a single company. For comps, expanding annual history into
    relative scalar selectors gives a clean company x metric x period grid and
    lets derived metrics resolve through the same path as ``lfy,lfy-1``.
    """
    periods = parse_period_spec(spec)
    if len(periods) == 1 and periods[0].startswith("annual:"):
        count = int(periods[0].split(":", 1)[1])
        if count <= 0:
            raise ValueError("annual:N must request at least one period")
        return ["lfy"] + [f"lfy-{idx}" for idx in range(1, count)]
    return periods


def _compact_citation_summaries(citations: dict[str, dict[str, object]]) -> list[str]:
    """Group value-level citation IDs by filing/window for compact footers."""
    grouped: dict[tuple[object, ...], list[str]] = {}
    records_by_key: dict[tuple[object, ...], dict[str, object]] = {}
    for cid, record in citations.items():
        key = (
            record.get("form_type"),
            record.get("fiscal_label"),
            record.get("period"),
            record.get("accession"),
            record.get("filed"),
        )
        grouped.setdefault(key, []).append(cid)
        records_by_key.setdefault(key, record)

    lines: list[str] = []
    for key, ids in grouped.items():
        record = records_by_key[key]
        if len(ids) == 1:
            lines.append(citation_summary(ids[0], record))
            continue
        id_list = ", ".join(ids)
        form_type = record.get("form_type")
        fiscal = record.get("fiscal_label")
        period = record.get("period")
        filing = record.get("accession")
        filed = record.get("filed")
        lines.append(
            f"[{id_list}] {form_type} {fiscal} | period {period} | "
            f"filing {filing} | filed {filed}"
        )
    return lines


def format_comps_table(
    results: dict[str, QueryResult],
    metrics: list[str],
    *,
    citations_mode: str = "inline",
    show_links: str = "primary",
    audit: bool = False,
    terminal_width: int | None = None,
) -> str:
    """Render comparison results as a human-readable table.

    Returns:
        Formatted string with table and citation/calculation registry.
    """
    citations_mode = citations_mode.lower().strip()
    show_links = show_links.lower().strip()

    def _with_width(text: str, indent: str = "  ") -> list[str]:
        width = terminal_width or 120
        wrapped = textwrap.fill(
            text,
            width=max(40, width),
            subsequent_indent=indent,
            break_long_words=False,
            break_on_hyphens=False,
        )
        return wrapped.splitlines()

    header_parts = ["Company"]
    for m in metrics:
        header_parts.append(m.replace("_", " ").title())

    registry = CitationRegistry()
    warnings: list[str] = []

    # Calculate column widths and emit markers
    rows: list[list[str]] = []

    for company, qr in results.items():
        row = [qr.company or company]
        for m in metrics:
            raw_value = qr.metrics.get(m)
            cited = raw_value[0] if isinstance(raw_value, list) and raw_value else raw_value
            if cited is None or cited.value is None:
                row.append("N/A")
            else:
                formatted = _format_value(cited)
                marker = registry.marker_for(m, cited)

                warn_marker = ""
                if cited.warnings:
                    warn_marker = " !"
                    warnings.extend(f"{qr.company or company} {m}: {w}" for w in cited.warnings)

                if citations_mode == "off":
                    row.append(f"{formatted}{warn_marker}")
                else:
                    row.append(f"{formatted} {marker}{warn_marker}".rstrip())
        rows.append(row)

    lines = []
    width = terminal_width or 120
    stacked_mode = width < 96 and len(metrics) > 1

    if stacked_mode:
        for row in rows:
            company_name = row[0]
            lines.append(company_name)
            for idx, metric_name in enumerate(metrics, start=1):
                label = metric_name.replace("_", " ").title()
                lines.append(f"  {label}: {row[idx]}")
            lines.append("")
        if lines and lines[-1] == "":
            lines.pop()
    else:
        all_rows = [header_parts] + rows
        col_widths = [max(len(row[i]) for row in all_rows) for i in range(len(header_parts))]
        header_line = "  ".join(
            header_parts[i].ljust(col_widths[i]) for i in range(len(header_parts))
        )
        lines.append(header_line)
        lines.append("  ".join("-" * w for w in col_widths))
        for row in rows:
            line = "  ".join(
                row[i].rjust(col_widths[i]) if i > 0 else row[i].ljust(col_widths[i])
                for i in range(len(row))
            )
            lines.append(line)

    if citations_mode == "footer":
        if registry.citations or registry.calculations or warnings:
            lines.append("")
        if registry.citations:
            lines.append("Sources:")
            for summary in _compact_citation_summaries(registry.citations):
                lines.extend(_with_width(summary))
        if registry.calculations:
            if registry.citations:
                lines.append("")
            lines.append("Calculations:")
            for calc_id, calc in registry.calculations.items():
                lines.extend(_with_width(calculation_summary(calc_id, calc), indent="       "))
                if audit:
                    components = calc.get("components", [])
                    if isinstance(components, list):
                        for comp in components:
                            if not isinstance(comp, dict):
                                continue
                            role = comp.get("role")
                            cid = comp.get("citation_id")
                            value = comp.get("value")
                            unit = comp.get("unit")
                            fiscal = comp.get("fiscal_label")
                            comp_line = f"     {role}[{cid}] value={value} {unit} | {fiscal}"
                            lines.extend(_with_width(comp_line, indent="       "))
        if warnings:
            lines.append("")
            lines.append("Warnings:")
            for warning in warnings:
                lines.extend(_with_width(f"- {warning}", indent="  "))
        return "\n".join(lines)

    if citations_mode != "off":
        from .links import compact_url, osc8, supports_osc8

        osc8_on = supports_osc8()

        if registry.citations:
            lines.append("")
            lines.append("Citations:")
            for cid, record in registry.citations.items():
                primary = record.get("primary_link")
                primary = primary if isinstance(primary, str) else ""
                label = f"[{cid}]"
                if show_links != "none" and osc8_on and primary:
                    label = osc8(primary, label)

                summary = citation_summary(cid, record).replace(f"[{cid}]", label, 1)
                if show_links != "none" and not osc8_on and primary:
                    summary = f"{summary}  {compact_url(primary)}"
                lines.extend(_with_width(summary, indent="       "))

                if show_links == "all":
                    links = record.get("links", {})
                    if isinstance(links, dict):
                        for link_key, link_value in links.items():
                            if not isinstance(link_value, str) or not link_value:
                                continue
                            rendered = compact_url(link_value)
                            if osc8_on:
                                rendered = osc8(link_value, rendered)
                            lines.extend(
                                _with_width(
                                    f"     {link_key}: {rendered}",
                                    indent="       ",
                                )
                            )

        if registry.calculations:
            lines.append("")
            lines.append("Calculations:")
            for calc_id, calc in registry.calculations.items():
                lines.extend(_with_width(calculation_summary(calc_id, calc), indent="       "))
                if audit:
                    components = calc.get("components", [])
                    if isinstance(components, list):
                        for comp in components:
                            if not isinstance(comp, dict):
                                continue
                            role = comp.get("role")
                            cid = comp.get("citation_id")
                            value = comp.get("value")
                            unit = comp.get("unit")
                            fiscal = comp.get("fiscal_label")
                            comp_line = f"     {role}[{cid}] value={value} {unit} | {fiscal}"
                            lines.extend(_with_width(comp_line, indent="       "))

    if warnings:
        lines.append("")
        lines.append("Warnings:")
        for warning in warnings:
            lines.extend(_with_width(f"- {warning}", indent="  "))

    return "\n".join(lines)


def format_comps_multi_period_table(
    results_by_period: dict[str, dict[str, QueryResult]],
    metrics: list[str],
    periods: list[str],
    *,
    companies: list[str] | None = None,
    citations_mode: str = "footer",
    show_links: str = "primary",
    audit: bool = False,
    terminal_width: int | None = None,
) -> str:
    """Render a cross-company, multi-period comparison grid.

    Rows are ``Company`` + ``Metric`` and columns are the caller's period
    selectors. This keeps comps ergonomics aligned with query's metrics x
    periods view while preserving cross-company scanability.
    """
    citations_mode = citations_mode.lower().strip()
    show_links = show_links.lower().strip()
    formula_records: dict[tuple[str, str], dict[str, object]] = {}
    registry = CitationRegistry(formula_records=formula_records)
    warnings: list[str] = []

    if companies is None:
        seen_companies: list[str] = []
        for period in periods:
            for company in results_by_period.get(period, {}):
                if company not in seen_companies:
                    seen_companies.append(company)
        companies = seen_companies

    header_parts = ["Company", "Metric"] + [_period_label(period) for period in periods]
    rows: list[list[str]] = []

    for company_key in companies:
        company_label = company_key
        for period in periods:
            qr = results_by_period.get(period, {}).get(company_key)
            if qr is not None and qr.company:
                company_label = qr.company
                break

        for metric_index, metric in enumerate(metrics):
            row = [company_label if metric_index == 0 else "", _metric_label(metric)]
            for period in periods:
                qr = results_by_period.get(period, {}).get(company_key)
                raw_value = None if qr is None else qr.metrics.get(metric)
                cited = raw_value[0] if isinstance(raw_value, list) and raw_value else raw_value
                if cited is None or cited.value is None:
                    row.append("N/A")
                    continue

                formatted = _format_value(cited)
                warn_marker = ""
                if cited.warnings:
                    warn_marker = " !"
                    warnings.extend(
                        f"{qr.company or company_key} {metric} ({period}): {w}"
                        for w in cited.warnings
                    )

                if citations_mode == "off":
                    row.append(f"{formatted}{warn_marker}")
                else:
                    marker = registry.marker_for(metric, cited)
                    row.append(f"{formatted} {marker}{warn_marker}".rstrip())
            rows.append(row)

    width = terminal_width or 120
    all_rows = [header_parts] + rows
    col_widths = [max(len(row[i]) for row in all_rows) for i in range(len(header_parts))]
    required_width = sum(col_widths) + 2 * (len(header_parts) - 1)
    stacked_mode = len(periods) > 1 and required_width > width

    lines: list[str] = []
    if stacked_mode:
        current_company = ""
        for row in rows:
            if row[0]:
                if lines:
                    lines.append("")
                current_company = row[0]
                lines.append(current_company)
            lines.append(f"  {row[1]}")
            for idx, period in enumerate(periods, start=2):
                lines.append(f"    {_period_label(period)}: {row[idx]}")
    else:
        header_line = "  ".join(
            header_parts[i].ljust(col_widths[i]) for i in range(len(header_parts))
        )
        lines.append(header_line)
        lines.append("  ".join("-" * width for width in col_widths))
        for row in rows:
            line = "  ".join(
                row[i].rjust(col_widths[i]) if i > 1 else row[i].ljust(col_widths[i])
                for i in range(len(row))
            )
            lines.append(line)

    def _wrap(text: str, indent: str = "  ") -> list[str]:
        w = terminal_width or 120
        wrapped = textwrap.fill(
            text,
            width=max(40, w),
            subsequent_indent=indent,
            break_long_words=False,
            break_on_hyphens=False,
        )
        return wrapped.splitlines()

    def _append_calculations(indent: str = "       ") -> None:
        if not formula_records:
            return
        lines.append("")
        lines.append("Calculations:")
        for (metric_name, _kind), rec in formula_records.items():
            formula = rec.get("formula", "")
            bound = rec.get("calc_ids", [])
            bound_list = [str(cid) for cid in bound] if isinstance(bound, list) else []
            lines.extend(_wrap(f"[{', '.join(bound_list)}] {metric_name} = {formula}", indent))
            if audit:
                for cid in bound_list:
                    calc = registry.calculations.get(cid)
                    if not isinstance(calc, dict):
                        continue
                    components = calc.get("components", [])
                    if not isinstance(components, list):
                        continue
                    for comp in components:
                        if not isinstance(comp, dict):
                            continue
                        role = comp.get("role")
                        c_cid = comp.get("citation_id")
                        value = comp.get("value")
                        unit = comp.get("unit")
                        fiscal = comp.get("fiscal_label")
                        lines.extend(
                            _wrap(
                                f"  [{cid}] {role}[{c_cid}] value={value} {unit} | {fiscal}",
                                indent=indent,
                            )
                        )

    if citations_mode == "footer":
        if registry.citations:
            lines.append("")
            lines.append("Sources:")
            for summary in _compact_citation_summaries(registry.citations):
                lines.extend(_wrap(summary))
        _append_calculations()
    elif citations_mode != "off":
        if registry.citations:
            lines.append("")
            lines.append("Citations:")
            for cid, record in registry.citations.items():
                summary = citation_summary(cid, record)
                lines.extend(_wrap(summary, indent="       "))
                if show_links == "primary":
                    link = record.get("primary_link")
                    link_type = record.get("primary_link_type")
                    if isinstance(link, str) and link:
                        lines.extend(_wrap(f"     link({link_type}): {link}", indent="       "))
                elif show_links == "all":
                    links = record.get("links", {})
                    if isinstance(links, dict):
                        for link_key, link_value in links.items():
                            if isinstance(link_value, str):
                                lines.extend(
                                    _wrap(f"     {link_key}: {link_value}", indent="       ")
                                )
        _append_calculations()

    if warnings:
        lines.append("")
        lines.append("Warnings:")
        for warning in warnings:
            lines.extend(_wrap(f"- {warning}", indent="  "))

    return "\n".join(lines)


def comps_multi_period_to_lean_json(
    results_by_period: dict[str, dict[str, QueryResult]],
    metrics: list[str],
    periods: list[str],
    *,
    companies: list[str] | None = None,
) -> str:
    """Serialize multi-period comps to lean JSON without flattening periods."""
    if companies is None:
        companies = []
        for period in periods:
            for company in results_by_period.get(period, {}):
                if company not in companies:
                    companies.append(company)

    company_payloads: dict[str, object] = {}
    for company in companies:
        per_period: dict[str, object] = {}
        for period in periods:
            qr = results_by_period.get(period, {}).get(company)
            per_period[period] = qr.to_lean_dict() if qr is not None else None
        company_payloads[company] = {"periods": per_period}

    return json.dumps(
        {
            "periods": periods,
            "requested_metrics": metrics,
            "companies": company_payloads,
        },
        indent=2,
        sort_keys=False,
        default=str,
    )


def comps_multi_period_to_json(
    results_by_period: dict[str, dict[str, QueryResult]],
    periods: list[str],
    *,
    companies: list[str] | None = None,
) -> str:
    """Serialize multi-period comps to verbose JSON without flattening periods."""
    if companies is None:
        companies = []
        for period in periods:
            for company in results_by_period.get(period, {}):
                if company not in companies:
                    companies.append(company)

    company_payloads: dict[str, object] = {}
    for company in companies:
        per_period: dict[str, object] = {}
        for period in periods:
            qr = results_by_period.get(period, {}).get(company)
            per_period[period] = qr.to_cited_dict() if qr is not None else None
        company_payloads[company] = {"periods": per_period}

    return json.dumps(
        {
            "periods": periods,
            "companies": company_payloads,
        },
        indent=2,
        sort_keys=False,
        default=str,
    )


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


def _period_label(spec: str) -> str:
    """Pretty label for a period selector.

    ``lfy`` -> ``LFY``, ``lfy-2`` -> ``LFY-2``, ``ltm-1`` -> ``LTM-1``, etc.
    """
    s = spec.strip().lower()
    if "-" in s:
        head, tail = s.split("-", 1)
        return f"{head.upper()}-{tail}"
    return s.upper()


def _metric_label(metric: str) -> str:
    """Human-readable metric label for table headers/rows.

    Keeps the ``Y`` uppercase on ``_3y`` / ``_5y`` suffixes so CAGR columns read
    as ``Revenue Cagr 3Y`` instead of ``Revenue Cagr 3y``.
    """
    label = metric.replace("_", " ").title()
    # Fix suffix 3y/5y casing.
    for token in (" 3Y", " 5Y", " 1Y", " 10Y"):
        lowered = token.lower()
        label = label.replace(lowered, token)
    return label


def format_financial_perf_table(
    results_by_period: dict[str, QueryResult],
    metrics: list[str],
    periods: list[str],
    *,
    citations_mode: str = "footer",
    show_links: str = "primary",
    audit: bool = False,
    terminal_width: int | None = None,
) -> str:
    """Render a single-company metrics x periods grid.

    Rows are metrics (in caller order). Columns are ``Metric`` plus the period
    labels in caller order. Cell values use the same currency/percentage
    formatting as ``format_comps_table``.

    ``citations_mode``:
    - ``"footer"`` (default for this view): emit one numbered citations table
      under the grid and omit per-cell markers
    - ``"inline"``: per-cell markers ``[C#]`` / ``[D#]`` / ``[L#]`` plus a full
      citations/calculations section
    - ``"off"``: no citation output at all
    """
    citations_mode = citations_mode.lower().strip()
    show_links = show_links.lower().strip()

    formula_records: dict[tuple[str, str], dict[str, object]] = {}
    registry = CitationRegistry(formula_records=formula_records)
    warnings: list[str] = []

    def _metric_marker(
        metric: str,
        cited: CitedValue | DerivedValue,
    ) -> str:
        return registry.marker_for(metric, cited)

    header_parts = ["Metric"] + [_period_label(p) for p in periods]

    data_rows: list[list[str]] = []
    for metric in metrics:
        row: list[str] = [_metric_label(metric)]
        for period in periods:
            qr = results_by_period.get(period)
            raw_value = None if qr is None else qr.metrics.get(metric)
            cited = raw_value[0] if isinstance(raw_value, list) and raw_value else raw_value
            if cited is None or cited.value is None:
                row.append("N/A")
                continue

            formatted = _format_value(cited)
            marker = ""
            if citations_mode != "off":
                marker = _metric_marker(metric, cited)

            warn_marker = ""
            if cited.warnings:
                warn_marker = " !"
                company_label = qr.company or "" if qr is not None else ""
                warnings.extend(f"{company_label} {metric} ({period}): {w}" for w in cited.warnings)

            if citations_mode == "off":
                row.append(f"{formatted}{warn_marker}")
            else:
                # Keep compact markers inline even in footer mode so each cell
                # still traces back to a specific source/calculation entry.
                row.append(f"{formatted} {marker}{warn_marker}".rstrip())
        data_rows.append(row)

    width = terminal_width or 120

    # Compute required table width from actual content; only fall back to
    # stacked layout if the grid genuinely won't fit. The static 96-col
    # threshold used by ``format_comps_table`` is too conservative for this
    # view, which usually has far fewer columns.
    all_rows = [header_parts] + data_rows
    col_widths = [max(len(row[i]) for row in all_rows) for i in range(len(header_parts))]
    required_width = sum(col_widths) + 2 * (len(header_parts) - 1)
    stacked_mode = len(periods) > 1 and required_width > width

    lines: list[str] = []
    primary_result = next(iter(results_by_period.values()), None)
    if primary_result is not None:
        lines.append(f"{primary_result.company} (CIK: {primary_result.cik})")
        lines.append("")

    if stacked_mode:
        for row in data_rows:
            label = row[0]
            lines.append(label)
            for idx, period in enumerate(periods, start=1):
                lines.append(f"  {_period_label(period)}: {row[idx]}")
            lines.append("")
        if lines and lines[-1] == "":
            lines.pop()
    else:
        header_line = "  ".join(
            header_parts[i].ljust(col_widths[i]) for i in range(len(header_parts))
        )
        lines.append(header_line)
        lines.append("  ".join("-" * w for w in col_widths))
        for row in data_rows:
            line = "  ".join(
                row[i].rjust(col_widths[i]) if i > 0 else row[i].ljust(col_widths[i])
                for i in range(len(row))
            )
            lines.append(line)

    # Citations / calculations blocks
    def _wrap(text: str, indent: str = "  ") -> list[str]:
        w = terminal_width or 120
        wrapped = textwrap.fill(
            text,
            width=max(40, w),
            subsequent_indent=indent,
            break_long_words=False,
            break_on_hyphens=False,
        )
        return wrapped.splitlines()

    def _append_dedup_calculations(indent: str = "       ") -> None:
        """Emit one formula summary per (metric, kind) instead of per-period.

        Under ``audit=True`` each bound calc_id also gets a per-period
        component breakdown so provenance stays traceable."""
        if not formula_records:
            return
        lines.append("")
        lines.append("Calculations:")
        for (metric_name, kind), rec in formula_records.items():
            formula = rec.get("formula", "")
            bound = rec.get("calc_ids", [])
            bound_list = [str(cid) for cid in bound] if isinstance(bound, list) else []
            id_list = ", ".join(bound_list)
            periods: list[str] = []
            for cid in bound_list:
                calc = registry.calculations.get(cid)
                if isinstance(calc, dict):
                    fl = calc.get("fiscal_label")
                    if isinstance(fl, str) and fl:
                        periods.append(fl)
            period_suffix = f"  ({', '.join(periods)})" if periods else ""
            head = f"[{id_list}] {metric_name} = {formula}{period_suffix}"
            lines.extend(_wrap(head, indent=indent))
            if audit:
                for cid in bound_list:
                    calc = registry.calculations.get(cid)
                    if not isinstance(calc, dict):
                        continue
                    fl = calc.get("fiscal_label", "")
                    components = calc.get("components", [])
                    if isinstance(components, list):
                        for comp in components:
                            if not isinstance(comp, dict):
                                continue
                            role = comp.get("role")
                            c_cid = comp.get("citation_id")
                            value = comp.get("value")
                            unit = comp.get("unit")
                            fiscal = comp.get("fiscal_label") or fl
                            lines.extend(
                                _wrap(
                                    f"  [{cid}] {role}[{c_cid}] value={value} {unit} | {fiscal}",
                                    indent=indent,
                                )
                            )

    if citations_mode == "footer":
        if registry.citations:
            lines.append("")
            lines.append("Sources:")
            for summary in _compact_citation_summaries(registry.citations):
                lines.extend(_wrap(summary))
        _append_dedup_calculations()
    elif citations_mode == "inline":
        if registry.citations:
            lines.append("")
            lines.append("Citations:")
            for cid, record in registry.citations.items():
                summary = citation_summary(cid, record)
                lines.extend(_wrap(summary, indent="       "))
                if show_links == "primary":
                    link = record.get("primary_link")
                    link_type = record.get("primary_link_type")
                    if isinstance(link, str) and link:
                        lines.extend(_wrap(f"     link({link_type}): {link}", indent="       "))
                elif show_links == "all":
                    links = record.get("links", {})
                    if isinstance(links, dict):
                        for link_key, link_value in links.items():
                            if isinstance(link_value, str):
                                lines.extend(
                                    _wrap(
                                        f"     {link_key}: {link_value}",
                                        indent="       ",
                                    )
                                )
        _append_dedup_calculations()

    if warnings:
        lines.append("")
        lines.append("Warnings:")
        for warning in warnings:
            lines.extend(_wrap(f"- {warning}", indent="  "))

    return "\n".join(lines)


def multi_period_to_lean_json(
    results_by_period: dict[str, QueryResult],
    metrics: list[str],
    periods: list[str],
    *,
    display_token: str | None = None,
) -> str:
    """Serialize a multi-period single-company query as lean JSON.

    Shape: ``metrics.<name>`` is an object keyed by period label, each value
    being the existing per-metric lean dict. Filings and citations are
    deduplicated across periods.
    """
    payload = _build_multi_period_dict(
        results_by_period, metrics, periods, lean=True, display_token=display_token
    )
    return json.dumps(payload, indent=2, sort_keys=False, default=str)


def multi_period_to_full_json(
    results_by_period: dict[str, QueryResult],
    metrics: list[str],
    periods: list[str],
    *,
    display_token: str | None = None,
) -> str:
    """Serialize a multi-period single-company query as full JSON (verbose)."""
    payload = _build_multi_period_dict(
        results_by_period, metrics, periods, lean=False, display_token=display_token
    )
    return json.dumps(payload, indent=2, sort_keys=False, default=str)


def _build_permalink(
    *,
    cik: str | None,
    company: str | None,
    metrics: list[str],
    periods: list[str],
    display_token: str | None,
) -> str:
    """Build the Reproduce line. Prefers user's input token over CIK."""
    subject = display_token or cik or company or ""
    return f"edgarpack query {subject} {','.join(metrics)} --period {','.join(periods)}"


def _build_multi_period_dict(
    results_by_period: dict[str, QueryResult],
    metrics: list[str],
    periods: list[str],
    *,
    lean: bool,
    display_token: str | None = None,
) -> dict[str, object]:
    """Build the period-keyed metric dict shape shared by lean and full JSON."""
    primary = next(iter(results_by_period.values()), None)
    company = primary.company if primary is not None else ""
    cik = primary.cik if primary is not None else ""

    registry = CitationRegistry()
    filings: dict[str, dict[str, object]] = {}

    def _add_filing(cited: CitedValue) -> None:
        if not cited.accession or cited.accession in filings:
            return
        entry: dict[str, object] = {
            "form_type": cited.form_type,
            "filed": str(cited.filed),
            "fiscal_year": cited.fiscal_year,
            "fiscal_period": cited.fiscal_period,
            "url": cited.filing_url,
            "primary_link": cited.primary_link,
            "primary_link_type": cited.primary_link_type,
        }
        if cited.viewer_url:
            entry["viewer_url"] = cited.viewer_url
        if cited.anchor_url and cited.fact_id:
            entry["anchor_url"] = cited.anchor_url
        filings[cited.accession] = entry

    def _serialize(cited: CitedValue | DerivedValue, metric_name: str) -> dict[str, object]:
        data = cited.to_lean_metric() if lean else cited.to_cited_dict()
        cid = registry.register_citation(cited)
        data["citation_ids"] = [cid]
        _add_filing(cited)
        if isinstance(cited, DerivedValue):
            calc_id = registry.register_calculation(metric_name, cited)
            data["calculation_id"] = calc_id
            component_citation_ids = registry.component_citation_ids_for(cited)
            for comp in cited.components.values():
                _add_filing(comp)
            if component_citation_ids:
                data["component_citation_ids"] = component_citation_ids
        return data

    metrics_out: dict[str, dict[str, object]] = {}
    for metric in metrics:
        per_period: dict[str, object] = {}
        for period in periods:
            qr = results_by_period.get(period)
            raw_value = None if qr is None else qr.metrics.get(metric)
            if raw_value is None:
                per_period[period] = None
                continue
            if isinstance(raw_value, list):
                per_period[period] = [_serialize(v, metric) for v in raw_value if v is not None]
                continue
            per_period[period] = _serialize(raw_value, metric)
        metrics_out[metric] = per_period

    diagnostics_by_period: dict[str, list[dict[str, object]]] = {}
    for period, qr in results_by_period.items():
        if qr.diagnostics:
            diagnostics_by_period[period] = [diag.model_dump() for diag in qr.diagnostics]

    result: dict[str, object] = {
        "company": company,
        "cik": cik,
        "periods": periods,
        "permalink": _build_permalink(
            cik=cik,
            company=company,
            metrics=metrics,
            periods=periods,
            display_token=display_token,
        ),
        "filings": filings,
        "metrics": metrics_out,
        "citations": registry.citations,
        "calculations": registry.calculations,
    }
    if diagnostics_by_period:
        result["diagnostics_by_period"] = diagnostics_by_period
    return result


def _format_value(cited: CitedValue) -> str:
    """Format a CitedValue for human display.

    Delegates to the canonical `format_number` primitive in
    `edgarpack.query.formatting`. See that module for the full rule set
    (magnitude scaling, small-value precision bump, finance negatives).
    """
    if cited.value is None:
        return "N/A"
    return format_number(cited.value, cited.unit or "")
