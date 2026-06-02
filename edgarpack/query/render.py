"""Single-period query-result rendering for the CLI `query` command.

Extracted verbatim from cli.py (behavior-preserving). Holds the single-period
table renderer and its citation/marker/badge/text-wrap helpers. The multi-period
and comps renderers live in query/comps.py; this is their single-period sibling.
"""

from __future__ import annotations

import shutil
import textwrap
from typing import Any, cast


def _wrap_cli_text(text: str, width: int, indent: str = "      ") -> list[str]:
    """Wrap CLI text while preserving readable hanging indentation."""
    wrapped = textwrap.fill(
        text,
        width=max(40, width),
        subsequent_indent=indent,
        break_long_words=False,
        break_on_hyphens=False,
    )
    return wrapped.splitlines()


def _render_citation_lines(
    citation_id: str,
    record: dict[str, object],
    *,
    show_links: str,
    width: int,
) -> list[str]:
    """Render one citation record for table/audit output."""
    from .links import compact_url, osc8, supports_osc8

    lines: list[str] = []
    form_type = record.get("form_type")
    fiscal_label = record.get("fiscal_label")
    period = record.get("period")
    accession = record.get("accession")
    filed = record.get("filed")

    primary = record.get("primary_link")
    primary = primary if isinstance(primary, str) else ""
    osc8_on = supports_osc8()

    marker_label = f"[{citation_id}]"
    if show_links != "none" and osc8_on and primary:
        marker_label = osc8(primary, marker_label)

    summary = (
        f"{marker_label} {form_type} {fiscal_label} | period {period} | "
        f"filing {accession} | filed {filed}"
    )
    if show_links != "none" and not osc8_on and primary:
        summary = f"{summary}  {compact_url(primary)}"
    lines.extend(_wrap_cli_text(summary, width, indent="         "))

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
                    _wrap_cli_text(f"     {link_key}: {rendered}", width, indent="         ")
                )

    return lines


def _marker_with_link(
    marker: str,
    payload: dict[str, object] | None,
    citations_lookup: dict[str, dict[str, object]],
    calculations_lookup: dict[str, dict[str, object]],
    *,
    show_links: str,
) -> str:
    from .links import osc8, supports_osc8

    if show_links == "none" or not marker or not supports_osc8():
        return marker

    tag = marker.strip().lstrip("[").rstrip("]").split(",")[0].strip()
    record: dict[str, object] | None = None
    if tag.startswith(("C",)):
        record = citations_lookup.get(tag)
    elif tag.startswith(("L", "D", "G")):
        calc = calculations_lookup.get(tag)
        if isinstance(calc, dict):
            result_cid = calc.get("result_citation_id")
            if isinstance(result_cid, str):
                record = citations_lookup.get(result_cid)
    if not isinstance(record, dict):
        return marker
    link = record.get("primary_link")
    if not isinstance(link, str) or not link:
        return marker
    return osc8(link, marker)


def _source_badge_for(v: Any) -> str:
    """Render the source indicator that follows a metric's formatted value.

    - 'hardcoded' -> empty (no badge).
    - 's1_snapshot' / 's1_pro_forma' -> inline marker `[S-1, accn-short]`
      or `[S-1 pro-forma, accn-short] *` so S-1-sourced cells are visually
      distinct from periodic filings.
    - 'no_api_key' -> empty (the stderr hint tells the user what to do).
    - 'learned:kpi-*' -> ' [discovered]' (all discovered-KPI sources collapse
      to one human label; the specific taxonomy stays on CitedValue.source).
    - other 'learned:*' -> ' [<source> ✓]' (self-heal learned badge).
    - warning contains 'unverified' -> ✓ becomes ⚠.
    """
    src = getattr(v, "source", "hardcoded")
    if src == "hardcoded":
        return ""
    if src in ("s1_snapshot", "s1_pro_forma"):
        from .formatting import format_citation_marker

        marker = format_citation_marker(v)
        return f" {marker}" if marker else ""
    if src == "no_api_key":
        return ""
    if src.startswith("learned:kpi-"):
        return " [discovered]"
    mark = "✓"
    for w in getattr(v, "warnings", []):
        if "unverified" in w.lower():
            mark = "⚠"
            break
    return f" [{src} {mark}]"


def _render_query_table(result: Any, args: Any) -> str:
    """Render single-company query output with inline citation/audit ergonomics."""
    from .currency import CurrencyMode, format_cited_currency

    def _identifier_label() -> str:
        for raw_value in result.metrics.values():
            if raw_value is None:
                continue
            values = raw_value if isinstance(raw_value, list) else [raw_value]
            for value in values:
                standard = getattr(value, "accounting_standard", "")
                if standard in {"CAS", "HKFRS"}:
                    return "Stock Code"
        return "CIK"

    lean = result.to_lean_dict()
    metrics_lean = lean.get("metrics", {})
    citations = lean.get("citations", {})
    calculations = lean.get("calculations", {})
    permalink = lean.get("permalink")

    width = shutil.get_terminal_size((120, 20)).columns
    lines: list[str] = [f"{result.company} ({_identifier_label()}: {result.cik})", ""]
    currency_mode = cast(CurrencyMode, getattr(args, "currency", "both"))

    strict = bool(getattr(args, "strict", False))
    # Strict filtering is canonical in query.strict.apply_strict. When
    # invoked from _cmd_query the result has already been filtered and
    # the rejected-name list rides on args. When invoked directly (tests,
    # library use) we filter here so the render path stays self-contained.
    strict_rejected_incoming: list[str] = list(getattr(args, "_strict_rejected_names", ()))
    if strict and not strict_rejected_incoming:
        from .strict import apply_strict as _apply_strict_local

        strict_rejected_incoming = _apply_strict_local(result)
    strict_rejected: list[str] = []

    for metric_name, raw_value in result.metrics.items():
        label = metric_name.replace("_", " ").title()
        lean_value = metrics_lean.get(metric_name)

        if raw_value is None:
            if strict and metric_name in strict_rejected_incoming:
                lines.append(f"{label}: N/A [strict]")
                strict_rejected.append(metric_name)
            else:
                lines.append(f"{label}: N/A")
            continue

        if isinstance(raw_value, list):
            lines.append(f"{label}:")
            lean_items = lean_value if isinstance(lean_value, list) else []
            for idx, item in enumerate(raw_value):
                if item.value is None:
                    continue
                payload = lean_items[idx] if idx < len(lean_items) else {}
                marker = ""
                if args.citations != "off":
                    calc_id = payload.get("calculation_id") if isinstance(payload, dict) else None
                    citation_ids = (
                        payload.get("citation_ids") if isinstance(payload, dict) else None
                    )
                    if isinstance(calc_id, str):
                        marker = f" [{calc_id}]"
                    elif isinstance(citation_ids, list) and citation_ids:
                        marker = f" [{','.join(str(cid) for cid in citation_ids)}]"
                    marker = _marker_with_link(
                        marker,
                        payload if isinstance(payload, dict) else None,
                        citations,
                        calculations,
                        show_links=getattr(args, "show_links", "primary"),
                    )

                formatted_value = format_cited_currency(
                    item,
                    mode=currency_mode,
                    metric=metric_name,
                )
                lines.append(f"  {item.fiscal_label}: {formatted_value}{marker}")
                if isinstance(payload, dict):
                    warnings = payload.get("warnings", [])
                    if isinstance(warnings, list):
                        for warning in warnings:
                            lines.extend(
                                _wrap_cli_text(
                                    f"  ! warning: {warning}",
                                    width,
                                    indent="             ",
                                )
                            )
            continue

        payload = lean_value if isinstance(lean_value, dict) else {}
        marker = ""
        calc_id = payload.get("calculation_id")
        citation_ids = payload.get("citation_ids", [])
        if args.citations != "off":
            if isinstance(calc_id, str):
                marker = f" [{calc_id}]"
            elif isinstance(citation_ids, list) and citation_ids:
                marker = f" [{','.join(str(cid) for cid in citation_ids)}]"
            marker = _marker_with_link(
                marker,
                payload if isinstance(payload, dict) else None,
                citations,
                calculations,
                show_links=getattr(args, "show_links", "primary"),
            )

        source_badge = _source_badge_for(raw_value)
        formatted_value = format_cited_currency(
            raw_value,
            mode=currency_mode,
            metric=metric_name,
        )
        lines.append(f"{label}: {formatted_value}{marker}{source_badge}")

        warnings = payload.get("warnings", []) if isinstance(payload, dict) else []
        if isinstance(warnings, list):
            for warning in warnings:
                lines.extend(
                    _wrap_cli_text(
                        f"  ! warning: {warning}",
                        width,
                        indent="             ",
                    )
                )

        if args.citations == "inline":
            if isinstance(calc_id, str):
                calc = calculations.get(calc_id, {})
                formula = calc.get("formula", "")
                kind = calc.get("kind", "")
                if kind == "ltm":
                    components = calc.get("components", [])
                    if isinstance(components, list) and components:
                        comp_map = {
                            str(comp.get("role")): str(comp.get("citation_id"))
                            for comp in components
                            if isinstance(comp, dict)
                        }
                        expr = (
                            f"mrp[{comp_map.get('mrp', '?')}] + "
                            f"lfy[{comp_map.get('lfy', '?')}] - "
                            f"mrp_prior[{comp_map.get('mrp_prior', '?')}]"
                        )
                        lines.extend(
                            _wrap_cli_text(f"  [{calc_id}] LTM = {expr}", width, indent="         ")
                        )
                    else:
                        lines.extend(
                            _wrap_cli_text(
                                f"  [{calc_id}] formula: {formula}",
                                width,
                                indent="         ",
                            )
                        )
                else:
                    lines.extend(
                        _wrap_cli_text(
                            f"  [{calc_id}] formula: {formula}",
                            width,
                            indent="         ",
                        )
                    )

                if args.audit:
                    window = calc.get("window")
                    if isinstance(window, dict):
                        w_start = window.get("start")
                        w_end = window.get("end")
                        lines.extend(
                            _wrap_cli_text(
                                f"     window: {w_start}..{w_end}",
                                width,
                                indent="             ",
                            )
                        )

                    components = calc.get("components", [])
                    if isinstance(components, list):
                        for component in components:
                            if not isinstance(component, dict):
                                continue
                            role = component.get("role")
                            cid = component.get("citation_id")
                            value = component.get("value")
                            unit = component.get("unit")
                            fiscal = component.get("fiscal_label")
                            comp_line = f"     {role}[{cid}] value={value} {unit} | {fiscal}"
                            lines.extend(_wrap_cli_text(comp_line, width, indent="             "))
                            if isinstance(cid, str):
                                record = citations.get(cid)
                                if isinstance(record, dict):
                                    lines.extend(
                                        _render_citation_lines(
                                            cid,
                                            record,
                                            show_links=args.show_links,
                                            width=width,
                                        )
                                    )
            elif isinstance(citation_ids, list):
                for cid in citation_ids:
                    record = citations.get(cid)
                    if isinstance(record, dict):
                        lines.extend(
                            _render_citation_lines(
                                str(cid), record, show_links=args.show_links, width=width
                            )
                        )

    if args.citations == "footer":
        if citations:
            from .comps import _compact_citation_summaries

            lines.append("")
            lines.append("Sources:")
            lines.extend(
                line
                for summary in _compact_citation_summaries(citations)
                for line in _wrap_cli_text(summary, width, indent="  ")
            )
        if calculations:
            from .citations import calculation_summary

            lines.append("")
            lines.append("Calculations:")
            for calc_id in sorted(
                calculations.keys(),
                key=lambda x: (x[:1], int(x[1:]) if x[1:].isdigit() else 9999),
            ):
                calc = calculations.get(calc_id)
                if not isinstance(calc, dict):
                    continue
                lines.extend(
                    _wrap_cli_text(
                        calculation_summary(calc_id, calc),
                        width,
                        indent="         ",
                    )
                )

    diagnostics = result.diagnostics
    if diagnostics:
        lines.append("")
        lines.append("Diagnostics:")
        for diag in diagnostics:
            # Diagnostic is a pydantic model; getattr guards against stub dicts
            # slipping in via monkey-patched tests.
            metric_name = getattr(diag, "metric", "?")
            message = getattr(diag, "message", "")
            lines.extend(
                _wrap_cli_text(
                    f"  {metric_name}: {message}",
                    width,
                    indent="    ",
                )
            )

    if strict_rejected:
        lines.append("")
        lines.append(f"Strict mode: rejected learned values for: {', '.join(strict_rejected)}")
        lines.append("Use `edgarpack learned list` to inspect, or re-run without --strict.")

    if isinstance(permalink, str) and permalink:
        lines.append("")
        lines.extend(_wrap_cli_text(f"Reproduce: {permalink}", width, indent="           "))

    return "\n".join(lines)
