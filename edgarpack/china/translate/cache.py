"""SQLite paragraph-level translation cache.

SHA256 exact-match on normalized Chinese text plus a strategy fingerprint.
Expected 50-60% hit rate after 5+ prospectuses due to heavy CSRC boilerplate.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from .provider import TranslationResult

DEFAULT_CACHE_PATH = Path.home() / ".edgarpack" / "translation_cache.db"
DEFAULT_NAMESPACE = "sse-translate-v10"

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS translation_cache (
    hash TEXT PRIMARY KEY,
    text_zh TEXT NOT NULL,
    text_en TEXT NOT NULL,
    provider TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def _normalize(text: str) -> str:
    """Collapse whitespace and strip markdown formatting for stable hashing."""
    text = re.sub(r"[#*_`~>|]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _hash_text(text: str, namespace: str = DEFAULT_NAMESPACE) -> str:
    payload = f"{namespace}\0{_normalize(text)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def provider_namespace(provider: str, namespace: str = DEFAULT_NAMESPACE) -> str:
    """Scope cached translations to the provider/model that produced them."""
    return f"{namespace}:{provider}"


class TranslationCache:
    """Paragraph-level exact-match translation cache in SQLite."""

    def __init__(
        self,
        db_path: Path | None = None,
        namespace: str = DEFAULT_NAMESPACE,
    ) -> None:
        self._db_path = db_path or DEFAULT_CACHE_PATH
        self._namespace = namespace
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)

    def get(self, text_zh: str) -> TranslationResult | None:
        """Look up a cached translation by normalized Chinese text hash."""
        h = _hash_text(text_zh, self._namespace)
        row = self._conn.execute(
            "SELECT text_zh, text_en, provider FROM translation_cache WHERE hash = ?",
            (h,),
        ).fetchone()
        if row is None:
            return None
        return TranslationResult(text_zh=row[0], text_en=row[1], provider=row[2])

    def put(self, result: TranslationResult) -> None:
        """Store a translation result, keyed by normalized Chinese text hash."""
        h = _hash_text(result.text_zh, self._namespace)
        self._conn.execute(
            "INSERT OR REPLACE INTO translation_cache "
            "(hash, text_zh, text_en, provider, created_at) VALUES (?, ?, ?, ?, ?)",
            (h, result.text_zh, result.text_en, result.provider, datetime.now(UTC).isoformat()),
        )
        self._conn.commit()

    def stats(self) -> dict[str, int]:
        """Return cache statistics."""
        (count,) = self._conn.execute("SELECT COUNT(*) FROM translation_cache").fetchone()
        return {"entries": count}

    def close(self) -> None:
        self._conn.close()
