"""Pre-IPO filers with no companyfacts must not re-hit SEC for a fresh 404
on every query. `fetch_company_facts` caches the "no XBRL" result with a
1-day TTL, but the no-silent-imputation boundary is non-negotiable:

  * a cached negative behaves exactly like a fresh 404: {} diagnostic-free.
  * network/HTTP failures still raise XBRLFetchError and are NEVER cached
    as a negative (a transient outage must not get remembered as "no
    XBRL forever").
  * a cache-layer error falls through to a live fetch rather than raising.
"""

from __future__ import annotations

import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

from edgarpack.sec.cache import DiskCache
from edgarpack.sec.client import HTTPError
from edgarpack.sec.xbrl import XBRLFetchError, fetch_company_facts


def _http_404(url: str) -> HTTPError:
    return HTTPError(url=url, status_code=404, headers={}, content=b"")


def _http_500(url: str) -> HTTPError:
    return HTTPError(url=url, status_code=500, headers={}, content=b"")


@contextmanager
def _isolated_cache_dir():
    with tempfile.TemporaryDirectory() as td:
        with patch("edgarpack.sec.xbrl.CACHE_DIR", Path(td)):
            yield


class NegativeCacheTest(unittest.IsolatedAsyncioTestCase):
    async def test_second_query_within_ttl_does_not_hit_network(self) -> None:
        client = AsyncMock()
        client.fetch_json.side_effect = _http_404("http://sec.test/companyfacts/CIK0002004711.json")

        with (
            _isolated_cache_dir(),
            patch("edgarpack.sec.xbrl.get_client", new=AsyncMock(return_value=client)),
        ):
            first = await fetch_company_facts("0002004711", force=True)
            self.assertEqual(first, {})
            self.assertEqual(client.fetch_json.await_count, 1)

            second = await fetch_company_facts("0002004711")
            self.assertEqual(second, {})
            # Still 1: the second call served the cached negative, no network hit.
            self.assertEqual(client.fetch_json.await_count, 1)

    async def test_fetch_error_is_not_cached(self) -> None:
        client = AsyncMock()
        client.fetch_json.side_effect = _http_500("http://sec.test/companyfacts/CIK0002004999.json")

        with (
            _isolated_cache_dir(),
            patch("edgarpack.sec.xbrl.get_client", new=AsyncMock(return_value=client)),
        ):
            with self.assertRaises(XBRLFetchError):
                await fetch_company_facts("0002004999", force=True)

            # A second call still hits the network: nothing was cached.
            with self.assertRaises(XBRLFetchError):
                await fetch_company_facts("0002004999")
            self.assertEqual(client.fetch_json.await_count, 2)

    async def test_post_ttl_refetches(self) -> None:
        client = AsyncMock()
        client.fetch_json.side_effect = _http_404("http://sec.test/companyfacts/CIK0002005000.json")

        with (
            _isolated_cache_dir(),
            patch("edgarpack.sec.xbrl.get_client", new=AsyncMock(return_value=client)),
        ):
            await fetch_company_facts("0002005000", force=True)
            self.assertEqual(client.fetch_json.await_count, 1)

            # Simulate TTL expiry: a real DiskCache.get with max_age_seconds=0
            # always misses (age > 0 is true for anything already written).
            with patch("edgarpack.sec.xbrl._NEGATIVE_CACHE_TTL_SECONDS", 0):
                await fetch_company_facts("0002005000")
            self.assertEqual(client.fetch_json.await_count, 2)

    async def test_cache_layer_error_falls_through_to_live_fetch(self) -> None:
        client = AsyncMock()
        client.fetch_json.return_value = ({"facts": {}}, {})

        real_get = DiskCache.get

        def flaky_negative_get(self, url, max_age_seconds=None):
            # Only the negative-cache lookup misbehaves; the pre-existing
            # positive-cache lookup is untouched by this fix.
            if url.endswith("#no-xbrl"):
                raise RuntimeError("simulated cache read fault")
            return real_get(self, url, max_age_seconds=max_age_seconds)

        with (
            _isolated_cache_dir(),
            patch("edgarpack.sec.xbrl.get_client", new=AsyncMock(return_value=client)),
            patch("edgarpack.sec.xbrl.DiskCache.get", new=flaky_negative_get),
        ):
            result = await fetch_company_facts("0002005001")
        self.assertEqual(result, {"facts": {}})
        client.fetch_json.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
