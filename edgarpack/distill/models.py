"""Data contracts for distilled filing outputs."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

OUTPUT_FILES = (
    "index.md",
    "findings.csv",
    "metrics.csv",
    "evidence.jsonl",
    "gaps.csv",
    "filing-map.md",
    "run-log.md",
    "bundle.json",
)


@dataclass(frozen=True)
class EvidenceRecord:
    id: str
    kind: str
    text: str
    source_ref: str
    accession: str
    form_type: str
    filing_date: str
    section_id: str = ""
    chunk_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FindingRow:
    id: str
    kind: str
    topic: str
    statement: str
    evidence_ids: tuple[str, ...]
    section: str = ""
    status: str = "supported"
    notes: str = ""


@dataclass(frozen=True)
class MetricRow:
    id: str
    metric: str
    period: str
    fiscal_year: int | None
    fiscal_period: str
    value: float | None
    unit: str
    currency: str
    evidence_ids: tuple[str, ...]
    section: str = ""
    status: str = "supported"
    notes: str = ""


@dataclass(frozen=True)
class GapRow:
    id: str
    area: str
    issue: str
    status: str
    action: str


@dataclass(frozen=True)
class FilingSection:
    id: str
    title: str
    path: str
    reason: str


@dataclass(frozen=True)
class DistillBundle:
    slug: str
    pack_dir: Path
    output_dir: Path
    filing: dict[str, str]
    source_url: str
    findings: tuple[FindingRow, ...]
    metrics: tuple[MetricRow, ...]
    evidence: tuple[EvidenceRecord, ...]
    gaps: tuple[GapRow, ...]
    filing_map: tuple[FilingSection, ...]
    warnings: tuple[str, ...] = ()

    def manifest(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "slug": self.slug,
            "pack_dir": str(self.pack_dir),
            "filing": self.filing,
            "source_url": self.source_url,
            "files": list(OUTPUT_FILES),
            "counts": {
                "findings": len(self.findings),
                "metrics": len(self.metrics),
                "evidence": len(self.evidence),
                "gaps": len(self.gaps),
                "filing_map": len(self.filing_map),
            },
            "warnings": list(self.warnings),
        }
