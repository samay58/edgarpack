"""Tests for SEC archives helpers."""

import unittest
from datetime import date
from unittest.mock import AsyncMock, patch

from edgarpack.sec.archives import identify_html_files
from edgarpack.sec.client import SECRateLimitError
from edgarpack.sec.submissions import FilingMeta


def _meta() -> FilingMeta:
    return FilingMeta(
        cik="0001045810",
        accession="0001045810-24-000029",
        form_type="10-K",
        filing_date=date(2024, 2, 21),
        primary_document="nvda-20240128.htm",
        company_name="NVIDIA CORP",
    )


class TestIdentifyHtmlFiles(unittest.TestCase):
    def test_skips_index_html_and_sorts(self) -> None:
        index = {
            "directory": {
                "item": [
                    {"name": "index.html"},
                    {"name": "B.htm"},
                    {"name": "a.htm"},
                    {"name": "doc.htm"},
                    {"name": "a.htm"},
                ]
            }
        }
        files = identify_html_files(index, primary_doc="doc.htm")
        self.assertEqual(files[0], "doc.htm")
        self.assertNotIn("index.html", files)
        self.assertEqual(files, ["doc.htm", "a.htm", "B.htm"])

    def test_skips_accession_index_and_filingsummary(self) -> None:
        index = {
            "directory": {
                "item": [
                    {"name": "0001045810-26-000003-index.html"},
                    {"name": "FilingSummary.html"},
                    {"name": "doc.htm"},
                ]
            }
        }
        files = identify_html_files(index, primary_doc="doc.htm")
        self.assertEqual(files, ["doc.htm"])


class TestFetchPrimaryFilingHtml(unittest.IsolatedAsyncioTestCase):
    async def test_fetches_primary_document_without_filing_index(self) -> None:
        import edgarpack.sec.archives as archives

        meta = _meta()
        with (
            patch.object(
                archives,
                "fetch_filing_index",
                new=AsyncMock(side_effect=AssertionError("index should not be fetched")),
            ),
            patch.object(archives, "fetch_file", new=AsyncMock(return_value=b"<html />")) as fetch,
        ):
            html_files = await archives.fetch_primary_filing_html(meta)

        self.assertEqual(html_files, [(meta.primary_document, b"<html />")])
        fetch.assert_awaited_once_with(meta, meta.primary_document, force=False)


class TestFetchFilingHtml(unittest.IsolatedAsyncioTestCase):
    async def test_rate_limit_error_propagates_after_sibling_tasks_finish(self) -> None:
        import edgarpack.sec.archives as archives

        meta = _meta()
        index = {
            "directory": {
                "item": [
                    {"name": meta.primary_document},
                    {"name": "a.htm"},
                    {"name": "b.htm"},
                ]
            }
        }
        calls: list[str] = []

        async def fake_fetch_file(_meta: FilingMeta, filename: str, force: bool = False) -> bytes:
            calls.append(filename)
            if filename == meta.primary_document:
                raise SECRateLimitError(
                    url="https://www.sec.gov/Archives/example.htm",
                    status_code=429,
                    headers={},
                    content=b"traffic limit",
                    cooldown_seconds=600,
                )
            return filename.encode()

        with (
            patch.object(archives, "fetch_filing_index", new=AsyncMock(return_value=index)),
            patch.object(archives, "fetch_file", new=fake_fetch_file),
        ):
            with self.assertRaises(SECRateLimitError):
                await archives.fetch_filing_html(meta)

        self.assertEqual(calls, [meta.primary_document, "a.htm", "b.htm"])


if __name__ == "__main__":
    unittest.main()
