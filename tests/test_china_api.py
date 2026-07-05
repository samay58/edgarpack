"""API smoke tests for the Observatory FastAPI app."""

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
class TestObservatoryApi(unittest.TestCase):
    def setUp(self) -> None:
        from edgarpack.api.main import create_app

        assert TestClientType is not None
        self.client = TestClientType(create_app())

    def test_healthz(self) -> None:
        health = self.client.get("/healthz")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["status"], "ok")

    def test_removed_china_workspace_routes_are_gone(self) -> None:
        for path in ("/api/v1/companies", "/api/v1/documents", "/api/v1/ask"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 404, path)


if __name__ == "__main__":
    unittest.main()
