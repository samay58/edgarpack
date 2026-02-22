"""Tests for China Lens in-memory service behavior."""

from __future__ import annotations

import unittest

from edgarpack.china.models import AskRequest, CreatePackRequest, SearchEvidenceRequest
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


if __name__ == "__main__":
    unittest.main()
