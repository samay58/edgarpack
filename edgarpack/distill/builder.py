"""Build distilled filing bundles from existing packs."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..pack.manifest import load_manifest_dict
from ..query.registration_profile import build_registration_profile
from ..query.s1_financials import SCHEMA_VERSION as S1_SCHEMA_VERSION
from ..query.s1_financials import SnapshotResult, source_sha256_for_pack
from ..sec.submissions import is_registration_form
from .models import (
    DistillBundle,
    EvidenceRecord,
    FilingSection,
    FindingRow,
    GapRow,
    MetricRow,
)


class DistillError(RuntimeError):
    pass


_SAFE_SLUG_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")


def validate_slug(slug: str) -> None:
    if not _SAFE_SLUG_RE.match(slug):
        raise DistillError(
            "Slug must start with a letter or number and contain only letters, "
            "numbers, dots, dashes, or underscores."
        )


def resolve_pack_path(
    *,
    pack: Path | None,
    accession: str | None,
    packs_root: Path,
) -> Path:
    if pack is not None:
        if not pack.exists():
            raise DistillError(f"Pack not found: {pack}")
        if not pack.is_dir():
            raise DistillError(f"Pack path is not a directory: {pack}")
        return pack

    if not accession:
        raise DistillError("Pass either --pack or --accession.")

    matches = sorted(Path(packs_root).glob(f"*/{accession}"))
    if not matches:
        raise DistillError(f"Pack for accession {accession} not found under {packs_root}.")
    if len(matches) > 1:
        paths = "\n".join(f"  - {path}" for path in matches)
        raise DistillError(f"Multiple packs found for accession {accession}:\n{paths}")
    return matches[0]


def build_distill_bundle(
    *,
    slug: str,
    pack_dir: Path,
    output_root: Path,
    company_hint: str | None = None,
) -> DistillBundle:
    validate_slug(slug)
    pack_dir = Path(pack_dir)
    manifest = load_manifest_dict(pack_dir)
    filing_raw = manifest.get("filing")
    if not isinstance(filing_raw, dict):
        raise DistillError(f"manifest.json at {pack_dir} has no filing object")

    filing = {
        "company_name": str(filing_raw.get("company_name") or company_hint or ""),
        "cik": str(filing_raw.get("cik") or ""),
        "accession": str(filing_raw.get("accession") or pack_dir.name),
        "form_type": str(filing_raw.get("form_type") or ""),
        "filing_date": str(filing_raw.get("filing_date") or ""),
        "period_of_report": str(filing_raw.get("period_of_report") or ""),
    }
    source = manifest.get("source") if isinstance(manifest.get("source"), dict) else {}
    source_url = str(source.get("url") or "")

    evidence: list[EvidenceRecord] = []
    findings: list[FindingRow] = []
    metrics: list[MetricRow] = []
    gaps: list[GapRow] = []
    warnings: list[str] = []

    if not is_registration_form(filing["form_type"]):
        gaps.append(
            GapRow(
                id="gap-001",
                area="form_support",
                issue=(
                    "Distill v1 only has first-class registration support; "
                    f"found {filing['form_type'] or 'unknown'}."
                ),
                status="unsupported_form",
                action=(
                    "Use an S-1/F-1 registration pack or extend the distill "
                    "builder for this form family."
                ),
            )
        )

    _add_registration_findings(
        pack_dir=pack_dir,
        filing=filing,
        findings=findings,
        evidence=evidence,
        gaps=gaps,
    )
    _add_s1_metrics(
        pack_dir=pack_dir,
        filing=filing,
        metrics=metrics,
        evidence=evidence,
        gaps=gaps,
    )

    if not findings:
        gaps.append(
            GapRow(
                id=_next_gap_id(gaps),
                area="findings",
                issue="No non-financial S-1 disclosures were extracted.",
                status="empty",
                action=(
                    "Read the filing map and source sections directly; extraction "
                    "may need a richer table or disclosure parser."
                ),
            )
        )
    if not metrics:
        gaps.append(
            GapRow(
                id=_next_gap_id(gaps),
                area="metrics",
                issue="No S-1 financial metrics were available from the cache.",
                status="empty",
                action=(
                    "Run the existing S-1 financial extraction/query path for this "
                    "pack, then rerun distill."
                ),
            )
        )

    return DistillBundle(
        slug=slug,
        pack_dir=pack_dir,
        output_dir=Path(output_root) / slug,
        filing=filing,
        source_url=source_url,
        findings=tuple(findings),
        metrics=tuple(metrics),
        evidence=tuple(evidence),
        gaps=tuple(gaps),
        filing_map=tuple(_filing_map(manifest)),
        warnings=tuple(warnings),
    )


def _add_registration_findings(
    *,
    pack_dir: Path,
    filing: dict[str, str],
    findings: list[FindingRow],
    evidence: list[EvidenceRecord],
    gaps: list[GapRow],
) -> None:
    profile = build_registration_profile(pack_dir)
    if profile is None:
        gaps.append(
            GapRow(
                id=_next_gap_id(gaps),
                area="registration_profile",
                issue="Registration profile could not be built from the pack.",
                status="missing",
                action="Check manifest.json, filing.full.md, and S-1 section extraction.",
            )
        )
        return
    if not profile.has_content:
        gaps.append(
            GapRow(
                id=_next_gap_id(gaps),
                area="registration_profile",
                issue=(
                    "Registration profile returned no content; source status was "
                    f"{profile.source_status}."
                ),
                status=profile.source_status or "empty",
                action=(
                    "Inspect the source sections and improve the registration "
                    "disclosure extractors if needed."
                ),
            )
        )

    section_by_topic = {
        "framing claims": "prospectus summary / business",
        "use of proceeds": "use of proceeds",
        "dilution": "dilution",
        "lockup terms": "underwriting / shares eligible for future sale",
        "principal holders": "principal stockholders",
    }
    kind_by_topic = {
        "framing claims": "market_claim",
        "use of proceeds": "use_of_proceeds",
        "dilution": "dilution",
        "lockup terms": "lockup",
        "principal holders": "ownership",
    }
    for group in profile.disclosures:
        for claim in group.claims:
            evidence_id = _next_evidence_id(evidence)
            source_ref = f"{filing['accession']}:{group.label}"
            evidence.append(
                EvidenceRecord(
                    id=evidence_id,
                    kind=kind_by_topic.get(group.label, "disclosure"),
                    text=claim,
                    source_ref=source_ref,
                    accession=filing["accession"],
                    form_type=filing["form_type"],
                    filing_date=filing["filing_date"],
                    section_id=section_by_topic.get(group.label, ""),
                )
            )
            findings.append(
                FindingRow(
                    id=_next_finding_id(findings),
                    kind=kind_by_topic.get(group.label, "disclosure"),
                    topic=group.label,
                    statement=claim,
                    evidence_ids=(evidence_id,),
                    section=section_by_topic.get(group.label, ""),
                )
            )


def _add_s1_metrics(
    *,
    pack_dir: Path,
    filing: dict[str, str],
    metrics: list[MetricRow],
    evidence: list[EvidenceRecord],
    gaps: list[GapRow],
) -> None:
    cache = pack_dir / "s1_financials.json"
    if not cache.exists():
        gaps.append(
            GapRow(
                id=_next_gap_id(gaps),
                area="s1_financials",
                issue="s1_financials.json is missing.",
                status="missing",
                action="Run a query path that extracts S-1 financials, then rerun distill.",
            )
        )
        return
    try:
        snapshot = SnapshotResult.from_json(cache.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        gaps.append(
            GapRow(
                id=_next_gap_id(gaps),
                area="s1_financials",
                issue=f"s1_financials.json could not be read: {exc}",
                status="unreadable",
                action="Regenerate the S-1 financial cache.",
            )
        )
        return
    if snapshot.schema_version != S1_SCHEMA_VERSION:
        gaps.append(
            GapRow(
                id=_next_gap_id(gaps),
                area="s1_financials",
                issue=(
                    f"S-1 financial cache schema {snapshot.schema_version} "
                    f"does not match {S1_SCHEMA_VERSION}."
                ),
                status="stale",
                action="Regenerate the S-1 financial cache.",
            )
        )
        return
    if snapshot.source_sha256 != source_sha256_for_pack(pack_dir):
        gaps.append(
            GapRow(
                id=_next_gap_id(gaps),
                area="s1_financials",
                issue="S-1 financial cache hash does not match filing.full.md.",
                status="stale",
                action="Regenerate the S-1 financial cache.",
            )
        )
        return

    skipped_window = 0
    for fact in snapshot.facts:
        if _outside_registration_window(
            fact.fiscal_year,
            fact.fiscal_period,
            filing["filing_date"],
        ):
            skipped_window += 1
            continue
        evidence_id = _next_evidence_id(evidence)
        value = fact.value_cents / 100
        period = _period_label(fact.fiscal_period, fact.fiscal_year)
        source_text = fact.source_text or f"{fact.metric} {period}: {value:g} {fact.currency}"
        has_locator = bool(fact.section_id or fact.chunk_id)
        evidence.append(
            EvidenceRecord(
                id=evidence_id,
                kind="metric",
                text=source_text,
                source_ref=f"{fact.accession}:{fact.metric}:{period}",
                accession=fact.accession or filing["accession"],
                form_type=filing["form_type"],
                filing_date=filing["filing_date"],
                section_id=fact.section_id or "",
                chunk_id=fact.chunk_id or "",
                metadata={
                    "metric": fact.metric,
                    "period_end": fact.period_end,
                    "is_audited": fact.is_audited,
                    "is_pro_forma": fact.is_pro_forma,
                },
            )
        )
        notes: list[str] = []
        if not has_locator:
            notes.append("metric cache has no section or chunk locator")
        if fact.is_pro_forma:
            notes.append(fact.pro_forma_note or "pro forma")
        if not fact.is_audited:
            notes.append("not audited")
        metrics.append(
            MetricRow(
                id=_next_metric_id(metrics),
                metric=fact.metric,
                period=period,
                fiscal_year=fact.fiscal_year,
                fiscal_period=fact.fiscal_period or "FY",
                value=value,
                unit=fact.currency,
                currency=fact.currency,
                evidence_ids=(evidence_id,),
                section=fact.section_id or "",
                status=(
                    "needs_review"
                    if not has_locator
                    else "pro_forma"
                    if fact.is_pro_forma
                    else "supported"
                ),
                notes="; ".join(notes),
            )
        )
    if skipped_window:
        gaps.append(
            GapRow(
                id=_next_gap_id(gaps),
                area="metric_window",
                issue=(
                    f"Skipped {skipped_window} metric row(s) outside the normal "
                    "S-1 annual/interim window."
                ),
                status="filtered",
                action=(
                    "Inspect s1_financials.json if the filing intentionally "
                    "includes longer historical periods."
                ),
            )
        )
    if any(row.status == "needs_review" for row in metrics):
        gaps.append(
            GapRow(
                id=_next_gap_id(gaps),
                area="metric_locators",
                issue=(
                    "One or more metric rows came from cache entries without "
                    "section or chunk locators."
                ),
                status="needs_review",
                action=(
                    "Use the evidence text and source filing before treating these "
                    "metrics as final."
                ),
            )
        )
    if snapshot.extraction_status != "ok":
        gaps.append(
            GapRow(
                id=_next_gap_id(gaps),
                area="s1_financials",
                issue=f"S-1 financial extraction status is {snapshot.extraction_status}.",
                status=snapshot.extraction_status,
                action="Treat metric coverage as partial until the cache is regenerated cleanly.",
            )
        )


def _filing_map(manifest: dict[str, Any]) -> list[FilingSection]:
    sections = manifest.get("sections")
    if not isinstance(sections, list):
        return []
    out: list[FilingSection] = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        section_id = str(section.get("id") or "")
        title = str(section.get("title") or section_id)
        path = str(section.get("path") or "")
        reason = _section_reason(section_id, title)
        if reason:
            out.append(FilingSection(id=section_id, title=title, path=path, reason=reason))
    return out


def _section_reason(section_id: str, title: str) -> str:
    text = f"{section_id} {title}".lower()
    if "summary" in text:
        return "high-level company framing and headline numbers"
    if "business" in text:
        return "operating model and core business claims"
    if "risk" in text:
        return "risk factors and company-specific warnings"
    if "management" in text or "discussion" in text:
        return "MD&A, period commentary, and metric explanations"
    if "use_of_proceeds" in text or "use of proceeds" in text:
        return "IPO proceeds allocation"
    if "dilution" in text:
        return "post-offering ownership and dilution mechanics"
    if "principal" in text or "holder" in text:
        return "ownership and control"
    if "underwriting" in text or "eligible" in text or "lock" in text:
        return "lockup and share-sale mechanics"
    if "relationship" in text:
        return "related-party and counterparty exposure"
    if "financial" in text or "consolidated" in text:
        return "financial statements and reconciliations"
    if "offering" in text:
        return "offering terms and blank fields"
    return ""


def _period_label(fiscal_period: str | None, fiscal_year: int) -> str:
    period = (fiscal_period or "FY").upper()
    if period == "FY":
        return f"FY{fiscal_year}"
    return f"{period} FY{fiscal_year}"


def _outside_registration_window(
    fiscal_year: int,
    fiscal_period: str | None,
    filing_date: str,
) -> bool:
    if not filing_date or len(filing_date) < 4:
        return False
    try:
        filing_year = int(filing_date[:4])
    except ValueError:
        return False
    period = (fiscal_period or "FY").upper()
    if period == "FY":
        return fiscal_year < filing_year - 3 or fiscal_year > filing_year
    return fiscal_year < filing_year - 1 or fiscal_year > filing_year


def _next_evidence_id(rows: list[EvidenceRecord]) -> str:
    return f"ev-{len(rows) + 1:04d}"


def _next_finding_id(rows: list[FindingRow]) -> str:
    return f"find-{len(rows) + 1:04d}"


def _next_metric_id(rows: list[MetricRow]) -> str:
    return f"metric-{len(rows) + 1:04d}"


def _next_gap_id(rows: list[GapRow]) -> str:
    return f"gap-{len(rows) + 1:04d}"
