"""Cross-company comparison queries."""

from __future__ import annotations

import asyncio
import json
import textwrap
from typing import Any

from .financials import financials
from .formatting import _CURRENCY_SYMBOLS, format_number  # noqa: F401
from .models import CitedValue, DerivedValue, QueryResult


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
    """Register a ``CitedValue`` into the citation id/record maps, dedup by key."""
    key = cited.citation_key
    existing = citation_ids.get(key)
    if existing:
        return existing
    cid = f"C{len(citation_ids) + 1}"
    citation_ids[key] = cid
    citation_records[cid] = cited.to_citation_record(cid)
    return cid


def _register_calculation(
    metric_name: str,
    item: DerivedValue,
    citation_ids: dict[str, str],
    citation_records: dict[str, dict[str, object]],
    calc_ids: dict[str, str],
    calc_records: dict[str, dict[str, object]],
    formula_records: dict[tuple[str, str], dict[str, object]] | None = None,
) -> str:
    """Register a ``DerivedValue`` into the calculation id/record maps.

    Supports three kinds: ``LTM*`` values use an ``L`` prefix, ``CAGR*``
    values use ``G``, and everything else uses ``D``. Component citations are
    registered at the same time so the records reference stable ``C#`` ids.

    When ``formula_records`` is provided, the formula string is deduped per
    ``(metric_name, kind)`` so multi-period renderers can print the formula
    once while keeping per-period calc ids for data-cell markers and audit.
    """
    calc_key = f"{metric_name}|{item.citation_key}"
    existing = calc_ids.get(calc_key)
    if existing:
        return existing

    fp = item.fiscal_period.upper()
    if fp.startswith("LTM"):
        prefix = "L"
    elif fp.startswith("CAGR"):
        prefix = "G"
    else:
        prefix = "D"
    next_idx = 1 + sum(1 for cid in calc_records if cid.startswith(prefix))
    calc_id = f"{prefix}{next_idx}"
    calc_ids[calc_key] = calc_id

    components: list[dict[str, object]] = []
    for role, component in item.components.items():
        comp_cid = _register_citation(component, citation_ids, citation_records)
        components.append(
            {
                "role": role,
                "citation_id": comp_cid,
                "value": component.value,
                "unit": component.unit,
                "fiscal_label": component.fiscal_label,
                "period": component._period_str(),
                "accession": component.accession,
            }
        )

    result_cid = _register_citation(item, citation_ids, citation_records)
    if prefix == "L":
        kind = "ltm"
        formula = "mrp + lfy - mrp_prior"
    elif prefix == "G":
        kind = "cagr"
        formula = item.concept
    else:
        kind = "derived"
        formula = item.concept
    calc_records[calc_id] = {
        "id": calc_id,
        "metric": metric_name,
        "kind": kind,
        "formula": formula,
        "result_citation_id": result_cid,
        "components": components,
        "warnings": list(item.warnings),
        "fiscal_label": item.fiscal_label,
    }

    if formula_records is not None:
        formula_key = (metric_name, kind)
        rec = formula_records.get(formula_key)
        if rec is None:
            rec = {
                "metric": metric_name,
                "kind": kind,
                "formula": formula,
                "calc_ids": [],
            }
            formula_records[formula_key] = rec
        bound = rec["calc_ids"]
        if isinstance(bound, list):
            bound.append(calc_id)

    return calc_id


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

    citation_ids: dict[str, str] = {}
    citation_records: dict[str, dict[str, object]] = {}
    calc_ids: dict[str, str] = {}
    calc_records: dict[str, dict[str, object]] = {}
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
                marker = ""
                if isinstance(cited, DerivedValue):
                    calc_id = _register_calculation(
                        m, cited, citation_ids, citation_records, calc_ids, calc_records
                    )
                    marker = f"[{calc_id}]"
                else:
                    cid = _register_citation(cited, citation_ids, citation_records)
                    marker = f"[{cid}]"

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

    if citations_mode == "footer" and citation_records:
        lines.append("")
        lines.append("Sources:")
        for cid, record in citation_records.items():
            lines.extend(_with_width(f"{cid}: {record.get('citation', '')}"))
        return "\n".join(lines)

    if citations_mode != "off":
        from .links import compact_url, osc8, supports_osc8

        osc8_on = supports_osc8()

        if citation_records:
            lines.append("")
            lines.append("Citations:")
            for cid, record in citation_records.items():
                period = record.get("period")
                fiscal = record.get("fiscal_label")
                accn = record.get("accession")
                form_type = record.get("form_type")
                filed = record.get("filed")

                primary = record.get("primary_link")
                primary = primary if isinstance(primary, str) else ""
                label = f"[{cid}]"
                if show_links != "none" and osc8_on and primary:
                    label = osc8(primary, label)

                summary = (
                    f"{label} {form_type} {fiscal} | period {period} | accn {accn} | filed {filed}"
                )
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

        if calc_records:
            lines.append("")
            lines.append("Calculations:")
            for calc_id, calc in calc_records.items():
                formula = calc.get("formula", "")
                metric_name = calc.get("metric", "")
                line = f"[{calc_id}] {metric_name} = {formula}"
                lines.extend(_with_width(line, indent="       "))
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

    citation_ids: dict[str, str] = {}
    citation_records: dict[str, dict[str, object]] = {}
    calc_ids: dict[str, str] = {}
    calc_records: dict[str, dict[str, object]] = {}
    formula_records: dict[tuple[str, str], dict[str, object]] = {}
    warnings: list[str] = []

    def _metric_marker(
        metric: str,
        cited: CitedValue | DerivedValue,
    ) -> str:
        if isinstance(cited, DerivedValue):
            calc_id = _register_calculation(
                metric,
                cited,
                citation_ids,
                citation_records,
                calc_ids,
                calc_records,
                formula_records=formula_records,
            )
            return f"[{calc_id}]"
        cid = _register_citation(cited, citation_ids, citation_records)
        return f"[{cid}]"

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
                calc = calc_records.get(cid)
                if isinstance(calc, dict):
                    fl = calc.get("fiscal_label")
                    if isinstance(fl, str) and fl:
                        periods.append(fl)
            period_suffix = f"  ({', '.join(periods)})" if periods else ""
            head = f"[{id_list}] {metric_name} = {formula}{period_suffix}"
            lines.extend(_wrap(head, indent=indent))
            if audit:
                for cid in bound_list:
                    calc = calc_records.get(cid)
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
        if citation_records:
            lines.append("")
            lines.append("Sources:")
            for cid, record in citation_records.items():
                lines.extend(_wrap(f"{cid}: {record.get('citation', '')}"))
        _append_dedup_calculations()
    elif citations_mode == "inline":
        if citation_records:
            lines.append("")
            lines.append("Citations:")
            for cid, record in citation_records.items():
                period = record.get("period")
                fiscal = record.get("fiscal_label")
                accn = record.get("accession")
                form_type = record.get("form_type")
                filed = record.get("filed")
                summary = (
                    f"[{cid}] {form_type} {fiscal} | period {period} | accn {accn} | filed {filed}"
                )
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
) -> str:
    """Serialize a multi-period single-company query as lean JSON.

    Shape: ``metrics.<name>`` is an object keyed by period label, each value
    being the existing per-metric lean dict. Filings and citations are
    deduplicated across periods.
    """
    payload = _build_multi_period_dict(results_by_period, metrics, periods, lean=True)
    return json.dumps(payload, indent=2, sort_keys=False, default=str)


def multi_period_to_full_json(
    results_by_period: dict[str, QueryResult],
    metrics: list[str],
    periods: list[str],
) -> str:
    """Serialize a multi-period single-company query as full JSON (verbose)."""
    payload = _build_multi_period_dict(results_by_period, metrics, periods, lean=False)
    return json.dumps(payload, indent=2, sort_keys=False, default=str)


def _build_multi_period_dict(
    results_by_period: dict[str, QueryResult],
    metrics: list[str],
    periods: list[str],
    *,
    lean: bool,
) -> dict[str, object]:
    """Build the period-keyed metric dict shape shared by lean and full JSON."""
    primary = next(iter(results_by_period.values()), None)
    company = primary.company if primary is not None else ""
    cik = primary.cik if primary is not None else ""

    citation_ids: dict[str, str] = {}
    citation_records: dict[str, dict[str, object]] = {}
    calc_ids: dict[str, str] = {}
    calc_records: dict[str, dict[str, object]] = {}
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
        cid = _register_citation(cited, citation_ids, citation_records)
        data["citation_ids"] = [cid]
        _add_filing(cited)
        if isinstance(cited, DerivedValue):
            calc_id = _register_calculation(
                metric_name, cited, citation_ids, citation_records, calc_ids, calc_records
            )
            data["calculation_id"] = calc_id
            component_citation_ids: dict[str, str] = {}
            for role, comp in cited.components.items():
                comp_cid = _register_citation(comp, citation_ids, citation_records)
                component_citation_ids[role] = comp_cid
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
        "permalink": (
            f"edgarpack query {cik or company} {','.join(metrics)} --period {','.join(periods)}"
        ),
        "filings": filings,
        "metrics": metrics_out,
        "citations": citation_records,
        "calculations": calc_records,
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
    return format_number(cited.value, cited.unit or "pure")
