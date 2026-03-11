"""Tests for China Lens repository and object-store adapters."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from edgarpack.china.models import CninfoSyncRequest, CreatePackRequest
from edgarpack.china.service import ChinaLensService
from edgarpack.china.storage import (
    JsonFileChinaLensRepository,
    LocalObjectStore,
    create_default_object_store,
    create_default_repository,
)


class TestChinaStorage(unittest.TestCase):
    def test_json_repository_persists_service_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JsonFileChinaLensRepository(tmpdir)
            service = ChinaLensService(repository=repo)

            created = service.create_pack_job(CreatePackRequest(company_id="cmp_tencent_0700"))
            service.get_pack_status(created.pack_id, auto_tick=False)

            reloaded = ChinaLensService(repository=JsonFileChinaLensRepository(tmpdir))
            pack = reloaded.get_pack(created.pack_id)
            status = reloaded.get_pack_status(created.pack_id, auto_tick=False)

        self.assertEqual(pack.id, created.pack_id)
        self.assertEqual(status.job_id, created.job_id)
        self.assertEqual(len(reloaded.list_companies()), 1)

    def test_manifest_sync_stores_pdf_in_local_object_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            object_root = Path(tmpdir) / "objects"
            pdf_path = Path(tmpdir) / "fixture.pdf"
            pdf_path.write_bytes(b"%PDF-1.4 mock pdf bytes")

            manifest_path = Path(tmpdir) / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "company_id": "cmp_tencent_0700",
                        "documents": [
                            {
                                "doc_id": "doc_pdf_fixture",
                                "title": "Tencent PDF Fixture",
                                "filing_date": "2025-04-01",
                                "source_url": "https://www.cninfo.com.cn/mock/tencent-fixture.pdf",
                                "pages": 2,
                                "local_pdf_path": str(pdf_path),
                                "snippets": [
                                    {
                                        "page": 1,
                                        "text_zh": "示例证据片段。",
                                        "text_en": "Example evidence snippet.",
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            service = ChinaLensService(object_store=LocalObjectStore(str(object_root)))
            response = service.cninfo_sync(
                CninfoSyncRequest(
                    company_id="cmp_tencent_0700",
                    manifest_path=str(manifest_path),
                    clear_existing=True,
                )
            )
            doc = response.documents[0]

            self.assertEqual(doc.object_key, "documents/cmp_tencent_0700/doc_pdf_fixture.pdf")
            self.assertTrue(doc.storage_url)
            self.assertTrue(Path(doc.storage_url).exists())
            self.assertEqual(response.ingested_chunks, 1)

    def test_default_factories_honor_environment(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "EDGARPACK_CHINA_STORAGE_BACKEND": "json",
                    "EDGARPACK_CHINA_STORAGE_DIR": str(Path(tmpdir) / "repo"),
                    "EDGARPACK_CHINA_OBJECT_STORE_DIR": str(Path(tmpdir) / "objects"),
                },
                clear=False,
            ):
                repository = create_default_repository()
                object_store = create_default_object_store()

        self.assertIsInstance(repository, JsonFileChinaLensRepository)
        self.assertIsInstance(object_store, LocalObjectStore)


if __name__ == "__main__":
    unittest.main()
