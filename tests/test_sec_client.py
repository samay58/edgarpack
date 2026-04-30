"""Tests for SEC HTTP client retry and singleton behavior."""

from __future__ import annotations

import asyncio
import unittest
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from unittest.mock import AsyncMock, patch

from edgarpack.config import _env_float, _env_int
from edgarpack.sec.client import SECClient, _parse_retry_after, get_client


class TestConfigEnvParsing(unittest.TestCase):
    def test_env_float_accepts_positive_values(self) -> None:
        with patch.dict("os.environ", {"EDGARPACK_SEC_RATE_LIMIT": "2.5"}):
            self.assertEqual(_env_float("EDGARPACK_SEC_RATE_LIMIT", 10.0), 2.5)

    def test_env_float_ignores_invalid_values(self) -> None:
        with patch.dict("os.environ", {"EDGARPACK_SEC_RATE_LIMIT": "-1"}):
            self.assertEqual(_env_float("EDGARPACK_SEC_RATE_LIMIT", 10.0), 10.0)
        with patch.dict("os.environ", {"EDGARPACK_SEC_RATE_LIMIT": "nope"}):
            self.assertEqual(_env_float("EDGARPACK_SEC_RATE_LIMIT", 10.0), 10.0)

    def test_env_int_accepts_positive_values(self) -> None:
        with patch.dict("os.environ", {"EDGARPACK_SEC_MAX_RETRIES": "6"}):
            self.assertEqual(_env_int("EDGARPACK_SEC_MAX_RETRIES", 3), 6)

    def test_env_int_ignores_invalid_values(self) -> None:
        with patch.dict("os.environ", {"EDGARPACK_SEC_MAX_RETRIES": "0"}):
            self.assertEqual(_env_int("EDGARPACK_SEC_MAX_RETRIES", 3), 3)
        with patch.dict("os.environ", {"EDGARPACK_SEC_MAX_RETRIES": "many"}):
            self.assertEqual(_env_int("EDGARPACK_SEC_MAX_RETRIES", 3), 3)


class TestRetryAfterParsing(unittest.TestCase):
    def test_parse_retry_after_seconds_clamps_to_sixty(self) -> None:
        self.assertEqual(_parse_retry_after({"Retry-After": "120"}), 60.0)

    def test_parse_retry_after_negative_clamps_to_zero(self) -> None:
        self.assertEqual(_parse_retry_after({"Retry-After": "-5"}), 0.0)

    def test_parse_retry_after_header_is_case_insensitive(self) -> None:
        self.assertEqual(_parse_retry_after({"retry-after": "7"}), 7.0)

    def test_parse_retry_after_http_date(self) -> None:
        retry_at = datetime.now(UTC) + timedelta(seconds=120)
        parsed = _parse_retry_after({"Retry-After": format_datetime(retry_at)})
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertGreaterEqual(parsed, 59.0)
        self.assertLessEqual(parsed, 60.0)


class TestRetryBackoff(unittest.IsolatedAsyncioTestCase):
    async def test_retry_uses_max_of_backoff_and_retry_after(self) -> None:
        client = SECClient(rate_limit=1000, max_retries=2)
        responses = [
            (b"", {"Retry-After": "0.2"}, 429),
            (b"ok", {}, 200),
        ]

        def _fake_fetch_sync(_url: str):
            return responses.pop(0)

        client._fetch_sync = _fake_fetch_sync  # type: ignore[assignment]
        client._rate_limiter.acquire = AsyncMock()  # type: ignore[method-assign]

        with patch("edgarpack.sec.client.asyncio.sleep", new=AsyncMock()) as sleep_mock:
            content, _headers = await client.fetch("https://example.test/data")

        self.assertEqual(content, b"ok")
        sleep_mock.assert_awaited_once()
        self.assertEqual(sleep_mock.await_args.args[0], 1.0)


class TestClientSingleton(unittest.IsolatedAsyncioTestCase):
    async def test_get_client_returns_same_instance_per_event_loop(self) -> None:
        import edgarpack.sec.client as client_module

        client_module._clients_by_loop.clear()
        gathered = await asyncio.gather(*(get_client() for _ in range(10)))
        self.assertEqual(len({id(c) for c in gathered}), 1)


if __name__ == "__main__":
    unittest.main()
