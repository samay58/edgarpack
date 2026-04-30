"""Tests for ticker-to-CIK resolution."""

from __future__ import annotations

import json
import unittest
from unittest.mock import AsyncMock, patch

from edgarpack.errors import AmbiguousCompany, UnknownCompany
from edgarpack.sec.tickers import resolve_company, resolve_ticker

# Sample SEC company_tickers.json format.
MOCK_TICKERS = {
    "0": {"cik_str": "320193", "ticker": "AAPL", "title": "Apple Inc"},
    "1": {"cik_str": "1045810", "ticker": "NVDA", "title": "NVIDIA CORP"},
    "2": {"cik_str": "2488", "ticker": "AMD", "title": "ADVANCED MICRO DEVICES INC"},
    "3": {"cik_str": "37996", "ticker": "F", "title": "FORD MOTOR CO"},
    "4": {"cik_str": "1652044", "ticker": "GOOGL", "title": "Alphabet Inc. Class A"},
    "5": {"cik_str": "1652044", "ticker": "GOOG", "title": "Alphabet Inc. Class C"},
    "6": {"cik_str": "1800", "ticker": "ABBV", "title": "AbbVie Inc."},
    "7": {"cik_str": "1067983", "ticker": "BRK-B", "title": "BERKSHIRE HATHAWAY INC"},
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


class TestResolveCompany(unittest.IsolatedAsyncioTestCase):
    """Exercise the name-aware resolve_company() surface."""

    def _cache(self, mock_cache_cls) -> None:
        cache_instance = mock_cache_cls.return_value
        cache_instance.get.return_value = json.dumps(MOCK_TICKERS).encode()

    @patch("edgarpack.sec.tickers.DiskCache")
    @patch("edgarpack.sec.tickers.get_client")
    async def test_exact_name_match_with_suffix_in_title(
        self, _mock_client, mock_cache_cls
    ) -> None:
        self._cache(mock_cache_cls)
        cik, ticker, title = await resolve_company("Apple Inc")
        self.assertEqual(cik, "0000320193")
        self.assertEqual(ticker, "AAPL")
        self.assertEqual(title, "Apple Inc")

    @patch("edgarpack.sec.tickers.DiskCache")
    @patch("edgarpack.sec.tickers.get_client")
    async def test_bare_name_matches_via_suffix_stripping(
        self, _mock_client, mock_cache_cls
    ) -> None:
        """'NVIDIA' should match 'NVIDIA CORP' after suffix stripping."""
        self._cache(mock_cache_cls)
        cik, ticker, title = await resolve_company("NVIDIA")
        self.assertEqual(cik, "0001045810")
        self.assertEqual(ticker, "NVDA")
        self.assertEqual(title, "NVIDIA CORP")

    @patch("edgarpack.sec.tickers.DiskCache")
    @patch("edgarpack.sec.tickers.get_client")
    async def test_name_is_case_and_punctuation_insensitive(
        self, _mock_client, mock_cache_cls
    ) -> None:
        self._cache(mock_cache_cls)
        cik, ticker, _title = await resolve_company("nvidia corp.")
        self.assertEqual(ticker, "NVDA")
        self.assertEqual(cik, "0001045810")

    @patch("edgarpack.sec.tickers.DiskCache")
    @patch("edgarpack.sec.tickers.get_client")
    async def test_lowercase_bare_name_resolves(self, _mock_client, mock_cache_cls) -> None:
        self._cache(mock_cache_cls)
        _cik, ticker, _title = await resolve_company("nvidia")
        self.assertEqual(ticker, "NVDA")

    @patch("edgarpack.sec.tickers.DiskCache")
    @patch("edgarpack.sec.tickers.get_client")
    async def test_short_ticker_shadow_prefers_ticker(self, _mock_client, mock_cache_cls) -> None:
        """'F' must resolve as the Ford ticker, not fuzzy-match a name."""
        self._cache(mock_cache_cls)
        cik, ticker, title = await resolve_company("F")
        self.assertEqual(cik, "0000037996")
        self.assertEqual(ticker, "F")
        self.assertEqual(title, "FORD MOTOR CO")

    @patch("edgarpack.sec.tickers.DiskCache")
    @patch("edgarpack.sec.tickers.get_client")
    async def test_dot_share_class_normalizes_to_sec_dash_ticker(
        self, _mock_client, mock_cache_cls
    ) -> None:
        self._cache(mock_cache_cls)
        cik, ticker, title = await resolve_company("BRK.B")
        self.assertEqual(cik, "0001067983")
        self.assertEqual(ticker, "BRK-B")
        self.assertEqual(title, "BERKSHIRE HATHAWAY INC")

    @patch("edgarpack.sec.tickers.DiskCache")
    @patch("edgarpack.sec.tickers.get_client")
    async def test_ambiguous_share_classes_raises(self, _mock_client, mock_cache_cls) -> None:
        """Both GOOGL (Class A) and GOOG (Class C) normalize to 'alphabet class a/c'
        but with suffix stripping 'alphabet' is not in the name map directly.
        A typed 'Alphabet Inc' without class disambiguator exposes the
        share-class ambiguity."""
        # Add a collision by mocking two issuers that normalize to the same key.
        collision = dict(MOCK_TICKERS)
        collision["100"] = {
            "cik_str": "9999991",
            "ticker": "ALPH",
            "title": "Alphabet Inc",
        }
        collision["101"] = {
            "cik_str": "9999992",
            "ticker": "ALPB",
            "title": "Alphabet Incorporated",
        }
        cache_instance = mock_cache_cls.return_value
        cache_instance.get.return_value = json.dumps(collision).encode()
        with self.assertRaises(AmbiguousCompany) as ctx:
            await resolve_company("Alphabet")
        msg = str(ctx.exception)
        self.assertIn("ALPH", msg)
        self.assertIn("ALPB", msg)

    @patch("edgarpack.sec.tickers.DiskCache")
    @patch("edgarpack.sec.tickers.get_client")
    async def test_unknown_company_name_raises_with_suggestions(
        self, _mock_client, mock_cache_cls
    ) -> None:
        """A typo of a real name surfaces close matches as 'Title (TICKER)'."""
        self._cache(mock_cache_cls)
        with self.assertRaises(UnknownCompany) as ctx:
            await resolve_company("Aple Corporation")
        msg = str(ctx.exception)
        self.assertTrue(msg.lower().startswith("unknown company"))
        self.assertIn("AAPL", msg)
        self.assertIn("Apple Inc", msg)

    @patch("edgarpack.sec.tickers.DiskCache")
    @patch("edgarpack.sec.tickers.get_client")
    async def test_unknown_company_no_near_matches_says_none(
        self, _mock_client, mock_cache_cls
    ) -> None:
        self._cache(mock_cache_cls)
        with self.assertRaises(UnknownCompany) as ctx:
            await resolve_company("Zzzzz Corporation")
        self.assertIn("none", str(ctx.exception).lower())

    @patch("edgarpack.sec.tickers.DiskCache")
    @patch("edgarpack.sec.tickers.get_client")
    async def test_unknown_ticker_shape_uses_ticker_label(
        self, _mock_client, mock_cache_cls
    ) -> None:
        """Ticker-shaped unknown input gets 'Unknown ticker' (not 'company')."""
        self._cache(mock_cache_cls)
        with self.assertRaises(UnknownCompany) as ctx:
            await resolve_company("ZZZZZ")
        self.assertTrue(str(ctx.exception).lower().startswith("unknown ticker"))

    @patch("edgarpack.sec.tickers.DiskCache")
    @patch("edgarpack.sec.tickers.get_client")
    async def test_resolve_ticker_is_backward_compatible(
        self, _mock_client, mock_cache_cls
    ) -> None:
        """resolve_ticker wrapper keeps the (cik, name) tuple shape."""
        self._cache(mock_cache_cls)
        cik, name = await resolve_ticker("NVDA")
        self.assertEqual(cik, "0001045810")
        self.assertEqual(name, "NVIDIA CORP")


if __name__ == "__main__":
    unittest.main()
