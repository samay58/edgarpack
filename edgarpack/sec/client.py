"""HTTP client with SEC-compliant rate limiting and retry logic.

The upstream SEC endpoints are simple HTTP/HTTPS and do not require a heavyweight
HTTP client dependency. This implementation uses the standard library so that
EdgarPack remains runnable in constrained environments.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from ..config import CONNECT_TIMEOUT, MAX_RETRIES, RATE_LIMIT, READ_TIMEOUT, USER_AGENT


@dataclass(frozen=True)
class HTTPError(Exception):
    """Raised for non-2xx HTTP responses."""

    url: str
    status_code: int
    headers: dict[str, str]
    content: bytes

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"HTTP {self.status_code} for {self.url}"


class RateLimiter:
    """Token bucket rate limiter for SEC compliance (default: 10 req/s)."""

    def __init__(self, rate: float = RATE_LIMIT):
        if rate <= 0:
            raise ValueError("rate must be > 0")
        self.rate = float(rate)
        self.tokens = float(rate)
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait until a token is available."""
        while True:
            async with self._lock:
                now = time.monotonic()
                elapsed = now - self.last_update
                self.tokens = min(self.rate, self.tokens + elapsed * self.rate)
                self.last_update = now

                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return

                wait_time = (1.0 - self.tokens) / self.rate

            await asyncio.sleep(wait_time)


class SECClient:
    """Async HTTP client for SEC EDGAR with rate limiting and retries."""

    def __init__(
        self,
        user_agent: str = USER_AGENT,
        rate_limit: float = RATE_LIMIT,
        max_retries: int = MAX_RETRIES,
    ):
        self.user_agent = user_agent
        self._rate_limiter = RateLimiter(rate_limit)
        self._max_retries = max(1, int(max_retries))

    async def fetch(self, url: str) -> tuple[bytes, dict[str, Any]]:
        """Fetch a URL respecting rate limits and retrying 429/5xx."""
        content, headers = await self._fetch_with_retry(url)
        return content, headers

    async def fetch_json(self, url: str) -> tuple[dict[str, Any], dict[str, Any]]:
        """Fetch and parse JSON from URL."""
        content, headers = await self.fetch(url)
        try:
            return json.loads(content.decode("utf-8")), headers
        except UnicodeDecodeError:
            return json.loads(content.decode("latin-1")), headers

    async def close(self) -> None:
        """Compatibility no-op (stdlib client has no persistent resources)."""
        return

    async def __aenter__(self) -> "SECClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def _fetch_with_retry(self, url: str) -> tuple[bytes, dict[str, Any]]:
        backoff = 1.0

        for attempt in range(1, self._max_retries + 1):
            await self._rate_limiter.acquire()
            try:
                content, headers, status = await asyncio.to_thread(self._fetch_sync, url)
            except Exception:
                if attempt >= self._max_retries:
                    raise
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2.0, 10.0)
                continue

            # Retry on rate limit or server errors.
            if status == 429 or status >= 500:
                if attempt >= self._max_retries:
                    raise HTTPError(url=url, status_code=status, headers=headers, content=content)
                retry_after = _parse_retry_after(headers)
                await asyncio.sleep(retry_after if retry_after is not None else backoff)
                backoff = min(backoff * 2.0, 10.0)
                continue

            if status >= 400:
                raise HTTPError(url=url, status_code=status, headers=headers, content=content)

            return content, headers

        raise RuntimeError("unreachable")

    def _fetch_sync(self, url: str) -> tuple[bytes, dict[str, str], int]:
        # urllib only has a single timeout, so we pick the larger of connect/read.
        timeout = max(float(CONNECT_TIMEOUT), float(READ_TIMEOUT))
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept-Encoding": "gzip",
            },
            method="GET",
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                status = int(getattr(resp, "status", 200))
                headers = {k: v for k, v in resp.headers.items()}
                content = resp.read() or b""
        except urllib.error.HTTPError as e:
            status = int(getattr(e, "code", 0) or 0)
            headers = {k: v for k, v in (e.headers.items() if e.headers else [])}
            content = e.read() or b""
            return _maybe_gunzip(content, headers), headers, status
        except urllib.error.URLError as e:
            # Treat as retryable network error.
            raise e

        return _maybe_gunzip(content, headers), headers, status


def _maybe_gunzip(content: bytes, headers: dict[str, str]) -> bytes:
    if (headers.get("Content-Encoding") or "").lower() != "gzip":
        return content
    try:
        return gzip.decompress(content)
    except Exception:
        return content


def _parse_retry_after(headers: dict[str, str]) -> float | None:
    value = headers.get("Retry-After")
    if not value:
        return None
    try:
        seconds = float(value.strip())
    except ValueError:
        return None
    # SEC wants us well under 10 req/s; clamp to sane bounds.
    return max(0.0, min(seconds, 60.0))


# Global client instance for reuse
_global_client: SECClient | None = None


async def get_client() -> SECClient:
    """Get the global SEC client instance."""
    global _global_client
    if _global_client is None:
        _global_client = SECClient()
    return _global_client

