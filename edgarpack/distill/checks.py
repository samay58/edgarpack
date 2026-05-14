"""Validation for distilled filing bundles."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

from .models import OUTPUT_FILES


@dataclass(frozen=True)
class CheckResult:
    path: Path
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.errors


def check_distill_bundle(path: Path) -> CheckResult:
    root = Path(path)
    errors: list[str] = []
    warnings: list[str] = []
    if not root.exists():
        return CheckResult(root, (f"Bundle directory does not exist: {root}",), ())
    if not root.is_dir():
        return CheckResult(root, (f"Bundle path is not a directory: {root}",), ())

    for name in OUTPUT_FILES:
        if not (root / name).exists():
            errors.append(f"Missing required file: {name}")

    evidence_ids = _read_evidence_ids(root / "evidence.jsonl", errors)
    _validate_bundle_json(root / "bundle.json", errors)
    _validate_findings(root / "findings.csv", evidence_ids, errors)
    _validate_metrics(root / "metrics.csv", evidence_ids, errors)
    _validate_gaps(root / "gaps.csv", warnings, errors)

    return CheckResult(root, tuple(errors), tuple(warnings))


def _read_evidence_ids(path: Path, errors: list[str]) -> set[str]:
    ids: set[str] = set()
    if not path.exists():
        return ids
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            errors.append(f"evidence.jsonl:{line_no} invalid JSON: {exc}")
            continue
        evidence_id = str(payload.get("id") or "")
        text = str(payload.get("text") or "")
        if not evidence_id:
            errors.append(f"evidence.jsonl:{line_no} missing id")
            continue
        if not text:
            errors.append(f"evidence.jsonl:{line_no} missing text")
        ids.add(evidence_id)
    return ids


def _validate_bundle_json(path: Path, errors: list[str]) -> None:
    if not path.exists():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"bundle.json invalid JSON: {exc}")
        return
    for key in ("schema_version", "slug", "filing", "files", "counts"):
        if key not in payload:
            errors.append(f"bundle.json missing {key}")


def _validate_findings(path: Path, evidence_ids: set[str], errors: list[str]) -> None:
    for index, row in enumerate(_read_csv(path, errors), start=2):
        row_id = row.get("id") or f"row {index}"
        statement = (row.get("statement") or "").strip()
        if not statement:
            errors.append(f"findings.csv:{index} {row_id} missing statement")
        _validate_evidence_refs("findings.csv", index, row_id, row, evidence_ids, errors)


def _validate_metrics(path: Path, evidence_ids: set[str], errors: list[str]) -> None:
    for index, row in enumerate(_read_csv(path, errors), start=2):
        row_id = row.get("id") or f"row {index}"
        for field in ("metric", "period", "unit"):
            if not (row.get(field) or "").strip():
                errors.append(f"metrics.csv:{index} {row_id} missing {field}")
        _validate_evidence_refs("metrics.csv", index, row_id, row, evidence_ids, errors)


def _validate_gaps(path: Path, warnings: list[str], errors: list[str]) -> None:
    rows = _read_csv(path, errors)
    if not rows:
        warnings.append("gaps.csv has no rows")
        return
    for index, row in enumerate(rows, start=2):
        if not (row.get("area") or "").strip():
            errors.append(f"gaps.csv:{index} missing area")
        if not (row.get("issue") or "").strip():
            errors.append(f"gaps.csv:{index} missing issue")


def _validate_evidence_refs(
    filename: str,
    index: int,
    row_id: str,
    row: dict[str, str],
    evidence_ids: set[str],
    errors: list[str],
) -> None:
    refs = [ref for ref in (row.get("evidence_ids") or "").split(";") if ref]
    if not refs:
        errors.append(f"{filename}:{index} {row_id} missing evidence_ids")
        return
    for ref in refs:
        if ref not in evidence_ids:
            errors.append(f"{filename}:{index} {row_id} references unknown evidence id {ref}")


def _read_csv(path: Path, errors: list[str]) -> list[dict[str, str]]:
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        return []
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))
    except csv.Error as exc:
        errors.append(f"{path.name} invalid CSV: {exc}")
        return []
