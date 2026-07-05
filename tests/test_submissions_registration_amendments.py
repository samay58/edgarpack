"""Tests for registration-family (S-1/F-1) amendment awareness in `get_latest_filing`.

Three blind spots this closes:
  1. `get_latest_filing` compared exact normalized form types, so an F-1/A
     never matched a target of "F-1".
  2. It only scanned `filings.recent`, so a filer with enough later filings
     to page the F-1 family out of that window would report not-found.
  3. Given several family members, it needs to pick the newest one by
     filing date (tie: accession), not just the first one encountered.
"""

from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import AsyncMock, patch

from edgarpack.sec.submissions import get_latest_filing, matches_registration_family


class MatchesRegistrationFamilyTest(unittest.TestCase):
    def test_f1_base_matches_f1_and_amendment(self) -> None:
        self.assertTrue(matches_registration_family("F-1", "F-1"))
        self.assertTrue(matches_registration_family("F-1/A", "F-1"))
        self.assertFalse(matches_registration_family("S-1", "F-1"))

    def test_s1_base_matches_s1_and_amendment(self) -> None:
        self.assertTrue(matches_registration_family("S-1", "S-1"))
        self.assertTrue(matches_registration_family("S-1/A", "S-1"))
        self.assertFalse(matches_registration_family("F-1", "S-1"))

    def test_non_registration_base_requires_exact_match(self) -> None:
        self.assertTrue(matches_registration_family("10-K", "10-K"))
        self.assertFalse(matches_registration_family("10-K/A", "10-K"))


def _fake_main_submissions(name: str = "Neutron Holdings, Inc.") -> dict:
    return {
        "name": name,
        "filings": {
            # No F-1 family member in the recent window: the filer has
            # since accumulated enough periodic filings to age it out.
            "recent": {
                "form": ["10-K", "4", "8-K"],
                "accessionNumber": [
                    "0001628280-26-003942",
                    "0000950103-26-005904",
                    "0001628280-26-025108",
                ],
                "filingDate": ["2026-01-29", "2026-04-17", "2026-04-14"],
                "reportDate": ["2025-12-31", "", ""],
                "primaryDocument": ["nh-20251231.htm", "form4.xml", "nh-8k.htm"],
            },
            "files": [
                {
                    "name": "page1.json",
                    "filingCount": 500,
                    "filingFrom": "2024-04-01",
                    "filingTo": "2025-12-31",
                },
                {
                    "name": "page2.json",
                    "filingCount": 500,
                    "filingFrom": "2022-01-01",
                    "filingTo": "2024-03-31",
                },
            ],
        },
    }


def _fake_page1_no_family() -> dict:
    """Second-newest page: noise only, no F-1 family member."""
    return {
        "form": ["10-Q", "8-K"],
        "accessionNumber": ["0001628280-25-000012", "0001628280-25-000051"],
        "filingDate": ["2025-08-01", "2025-05-12"],
        "reportDate": ["2025-06-30", ""],
        "primaryDocument": ["nh-20250630.htm", "nh-8k.htm"],
    }


def _fake_page2_has_family() -> dict:
    """Oldest page: the original F-1 and its later amendment both live here."""
    return {
        "form": ["F-1", "F-1/A", "S-1"],
        "accessionNumber": [
            "0001628280-23-000010",
            "0001628280-23-000099",
            "0001628280-22-000001",
        ],
        "filingDate": ["2023-02-01", "2023-04-18", "2022-01-05"],
        "reportDate": ["", "", ""],
        "primaryDocument": ["nh-f1.htm", "nh-f1a.htm", "nh-s1.htm"],
    }


class GetLatestFilingAmendmentTest(unittest.IsolatedAsyncioTestCase):
    async def test_matches_amendment_form_directly_in_recent(self) -> None:
        """An F-1/A sitting in `recent` matches a request for "F-1"."""
        data = _fake_main_submissions()
        data["filings"]["recent"]["form"] = ["F-1/A", "10-K", "4"]
        data["filings"]["recent"]["accessionNumber"] = [
            "0001628280-26-000001",
            "0001628280-26-003942",
            "0000950103-26-005904",
        ]
        data["filings"]["recent"]["filingDate"] = ["2026-01-05", "2026-01-29", "2026-04-17"]
        data["filings"]["recent"]["reportDate"] = ["", "2025-12-31", ""]
        data["filings"]["recent"]["primaryDocument"] = [
            "nh-f1a.htm",
            "nh-20251231.htm",
            "form4.xml",
        ]

        with patch(
            "edgarpack.sec.submissions.fetch_submissions",
            new=AsyncMock(return_value=data),
        ):
            meta = await get_latest_filing("0001628280", "F-1")
        self.assertEqual(meta.form_type, "F-1/A")
        self.assertEqual(meta.accession, "0001628280-26-000001")

    async def test_paginates_past_recent_to_find_amendment_family(self) -> None:
        """The family is entirely aged out of `recent` and off page one; only
        page two (the oldest historical page) has it, and the newest member
        there is the F-1/A."""
        with (
            patch(
                "edgarpack.sec.submissions.fetch_submissions",
                new=AsyncMock(return_value=_fake_main_submissions()),
            ),
            patch(
                "edgarpack.sec.submissions._fetch_submissions_page",
                new=AsyncMock(side_effect=[_fake_page1_no_family(), _fake_page2_has_family()]),
            ) as fetch_page,
        ):
            meta = await get_latest_filing("0001628280", "F-1")

        self.assertEqual(meta.form_type, "F-1/A")
        self.assertEqual(meta.accession, "0001628280-23-000099")
        self.assertEqual(meta.filing_date, date(2023, 4, 18))
        self.assertEqual(fetch_page.await_count, 2)

    async def test_picks_newest_by_date_when_family_spans_one_page(self) -> None:
        """Within the page that has the family, pick the newest by filing
        date rather than the first match encountered."""
        with (
            patch(
                "edgarpack.sec.submissions.fetch_submissions",
                new=AsyncMock(return_value=_fake_main_submissions()),
            ),
            patch(
                "edgarpack.sec.submissions._fetch_submissions_page",
                new=AsyncMock(side_effect=[_fake_page1_no_family(), _fake_page2_has_family()]),
            ),
        ):
            meta = await get_latest_filing("0001628280", "F-1")
        # F-1 (2023-02-01) precedes F-1/A (2023-04-18) in the fixture array,
        # so a first-match implementation would wrongly return the original.
        self.assertNotEqual(meta.accession, "0001628280-23-000010")

    async def test_tie_breaks_by_accession_when_dates_match(self) -> None:
        page = {
            "form": ["F-1", "F-1/A"],
            "accessionNumber": ["0001628280-23-000010", "0001628280-23-000099"],
            "filingDate": ["2023-02-01", "2023-02-01"],
            "reportDate": ["", ""],
            "primaryDocument": ["nh-f1.htm", "nh-f1a.htm"],
        }
        data = {"name": "Neutron Holdings, Inc.", "filings": {"recent": page, "files": []}}
        with patch(
            "edgarpack.sec.submissions.fetch_submissions",
            new=AsyncMock(return_value=data),
        ):
            meta = await get_latest_filing("0001628280", "F-1")
        self.assertEqual(meta.accession, "0001628280-23-000099")

    async def test_still_raises_when_family_never_found(self) -> None:
        with (
            patch(
                "edgarpack.sec.submissions.fetch_submissions",
                new=AsyncMock(return_value=_fake_main_submissions()),
            ),
            patch(
                "edgarpack.sec.submissions._fetch_submissions_page",
                new=AsyncMock(return_value=_fake_page1_no_family()),
            ),
        ):
            with self.assertRaises(ValueError):
                await get_latest_filing("0001628280", "F-1")

    async def test_non_registration_form_unaffected(self) -> None:
        """A plain 10-K request still matches exactly, no amendment fuzzing."""
        with patch(
            "edgarpack.sec.submissions.fetch_submissions",
            new=AsyncMock(return_value=_fake_main_submissions()),
        ):
            meta = await get_latest_filing("0001628280", "10-K")
        self.assertEqual(meta.form_type, "10-K")
        self.assertEqual(meta.accession, "0001628280-26-003942")


if __name__ == "__main__":
    unittest.main()
