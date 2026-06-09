"""Write distilled filing bundles to disk."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, fields
from pathlib import Path

from .models import OUTPUT_FILES, DistillBundle, FindingRow, GapRow, MetricRow


def write_distill_bundle(bundle: DistillBundle, *, force: bool = False) -> Path:
    out = bundle.output_dir
    if out.exists() and any(out.iterdir()) and not force:
        raise FileExistsError(f"{out} already exists and is not empty. Pass --force to overwrite.")
    out.mkdir(parents=True, exist_ok=True)

    _write_index(bundle, out / "index.md")
    _write_csv(out / "findings.csv", bundle.findings, FindingRow)
    _write_csv(out / "metrics.csv", bundle.metrics, MetricRow)
    _write_csv(out / "gaps.csv", bundle.gaps, GapRow)
    _write_evidence(bundle, out / "evidence.jsonl")
    _write_filing_map(bundle, out / "filing-map.md")
    _write_run_log(bundle, out / "run-log.md")
    (out / "bundle.json").write_text(
        json.dumps(bundle.manifest(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return out


def _write_csv(
    path: Path,
    rows: tuple[FindingRow | MetricRow | GapRow, ...],
    model: type[FindingRow] | type[MetricRow] | type[GapRow],
) -> None:
    payload = []
    for row in rows:
        item = asdict(row)
        for key, value in list(item.items()):
            if isinstance(value, tuple):
                item[key] = ";".join(str(v) for v in value)
        payload.append(item)

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[f.name for f in fields(model)])
        writer.writeheader()
        writer.writerows(payload)


def _write_evidence(bundle: DistillBundle, path: Path) -> None:
    lines = [json.dumps(record.to_dict(), sort_keys=True) for record in bundle.evidence]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _write_index(bundle: DistillBundle, path: Path) -> None:
    filing = bundle.filing
    lines = [
        f"# {filing.get('company_name') or bundle.slug} Distilled Filing",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| Form | {filing.get('form_type', '')} |",
        f"| Filed | {filing.get('filing_date', '')} |",
        f"| Accession | {filing.get('accession', '')} |",
        f"| Pack | `{bundle.pack_dir}` |",
        "",
        "## Metrics",
        "",
    ]
    if bundle.metrics:
        lines.extend(
            [
                "| Metric | Period | Value | Unit | Evidence | Status |",
                "| --- | --- | ---: | --- | --- | --- |",
            ]
        )
        for metric_row in bundle.metrics:
            value = _format_metric_value(metric_row.value, metric_row.unit)
            lines.append(
                f"| {metric_row.metric} | {metric_row.period} | {value} | {metric_row.unit} | "
                f"{'; '.join(metric_row.evidence_ids)} | {metric_row.status} |"
            )
    else:
        lines.append("No metrics extracted.")

    lines.extend(["", "## Findings", ""])
    if bundle.findings:
        lines.extend(
            [
                "| Topic | Statement | Evidence | Status |",
                "| --- | --- | --- | --- |",
            ]
        )
        for finding_row in bundle.findings:
            lines.append(
                f"| {_md_cell(finding_row.topic)} | {_md_cell(finding_row.statement)} | "
                f"{'; '.join(finding_row.evidence_ids)} | {finding_row.status} |"
            )
    else:
        lines.append("No findings extracted.")

    lines.extend(["", "## Gaps", ""])
    if bundle.gaps:
        lines.extend(["| Area | Issue | Status |", "| --- | --- | --- |"])
        for gap_row in bundle.gaps:
            lines.append(f"| {gap_row.area} | {_md_cell(gap_row.issue)} | {gap_row.status} |")
    else:
        lines.append("No gaps recorded.")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _md_cell(text: str) -> str:
    """Make free filing text safe inside a one-line markdown table cell."""
    return text.replace("\n", " ").replace("|", "\\|")


def _format_metric_value(value: float | None, unit: str) -> str:
    if value is None:
        return ""
    negative = value < 0
    absolute = abs(value)
    if unit.upper() == "USD":
        rendered = f"${absolute:,.0f}"
    elif float(absolute).is_integer():
        rendered = f"{absolute:,.0f}"
    else:
        rendered = f"{absolute:,.2f}"
    return f"({rendered})" if negative else rendered


def _write_filing_map(bundle: DistillBundle, path: Path) -> None:
    lines = [f"# {bundle.slug} Filing Map", ""]
    if not bundle.filing_map:
        lines.append("No high-signal sections identified from manifest metadata.")
    else:
        lines.extend(["| Section | Path | Why it matters |", "| --- | --- | --- |"])
        for section in bundle.filing_map:
            label = _md_cell(section.title or section.id)
            lines.append(f"| {label} | `{section.path}` | {section.reason} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_run_log(bundle: DistillBundle, path: Path) -> None:
    lines = [
        f"# {bundle.slug} Distill Run Log",
        "",
        f"- Pack: `{bundle.pack_dir}`",
        f"- Output: `{bundle.output_dir}`",
        f"- Form: {bundle.filing.get('form_type', '')}",
        f"- Accession: {bundle.filing.get('accession', '')}",
        f"- Source URL: {bundle.source_url or 'not recorded'}",
        "",
        "## Files",
        "",
    ]
    for name in OUTPUT_FILES:
        lines.append(f"- `{name}`")
    if bundle.warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in bundle.warnings)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
