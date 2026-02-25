"""SQLite registry of all built packs for sub-ms lookups."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from ..config import CACHE_DIR

DEFAULT_REGISTRY_PATH = CACHE_DIR.parent / "registry.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS packs (
    accession TEXT PRIMARY KEY,
    cik TEXT NOT NULL,
    ticker TEXT,
    company_name TEXT NOT NULL,
    form_type TEXT NOT NULL,
    filing_date TEXT NOT NULL,
    sections_count INTEGER NOT NULL,
    tokens_total INTEGER NOT NULL,
    pack_dir TEXT NOT NULL,
    built_at TEXT NOT NULL,
    manifest_hash TEXT,
    warnings_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_packs_cik ON packs(cik);
CREATE INDEX IF NOT EXISTS idx_packs_ticker ON packs(ticker);
CREATE INDEX IF NOT EXISTS idx_packs_form_type ON packs(form_type);
CREATE INDEX IF NOT EXISTS idx_packs_filing_date ON packs(filing_date);
"""


class PackRecord(BaseModel):
    """A registered pack in the registry."""

    accession: str
    cik: str
    ticker: str | None = None
    company_name: str
    form_type: str
    filing_date: str
    sections_count: int
    tokens_total: int
    pack_dir: str
    built_at: str
    manifest_hash: str | None = None
    warnings_json: str | None = None


class PackRegistry:
    """SQLite-backed registry of built filing packs."""

    def __init__(self, db_path: Path | None = None):
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
        conn.commit()

    def register(
        self,
        accession: str,
        cik: str,
        ticker: str | None,
        company_name: str,
        form_type: str,
        filing_date: str,
        sections_count: int,
        tokens_total: int,
        pack_dir: str,
        manifest_hash: str | None = None,
        warnings: list[str] | None = None,
    ) -> None:
        """Register a built pack in the registry."""
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO packs
            (accession, cik, ticker, company_name, form_type, filing_date,
             sections_count, tokens_total, pack_dir, built_at, manifest_hash, warnings_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                accession,
                cik,
                ticker,
                company_name,
                form_type,
                filing_date,
                sections_count,
                tokens_total,
                pack_dir,
                datetime.now(UTC).isoformat(),
                manifest_hash,
                json.dumps(warnings) if warnings else None,
            ),
        )
        conn.commit()

    def lookup(self, accession: str) -> PackRecord | None:
        """Look up a pack by accession number."""
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM packs WHERE accession = ?", (accession,)).fetchone()
        if row is None:
            return None
        return PackRecord(**dict(row))

    def has_accession(self, accession: str) -> bool:
        """Check if an accession is already registered."""
        conn = self._get_conn()
        row = conn.execute("SELECT 1 FROM packs WHERE accession = ?", (accession,)).fetchone()
        return row is not None

    def list_packs(
        self,
        cik: str | None = None,
        ticker: str | None = None,
        form_type: str | None = None,
        limit: int = 1000,
    ) -> list[PackRecord]:
        """List packs matching optional filters."""
        conn = self._get_conn()
        conditions: list[str] = []
        params: list[str] = []
        if cik:
            conditions.append("cik = ?")
            params.append(cik)
        if ticker:
            conditions.append("UPPER(ticker) = UPPER(?)")
            params.append(ticker)
        if form_type:
            conditions.append("form_type = ?")
            params.append(form_type)

        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        query = f"SELECT * FROM packs{where} ORDER BY filing_date DESC LIMIT ?"
        params.append(str(limit))

        rows = conn.execute(query, params).fetchall()
        return [PackRecord(**dict(r)) for r in rows]

    def list_companies(self) -> list[dict]:
        """List all unique companies with their filing counts."""
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT cik, ticker, company_name,
                      COUNT(*) as filing_count,
                      MAX(filing_date) as latest_filing,
                      SUM(tokens_total) as total_tokens
               FROM packs
               GROUP BY cik
               ORDER BY company_name"""
        ).fetchall()
        return [dict(r) for r in rows]

    def get_stats(self) -> dict:
        """Get registry statistics."""
        conn = self._get_conn()
        row = conn.execute(
            """SELECT COUNT(*) as total_packs,
                      COUNT(DISTINCT cik) as companies,
                      SUM(tokens_total) as total_tokens,
                      SUM(sections_count) as total_sections,
                      MIN(filing_date) as earliest_filing,
                      MAX(filing_date) as latest_filing
               FROM packs"""
        ).fetchone()
        return dict(row) if row else {}

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
