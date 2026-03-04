"""API smoke tests for China Lens FastAPI routes."""

from __future__ import annotations

import importlib.util
import unittest

FASTAPI_AVAILABLE = importlib.util.find_spec("fastapi") is not None
TESTCLIENT_AVAILABLE = False
TestClientType = None
if FASTAPI_AVAILABLE:
    try:
        from fastapi.testclient import TestClient as FastAPITestClient
    except Exception:
        FastAPITestClient = None
    else:
        TESTCLIENT_AVAILABLE = True
        TestClientType = FastAPITestClient


@unittest.skipUnless(TESTCLIENT_AVAILABLE, "fastapi testclient stack not installed")
class TestChinaApi(unittest.TestCase):
    def setUp(self) -> None:
        from edgarpack.api.main import create_app

        assert TestClientType is not None
        self.client = TestClientType(create_app())

    def test_health_and_companies(self) -> None:
        health = self.client.get("/healthz")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["status"], "ok")

        companies = self.client.get("/api/v1/companies")
        self.assertEqual(companies.status_code, 200)
        self.assertGreaterEqual(len(companies.json()), 1)

    def test_pack_creation_and_status(self) -> None:
        created = self.client.post(
            "/api/v1/packs",
            json={"company_id": "cmp_tencent_0700"},
        )
        self.assertEqual(created.status_code, 200)
        payload = created.json()

        status = self.client.get(f"/api/v1/packs/{payload['pack_id']}/status")
        self.assertEqual(status.status_code, 200)
        self.assertIn("stage", status.json())

    def test_evidence_search_and_citation_resolve(self) -> None:
        search = self.client.post(
            "/api/v1/evidence/search",
            json={"query": "top customers", "company_id": "cmp_tencent_0700"},
        )
        self.assertEqual(search.status_code, 200)
        hits = search.json()["hits"]
        self.assertGreaterEqual(len(hits), 1)

        resolved = self.client.post(
            "/api/v1/citations/resolve",
            json={"chunk_id": hits[0]["chunk_id"]},
        )
        self.assertEqual(resolved.status_code, 200)
        self.assertIn("citation_label", resolved.json())


if __name__ == "__main__":
    unittest.main()
