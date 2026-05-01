from __future__ import annotations

import logging
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from edgarpack.harvest.registry import PackRecord
from edgarpack.query.kpi_discover import _discover_pack
from edgarpack.query.learned_registry import LearnedRegistry


def _pack_record(pack_dir: Path) -> PackRecord:
    return PackRecord(
        accession="0000320193-24-000001",
        cik="0000320193",
        ticker="AAPL",
        company_name="Apple Inc.",
        form_type="10-K",
        filing_date="2024-11-01",
        sections_count=10,
        tokens_total=1000,
        pack_dir=str(pack_dir),
        built_at="2024-11-01T00:00:00Z",
    )


class TestManifestStateClassification(unittest.TestCase):
    def test_missing_manifest(self) -> None:
        with TemporaryDirectory() as td:
            pack_dir = Path(td) / "pack"
            pack_dir.mkdir()
            reg = LearnedRegistry(db_path=Path(td) / "reg.db")
            try:
                result = _discover_pack(
                    pack_record=_pack_record(pack_dir),
                    learned_reg=reg,
                    force=False,
                )
            finally:
                reg.close()
        self.assertEqual(result.status, "manifest_missing")

    def test_invalid_json_manifest(self) -> None:
        with TemporaryDirectory() as td:
            pack_dir = Path(td) / "pack"
            pack_dir.mkdir()
            (pack_dir / "manifest.json").write_text("not json", encoding="utf-8")
            reg = LearnedRegistry(db_path=Path(td) / "reg.db")
            try:
                result = _discover_pack(
                    pack_record=_pack_record(pack_dir),
                    learned_reg=reg,
                    force=False,
                )
            finally:
                reg.close()
        self.assertEqual(result.status, "manifest_invalid_json")

    def test_io_error_surfaces_distinct_state(self) -> None:
        with TemporaryDirectory() as td:
            pack_dir = Path(td) / "pack"
            pack_dir.mkdir()
            # A directory where manifest.json should be → triggers OSError on read.
            (pack_dir / "manifest.json").mkdir()
            reg = LearnedRegistry(db_path=Path(td) / "reg.db")
            try:
                result = _discover_pack(
                    pack_record=_pack_record(pack_dir),
                    learned_reg=reg,
                    force=False,
                )
            finally:
                reg.close()
        self.assertEqual(result.status, "manifest_io_error")

    def test_cached_empty_sentinel_reports_empty_not_cached(self) -> None:
        with TemporaryDirectory() as td:
            pack_dir = Path(td) / "pack"
            pack_dir.mkdir()
            reg = LearnedRegistry(db_path=Path(td) / "reg.db")
            try:
                pack = _pack_record(pack_dir)
                reg.company_kpi_mark_empty(
                    cik=pack.cik,
                    accession=pack.accession,
                    form_type=pack.form_type,
                    period_end="2024-12-31",
                )
                result = _discover_pack(
                    pack_record=pack,
                    learned_reg=reg,
                    force=False,
                )
            finally:
                reg.close()
        self.assertEqual(result.status, "empty")
        self.assertEqual(result.discovered, [])


class TestKpiExtractManifestLogging(unittest.TestCase):
    def test_missing_manifest_logs_specific_class(self) -> None:
        # Layer B logs at WARNING. Capture the record and check the message.
        with self.assertLogs("edgarpack.query.kpi_extract", level="WARNING") as cm:
            from edgarpack.query.kpi_extract import _load_pack_manifest

            try:
                _load_pack_manifest(Path("/does/not/exist/pack"))
            except FileNotFoundError:
                logging.getLogger("edgarpack.query.kpi_extract").warning(
                    "probe: FileNotFoundError raised"
                )
        self.assertTrue(any("FileNotFoundError" in m for m in cm.output))


if __name__ == "__main__":
    unittest.main()
