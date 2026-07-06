"""HTTP client with SEC-compliant rate limiting and retry logic.

The upstream SEC endpoints are simple HTTP/HTTPS and do not require a heavyweight
HTTP client dependency. This implementation uses the standard library so that
EdgarPack remains runnable in constrained environments.
"""

from __future__ import annotations

import asyncio
import gzip
import http.client
import json
import logging
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from threading import Lock
from typing import Any
from weakref import WeakKeyDictionary

from ..config import CONNECT_TIMEOUT, MAX_RETRIES, RATE_LIMIT, READ_TIMEOUT, USER_AGENT

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HTTPError(Exception):
    """Raised for non-2xx HTTP responses."""

    url: str
    status_code: int
    headers: dict[str, str]
    content: bytes

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"HTTP {self.status_code} for {self.url}"


@dataclass(frozen=True)
class SECRateLimitError(HTTPError):
    """Raised when SEC.gov has put the caller in a fair-access cooldown."""

    cooldown_seconds: int = 600

    def __str__(self) -> str:
        minutes = max(1, round(self.cooldown_seconds / 60))
        return (
            f"SEC rate limit reached for {self.url}. Wait {minutes} minutes "
            "before retrying; continuing requests can extend the cooldown."
        )


class RateLimiter:
    """Pace SEC request starts without an initial burst."""

    def __init__(self, rate: float = RATE_LIMIT):
        if rate <= 0:
            raise ValueError("rate must be > 0")
        self.rate = float(rate)
        self._interval = 1.0 / self.rate
        self._next_available_at = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait until the next request slot is available."""
        async with self._lock:
            now = time.monotonic()
            wait_time = max(0.0, self._next_available_at - now)
            scheduled_at = max(now, self._next_available_at)
            self._next_available_at = scheduled_at + self._interval

        if wait_time > 0:
            await asyncio.sleep(wait_time)


class SECClient:
    """Async HTTP client for SEC EDGAR with rate limiting and retries."""

    def __init__(
        self,
        user_agent: str | None = None,
        rate_limit: float = RATE_LIMIT,
        max_retries: int = MAX_RETRIES,
    ):
        resolved_user_agent = (
            user_agent if user_agent is not None else os.getenv("EDGARPACK_USER_AGENT", USER_AGENT)
        )
        if not resolved_user_agent or not resolved_user_agent.strip():
            raise ValueError(
                "EDGARPACK_USER_AGENT is not set. SEC requires you to identify "
                "yourself on every request.\n"
                'Example: export EDGARPACK_USER_AGENT="Your Name your.email@example.com"'
            )
        self.user_agent = resolved_user_agent
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
            logger.debug("fetch_json UTF-8 decode failed for %s, falling back to latin-1", url)
            return json.loads(content.decode("latin-1")), headers

    async def close(self) -> None:
        """Compatibility no-op (stdlib client has no persistent resources)."""
        return

    async def __aenter__(self) -> SECClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def _fetch_with_retry(self, url: str) -> tuple[bytes, dict[str, Any]]:
        backoff = 1.0

        for attempt in range(1, self._max_retries + 1):
            await self._rate_limiter.acquire()
            try:
                content, headers, status = await asyncio.to_thread(self._fetch_sync, url)
            except (TimeoutError, OSError, urllib.error.URLError, http.client.HTTPException):
                if attempt >= self._max_retries:
                    raise
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2.0, 10.0)
                continue

            # Retry on rate limit or server errors.
            if status == 429 or status >= 500:
                retry_after = _parse_retry_after(headers)
                if status == 429 and _is_sec_traffic_limit_page(content):
                    cooldown_seconds = int(retry_after) if retry_after is not None else 600
                    raise SECRateLimitError(
                        url=url,
                        status_code=status,
                        headers=headers,
                        content=content,
                        cooldown_seconds=cooldown_seconds,
                    )
                if attempt >= self._max_retries:
                    if status == 429:
                        cooldown_seconds = int(retry_after) if retry_after is not None else 600
                        raise SECRateLimitError(
                            url=url,
                            status_code=status,
                            headers=headers,
                            content=content,
                            cooldown_seconds=cooldown_seconds,
                        )
                    raise HTTPError(url=url, status_code=status, headers=headers, content=content)
                delay = max(backoff, retry_after if retry_after is not None else 0.0)
                await asyncio.sleep(delay)
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
        return _maybe_gunzip(content, headers), headers, status


def _maybe_gunzip(content: bytes, headers: dict[str, str]) -> bytes:
    if (headers.get("Content-Encoding") or "").lower() != "gzip":
        return content
    try:
        return gzip.decompress(content)
    except Exception as e:
        # Passing compressed bytes through would cache garbage as content;
        # surface it as a retryable network-class failure instead.
        raise OSError(f"gzip decompression failed: {e}") from e


def _is_sec_traffic_limit_page(content: bytes) -> bool:
    """Return True for SEC's fair-access timeout HTML page."""
    head = content[:8192].lower()
    return b"request rate threshold exceeded" in head or (
        b"exceeded" in head and b"sec" in head and b"traffic limit" in head
    )


def _parse_retry_after(headers: dict[str, str]) -> float | None:
    """Parse Retry-After in seconds or HTTP-date and clamp to [0, 60]."""
    value = next((v for k, v in headers.items() if k.lower() == "retry-after"), None)
    if not value:
        return None
    try:
        seconds = float(value.strip())
    except ValueError:
        try:
            dt = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        seconds = (dt - datetime.now(UTC)).total_seconds()
    # SEC wants us well under 10 req/s; clamp to sane bounds.
    return max(0.0, min(seconds, 60.0))


# Per-event-loop clients for safe reuse in async code that may span threads.
_clients_by_loop: WeakKeyDictionary[asyncio.AbstractEventLoop, SECClient] = WeakKeyDictionary()
_clients_lock = Lock()


async def get_client() -> SECClient:
    """Get the SEC client singleton for the current event loop."""
    loop = asyncio.get_running_loop()
    with _clients_lock:
        client = _clients_by_loop.get(loop)
        if client is None:
            client = SECClient()
            _clients_by_loop[loop] = client
        return client
