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
        self.assertEqual(finding.status, FindingStatus.UNSUPPORTED)
        self.assertEqual(
            finding.unknown_reason,
            "Numeric claim does not align with cited evidence",
        )
        self.assertTrue(
            any(issue.code == "numeric_claim_without_evidence" for issue in report.issues)
        )

    def test_missing_cited_chunk_marks_finding_unsupported(self) -> None:
        citation = CitationRef(
            chunk_id="missing",
            doc_id="d1",
            page=12,
            citation_label="CNINFO 2024 Annual Report, p. 12",
        )
        finding = Finding(
            id="f3",
            pack_id="p3",
            section_id="risk_register",
            claim_text="Risk disclosures cover regulation.",
            claim_type="risk",
            citations=[citation],
            status=FindingStatus.SUPPORTED,
        )
        pack = Pack(
            id="p3",
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
                    id="risk_register",
                    title="Risk Register",
                    thesis="t",
                    findings=[finding],
                )
            ],
        )

        report = run_publish_checks(pack, chunks_by_id={})

        self.assertFalse(report.passed)
        self.assertEqual(finding.status, FindingStatus.UNSUPPORTED)
        self.assertEqual(finding.unknown_reason, "Cited evidence is not indexed")
        self.assertTrue(any(issue.code == "missing_cited_chunk" for issue in report.issues))

    def test_citation_outside_pack_doc_set_is_unsupported(self) -> None:
        chunk = EvidenceChunk(
            id="outside",
            doc_id="d2",
            page_start=4,
            page_end=4,
            text_zh="",
            text_en="Supplier concentration was 18%.",
            language="en",
            extraction_method=ExtractionMethod.EMBEDDED_TEXT,
            confidence=0.99,
        )
        citation = CitationRef(
            chunk_id=chunk.id,
            doc_id=chunk.doc_id,
            page=chunk.page_start,
            citation_label="CNINFO 2024 Annual Report, p. 4",
        )
        finding = Finding(
            id="f4",
            pack_id="p4",
            section_id="customers_suppliers",
            claim_text="Supplier concentration was 18%.",
            claim_type="supplier_concentration",
            citations=[citation],
            status=FindingStatus.SUPPORTED,
        )
        pack = Pack(
            id="p4",
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
                    id="customers_suppliers",
                    title="Customers & Suppliers",
                    thesis="t",
                    findings=[finding],
                )
            ],
        )

        report = run_publish_checks(pack, chunks_by_id={chunk.id: chunk})

        self.assertFalse(report.passed)
        self.assertEqual(finding.status, FindingStatus.UNSUPPORTED)
        self.assertTrue(any(issue.code == "missing_cited_chunk" for issue in report.issues))


if __name__ == "__main__":
    unittest.main()
