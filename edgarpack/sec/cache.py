"""Disk cache for SEC API responses."""

import hashlib
import json
import os

try:
    from datetime import UTC, datetime
except ImportError:  # Python 3.9 fallback
    from datetime import datetime

    UTC = UTC
from pathlib import Path
from threading import Lock, get_ident
from typing import Any


class DiskCache:
    """Simple disk cache keyed by URL hash.

    Structure: {cache_dir}/{key[:2]}/{key[2:4]}/{key}.bin
    Metadata stored alongside as {key}.meta.json
    """

    _key_locks: dict[str, Lock] = {}
    _key_locks_guard = Lock()

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise RuntimeError(
                f"Cannot create cache directory {cache_dir}: {e}. "
                "Set EDGARPACK_CACHE_DIR to a writable path."
            ) from e

    @staticmethod
    def _cache_key(url: str) -> str:
        return hashlib.sha256(url.encode()).hexdigest()

    @classmethod
    def _lock_for_key(cls, key: str) -> Lock:
        with cls._key_locks_guard:
            lock = cls._key_locks.get(key)
            if lock is None:
                lock = Lock()
                cls._key_locks[key] = lock
            return lock

    def _key_path(self, url: str) -> Path:
        """Get the cache file path for a URL."""
        key = self._cache_key(url)
        return self.cache_dir / key[:2] / key[2:4] / f"{key}.bin"

    def _meta_path(self, url: str) -> Path:
        """Get the metadata file path for a URL."""
        key = self._cache_key(url)
        return self.cache_dir / key[:2] / key[2:4] / f"{key}.meta.json"

    @staticmethod
    def _atomic_write_bytes(path: Path, content: bytes) -> None:
        tmp = path.with_name(f".{path.name}.{os.getpid()}.{get_ident()}.tmp")
        try:
            tmp.write_bytes(content)
            os.replace(tmp, path)
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass

    @staticmethod
    def _atomic_write_text(path: Path, content: str) -> None:
        tmp = path.with_name(f".{path.name}.{os.getpid()}.{get_ident()}.tmp")
        try:
            tmp.write_text(content, encoding="utf-8")
            os.replace(tmp, path)
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass

    def get(self, url: str, max_age_seconds: int | None = None) -> bytes | None:
        """Get cached content for a URL.

        Args:
            url: The URL to look up
            max_age_seconds: If set, only return if cache is younger than this

        Returns:
            Cached bytes or None if not found/expired
        """
        path = self._key_path(url)
        meta_path = self._meta_path(url)

        if not path.exists():
            return None

        if max_age_seconds is not None and meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                cached_at = datetime.fromisoformat(meta.get("cached_at", ""))
                age = (datetime.now(UTC) - cached_at).total_seconds()
                if age > max_age_seconds:
                    return None
            except (json.JSONDecodeError, OSError, ValueError):
                pass

        try:
            return path.read_bytes()
        except OSError:
            return None

    def put(self, url: str, content: bytes, headers: dict[str, Any] | None = None) -> None:
        """Store content in cache.

        Args:
            url: The URL being cached
            content: Raw bytes to store
            headers: Optional HTTP headers to store in metadata
        """
        path = self._key_path(url)
        meta_path = self._meta_path(url)
        lock = self._lock_for_key(self._cache_key(url))

        with lock:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                self._atomic_write_bytes(path, content)
            except OSError:
                return

            meta = {
                "url": url,
                "cached_at": datetime.now(UTC).isoformat(),
                "size": len(content),
                "headers": headers or {},
            }
            try:
                self._atomic_write_text(meta_path, json.dumps(meta, indent=2, sort_keys=True))
            except OSError:
                return

    def exists(self, url: str) -> bool:
        """Check if URL is in cache."""
        return self._key_path(url).exists()

    def clear(self, url: str) -> bool:
        """Remove a URL from cache.

        Returns:
            True if removed, False if not found
        """
        path = self._key_path(url)
        meta_path = self._meta_path(url)
        lock = self._lock_for_key(self._cache_key(url))

        removed = path.exists() or meta_path.exists()
        with lock:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            try:
                meta_path.unlink(missing_ok=True)
            except OSError:
                pass

        return removed
