"""Tests for China Lens deterministic QA validators."""

from __future__ import annotations

import unittest

from edgarpack.china.models import (
    CitationRef,
    EvidenceChunk,
    ExtractionMethod,
    Finding,
    FindingStatus,
    Pack,
    PackSection,
    PackStatus,
    utc_now,
)
from edgarpack.china.qa.validators import run_publish_checks


class TestChinaValidators(unittest.TestCase):
    def test_missing_citation_marks_finding_unsupported(self) -> None:
        finding = Finding(
            id="f1",
            pack_id="p1",
            section_id="summary",
            claim_text="Cloud demand remained resilient.",
            claim_type="outlook",
            citations=[],
            status=FindingStatus.SUPPORTED,
        )
        pack = Pack(
            id="p1",
            company_id="cmp",
            created_at=utc_now(),
            updated_at=utc_now(),
            doc_set=[],
            time_range="x",
            translation_mode="key_sections",
            template="Investor diligence",
            status=PackStatus.RUNNING,
            sections=[
                PackSection(
                    id="summary",
                    title="Summary",
                    thesis="t",
                    findings=[finding],
                )
            ],
        )

        report = run_publish_checks(pack, chunks_by_id={})

        self.assertFalse(report.passed)
        self.assertEqual(finding.status, FindingStatus.UNSUPPORTED)
        self.assertEqual(pack.sections[0].coverage_status.value, "incomplete")

    def test_numeric_alignment_fails_without_matching_evidence_token(self) -> None:
        citation = CitationRef(
            chunk_id="c1",
            doc_id="d1",
            page=12,
            citation_label="CNINFO 2024 Annual Report, p. 12",
        )
        finding = Finding(
            id="f2",
            pack_id="p2",
            section_id="financials",
            claim_text="Revenue increased 99.9% year over year.",
            claim_type="growth",
            citations=[citation],
            status=FindingStatus.SUPPORTED,
        )
        pack = Pack(
            id="p2",
            company_id="cmp",
            created_at=utc_now(),
            updated_at=utc_now(),
            doc_set=["d1"],
            time_range="x",
            translation_mode="key_sections",
            template="Investor diligence",
            status=PackStatus.RUNNING,
            sections=[
                PackSection(
                    id="financials",
                    title="Financials",
                    thesis="t",
                    findings=[finding],
                )
            ],
        )
        chunks = {
            "c1": EvidenceChunk(
                id="c1",
                doc_id="d1",
                page_start=12,
                page_end=12,
                text_zh="收入同比增长15%。",
                text_en="Revenue increased 15% year over year.",
                language="zh",
                extraction_method=ExtractionMethod.EMBEDDED_TEXT,
                confidence=0.98,
            )
        }

        report = run_publish_checks(pack, chunks_by_id=chunks)

        self.assertFalse(report.passed)
        self.assertTrue(
            any(issue.code == "numeric_claim_without_evidence" for issue in report.issues)
        )


if __name__ == "__main__":
    unittest.main()
