"""Tests for public subpackage exports."""

from __future__ import annotations

import unittest


class TestQueryExports(unittest.TestCase):
    def test_query_exports(self) -> None:
        from edgarpack.query import CitedValue, DerivedValue, QueryResult, comps, financials

        self.assertTrue(callable(comps))
        self.assertTrue(callable(financials))
        self.assertTrue(issubclass(CitedValue, object))
        self.assertTrue(issubclass(DerivedValue, object))
        self.assertTrue(issubclass(QueryResult, object))


class TestPackExports(unittest.TestCase):
    def test_pack_exports(self) -> None:
        from edgarpack.pack import PackResult, build_pack

        self.assertTrue(callable(build_pack))
        self.assertTrue(issubclass(PackResult, object))


class TestChinaExports(unittest.TestCase):
    def test_china_surviving_exports(self) -> None:
        from edgarpack.china.acquire import CninfoAnnualReportRef, find_latest_annual_report
        from edgarpack.china.extract.pdf_extract import extract_pdf_pages
        from edgarpack.china.models import ExtractionMethod

        self.assertTrue(callable(find_latest_annual_report))
        self.assertTrue(callable(extract_pdf_pages))
        self.assertTrue(issubclass(CninfoAnnualReportRef, object))
        self.assertTrue(issubclass(ExtractionMethod, object))

    def test_api_create_app_export(self) -> None:
        from edgarpack.api import create_app

        self.assertTrue(callable(create_app))


if __name__ == "__main__":
    unittest.main()
