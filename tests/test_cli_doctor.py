from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from edgarpack.cli import main


class TestDoctorCLI(unittest.TestCase):
    def test_doctor_single_pack_path_text(self) -> None:
        with TemporaryDirectory() as td:
            pack_dir = Path(td) / "pack"
            pack_dir.mkdir()
            (pack_dir / "manifest.json").write_text("not json", encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = main(["doctor", str(pack_dir)])
            self.assertEqual(rc, 0)
            output = buf.getvalue()
            self.assertIn("manifest_invalid_json", output)

    def test_doctor_single_pack_path_json(self) -> None:
        with TemporaryDirectory() as td:
            pack_dir = Path(td) / "pack"
            pack_dir.mkdir()
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = main(["doctor", str(pack_dir), "--format", "json"])
            self.assertEqual(rc, 0)
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload["manifest_state"], "manifest_missing")

    def test_doctor_ticker_sweep_empty_registry(self) -> None:
        from edgarpack.harvest.registry import PackRegistry

        with patch.object(PackRegistry, "list_packs", return_value=[]):
            with patch(
                "edgarpack.cli._resolve_cli_company",
                return_value=type(
                    "C", (), {"cik": "0000320193", "ticker": "AAPL", "name": "Apple Inc."}
                )(),
            ):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = main(["doctor", "AAPL"])
            self.assertEqual(rc, 0)
            self.assertIn("No packs registered", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
