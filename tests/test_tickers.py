"""Tests for ticker-to-CIK resolution."""

from __future__ import annotations

import json
import unittest
from unittest.mock import AsyncMock, patch

from edgarpack.sec.tickers import resolve_ticker

# Sample SEC company_tickers.json format
MOCK_TICKERS = {
    "0": {"cik_str": "320193", "ticker": "AAPL", "title": "Apple Inc"},
    "1": {"cik_str": "1045810", "ticker": "NVDA", "title": "NVIDIA CORP"},
    "2": {"cik_str": "2488", "ticker": "AMD", "title": "ADVANCED MICRO DEVICES INC"},
}


def _mock_fetch_json(data: dict):
    """Create an AsyncMock for SECClient.fetch_json."""

    async def _fetch(url: str):
        return data, {}

    return _fetch


class TestResolveTicker(unittest.IsolatedAsyncioTestCase):
    @patch("edgarpack.sec.tickers.DiskCache")
    @patch("edgarpack.sec.tickers.get_client")
    async def test_resolve_known_ticker(self, mock_get_client, mock_cache_cls) -> None:
        cache_instance = mock_cache_cls.return_value
        cache_instance.get.return_value = json.dumps(MOCK_TICKERS).encode()

        cik, name = await resolve_ticker("NVDA")
        self.assertEqual(cik, "0001045810")
        self.assertEqual(name, "NVIDIA CORP")

    @patch("edgarpack.sec.tickers.DiskCache")
    @patch("edgarpack.sec.tickers.get_client")
    async def test_resolve_case_insensitive(self, mock_get_client, mock_cache_cls) -> None:
        cache_instance = mock_cache_cls.return_value
        cache_instance.get.return_value = json.dumps(MOCK_TICKERS).encode()

        cik, name = await resolve_ticker("aapl")
        self.assertEqual(cik, "0000320193")
        self.assertEqual(name, "Apple Inc")

    @patch("edgarpack.sec.tickers.DiskCache")
    @patch("edgarpack.sec.tickers.get_client")
    async def test_cik_passthrough(self, mock_get_client, mock_cache_cls) -> None:
        cache_instance = mock_cache_cls.return_value
        cache_instance.get.return_value = json.dumps(MOCK_TICKERS).encode()

        cik, name = await resolve_ticker("1045810")
        self.assertEqual(cik, "0001045810")
        self.assertEqual(name, "NVIDIA CORP")

    @patch("edgarpack.sec.tickers.DiskCache")
    @patch("edgarpack.sec.tickers.get_client")
    async def test_cik_passthrough_unknown(self, mock_get_client, mock_cache_cls) -> None:
        cache_instance = mock_cache_cls.return_value
        cache_instance.get.return_value = json.dumps(MOCK_TICKERS).encode()

        cik, name = await resolve_ticker("9999999")
        self.assertEqual(cik, "0009999999")
        self.assertIn("CIK", name)

    @patch("edgarpack.sec.tickers.DiskCache")
    @patch("edgarpack.sec.tickers.get_client")
    async def test_unknown_ticker_raises(self, mock_get_client, mock_cache_cls) -> None:
        cache_instance = mock_cache_cls.return_value
        cache_instance.get.return_value = json.dumps(MOCK_TICKERS).encode()

        with self.assertRaises(ValueError):
            await resolve_ticker("ZZZZZ")

    @patch("edgarpack.sec.tickers.DiskCache")
    @patch("edgarpack.sec.tickers.get_client")
    async def test_fetches_from_network_on_cache_miss(
        self, mock_get_client, mock_cache_cls
    ) -> None:
        cache_instance = mock_cache_cls.return_value
        cache_instance.get.return_value = None

        client = AsyncMock()
        client.fetch_json = AsyncMock(return_value=(MOCK_TICKERS, {}))
        mock_get_client.return_value = client

        cik, name = await resolve_ticker("AMD")
        self.assertEqual(cik, "0000002488")
        self.assertEqual(name, "ADVANCED MICRO DEVICES INC")
        cache_instance.put.assert_called_once()


if __name__ == "__main__":
    unittest.main()
