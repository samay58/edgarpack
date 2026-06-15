from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from edgarpack.config import PARSER_VERSION, SCHEMA_VERSION


class TestDiagnosePackManifestStates(unittest.TestCase):
    def _write_ok_manifest(self, pack_dir: Path) -> None:
        pack_dir.mkdir(parents=True, exist_ok=True)
        (pack_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "parser_version": PARSER_VERSION,
                    "generated_at": "2024-11-01T00:00:00+00:00",
                    "source": {
                        "url": "https://example.test",
                        "fetched_at": "2024-11-01T00:00:00+00:00",
                    },
                    "filing": {
                        "cik": "0000320193",
                        "accession": "0000320193-24-000001",
                        "form_type": "10-K",
                        "filing_date": "2024-11-01",
                        "company_name": "Apple Inc.",
                    },
                    "sections": [
                        {
                            "id": "part1_item1_business",
                            "title": "Business",
                            "path": "sections/part1_item1_business.md",
                            "char_start": 0,
                            "char_end": 10,
                            "tokens_approx": 3,
                            "sha256": "x",
                        }
                    ],
                    "artifacts": {"filing.full.md": "hash"},
                    "warnings": [],
                    "tokens_total": 3,
                }
            ),
            encoding="utf-8",
        )
        (pack_dir / "sections").mkdir(exist_ok=True)
        (pack_dir / "sections" / "part1_item1_business.md").write_text(
            "# Business\n\nBody", encoding="utf-8"
        )
        (pack_dir / "filing.full.md").write_text("# Filing\n\nBody", encoding="utf-8")

    def test_ok_state(self) -> None:
        from edgarpack.pack.doctor import diagnose_pack

        with TemporaryDirectory() as td:
            pack_dir = Path(td) / "pack"
            self._write_ok_manifest(pack_dir)
            diag = diagnose_pack(pack_dir, registry=None)
        self.assertEqual(diag.manifest_state, "ok")
        self.assertIsNone(diag.manifest_error)
        self.assertGreaterEqual(diag.sections_count, 1)
        self.assertIn("filing.full.md", diag.artifacts_present)

    def test_missing_manifest_state(self) -> None:
        from edgarpack.pack.doctor import diagnose_pack

        with TemporaryDirectory() as td:
            pack_dir = Path(td) / "pack"
            pack_dir.mkdir()
            diag = diagnose_pack(pack_dir, registry=None)
        self.assertEqual(diag.manifest_state, "manifest_missing")
        self.assertIn("rebuild", diag.remediation or "")

    def test_invalid_json_state(self) -> None:
        from edgarpack.pack.doctor import diagnose_pack

        with TemporaryDirectory() as td:
            pack_dir = Path(td) / "pack"
            pack_dir.mkdir()
            (pack_dir / "manifest.json").write_text("not json", encoding="utf-8")
            diag = diagnose_pack(pack_dir, registry=None)
        self.assertEqual(diag.manifest_state, "manifest_invalid_json")
        self.assertIsNotNone(diag.manifest_error)

    def test_schema_mismatch_state(self) -> None:
        from edgarpack.pack.doctor import diagnose_pack

        with TemporaryDirectory() as td:
            pack_dir = Path(td) / "pack"
            pack_dir.mkdir()
            (pack_dir / "manifest.json").write_text(
                json.dumps({"schema_version": 999, "filing": {}}), encoding="utf-8"
            )
            diag = diagnose_pack(pack_dir, registry=None)
        self.assertEqual(diag.manifest_state, "manifest_schema_mismatch")

    def test_io_error_state(self) -> None:
        from edgarpack.pack.doctor import diagnose_pack

        with TemporaryDirectory() as td:
            pack_dir = Path(td) / "pack"
            pack_dir.mkdir()
            (pack_dir / "manifest.json").mkdir()
            diag = diagnose_pack(pack_dir, registry=None)
        self.assertEqual(diag.manifest_state, "manifest_io_error")


class TestDiagnosePackCoverage(unittest.TestCase):
    def test_json_round_trip_stable(self) -> None:
        from edgarpack.pack.doctor import diagnose_pack

        with TemporaryDirectory() as td:
            pack_dir = Path(td) / "pack"
            pack_dir.mkdir()
            diag = diagnose_pack(pack_dir, registry=None)
            payload = diag.model_dump_json()
        data = json.loads(payload)
        self.assertIn("manifest_state", data)
        self.assertIn("artifacts_present", data)
        self.assertIn("catalog_concepts_total", data)

    def test_registration_pack_flags_body_collapse_and_unknown_only(self) -> None:
        from edgarpack.pack.doctor import diagnose_pack

        with TemporaryDirectory() as td:
            pack_dir = Path(td) / "pack"
            sections_dir = pack_dir / "sections"
            sections_dir.mkdir(parents=True)
            (sections_dir / "unknown_01.md").write_text("tiny body", encoding="utf-8")
            (pack_dir / "filing.full.md").write_text("tiny body", encoding="utf-8")
            (pack_dir / "manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": SCHEMA_VERSION,
                        "parser_version": PARSER_VERSION,
                        "generated_at": "2026-06-15T00:00:00+00:00",
                        "source": {
                            "url": "https://www.sec.gov/Archives/test/f1.htm",
                            "fetched_at": "2026-06-15T00:00:00+00:00",
                        },
                        "filing": {
                            "cik": "0001493318",
                            "accession": "0001013762-25-001589",
                            "form_type": "F-1",
                            "filing_date": "2025-03-24",
                            "company_name": "eToro Group Ltd.",
                        },
                        "sections": [
                            {
                                "id": "unknown_01",
                                "title": "Unknown Section",
                                "path": "sections/unknown_01.md",
                                "char_start": 0,
                                "char_end": 39,
                                "tokens_approx": 39,
                                "sha256": "x",
                            }
                        ],
                        "artifacts": {"filing.full.md": "hash"},
                        "warnings": ["No section headings detected in document"],
                        "tokens_total": 39,
                    }
                ),
                encoding="utf-8",
            )

            diag = diagnose_pack(pack_dir, registry=None)

        self.assertFalse(diag.healthy)
        self.assertEqual(diag.health_model, "registration")
        self.assertIn("body_collapse", diag.registration_health_flags)
        self.assertIn("unknown_only_sections", diag.registration_health_flags)
        self.assertIn("body collapse", diag.remediation or "")


if __name__ == "__main__":
    unittest.main()
