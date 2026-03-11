"""Tests for China Lens in-memory service behavior."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from edgarpack.china.models import (
    AskRequest,
    CninfoSyncRequest,
    CreatePackRequest,
    SearchEvidenceRequest,
)
from edgarpack.china.service import ChinaLensService


class TestChinaLensService(unittest.TestCase):
    def setUp(self) -> None:
        self.service = ChinaLensService()
        self.company_id = "cmp_tencent_0700"

    def test_create_pack_and_progress_to_completion(self) -> None:
        created = self.service.create_pack_job(CreatePackRequest(company_id=self.company_id))
        self.assertTrue(created.pack_id.startswith("pack_"))

        # Deterministically tick until complete.
        for _ in range(30):
            status = self.service.get_pack_status(created.pack_id, auto_tick=True)
            if status.status.value in {"completed", "failed", "canceled"}:
                break

        pack = self.service.get_pack(created.pack_id)
        self.assertIn(pack.status.value, {"ready", "partial"})
        self.assertGreater(len(pack.sections), 0)

    def test_search_evidence_returns_hits_for_customer_query(self) -> None:
        result = self.service.search_evidence(
            SearchEvidenceRequest(
                query="top customers concentration disclosed by name",
                company_id=self.company_id,
            )
        )
        self.assertGreaterEqual(len(result.hits), 1)
        self.assertEqual(result.hits[0].chunk_id, "chunk_top_customers")

    def test_ask_not_found_path(self) -> None:
        answer = self.service.ask(
            AskRequest(
                company_id=self.company_id,
                question="What is capex guidance for 2035?",
            )
        )
        self.assertTrue(answer.not_found)
        self.assertIn("Not found", answer.answer[0].text)

    def test_cninfo_sync_manifest_ingests_snippets_and_indexes_search(self) -> None:
        payload = {
            "company_id": self.company_id,
            "documents": [
                {
                    "doc_id": "doc_tencent_2025_board",
                    "title": "Tencent 2025 Board Update",
                    "filing_date": "2025-04-01",
                    "source_url": "https://www.cninfo.com.cn/mock/tencent-2025-board.pdf",
                    "pages": 12,
                    "snippets": [
                        {
                            "page": 3,
                            "text_zh": "董事会成员调整，新增两名独立董事。",
                            "text_en": (
                                "Board composition changed with two new "
                                "independent directors."
                            ),
                        },
                        {
                            "page": 8,
                            "text_zh": "风险披露覆盖监管和数据合规。",
                            "text_en": "Risk disclosures cover regulation and data compliance.",
                        },
                    ],
                }
            ],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "cninfo-manifest.json"
            manifest_path.write_text(json.dumps(payload), encoding="utf-8")

            response = self.service.cninfo_sync(
                CninfoSyncRequest(
                    company_id=self.company_id,
                    manifest_path=str(manifest_path),
                    clear_existing=True,
                )
            )

        self.assertEqual(response.ingested_chunks, 2)
        doc_ids = {doc.id for doc in response.documents}
        self.assertEqual(doc_ids, {"doc_tencent_2025_board"})

        search = self.service.search_evidence(
            SearchEvidenceRequest(
                query="board composition independent directors",
                company_id=self.company_id,
            )
        )
        self.assertGreaterEqual(len(search.hits), 1)
        self.assertEqual(search.hits[0].doc_id, "doc_tencent_2025_board")

    def test_cninfo_sync_manifest_honors_date_window(self) -> None:
        payload = {
            "company_id": self.company_id,
            "documents": [
                {
                    "doc_id": "doc_old",
                    "title": "Tencent 2023 Interim",
                    "filing_date": "2023-08-15",
                    "source_url": "https://www.cninfo.com.cn/mock/tencent-2023-interim.pdf",
                    "pages": 4,
                    "snippets": [{"page": 1, "text_zh": "旧披露", "text_en": "Older disclosure"}],
                },
                {
                    "doc_id": "doc_new",
                    "title": "Tencent 2025 Annual",
                    "filing_date": "2025-03-20",
                    "source_url": "https://www.cninfo.com.cn/mock/tencent-2025-annual.pdf",
                    "pages": 6,
                    "snippets": [{"page": 2, "text_zh": "新增披露", "text_en": "Newer disclosure"}],
                },
            ],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "cninfo-manifest-window.json"
            manifest_path.write_text(json.dumps(payload), encoding="utf-8")

            response = self.service.cninfo_sync(
                CninfoSyncRequest(
                    company_id=self.company_id,
                    manifest_path=str(manifest_path),
                    start_date="2024-01-01",
                    end_date="2025-12-31",
                    clear_existing=True,
                )
            )

        doc_ids = {doc.id for doc in response.documents}
        self.assertEqual(doc_ids, {"doc_new"})
        self.assertEqual(response.ingested_chunks, 1)


if __name__ == "__main__":
    unittest.main()
