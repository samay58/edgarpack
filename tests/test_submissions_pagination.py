"""Tests for paginated historical filing lookup.

SEC splits high-volume filers' submission histories across multiple JSON
files. These tests verify that `get_filing_by_accession` and `list_filings`
correctly paginate into older files when a match is not in the recent
window.
"""

from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import AsyncMock, patch

from edgarpack.sec.submissions import (
    _iter_submission_pages,
    get_filing_by_accession,
    list_filings,
)


def _fake_recent_page() -> dict:
    """Columnar recent page with two FY2024/FY2025-ish 10-K entries."""
    return {
        "form": ["10-K", "4", "8-K", "10-K"],
        "accessionNumber": [
            "0001628280-26-003942",
            "0000950103-26-005904",
            "0001628280-26-025108",
            "0001326801-25-000017",
        ],
        "filingDate": [
            "2026-01-29",
            "2026-04-17",
            "2026-04-14",
            "2025-01-30",
        ],
        "reportDate": ["2025-12-31", "", "", "2024-12-31"],
        "primaryDocument": [
            "meta-20251231.htm",
            "xslF345X05/form4.xml",
            "meta-8k.htm",
            "meta-20241231.htm",
        ],
    }


def _fake_older_page() -> dict:
    """Columnar older page with two historical 10-Ks that are NOT in recent."""
    return {
        "form": ["10-K", "10-Q", "10-K"],
        "accessionNumber": [
            "0001326801-24-000012",
            "0001326801-24-000051",
            "0001326801-23-000013",
        ],
        "filingDate": ["2024-02-02", "2024-07-25", "2023-02-02"],
        "reportDate": ["2023-12-31", "2024-06-30", "2022-12-31"],
        "primaryDocument": [
            "fb-20231231.htm",
            "fb-20240630.htm",
            "fb-20221231.htm",
        ],
    }


def _fake_main_submissions(name: str = "Meta Platforms, Inc.") -> dict:
    return {
        "name": name,
        "filings": {
            "recent": _fake_recent_page(),
            "files": [
                {
                    "name": "CIK0001326801-submissions-001.json",
                    "filingCount": 2001,
                    "filingFrom": "2016-11-02",
                    "filingTo": "2024-03-18",
                },
            ],
        },
    }


class IterSubmissionPagesTest(unittest.IsolatedAsyncioTestCase):
    async def test_yields_recent_only_when_no_files(self) -> None:
        data = {"filings": {"recent": _fake_recent_page(), "files": []}}
        pages = []
        async for page in _iter_submission_pages(data):
            pages.append(page)
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0]["form"][0], "10-K")

    async def test_yields_recent_then_older(self) -> None:
        data = _fake_main_submissions()
        with patch(
            "edgarpack.sec.submissions._fetch_submissions_page",
            new=AsyncMock(return_value=_fake_older_page()),
        ):
            pages = [p async for p in _iter_submission_pages(data)]
        self.assertEqual(len(pages), 2)
        self.assertIn("0001326801-24-000012", pages[1]["accessionNumber"])

    async def test_skips_older_page_on_fetch_failure(self) -> None:
        data = _fake_main_submissions()
        with patch(
            "edgarpack.sec.submissions._fetch_submissions_page",
            new=AsyncMock(side_effect=RuntimeError("simulated SEC timeout")),
        ):
            pages = [p async for p in _iter_submission_pages(data)]
        # Recent still yielded; older page dropped with a warning.
        self.assertEqual(len(pages), 1)


class GetFilingByAccessionTest(unittest.IsolatedAsyncioTestCase):
    async def test_resolves_from_recent(self) -> None:
        with (
            patch(
                "edgarpack.sec.submissions.fetch_submissions",
                new=AsyncMock(return_value=_fake_main_submissions()),
            ),
            patch(
                "edgarpack.sec.submissions._fetch_submissions_page",
                new=AsyncMock(return_value=_fake_older_page()),
            ) as older,
        ):
            meta = await get_filing_by_accession(
                "0001326801", "0001326801-25-000017"
            )
        self.assertEqual(meta.form_type, "10-K")
        self.assertEqual(meta.filing_date, date(2025, 1, 30))
        # Older page should not have been fetched; recent was enough.
        older.assert_not_awaited()

    async def test_resolves_from_older_page(self) -> None:
        with (
            patch(
                "edgarpack.sec.submissions.fetch_submissions",
                new=AsyncMock(return_value=_fake_main_submissions()),
            ),
            patch(
                "edgarpack.sec.submissions._fetch_submissions_page",
                new=AsyncMock(return_value=_fake_older_page()),
            ),
        ):
            meta = await get_filing_by_accession(
                "0001326801", "0001326801-23-000013"
            )
        self.assertEqual(meta.form_type, "10-K")
        self.assertEqual(meta.filing_date, date(2023, 2, 2))
        self.assertEqual(meta.period_of_report, date(2022, 12, 31))

    async def test_raises_when_accession_missing_everywhere(self) -> None:
        with (
            patch(
                "edgarpack.sec.submissions.fetch_submissions",
                new=AsyncMock(return_value=_fake_main_submissions()),
            ),
            patch(
                "edgarpack.sec.submissions._fetch_submissions_page",
                new=AsyncMock(return_value=_fake_older_page()),
            ),
        ):
            with self.assertRaises(ValueError):
                await get_filing_by_accession(
                    "0001326801", "0000000000-00-000000"
                )


class ListFilingsTest(unittest.IsolatedAsyncioTestCase):
    async def test_stops_at_limit_without_fetching_older(self) -> None:
        with (
            patch(
                "edgarpack.sec.submissions.fetch_submissions",
                new=AsyncMock(return_value=_fake_main_submissions()),
            ),
            patch(
                "edgarpack.sec.submissions._fetch_submissions_page",
                new=AsyncMock(return_value=_fake_older_page()),
            ) as older,
        ):
            results = await list_filings("0001326801", form_type="10-K", limit=2)
        self.assertEqual(len(results), 2)
        older.assert_not_awaited()
        self.assertEqual(results[0].accession, "0001628280-26-003942")
        self.assertEqual(results[1].accession, "0001326801-25-000017")

    async def test_spans_recent_and_older_when_limit_exceeds_recent(self) -> None:
        with (
            patch(
                "edgarpack.sec.submissions.fetch_submissions",
                new=AsyncMock(return_value=_fake_main_submissions()),
            ),
            patch(
                "edgarpack.sec.submissions._fetch_submissions_page",
                new=AsyncMock(return_value=_fake_older_page()),
            ) as older,
        ):
            results = await list_filings("0001326801", form_type="10-K", limit=4)
        older.assert_awaited_once()
        self.assertEqual(len(results), 4)
        accessions = [r.accession for r in results]
        self.assertEqual(
            accessions,
            [
                "0001628280-26-003942",  # recent FY2025
                "0001326801-25-000017",  # recent FY2024
                "0001326801-24-000012",  # older FY2023
                "0001326801-23-000013",  # older FY2022
            ],
        )


if __name__ == "__main__":
    unittest.main()
