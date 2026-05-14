"""Write distilled filing bundles to disk."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path

from .models import OUTPUT_FILES, DistillBundle


def write_distill_bundle(bundle: DistillBundle, *, force: bool = False) -> Path:
    out = bundle.output_dir
    if out.exists() and any(out.iterdir()) and not force:
        raise FileExistsError(f"{out} already exists and is not empty. Pass --force to overwrite.")
    out.mkdir(parents=True, exist_ok=True)

    _write_index(bundle, out / "index.md")
    _write_csv(out / "findings.csv", bundle.findings)
    _write_csv(out / "metrics.csv", bundle.metrics)
    _write_csv(out / "gaps.csv", bundle.gaps)
    _write_evidence(bundle, out / "evidence.jsonl")
    _write_filing_map(bundle, out / "filing-map.md")
    _write_run_log(bundle, out / "run-log.md")
    (out / "bundle.json").write_text(
        json.dumps(bundle.manifest(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return out


def _write_csv(path: Path, rows: tuple[object, ...]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    payload = []
    for row in rows:
        item = asdict(row)
        for key, value in list(item.items()):
            if isinstance(value, tuple):
                item[key] = ";".join(str(v) for v in value)
        payload.append(item)

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(payload[0].keys()))
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
        for row in bundle.metrics:
            value = _format_metric_value(row.value, row.unit)
            lines.append(
                f"| {row.metric} | {row.period} | {value} | {row.unit} | "
                f"{'; '.join(row.evidence_ids)} | {row.status} |"
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
        for row in bundle.findings:
            statement = row.statement.replace("\n", " ")
            lines.append(
                f"| {row.topic} | {statement} | {'; '.join(row.evidence_ids)} | {row.status} |"
            )
    else:
        lines.append("No findings extracted.")

    lines.extend(["", "## Gaps", ""])
    if bundle.gaps:
        lines.extend(["| Area | Issue | Status |", "| --- | --- | --- |"])
        for row in bundle.gaps:
            lines.append(f"| {row.area} | {row.issue} | {row.status} |")
    else:
        lines.append("No gaps recorded.")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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
            label = section.title or section.id
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
