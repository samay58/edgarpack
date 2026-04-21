"""Pack health diagnostics shared by `edgarpack doctor` single-pack and ticker modes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from ..config import SCHEMA_VERSION
from ..harvest.registry import PackRecord, PackRegistry
from .manifest import load_manifest_dict

ManifestState = Literal[
    "ok",
    "manifest_missing",
    "manifest_invalid_json",
    "manifest_schema_mismatch",
    "manifest_io_error",
]


_REMEDIATION: dict[str, str] = {
    "manifest_missing": "rebuild the pack with `edgarpack build <ticker> --force`",
    "manifest_invalid_json": (
        "manifest is not valid JSON; rebuild with `edgarpack build <ticker> --force`"
    ),
    "manifest_schema_mismatch": (
        "manifest schema version does not match this EdgarPack; "
        "rebuild with `edgarpack build <ticker> --force`"
    ),
    "manifest_io_error": "check filesystem permissions at the pack directory",
}

_ARTIFACT_NAMES = ("sections", "chunks.ndjson", "xbrl.json", "llms.txt", "filing.full.md")

_HEALTHY_COVERAGE_THRESHOLD = 0.5


class PackDiagnosis(BaseModel):
    pack_dir: str
    manifest_state: ManifestState
    manifest_error: str | None = None
    cik: str | None = None
    accession: str | None = None
    form_type: str | None = None
    filing_date: str | None = None
    company_name: str | None = None
    sections_count: int = 0
    tokens_total: int = 0
    artifacts_present: list[str] = []
    artifact_sizes: dict[str, int] = {}
    catalog_concepts_total: int = 0
    catalog_concepts_resolved: int = 0
    catalog_concepts_missing: list[str] = []
    discovered_kpi_count: int = 0
    healthy: bool = False
    remediation: str | None = None


def _classify_manifest(pack_dir: Path) -> tuple[ManifestState, str | None, dict | None]:
    manifest_path = pack_dir / "manifest.json"
    if not manifest_path.exists():
        return "manifest_missing", None, None
    try:
        manifest = load_manifest_dict(pack_dir, on_missing="raise")
    except json.JSONDecodeError as e:
        return "manifest_invalid_json", str(e), None
    except (OSError, UnicodeDecodeError) as e:
        return "manifest_io_error", str(e), None

    schema_version = manifest.get("schema_version") if isinstance(manifest, dict) else None
    required = {"filing", "sections", "parser_version"}
    missing = required - set(manifest.keys() if isinstance(manifest, dict) else [])
    if not isinstance(schema_version, int) or schema_version != SCHEMA_VERSION or missing:
        err = f"schema_version={schema_version!r} missing_fields={sorted(missing)}"
        return "manifest_schema_mismatch", err, None

    return "ok", None, manifest


def _list_artifacts(pack_dir: Path) -> tuple[list[str], dict[str, int]]:
    present: list[str] = []
    sizes: dict[str, int] = {}
    for name in _ARTIFACT_NAMES:
        candidate = pack_dir / name
        if candidate.exists():
            present.append(name)
            if candidate.is_file():
                sizes[name] = candidate.stat().st_size
            elif candidate.is_dir():
                sizes[name] = sum(f.stat().st_size for f in candidate.rglob("*") if f.is_file())
    return present, sizes


def _coverage(manifest: dict, pack_record: PackRecord | None) -> tuple[int, int, list[str], int]:
    from ..query.kpi_extract import KPI_CATALOG
    from ..query.learned_registry import LearnedRegistry

    form_type = (manifest.get("filing", {}) or {}).get("form_type", "")
    relevant = [
        (metric, kpi_def)
        for metric, kpi_def in KPI_CATALOG.items()
        if not kpi_def.industry or form_type.startswith("10-")
    ]
    total = len(relevant)

    resolved_count = 0
    missing: list[str] = []
    discovered_count = 0

    if pack_record is not None:
        reg = LearnedRegistry()
        try:
            cik = pack_record.cik
            accession = pack_record.accession
            for metric, _ in relevant:
                row = reg.lookup(cik=cik, metric=metric, accession=accession)
                if row is not None and row.value_sample is not None:
                    resolved_count += 1
                else:
                    missing.append(metric)
            discovered_rows = reg.company_kpi_list(cik=cik, accession=accession)
            discovered_count = len(discovered_rows)
        finally:
            reg.close()
    else:
        missing = [metric for metric, _ in relevant]

    return total, resolved_count, missing, discovered_count


def diagnose_pack(pack_dir: Path, registry: PackRegistry | None) -> PackDiagnosis:
    state, error, manifest = _classify_manifest(pack_dir)

    if state != "ok" or manifest is None:
        return PackDiagnosis(
            pack_dir=str(pack_dir),
            manifest_state=state,
            manifest_error=error,
            remediation=_REMEDIATION.get(state),
        )

    filing = manifest.get("filing", {}) if isinstance(manifest, dict) else {}
    cik = filing.get("cik") if isinstance(filing, dict) else None
    accession = filing.get("accession") if isinstance(filing, dict) else None
    sections = manifest.get("sections", []) if isinstance(manifest, dict) else []
    tokens_total = manifest.get("tokens_total", 0) if isinstance(manifest, dict) else 0
    artifacts, sizes = _list_artifacts(pack_dir)

    pack_record: PackRecord | None = None
    if registry is not None and isinstance(cik, str) and isinstance(accession, str):
        matches = registry.list_packs(cik=cik)
        for rec in matches:
            if rec.accession == accession:
                pack_record = rec
                break
    if pack_record is None and isinstance(cik, str) and isinstance(accession, str):
        pack_record = PackRecord(
            accession=accession,
            cik=cik,
            ticker=None,
            company_name=filing.get("company_name", "") if isinstance(filing, dict) else "",
            form_type=filing.get("form_type", "") if isinstance(filing, dict) else "",
            filing_date=filing.get("filing_date", "") if isinstance(filing, dict) else "",
            sections_count=len(sections) if isinstance(sections, list) else 0,
            tokens_total=int(tokens_total) if isinstance(tokens_total, int) else 0,
            pack_dir=str(pack_dir),
            built_at="",
        )

    total, resolved, missing, discovered = _coverage(manifest, pack_record)

    healthy = total > 0 and resolved / total >= _HEALTHY_COVERAGE_THRESHOLD
    remediation: str | None = None
    if not healthy and total > 0:
        remediation = (
            f"catalog coverage {resolved}/{total} below "
            f"{int(_HEALTHY_COVERAGE_THRESHOLD * 100)}% threshold; "
            f"missing concepts: {', '.join(missing[:5])}" + ("..." if len(missing) > 5 else "")
        )

    return PackDiagnosis(
        pack_dir=str(pack_dir),
        manifest_state="ok",
        cik=cik if isinstance(cik, str) else None,
        accession=accession if isinstance(accession, str) else None,
        form_type=filing.get("form_type") if isinstance(filing, dict) else None,
        filing_date=filing.get("filing_date") if isinstance(filing, dict) else None,
        company_name=filing.get("company_name") if isinstance(filing, dict) else None,
        sections_count=len(sections) if isinstance(sections, list) else 0,
        tokens_total=int(tokens_total) if isinstance(tokens_total, int) else 0,
        artifacts_present=artifacts,
        artifact_sizes=sizes,
        catalog_concepts_total=total,
        catalog_concepts_resolved=resolved,
        catalog_concepts_missing=missing,
        discovered_kpi_count=discovered,
        healthy=healthy,
        remediation=remediation,
    )
