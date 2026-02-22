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
    def test_china_exports(self) -> None:
        from edgarpack.china import Company, Pack, SearchEvidenceRequest

        self.assertTrue(issubclass(Company, object))
        self.assertTrue(issubclass(Pack, object))
        self.assertTrue(issubclass(SearchEvidenceRequest, object))

    def test_api_create_app_export(self) -> None:
        from edgarpack.api import create_app

        self.assertTrue(callable(create_app))


if __name__ == "__main__":
    unittest.main()
