"""Build distilled filing bundles from existing packs."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..pack.manifest import load_manifest_dict
from ..query.registration_profile import build_registration_profile
from ..query.s1_financials import SnapshotResult, load_validated_snapshot
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
    try:
        manifest = load_manifest_dict(pack_dir)
    except FileNotFoundError as exc:
        raise DistillError(f"{pack_dir} is not a filing pack (no manifest.json)") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise DistillError(f"manifest.json at {pack_dir} could not be read: {exc}") from exc
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
    source_raw = manifest.get("source")
    source = source_raw if isinstance(source_raw, dict) else {}
    source_url = str(source.get("url") or "")

    evidence: list[EvidenceRecord] = []
    findings: list[FindingRow] = []
    metrics: list[MetricRow] = []
    gaps: list[GapRow] = []

    if not is_registration_form(filing["form_type"]):
        # One accurate gap; running the S-1 extractors would only add
        # misleading "missing" diagnoses for artifacts the form never has.
        gaps.append(
            GapRow(
                id=_next_id("gap", gaps),
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
    else:
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
                    id=_next_id("gap", gaps),
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
                    id=_next_id("gap", gaps),
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
                id=_next_id("gap", gaps),
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
                id=_next_id("gap", gaps),
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
            evidence_id = _next_id("ev", evidence)
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
                    id=_next_id("find", findings),
                    kind=kind_by_topic.get(group.label, "disclosure"),
                    topic=group.label,
                    statement=claim,
                    evidence_ids=(evidence_id,),
                    section=section_by_topic.get(group.label, ""),
                )
            )


_SNAPSHOT_GAPS = {
    "not_extracted": ("s1_financials.json is missing.", "missing"),
    "cache_unreadable": ("s1_financials.json could not be read.", "unreadable"),
    "cache_stale_schema": (
        "S-1 financial cache schema does not match the current extractor.",
        "stale",
    ),
    "cache_stale_source": (
        "S-1 financial cache hash does not match filing.full.md.",
        "stale",
    ),
}


def _add_s1_metrics(
    *,
    pack_dir: Path,
    filing: dict[str, str],
    metrics: list[MetricRow],
    evidence: list[EvidenceRecord],
    gaps: list[GapRow],
) -> None:
    snapshot, status = load_validated_snapshot(pack_dir)
    if snapshot is None:
        issue, gap_status = _SNAPSHOT_GAPS.get(
            status, (f"s1_financials.json was rejected: {status}.", "unreadable")
        )
        gaps.append(
            GapRow(
                id=_next_id("gap", gaps),
                area="s1_financials",
                issue=issue,
                status=gap_status,
                action=(
                    "Run a query path that extracts S-1 financials, then rerun distill."
                    if status == "not_extracted"
                    else "Regenerate the S-1 financial cache."
                ),
            )
        )
        return

    anchor = _window_anchor(snapshot, filing["filing_date"])
    skipped: list[str] = []
    for fact in snapshot.facts:
        period = _period_label(fact.fiscal_period, fact.fiscal_year)
        if anchor is not None and _outside_registration_window(
            fact.fiscal_year,
            fact.fiscal_period,
            anchor,
        ):
            skipped.append(f"{fact.metric} {period}")
            continue
        evidence_id = _next_id("ev", evidence)
        value = fact.value_cents / 100
        has_locator = bool(fact.section_id or fact.chunk_id)
        has_source_text = bool(fact.source_text)
        # Evidence text must be filing language. When the cache captured no
        # quote, say so explicitly instead of synthesizing one from the value.
        source_text = fact.source_text or (
            f"No source text captured for {fact.metric} {period}; "
            "value taken from the S-1 financial cache, not quoted from the filing."
        )
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
                    "quoted_from_filing": has_source_text,
                },
            )
        )
        notes: list[str] = []
        if not has_locator:
            notes.append("metric cache has no section or chunk locator")
        if not has_source_text:
            notes.append("metric cache has no quoted source text")
        if fact.is_pro_forma:
            notes.append(fact.pro_forma_note or "pro forma")
        if not fact.is_audited:
            notes.append("not audited")
        metrics.append(
            MetricRow(
                id=_next_id("metric", metrics),
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
                    if not (has_locator and has_source_text)
                    else "pro_forma"
                    if fact.is_pro_forma
                    else "supported"
                ),
                notes="; ".join(notes),
            )
        )
    if skipped:
        gaps.append(
            GapRow(
                id=_next_id("gap", gaps),
                area="metric_window",
                issue=(
                    f"Skipped {len(skipped)} metric row(s) outside the normal "
                    f"S-1 annual/interim window: {', '.join(skipped)}."
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
                id=_next_id("gap", gaps),
                area="metric_locators",
                issue=(
                    "One or more metric rows came from cache entries without "
                    "section/chunk locators or quoted source text."
                ),
                status="needs_review",
                action=(
                    "Verify these values against the source filing before treating them as final."
                ),
            )
        )
    if snapshot.extraction_status != "ok":
        gaps.append(
            GapRow(
                id=_next_id("gap", gaps),
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


def _window_anchor(snapshot: SnapshotResult, filing_date: str) -> int | None:
    """Latest fiscal year the window is measured from.

    Anchoring on the snapshot's own latest fiscal year (not the filing year)
    keeps legitimate disclosures: an S-1 filed early in a calendar year carries
    audited years and interim comparatives that all trail the filing year by
    one. The filing year still caps the anchor so a typo'd far-future fiscal
    year in the cache cannot drag the window away from the real data.
    """
    years = [fact.fiscal_year for fact in snapshot.facts if fact.fiscal_year]
    if not years:
        return None
    anchor = max(years)
    if filing_date and len(filing_date) >= 4:
        try:
            anchor = min(anchor, int(filing_date[:4]))
        except ValueError:
            pass
    return anchor


def _outside_registration_window(
    fiscal_year: int,
    fiscal_period: str | None,
    anchor_year: int,
) -> bool:
    period = (fiscal_period or "FY").upper()
    if period == "FY":
        return fiscal_year < anchor_year - 3 or fiscal_year > anchor_year
    return fiscal_year < anchor_year - 1 or fiscal_year > anchor_year


def _next_id(prefix: str, rows: list[Any]) -> str:
    return f"{prefix}-{len(rows) + 1:04d}"
