"""Tests for the learned_concepts schema migration (v1 -> v2)."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path


class TestLearnedRegistryMigration(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db_path = Path(self._tmp.name) / "registry.db"

    def _create_pre_migration_schema_with_row(self) -> None:
        """Write a pre-migration v0 schema + one row (user_version=0), as it would look before any self-heal migration ran."""
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS learned_concepts (
                cik           TEXT NOT NULL,
                metric        TEXT NOT NULL,
                concept       TEXT NOT NULL,
                taxonomy      TEXT NOT NULL,
                source        TEXT NOT NULL,
                verified      INTEGER NOT NULL,
                verif_method  TEXT,
                value_sample  REAL,
                learned_at    TEXT NOT NULL,
                hit_count     INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (cik, metric)
            )
        """)
        conn.execute(
            "INSERT INTO learned_concepts (cik, metric, concept, taxonomy, "
            "source, verified, verif_method, value_sample, learned_at, hit_count) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("0001045810", "revenue", "Revenues", "us-gaap",
             "fuzzy", 1, "order_of_magnitude", 130e9,
             datetime.now(UTC).isoformat(), 0),
        )
        conn.execute("PRAGMA user_version = 0")
        conn.commit()
        conn.close()

    def test_migration_adds_accession_column(self) -> None:
        self._create_pre_migration_schema_with_row()

        from edgarpack.query.learned_registry import LearnedRegistry
        reg = LearnedRegistry(db_path=self.db_path)

        # Check schema has new column
        conn = sqlite3.connect(str(self.db_path))
        cols = [row[1] for row in conn.execute("PRAGMA table_info(learned_concepts)").fetchall()]
        self.assertIn("accession", cols)

        # user_version bumped to at least 1 (currently 2 after PK rebuild)
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        self.assertGreaterEqual(version, 1)
        conn.close()
        reg.close()

    def test_migration_preserves_existing_v1_rows(self) -> None:
        self._create_pre_migration_schema_with_row()

        from edgarpack.query.learned_registry import LearnedRegistry
        reg = LearnedRegistry(db_path=self.db_path)
        reg.close()

        # Query the raw row to verify every field survived migration,
        # especially that the new accession column defaulted to ''.
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM learned_concepts WHERE cik = ? AND metric = ?",
            ("0001045810", "revenue"),
        ).fetchone()
        conn.close()

        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["concept"], "Revenues")
        self.assertEqual(row["taxonomy"], "us-gaap")
        self.assertEqual(row["source"], "fuzzy")
        self.assertEqual(row["verified"], 1)
        self.assertEqual(row["verif_method"], "order_of_magnitude")
        self.assertAlmostEqual(row["value_sample"], 130e9)
        self.assertEqual(row["hit_count"], 0)
        # The critical invariant: the new accession column was
        # backfilled with '' (DEFAULT clause) on the existing v1 row.
        self.assertEqual(row["accession"], "")

    def test_migration_is_idempotent(self) -> None:
        self._create_pre_migration_schema_with_row()

        from edgarpack.query.learned_registry import LearnedRegistry
        LearnedRegistry(db_path=self.db_path).close()  # first open: migrates
        LearnedRegistry(db_path=self.db_path).close()  # second open: no-op

        # Still exactly one row, still has the column
        conn = sqlite3.connect(str(self.db_path))
        rows = conn.execute("SELECT * FROM learned_concepts").fetchall()
        self.assertEqual(len(rows), 1)
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        self.assertGreaterEqual(version, 1)
        conn.close()

    def test_fresh_install_has_migrated_schema(self) -> None:
        """A fresh DB (no pre-existing table) should still end up at user_version=2."""
        from edgarpack.query.learned_registry import LearnedRegistry
        reg = LearnedRegistry(db_path=self.db_path)

        conn = sqlite3.connect(str(self.db_path))
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        self.assertEqual(version, 2)
        cols = [row[1] for row in conn.execute("PRAGMA table_info(learned_concepts)").fetchall()]
        self.assertIn("accession", cols)
        conn.close()
        reg.close()

    def _create_v1_schema_with_row(self) -> None:
        """Write a true v1-state schema (has accession column, old PK, user_version=1)
        with one row containing a non-empty accession value.

        This simulates a production DB that was migrated from v0 to v1 (column
        added, user_version=1) but has not yet been migrated to v2 (PK still
        (cik, metric), not (cik, accession, metric)).
        """
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS learned_concepts (
                cik           TEXT NOT NULL,
                metric        TEXT NOT NULL,
                concept       TEXT NOT NULL,
                taxonomy      TEXT NOT NULL,
                source        TEXT NOT NULL,
                verified      INTEGER NOT NULL,
                verif_method  TEXT,
                value_sample  REAL,
                learned_at    TEXT NOT NULL,
                hit_count     INTEGER NOT NULL DEFAULT 0,
                accession     TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (cik, metric)
            )
        """)
        conn.execute(
            "INSERT INTO learned_concepts (cik, metric, concept, taxonomy, "
            "source, verified, verif_method, value_sample, learned_at, "
            "hit_count, accession) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("0001535527", "arr", "annual recurring revenue", "kpi-prose",
             "kpi-llm", 1, "prior_filing_crosscheck", 3.44e9,
             datetime.now(UTC).isoformat(), 5, "0001535527-24-000123"),
        )
        conn.execute("PRAGMA user_version = 1")
        conn.commit()
        conn.close()

    def test_v1_to_v2_rebuild_in_isolation(self) -> None:
        """Migrating a true v1 database (user_version=1, has accession column,
        old PK) should produce a v2 database (user_version=2, new PK) with the
        existing row fully preserved including its non-empty accession."""
        self._create_v1_schema_with_row()

        from edgarpack.query.learned_registry import LearnedRegistry
        reg = LearnedRegistry(db_path=self.db_path)
        reg.close()

        # user_version bumped to 2
        conn = sqlite3.connect(str(self.db_path))
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        self.assertEqual(version, 2)

        # Row preserved with all fields intact
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM learned_concepts WHERE cik = ? AND metric = ?",
            ("0001535527", "arr"),
        ).fetchone()
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["concept"], "annual recurring revenue")
        self.assertEqual(row["taxonomy"], "kpi-prose")
        self.assertEqual(row["source"], "kpi-llm")
        self.assertEqual(row["verified"], 1)
        self.assertEqual(row["verif_method"], "prior_filing_crosscheck")
        self.assertAlmostEqual(row["value_sample"], 3.44e9)
        self.assertEqual(row["hit_count"], 5)
        self.assertEqual(row["accession"], "0001535527-24-000123")

        # The new PK is (cik, accession, metric) -- verify by inserting a
        # second row with the same (cik, metric) but different accession.
        # Under the old PK this would have raised UNIQUE constraint.
        conn.execute(
            "INSERT INTO learned_concepts (cik, metric, concept, taxonomy, "
            "source, verified, verif_method, value_sample, learned_at, "
            "hit_count, accession) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("0001535527", "arr", "annual recurring revenue", "kpi-prose",
             "kpi-llm", 1, "prior_filing_crosscheck", 2.56e9,
             datetime.now(UTC).isoformat(), 0, "0001535527-23-000045"),
        )
        conn.commit()

        # Both rows coexist
        rows = conn.execute(
            "SELECT accession, value_sample FROM learned_concepts "
            "WHERE cik = ? AND metric = ? ORDER BY accession",
            ("0001535527", "arr"),
        ).fetchall()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["accession"], "0001535527-23-000045")
        self.assertEqual(rows[1]["accession"], "0001535527-24-000123")
        conn.close()


if __name__ == "__main__":
    unittest.main()
