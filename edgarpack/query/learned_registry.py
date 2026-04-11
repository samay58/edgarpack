"""SQLite DAO for the learned_concepts table.

Shares ~/.edgarpack/registry.db with harvest/registry.py but owns a separate
table. Thin wrapper over raw SQL; no ORM, no migrations framework.

Schema:
    learned_concepts (
        cik, metric, concept, taxonomy,
        source ('fuzzy' | 'llm' | 'user'),
        verified (0/1), verif_method, value_sample,
        learned_at, hit_count
    )
    PRIMARY KEY (cik, metric)
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ..config import CACHE_DIR

DEFAULT_REGISTRY_PATH = CACHE_DIR.parent / "registry.db"

_SCHEMA = """
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
);

CREATE INDEX IF NOT EXISTS idx_learned_source
    ON learned_concepts(source);
CREATE INDEX IF NOT EXISTS idx_learned_hit_count
    ON learned_concepts(hit_count DESC);
"""


@dataclass(frozen=True)
class LearnedRow:
    cik: str
    metric: str
    concept: str
    taxonomy: str
    source: str
    verified: bool
    verif_method: str | None
    value_sample: float | None
    learned_at: str
    hit_count: int


class LearnedRegistry:
    """SQLite-backed registry of learned metric -> concept mappings."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or DEFAULT_REGISTRY_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._ensure_schema()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
        return self._conn

    def _ensure_schema(self) -> None:
        conn = self._get_conn()
        conn.executescript(_SCHEMA)
        current_version = conn.execute("PRAGMA user_version").fetchone()[0]
        if current_version < 1:
            # v2 migration: add accession column and a (cik, accession, metric) unique index
            existing_cols = {row[1] for row in conn.execute(
                "PRAGMA table_info(learned_concepts)"
            ).fetchall()}
            if "accession" not in existing_cols:
                conn.execute(
                    "ALTER TABLE learned_concepts "
                    "ADD COLUMN accession TEXT NOT NULL DEFAULT ''"
                )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_learned_cik_accn_metric "
                "ON learned_concepts(cik, accession, metric)"
            )
            conn.execute("PRAGMA user_version = 1")
        conn.commit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def lookup(self, cik: str, metric: str) -> LearnedRow | None:
        conn = self._get_conn()
        cur = conn.execute(
            "SELECT * FROM learned_concepts WHERE cik = ? AND metric = ?",
            (cik, metric),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return _row_to_dataclass(row)

    def upsert(
        self,
        *,
        cik: str,
        metric: str,
        concept: str,
        taxonomy: str,
        source: str,
        verified: bool,
        verif_method: str | None = None,
        value_sample: float | None = None,
    ) -> None:
        conn = self._get_conn()
        conn.execute(
            """
            INSERT INTO learned_concepts (
                cik, metric, concept, taxonomy, source,
                verified, verif_method, value_sample, learned_at, hit_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            ON CONFLICT(cik, metric) DO UPDATE SET
                concept      = excluded.concept,
                taxonomy     = excluded.taxonomy,
                source       = excluded.source,
                verified     = excluded.verified,
                verif_method = excluded.verif_method,
                value_sample = excluded.value_sample,
                learned_at   = excluded.learned_at
            """,
            (
                cik, metric, concept, taxonomy, source,
                1 if verified else 0, verif_method, value_sample,
                datetime.now(UTC).isoformat(),
            ),
        )
        conn.commit()

    def bump_hit_count(self, cik: str, metric: str) -> None:
        conn = self._get_conn()
        conn.execute(
            "UPDATE learned_concepts SET hit_count = hit_count + 1 "
            "WHERE cik = ? AND metric = ?",
            (cik, metric),
        )
        conn.commit()

    def list_rows(
        self,
        *,
        cik: str | None = None,
        metric: str | None = None,
        source: str | None = None,
        only_unverified: bool = False,
    ) -> list[LearnedRow]:
        sql = "SELECT * FROM learned_concepts WHERE 1=1"
        params: list[object] = []
        if cik is not None:
            sql += " AND cik = ?"
            params.append(cik)
        if metric is not None:
            sql += " AND metric = ?"
            params.append(metric)
        if source is not None:
            sql += " AND source = ?"
            params.append(source)
        if only_unverified:
            sql += " AND verified = 0"
        sql += " ORDER BY hit_count DESC, learned_at DESC"
        conn = self._get_conn()
        cur = conn.execute(sql, tuple(params))
        return [_row_to_dataclass(r) for r in cur.fetchall()]

    def verify_row(self, cik: str, metric: str) -> None:
        conn = self._get_conn()
        conn.execute(
            "UPDATE learned_concepts SET verified = 1, verif_method = 'manual' "
            "WHERE cik = ? AND metric = ?",
            (cik, metric),
        )
        conn.commit()

    def clear(
        self,
        *,
        cik: str | None = None,
        metric: str | None = None,
        all: bool = False,
    ) -> int:
        if cik is None and metric is None and not all:
            raise ValueError(
                "learned_registry.clear: refusing to clear entire table "
                "without all=True or a cik/metric filter"
            )
        sql = "DELETE FROM learned_concepts WHERE 1=1"
        params: list[object] = []
        if cik is not None:
            sql += " AND cik = ?"
            params.append(cik)
        if metric is not None:
            sql += " AND metric = ?"
            params.append(metric)
        conn = self._get_conn()
        cur = conn.execute(sql, tuple(params))
        conn.commit()
        return cur.rowcount or 0


def _row_to_dataclass(row: sqlite3.Row) -> LearnedRow:
    return LearnedRow(
        cik=row["cik"],
        metric=row["metric"],
        concept=row["concept"],
        taxonomy=row["taxonomy"],
        source=row["source"],
        verified=bool(row["verified"]),
        verif_method=row["verif_method"],
        value_sample=row["value_sample"],
        learned_at=row["learned_at"],
        hit_count=int(row["hit_count"]),
    )
