"""Citation-gated pack synthesis utilities for China Lens MVP."""

from __future__ import annotations

from dataclasses import dataclass

from ..models import CitationRef, Finding, Pack, PackSection


@dataclass(frozen=True)
class SectionTemplate:
    id: str
    title: str
    thesis: str


DEFAULT_SECTION_TEMPLATES: tuple[SectionTemplate, ...] = (
    SectionTemplate("summary", "Summary", "Core diligence signals from indexed filings."),
    SectionTemplate("financials", "Financials", "Revenue and profitability trend with evidence."),
    SectionTemplate(
        "customers_suppliers", "Customers + Suppliers", "Concentration risk and disclosure quality."
    ),
    SectionTemplate(
        "ownership_governance",
        "Ownership + Governance",
        "Control, board, and related-party disclosures.",
    ),
    SectionTemplate(
        "risk_register", "Risk Register", "Material risk factors supported by source excerpts."
    ),
)


def build_empty_sections() -> list[PackSection]:
    """Build section shells for fast-first render with reserved structure."""
    return [
        PackSection(
            id=template.id,
            title=template.title,
            thesis=template.thesis,
            key_points=[],
            key_tables=[],
            findings=[],
            unknowns=[],
        )
        for template in DEFAULT_SECTION_TEMPLATES
    ]


def finding_to_key_point(finding: Finding) -> str:
    """Convert a finding into display text honoring support state."""
    if finding.status.value == "unsupported":
        return f"Unsupported: {finding.claim_text}"
    return finding.claim_text


def inject_findings(pack: Pack, findings: list[Finding]) -> None:
    """Attach findings to matching sections and derive key-point bullets."""
    by_section = {section.id: section for section in pack.sections}
    for finding in findings:
        section = by_section.get(finding.section_id)
        if section is None:
            continue
        section.findings.append(finding)

    for section in pack.sections:
        section.key_points = [finding_to_key_point(f) for f in section.findings]


def citation_label(source: str, year: str, page: int, table: str | None = None) -> str:
    """Create a stable citation label for UI copy interactions."""
    if table:
        return f"{source} {year} Annual Report, p. {page}, {table}"
    return f"{source} {year} Annual Report, p. {page}"


def make_citation(chunk_id: str, doc_id: str, page: int, label: str) -> CitationRef:
    """Construct a citation reference for findings and answers."""
    return CitationRef(
        chunk_id=chunk_id,
        doc_id=doc_id,
        page=page,
        quote_start=0,
        quote_end=0,
        citation_label=label,
    )
