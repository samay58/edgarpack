"""SQLite registry of all built packs for sub-ms lookups.

PRAGMA user_version note: this module does NOT use PRAGMA user_version
for migrations; it uses a list-based try/except scheme via _run_migrations.
The learned_concepts table (edgarpack/query/learned_registry.py) owns
PRAGMA user_version for its own migrations. Do not touch user_version
from this module unless you coordinate with learned_registry.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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

_MIGRATIONS = [
    ("indexed_at", "ALTER TABLE packs ADD COLUMN indexed_at TEXT"),
    (
        "harvest_errors",
        """CREATE TABLE IF NOT EXISTS harvest_errors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            accession TEXT,
            form_type TEXT,
            error TEXT NOT NULL,
            error_stage TEXT NOT NULL DEFAULT 'build',
            created_at TEXT NOT NULL
        )""",
    ),
    (
        "idx_harvest_errors_ticker",
        "CREATE INDEX IF NOT EXISTS idx_harvest_errors_ticker ON harvest_errors(ticker)",
    ),
    ("market", "ALTER TABLE packs ADD COLUMN market TEXT"),
    ("stock_code", "ALTER TABLE packs ADD COLUMN stock_code TEXT"),
    (
        "idx_packs_stock_code",
        "CREATE INDEX IF NOT EXISTS idx_packs_stock_code ON packs(stock_code)",
    ),
]


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
    indexed_at: str | None = None
    # China A-share (SSE) packs have no CIK/accession; the natural key is
    # (stock_code, filing_date). SEC rows leave both None.
    market: str | None = None
    stock_code: str | None = None


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
        self._run_migrations(conn)
        conn.commit()

    # NOTE: Uses a list-based migration scheme, not PRAGMA user_version.
    # PRAGMA user_version is claimed by query/learned_registry.py for its
    # migrations. See learned_registry.py's module docstring for details.
    def _run_migrations(self, conn: sqlite3.Connection) -> None:
        for name, sql in _MIGRATIONS:
            try:
                conn.execute(sql)
            except sqlite3.OperationalError as e:
                msg = str(e).lower()
                if "duplicate column" not in msg and "already exists" not in msg:
                    raise

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
        built_at: str | None = None,
        market: str | None = None,
        stock_code: str | None = None,
    ) -> None:
        """Register a built pack in the registry.

        market/stock_code are for China A-share (SSE) packs, which have no
        real SEC cik/accession; SEC rows leave both None.
        """
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO packs
            (accession, cik, ticker, company_name, form_type, filing_date,
             sections_count, tokens_total, pack_dir, built_at, manifest_hash, warnings_json,
             market, stock_code)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                built_at or datetime.now(UTC).isoformat(),
                manifest_hash,
                json.dumps(warnings) if warnings else None,
                market,
                stock_code,
            ),
        )
        conn.commit()

    def register_pack(self, record: PackRecord) -> None:
        """Register a PackRecord directly (convenience wrapper around register).

        Preserves record.built_at (falls back to now() if the record has no
        timestamp). warnings_json is decoded and passed as the warnings list.
        """
        warnings = json.loads(record.warnings_json) if record.warnings_json else None
        self.register(
            accession=record.accession,
            cik=record.cik,
            ticker=record.ticker,
            company_name=record.company_name,
            form_type=record.form_type,
            filing_date=record.filing_date,
            sections_count=record.sections_count,
            tokens_total=record.tokens_total,
            pack_dir=record.pack_dir,
            manifest_hash=record.manifest_hash,
            warnings=warnings,
            built_at=record.built_at,
            market=record.market,
            stock_code=record.stock_code,
        )

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

    def has_sse_filing(self, stock_code: str, filing_date: str) -> bool:
        """Check by the SSE natural key: (stock_code, filing_date).

        SSE packs have no SEC accession, so this is the equivalent of
        has_accession() for the China A-share lane.
        """
        conn = self._get_conn()
        row = conn.execute(
            "SELECT 1 FROM packs WHERE stock_code = ? AND filing_date = ?",
            (stock_code, filing_date),
        ).fetchone()
        return row is not None

    def list_packs(
        self,
        cik: str | None = None,
        ticker: str | None = None,
        form_type: str | None = None,
        limit: int | None = 1000,
    ) -> list[PackRecord]:
        """List packs matching optional filters; limit=None returns everything."""
        conn = self._get_conn()
        conditions: list[str] = []
        params: list[object] = []
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
        query = f"SELECT * FROM packs{where} ORDER BY filing_date DESC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)

        rows = conn.execute(query, params).fetchall()
        return [PackRecord(**dict(r)) for r in rows]

    def list_companies(self) -> list[dict[str, Any]]:
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

    def get_stats(self) -> dict[str, Any]:
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

    def mark_indexed(self, accession: str) -> None:
        """Mark a pack as indexed in the search index."""
        conn = self._get_conn()
        conn.execute(
            "UPDATE packs SET indexed_at = ? WHERE accession = ?",
            (datetime.now(UTC).isoformat(), accession),
        )
        conn.commit()

    def mark_indexed_batch(self, accessions: list[str]) -> None:
        """Mark multiple packs as indexed."""
        conn = self._get_conn()
        now = datetime.now(UTC).isoformat()
        conn.executemany(
            "UPDATE packs SET indexed_at = ? WHERE accession = ?",
            [(now, acc) for acc in accessions],
        )
        conn.commit()

    def unindexed_packs(self) -> list[PackRecord]:
        """Return packs that have not yet been indexed."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM packs WHERE indexed_at IS NULL ORDER BY filing_date DESC"
        ).fetchall()
        return [PackRecord(**dict(r)) for r in rows]

    def log_error(
        self,
        ticker: str,
        error: str,
        accession: str | None = None,
        form_type: str | None = None,
        error_stage: str = "build",
    ) -> None:
        """Log a harvest error for later reporting."""
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO harvest_errors
            (ticker, accession, form_type, error, error_stage, created_at)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (ticker, accession, form_type, error, error_stage, datetime.now(UTC).isoformat()),
        )
        conn.commit()

    def get_errors(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get recent harvest errors."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM harvest_errors ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
