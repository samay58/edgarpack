"""Tests for disk cache behavior under concurrent writes."""

from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path

from edgarpack.sec.cache import DiskCache


class TestDiskCache(unittest.TestCase):
    def test_put_get_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cache = DiskCache(Path(td))
            url = "https://example.test/value"
            payload = b'{"ok": true}'

            cache.put(url, payload, headers={"Content-Type": "application/json"})
            self.assertEqual(cache.get(url), payload)
            self.assertTrue(cache.exists(url))

    def test_concurrent_put_same_key_keeps_full_payload(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cache = DiskCache(Path(td))
            url = "https://example.test/race"
            payload_a = b"A" * 20000
            payload_b = b"B" * 20000

            errors: list[Exception] = []

            def _writer(payload: bytes) -> None:
                try:
                    for _ in range(200):
                        cache.put(url, payload)
                except Exception as exc:  # pragma: no cover - diagnostic path
                    errors.append(exc)

            t1 = threading.Thread(target=_writer, args=(payload_a,))
            t2 = threading.Thread(target=_writer, args=(payload_b,))
            t1.start()
            t2.start()
            t1.join()
            t2.join()

            self.assertFalse(errors)
            cached = cache.get(url)
            self.assertIn(cached, {payload_a, payload_b})

    def test_clear_reports_presence(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cache = DiskCache(Path(td))
            url = "https://example.test/clear"
            self.assertFalse(cache.clear(url))
            cache.put(url, b"value")
            self.assertTrue(cache.clear(url))
            self.assertIsNone(cache.get(url))


if __name__ == "__main__":
    unittest.main()

    def test_ttl_expires_entry_with_missing_meta(self) -> None:
        # An entry that cannot prove its age must be treated as expired,
        # not fresh forever (crash between .bin and .meta writes).
        with tempfile.TemporaryDirectory() as td:
            cache = DiskCache(Path(td))
            url = "https://example.test/ttl"
            cache.put(url, b"payload")
            meta_path = cache._meta_path(url)
            meta_path.unlink()

            self.assertIsNone(cache.get(url, max_age_seconds=3600))
            # Without a TTL the raw bytes are still served.
            self.assertEqual(cache.get(url), b"payload")

    def test_ttl_expires_entry_with_corrupt_meta(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cache = DiskCache(Path(td))
            url = "https://example.test/ttl-corrupt"
            cache.put(url, b"payload")
            cache._meta_path(url).write_text("{not json", encoding="utf-8")

            self.assertIsNone(cache.get(url, max_age_seconds=3600))
