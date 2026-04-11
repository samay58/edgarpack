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

    def _create_v1_schema_with_row(self) -> None:
        """Write a pre-migration v1 schema + one row, as a v1 installation would."""
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
        self._create_v1_schema_with_row()

        from edgarpack.query.learned_registry import LearnedRegistry
        reg = LearnedRegistry(db_path=self.db_path)

        # Check schema has new column
        conn = sqlite3.connect(str(self.db_path))
        cols = [row[1] for row in conn.execute("PRAGMA table_info(learned_concepts)").fetchall()]
        self.assertIn("accession", cols)

        # user_version bumped to 1
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        self.assertEqual(version, 1)
        conn.close()
        reg.close()

    def test_migration_preserves_existing_v1_rows(self) -> None:
        self._create_v1_schema_with_row()

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
        self._create_v1_schema_with_row()

        from edgarpack.query.learned_registry import LearnedRegistry
        LearnedRegistry(db_path=self.db_path).close()  # first open: migrates
        LearnedRegistry(db_path=self.db_path).close()  # second open: no-op

        # Still exactly one row, still has the column
        conn = sqlite3.connect(str(self.db_path))
        rows = conn.execute("SELECT * FROM learned_concepts").fetchall()
        self.assertEqual(len(rows), 1)
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        self.assertEqual(version, 1)
        conn.close()

    def test_fresh_install_has_migrated_schema(self) -> None:
        """A fresh DB (no pre-existing table) should still end up at user_version=1."""
        from edgarpack.query.learned_registry import LearnedRegistry
        reg = LearnedRegistry(db_path=self.db_path)

        conn = sqlite3.connect(str(self.db_path))
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        self.assertEqual(version, 1)
        cols = [row[1] for row in conn.execute("PRAGMA table_info(learned_concepts)").fetchall()]
        self.assertIn("accession", cols)
        conn.close()
        reg.close()


if __name__ == "__main__":
    unittest.main()
