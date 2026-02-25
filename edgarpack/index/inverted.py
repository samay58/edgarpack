"""SQLite FTS5 inverted index for cross-corpus search."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from pydantic import BaseModel

from ..config import CACHE_DIR
from .topic_extract import extract_topics

DEFAULT_INDEX_PATH = CACHE_DIR.parent / "search_index.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,
    section_id TEXT NOT NULL,
    accession TEXT NOT NULL,
    cik TEXT NOT NULL,
    ticker TEXT,
    company_name TEXT,
    form_type TEXT NOT NULL,
    filing_date TEXT NOT NULL,
    text TEXT NOT NULL,
    topics_json TEXT
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text,
    content='chunks',
    content_rowid='rowid',
    tokenize='porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, text) VALUES (new.rowid, new.text);
END;

CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES('delete', old.rowid, old.text);
END;

CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES('delete', old.rowid, old.text);
    INSERT INTO chunks_fts(rowid, text) VALUES (new.rowid, new.text);
END;

CREATE INDEX IF NOT EXISTS idx_chunks_accession ON chunks(accession);
CREATE INDEX IF NOT EXISTS idx_chunks_cik ON chunks(cik);
CREATE INDEX IF NOT EXISTS idx_chunks_ticker ON chunks(ticker);
CREATE INDEX IF NOT EXISTS idx_chunks_section_id ON chunks(section_id);
CREATE INDEX IF NOT EXISTS idx_chunks_filing_date ON chunks(filing_date);
"""


class IndexedChunk(BaseModel):
    """A chunk stored in the search index."""

    chunk_id: str
    section_id: str
    accession: str
    cik: str
    ticker: str | None = None
    company_name: str | None = None
    form_type: str
    filing_date: str
    text: str
    topics: list[str] = []


class SearchHit(BaseModel):
    """A search result from the index."""

    chunk_id: str
    section_id: str
    accession: str
    cik: str
    ticker: str | None = None
    company_name: str | None = None
    form_type: str
    filing_date: str
    snippet: str
    topics: list[str] = []
    rank: float = 0.0


class SearchIndex:
    """SQLite FTS5 search index over filing chunks."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or DEFAULT_INDEX_PATH
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

    def index_chunk(self, chunk: IndexedChunk) -> None:
        """Add a single chunk to the index."""
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO chunks
            (chunk_id, section_id, accession, cik, ticker, company_name,
             form_type, filing_date, text, topics_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                chunk.chunk_id,
                chunk.section_id,
                chunk.accession,
                chunk.cik,
                chunk.ticker,
                chunk.company_name,
                chunk.form_type,
                chunk.filing_date,
                chunk.text,
                json.dumps(chunk.topics),
            ),
        )
        conn.commit()

    def index_chunks_batch(self, chunks: list[IndexedChunk]) -> int:
        """Bulk-insert chunks into the index."""
        conn = self._get_conn()
        rows = [
            (
                c.chunk_id,
                c.section_id,
                c.accession,
                c.cik,
                c.ticker,
                c.company_name,
                c.form_type,
                c.filing_date,
                c.text,
                json.dumps(c.topics),
            )
            for c in chunks
        ]
        conn.executemany(
            """INSERT OR REPLACE INTO chunks
            (chunk_id, section_id, accession, cik, ticker, company_name,
             form_type, filing_date, text, topics_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        conn.commit()
        return len(rows)

    def search(
        self,
        query: str,
        topic: str | None = None,
        ticker: str | None = None,
        form_type: str | None = None,
        limit: int = 20,
    ) -> list[SearchHit]:
        """Full-text search across the index with optional filters.

        Args:
            query: Search query (FTS5 syntax supported)
            topic: Optional topic tag filter
            ticker: Optional ticker filter
            form_type: Optional form type filter
            limit: Maximum results

        Returns:
            Ranked list of SearchHit objects
        """
        conn = self._get_conn()

        # Build the query using FTS5 ranking
        sql = """
            SELECT c.chunk_id, c.section_id, c.accession, c.cik, c.ticker,
                   c.company_name, c.form_type, c.filing_date,
                   snippet(chunks_fts, 0, '>>>', '<<<', '...', 64) as snippet,
                   c.topics_json,
                   rank
            FROM chunks_fts
            JOIN chunks c ON chunks_fts.rowid = c.rowid
            WHERE chunks_fts MATCH ?
        """
        params: list = [query]

        if topic:
            sql += " AND c.topics_json LIKE ?"
            params.append(f'%"{topic}"%')
        if ticker:
            sql += " AND UPPER(c.ticker) = UPPER(?)"
            params.append(ticker)
        if form_type:
            sql += " AND c.form_type = ?"
            params.append(form_type)

        sql += " ORDER BY rank LIMIT ?"
        params.append(limit)

        rows = conn.execute(sql, params).fetchall()
        hits: list[SearchHit] = []
        for row in rows:
            d = dict(row)
            topics_raw = d.pop("topics_json", None)
            topics = json.loads(topics_raw) if topics_raw else []
            hits.append(SearchHit(**d, topics=topics))

        return hits

    def get_topic_stats(self) -> dict[str, int]:
        """Get counts of chunks per topic."""
        conn = self._get_conn()
        rows = conn.execute("SELECT topics_json FROM chunks").fetchall()
        counts: dict[str, int] = {}
        for row in rows:
            topics = json.loads(row["topics_json"]) if row["topics_json"] else []
            for t in topics:
                counts[t] = counts.get(t, 0) + 1
        return dict(sorted(counts.items(), key=lambda x: -x[1]))

    def count(self) -> int:
        """Total number of indexed chunks."""
        conn = self._get_conn()
        row = conn.execute("SELECT COUNT(*) as cnt FROM chunks").fetchone()
        return row["cnt"] if row else 0

    def index_pack(
        self,
        pack_dir: Path,
        ticker: str | None = None,
    ) -> int:
        """Index all chunks from a pack directory.

        Reads chunks.ndjson if available, otherwise generates chunks from sections.

        Args:
            pack_dir: Path to the pack directory
            ticker: Optional ticker (will try to infer from registry)

        Returns:
            Number of chunks indexed
        """
        manifest_path = pack_dir / "manifest.json"
        if not manifest_path.exists():
            return 0

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        filing = manifest.get("filing", {})

        chunks_path = pack_dir / "optional" / "chunks.ndjson"
        indexed: list[IndexedChunk] = []

        if chunks_path.exists():
            for line in chunks_path.read_text(encoding="utf-8").strip().split("\n"):
                if not line.strip():
                    continue
                chunk_data = json.loads(line)
                text = chunk_data.get("text", "")
                topics = extract_topics(text)
                indexed.append(
                    IndexedChunk(
                        chunk_id=chunk_data["chunk_id"],
                        section_id=chunk_data["section_id"],
                        accession=filing.get("accession", ""),
                        cik=filing.get("cik", ""),
                        ticker=ticker,
                        company_name=filing.get("company_name"),
                        form_type=filing.get("form_type", ""),
                        filing_date=filing.get("filing_date", ""),
                        text=text,
                        topics=topics,
                    )
                )
        else:
            # Fall back to indexing full sections
            sections_dir = pack_dir / "sections"
            if sections_dir.exists():
                for section in manifest.get("sections", []):
                    section_path = pack_dir / section["path"]
                    if not section_path.exists():
                        continue
                    text = section_path.read_text(encoding="utf-8")
                    topics = extract_topics(text)
                    indexed.append(
                        IndexedChunk(
                            chunk_id=f"{filing.get('accession', '')}:{section['id']}",
                            section_id=section["id"],
                            accession=filing.get("accession", ""),
                            cik=filing.get("cik", ""),
                            ticker=ticker,
                            company_name=filing.get("company_name"),
                            form_type=filing.get("form_type", ""),
                            filing_date=filing.get("filing_date", ""),
                            text=text,
                            topics=topics,
                        )
                    )

        if indexed:
            return self.index_chunks_batch(indexed)
        return 0

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
