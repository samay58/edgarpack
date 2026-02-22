"""Deterministic QA checks for citation-backed pack publication."""

from __future__ import annotations

import re

from ..models import CoverageStatus, EvidenceChunk, Finding, FindingStatus, Pack, QAIssue, QAReport

_NUMERIC_RE = re.compile(r"\d+[\d,.]*")


def _numeric_tokens(text: str) -> set[str]:
    return {m.group(0).replace(",", "") for m in _NUMERIC_RE.finditer(text)}


def enforce_citation_presence(findings: list[Finding]) -> list[QAIssue]:
    """Mark findings without citations as unsupported and report issues."""
    issues: list[QAIssue] = []
    for finding in findings:
        if finding.citations:
            continue
        finding.status = FindingStatus.UNSUPPORTED
        finding.unknown_reason = finding.unknown_reason or "Not found in indexed sources"
        issues.append(
            QAIssue(
                code="missing_citation",
                message="Finding has no citations and cannot be published as supported.",
                finding_id=finding.id,
                section_id=finding.section_id,
            )
        )
    return issues


def validate_numeric_claim_alignment(
    findings: list[Finding], chunks_by_id: dict[str, EvidenceChunk]
) -> list[QAIssue]:
    """Validate numeric claims have nearby numeric evidence in cited chunks."""
    issues: list[QAIssue] = []
    for finding in findings:
        claim_numbers = _numeric_tokens(finding.claim_text)
        if not claim_numbers or not finding.citations:
            continue

        evidence_numbers: set[str] = set()
        for citation in finding.citations:
            chunk = chunks_by_id.get(citation.chunk_id)
            if chunk is None:
                continue
            evidence_numbers |= _numeric_tokens(f"{chunk.text_zh} {chunk.text_en}")

        if not (claim_numbers & evidence_numbers):
            issues.append(
                QAIssue(
                    code="numeric_claim_without_evidence",
                    message="Numeric claim lacks nearby numeric token in cited evidence.",
                    finding_id=finding.id,
                    section_id=finding.section_id,
                )
            )
    return issues


def apply_section_coverage(pack: Pack, min_citations_per_section: int = 2) -> None:
    """Compute section coverage labels based on citation density and support state."""
    for section in pack.sections:
        supported = [f for f in section.findings if f.status == FindingStatus.SUPPORTED]
        citation_count = sum(len(f.citations) for f in supported)

        if not section.findings:
            section.coverage_status = CoverageStatus.PENDING
        elif citation_count >= min_citations_per_section:
            section.coverage_status = CoverageStatus.COMPLETE
        elif citation_count > 0:
            section.coverage_status = CoverageStatus.PARTIAL
        else:
            section.coverage_status = CoverageStatus.INCOMPLETE


def run_publish_checks(
    pack: Pack, chunks_by_id: dict[str, EvidenceChunk], min_citations_per_section: int = 2
) -> QAReport:
    """Run deterministic publication checks and mutate finding states when needed."""
    issues: list[QAIssue] = []

    all_findings: list[Finding] = []
    for section in pack.sections:
        all_findings.extend(section.findings)

    issues.extend(enforce_citation_presence(all_findings))
    issues.extend(validate_numeric_claim_alignment(all_findings, chunks_by_id))
    apply_section_coverage(pack, min_citations_per_section=min_citations_per_section)

    return QAReport(passed=not issues, issues=issues)
