"""Tests for the learned_concepts SQLite DAO."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from edgarpack.query.learned_registry import LearnedRegistry


class TestLearnedRegistry(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db_path = Path(self._tmp.name) / "registry.db"
        self.reg = LearnedRegistry(db_path=self.db_path)

    def test_schema_created_on_init(self) -> None:
        # Table exists; lookup on an empty registry returns None
        self.assertIsNone(self.reg.lookup("0001045810", "revenue"))

    def test_upsert_and_lookup(self) -> None:
        self.reg.upsert(
            cik="0001045810",
            metric="revenue",
            concept="Revenues",
            taxonomy="us-gaap",
            source="fuzzy",
            verified=True,
            verif_method="order_of_magnitude",
            value_sample=130_000_000_000.0,
        )
        row = self.reg.lookup("0001045810", "revenue")
        self.assertIsNotNone(row)
        assert row is not None  # for type narrowing
        self.assertEqual(row.cik, "0001045810")
        self.assertEqual(row.metric, "revenue")
        self.assertEqual(row.concept, "Revenues")
        self.assertEqual(row.taxonomy, "us-gaap")
        self.assertEqual(row.source, "fuzzy")
        self.assertTrue(row.verified)
        self.assertEqual(row.verif_method, "order_of_magnitude")
        self.assertAlmostEqual(row.value_sample or 0.0, 130_000_000_000.0)
        self.assertEqual(row.hit_count, 0)

    def test_upsert_overwrites_existing(self) -> None:
        self.reg.upsert(
            cik="0001045810", metric="revenue", concept="SalesRevenueNet",
            taxonomy="us-gaap", source="fuzzy", verified=False,
        )
        self.reg.upsert(
            cik="0001045810", metric="revenue", concept="Revenues",
            taxonomy="us-gaap", source="llm", verified=True,
            verif_method="order_of_magnitude", value_sample=100.0,
        )
        row = self.reg.lookup("0001045810", "revenue")
        assert row is not None
        self.assertEqual(row.concept, "Revenues")
        self.assertEqual(row.source, "llm")
        self.assertTrue(row.verified)

    def test_bump_hit_count(self) -> None:
        self.reg.upsert(
            cik="0001045810", metric="revenue", concept="Revenues",
            taxonomy="us-gaap", source="fuzzy", verified=True,
        )
        self.reg.bump_hit_count("0001045810", "revenue")
        self.reg.bump_hit_count("0001045810", "revenue")
        row = self.reg.lookup("0001045810", "revenue")
        assert row is not None
        self.assertEqual(row.hit_count, 2)

    def test_bump_hit_count_noop_on_missing_row(self) -> None:
        # Should not raise; the row simply doesn't exist.
        self.reg.bump_hit_count("9999999", "nothing")

    def test_list_rows_filters_by_cik(self) -> None:
        self.reg.upsert(cik="A", metric="rev", concept="X", taxonomy="us-gaap",
                        source="fuzzy", verified=True)
        self.reg.upsert(cik="B", metric="rev", concept="Y", taxonomy="us-gaap",
                        source="fuzzy", verified=True)
        rows = self.reg.list_rows(cik="A")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].cik, "A")

    def test_list_rows_filters_by_source(self) -> None:
        self.reg.upsert(cik="A", metric="rev", concept="X", taxonomy="us-gaap",
                        source="fuzzy", verified=True)
        self.reg.upsert(cik="A", metric="ni", concept="Y", taxonomy="us-gaap",
                        source="llm", verified=True)
        fuzzy = self.reg.list_rows(source="fuzzy")
        self.assertEqual(len(fuzzy), 1)
        self.assertEqual(fuzzy[0].source, "fuzzy")

    def test_list_rows_filters_unverified(self) -> None:
        self.reg.upsert(cik="A", metric="rev", concept="X", taxonomy="us-gaap",
                        source="fuzzy", verified=True)
        self.reg.upsert(cik="A", metric="ni", concept="Y", taxonomy="us-gaap",
                        source="fuzzy", verified=False)
        only_unverified = self.reg.list_rows(only_unverified=True)
        self.assertEqual(len(only_unverified), 1)
        self.assertFalse(only_unverified[0].verified)

    def test_verify_promotes_row(self) -> None:
        self.reg.upsert(cik="A", metric="rev", concept="X", taxonomy="us-gaap",
                        source="llm", verified=False)
        self.reg.verify_row("A", "rev")
        row = self.reg.lookup("A", "rev")
        assert row is not None
        self.assertTrue(row.verified)
        self.assertEqual(row.verif_method, "manual")

    def test_clear_by_cik(self) -> None:
        self.reg.upsert(cik="A", metric="rev", concept="X", taxonomy="us-gaap",
                        source="fuzzy", verified=True)
        self.reg.upsert(cik="B", metric="rev", concept="Y", taxonomy="us-gaap",
                        source="fuzzy", verified=True)
        removed = self.reg.clear(cik="A")
        self.assertEqual(removed, 1)
        self.assertIsNone(self.reg.lookup("A", "rev"))
        self.assertIsNotNone(self.reg.lookup("B", "rev"))

    def test_clear_all_requires_explicit_flag(self) -> None:
        self.reg.upsert(cik="A", metric="rev", concept="X", taxonomy="us-gaap",
                        source="fuzzy", verified=True)
        with self.assertRaises(ValueError):
            self.reg.clear()  # no filter, no all=True -> refuse
        self.assertIsNotNone(self.reg.lookup("A", "rev"))
        self.reg.clear(all=True)
        self.assertIsNone(self.reg.lookup("A", "rev"))


if __name__ == "__main__":
    unittest.main()
