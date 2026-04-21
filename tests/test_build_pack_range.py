from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

from edgarpack.pack.build import PackResult
from edgarpack.sec.submissions import FilingMeta


def _meta(accn: str, filing_date: date) -> FilingMeta:
    return FilingMeta(
        cik="0000320193",
        accession=accn,
        form_type="10-K",
        filing_date=filing_date,
        primary_document="aapl.htm",
        company_name="Apple Inc.",
    )


def _result(accn: str) -> PackResult:
    return PackResult(
        output_dir=Path(f"/tmp/packs/0000320193/{accn}"),
        filing_meta={"accession": accn, "form_type": "10-K"},
        sections_count=1,
        tokens_total=100,
        warnings=[],
        artifacts=["filing.full.md"],
    )


class TestBuildPackRange(unittest.IsolatedAsyncioTestCase):
    async def test_last_slices_to_n(self) -> None:
        from edgarpack.pack.build import build_pack_range

        filings = [
            _meta("0000320193-24-000001", date(2024, 11, 1)),
            _meta("0000320193-23-000001", date(2023, 11, 1)),
            _meta("0000320193-22-000001", date(2022, 11, 1)),
            _meta("0000320193-21-000001", date(2021, 11, 1)),
        ]
        with (
            patch(
                "edgarpack.pack.build.list_filings",
                new=AsyncMock(return_value=filings),
            ),
            patch(
                "edgarpack.pack.build.build_pack",
                new=AsyncMock(side_effect=lambda cik, accession, **kw: _result(accession)),
            ) as mock_build,
        ):
            results = await build_pack_range(
                cik="0000320193",
                form_type="10-K",
                last=2,
                out_dir=Path("/tmp/packs"),
                with_chunks=False,
                with_xbrl=False,
                force=False,
            )
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].filing_meta["accession"], "0000320193-24-000001")
        self.assertEqual(results[1].filing_meta["accession"], "0000320193-23-000001")
        self.assertEqual(mock_build.await_count, 2)

    async def test_after_before_filters_date_window(self) -> None:
        from edgarpack.pack.build import build_pack_range

        filings = [
            _meta("a", date(2024, 11, 1)),
            _meta("b", date(2022, 6, 15)),
            _meta("c", date(2021, 3, 3)),
            _meta("d", date(2019, 12, 1)),
        ]
        with (
            patch(
                "edgarpack.pack.build.list_filings",
                new=AsyncMock(return_value=filings),
            ),
            patch(
                "edgarpack.pack.build.build_pack",
                new=AsyncMock(side_effect=lambda cik, accession, **kw: _result(accession)),
            ),
        ):
            results = await build_pack_range(
                cik="0000320193",
                form_type="10-K",
                after=date(2020, 1, 1),
                before=date(2022, 12, 31),
                out_dir=Path("/tmp/packs"),
                with_chunks=False,
                with_xbrl=False,
                force=False,
            )
        accns = [r.filing_meta["accession"] for r in results]
        self.assertEqual(accns, ["b", "c"])

    async def test_last_and_date_window_compose(self) -> None:
        from edgarpack.pack.build import build_pack_range

        filings = [
            _meta("a", date(2024, 11, 1)),
            _meta("b", date(2022, 6, 15)),
            _meta("c", date(2021, 3, 3)),
            _meta("d", date(2019, 12, 1)),
        ]
        with (
            patch(
                "edgarpack.pack.build.list_filings",
                new=AsyncMock(return_value=filings),
            ),
            patch(
                "edgarpack.pack.build.build_pack",
                new=AsyncMock(side_effect=lambda cik, accession, **kw: _result(accession)),
            ),
        ):
            results = await build_pack_range(
                cik="0000320193",
                form_type="10-K",
                last=1,
                after=date(2020, 1, 1),
                out_dir=Path("/tmp/packs"),
                with_chunks=False,
                with_xbrl=False,
                force=False,
            )
        self.assertEqual([r.filing_meta["accession"] for r in results], ["a"])

    async def test_force_is_passed_through(self) -> None:
        from edgarpack.pack.build import build_pack_range

        filings = [_meta("a", date(2024, 11, 1))]
        mock_build = AsyncMock(side_effect=lambda cik, accession, **kw: _result(accession))
        with (
            patch(
                "edgarpack.pack.build.list_filings",
                new=AsyncMock(return_value=filings),
            ),
            patch("edgarpack.pack.build.build_pack", new=mock_build),
        ):
            await build_pack_range(
                cik="0000320193",
                form_type="10-K",
                last=1,
                out_dir=Path("/tmp/packs"),
                with_chunks=True,
                with_xbrl=True,
                force=True,
            )
        kwargs = mock_build.await_args.kwargs
        self.assertTrue(kwargs["force"])
        self.assertTrue(kwargs["with_chunks"])
        self.assertTrue(kwargs["with_xbrl"])

    async def test_empty_window_returns_empty_list(self) -> None:
        from edgarpack.pack.build import build_pack_range

        filings = [_meta("a", date(2024, 11, 1))]
        with (
            patch(
                "edgarpack.pack.build.list_filings",
                new=AsyncMock(return_value=filings),
            ),
            patch("edgarpack.pack.build.build_pack", new=AsyncMock()) as mock_build,
        ):
            results = await build_pack_range(
                cik="0000320193",
                form_type="10-K",
                after=date(2030, 1, 1),
                out_dir=Path("/tmp/packs"),
                with_chunks=False,
                with_xbrl=False,
                force=False,
            )
        self.assertEqual(results, [])
        self.assertEqual(mock_build.await_count, 0)
