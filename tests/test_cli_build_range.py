"""CLI-level tests for `build` range flags."""

from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from edgarpack.cli import main
from edgarpack.pack.build import PackResult
from edgarpack.sec.client import SECRateLimitError


def _result(accn: str, warnings: list[str] | None = None) -> PackResult:
    return PackResult(
        output_dir=Path(f"/tmp/packs/0000320193/{accn}"),
        filing_meta={"accession": accn, "company_name": "Apple Inc.", "form_type": "10-K"},
        sections_count=1,
        tokens_total=100,
        warnings=warnings or [],
        artifacts=["filing.full.md"],
    )


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


class TestBuildRangeDispatch(unittest.TestCase):
    def test_range_flag_invokes_build_pack_range(self) -> None:
        with (
            patch(
                "edgarpack.cli._cik_from_company_args",
                new=AsyncMock(return_value=(0, "0000320193")),
            ),
            patch(
                "edgarpack.cli._resolve_cli_company",
                new=AsyncMock(return_value=SimpleNamespace(ticker="AAPL")),
            ),
            patch(
                "edgarpack.pack.build.build_pack_range",
                new=AsyncMock(return_value=[_result("a"), _result("b")]),
            ) as mock_range,
            patch(
                "edgarpack.cli._register_pack_result",
                return_value=None,
            ),
        ):
            rc = main(["build", "AAPL", "--form", "10-K", "--last", "2"])
        self.assertEqual(rc, 0)
        self.assertEqual(mock_range.await_count, 1)
        kwargs = mock_range.await_args.kwargs
        self.assertEqual(kwargs["last"], 2)
        self.assertEqual(kwargs["form_type"], "10-K")

    def test_already_built_hint_appears_in_single_filing_mode(self) -> None:
        warnings = ["Pack already exists, use --force to rebuild"]
        with (
            patch(
                "edgarpack.cli._cik_from_company_args",
                new=AsyncMock(return_value=(0, "0000320193")),
            ),
            patch(
                "edgarpack.cli._resolve_cli_company",
                new=AsyncMock(return_value=SimpleNamespace(ticker="AAPL")),
            ),
            patch(
                "edgarpack.pack.build.build_pack",
                new=AsyncMock(return_value=_result("a", warnings=warnings)),
            ),
            patch("edgarpack.cli._register_pack_result", return_value=None),
            patch("sys.stdout") as mock_stdout,
        ):
            rc = main(["build", "AAPL", "--form", "10-K"])
        self.assertEqual(rc, 0)
        printed = "".join(call.args[0] for call in mock_stdout.write.call_args_list if call.args)
        self.assertIn("edgarpack list AAPL", printed)
        self.assertIn("--last 5", printed)

    def test_rate_limit_error_gets_cooldown_message(self) -> None:
        with (
            patch(
                "edgarpack.cli._cik_from_company_args",
                new=AsyncMock(return_value=(0, "0000320193")),
            ),
            patch(
                "edgarpack.cli._resolve_cli_company",
                new=AsyncMock(return_value=SimpleNamespace(ticker="AAPL")),
            ),
            patch(
                "edgarpack.pack.build.build_pack_range",
                new=AsyncMock(
                    side_effect=SECRateLimitError(
                        url="https://www.sec.gov/Archives/example.htm",
                        status_code=429,
                        headers={},
                        content=b"traffic limit",
                        cooldown_seconds=600,
                    )
                ),
            ),
            patch("sys.stderr") as mock_stderr,
        ):
            rc = main(["build", "AAPL", "--form", "10-K", "--last", "2"])

        self.assertEqual(rc, 1)
        printed = "".join(call.args[0] for call in mock_stderr.write.call_args_list if call.args)
        self.assertIn("SEC rate limit", printed)
        self.assertIn("10 minutes", printed)
