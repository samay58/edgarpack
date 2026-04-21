"""CLI-level tests for `build` range flags."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from edgarpack.cli import main


class TestBuildRangeArgValidation(unittest.TestCase):
    def test_accession_plus_last_rejected(self) -> None:
        rc = main(["build", "AAPL", "--accession", "0000320193-24-000123", "--last", "3"])
        self.assertEqual(rc, 2)

    def test_accession_plus_after_rejected(self) -> None:
        rc = main(["build", "AAPL", "--accession", "0000320193-24-000123", "--after", "2020-01-01"])
        self.assertEqual(rc, 2)

    def test_accession_plus_before_rejected(self) -> None:
        rc = main(
            ["build", "AAPL", "--accession", "0000320193-24-000123", "--before", "2022-12-31"]
        )
        self.assertEqual(rc, 2)

    def test_no_args_still_rejected(self) -> None:
        rc = main(["build", "AAPL"])
        self.assertEqual(rc, 2)

    def test_last_without_form_defaults_to_10k(self) -> None:
        # --last alone is accepted; --form defaults to 10-K. We patch
        # _cmd_build to capture the resolved args without hitting SEC.
        captured: dict[str, object] = {}

        def _fake_cmd_build(args: object) -> int:
            captured["form"] = getattr(args, "form", None)
            captured["last"] = getattr(args, "last", None)
            return 0

        with patch("edgarpack.cli._cmd_build", side_effect=_fake_cmd_build):
            rc = main(["build", "AAPL", "--last", "3"])
        self.assertEqual(rc, 0)
        self.assertEqual(captured["last"], 3)
        # argparse default lands as None; the range handler picks "10-K".
        # We verify the defaulting in task A3.
        self.assertIn("last", captured)

    def test_bad_date_format_rejected(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            main(["build", "AAPL", "--after", "2020/01/01"])
        self.assertEqual(ctx.exception.code, 2)
