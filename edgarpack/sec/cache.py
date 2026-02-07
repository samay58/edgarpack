"""Disk cache for SEC API responses."""

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class DiskCache:
    """Simple disk cache keyed by URL hash.

    Structure: {cache_dir}/{key[:2]}/{key[2:4]}/{key}.bin
    Metadata stored alongside as {key}.meta.json
    """

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            # Best-effort fallback (helps in sandboxed environments).
            fallback = Path(os.getenv("EDGARPACK_CACHE_DIR_FALLBACK", "/tmp/edgarpack-cache"))
            self.cache_dir = fallback
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _key_path(self, url: str) -> Path:
        """Get the cache file path for a URL."""
        key = hashlib.sha256(url.encode()).hexdigest()
        return self.cache_dir / key[:2] / key[2:4] / f"{key}.bin"

    def _meta_path(self, url: str) -> Path:
        """Get the metadata file path for a URL."""
        key = hashlib.sha256(url.encode()).hexdigest()
        return self.cache_dir / key[:2] / key[2:4] / f"{key}.meta.json"

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
                meta = json.loads(meta_path.read_text())
                cached_at = datetime.fromisoformat(meta.get("cached_at", ""))
                age = (datetime.now(UTC) - cached_at).total_seconds()
                if age > max_age_seconds:
                    return None
            except (json.JSONDecodeError, ValueError):
                pass

        return path.read_bytes()

    def put(self, url: str, content: bytes, headers: dict[str, Any] | None = None) -> None:
        """Store content in cache.

        Args:
            url: The URL being cached
            content: Raw bytes to store
            headers: Optional HTTP headers to store in metadata
        """
        path = self._key_path(url)
        meta_path = self._meta_path(url)

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        except OSError:
            return

        meta = {
            "url": url,
            "cached_at": datetime.now(UTC).isoformat(),
            "size": len(content),
            "headers": headers or {},
        }
        try:
            meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True))
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

        removed = False
        if path.exists():
            path.unlink()
            removed = True
        if meta_path.exists():
            meta_path.unlink()

        return removed
