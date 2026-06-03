# Reference: sec/client.py

`edgarpack/sec/client.py` (215 lines)

The SEC HTTP path. Every network call in EdgarPack goes through a `SECClient` instance. The module defines a rate limiter, an error type, the client class, a gzip helper, a Retry-After parser, and a per-event-loop singleton getter. See [Trail 2](../trail-2-rate-limited-fetch.md) for a walkthrough of how a single fetch flows through all of it.

---

## Exceptions

### HTTPError

```python
@dataclass(frozen=True)
class HTTPError(Exception):
    url: str
    status_code: int
    headers: dict[str, str]
    content: bytes
```

Raised for non-2xx HTTP responses that the retry loop decided not to retry (4xx other than 429, or a 5xx/429 that exhausted retries). Carries the full response so callers can inspect the body. `str(HTTPError)` returns `"HTTP {status} for {url}"`.

---

## Rate limiter

### RateLimiter

```python
class RateLimiter:
    def __init__(self, rate: float = RATE_LIMIT): ...
    async def acquire(self) -> None: ...
```

No-burst request pacer with `rate` request starts per second. Uses `time.monotonic()` and an `asyncio.Lock` to reserve request slots in order.

**Load-bearing invariants:**

- The first request can proceed immediately, but the second request must wait for the next slot. There is no startup burst.
- The lock is held only while reserving the next slot. Sleeping happens after releasing the lock, so waiting callers don't serialize on the sleep.
- `rate <= 0` raises `ValueError` at construction time. Negative or zero rate would mean infinite wait or division-by-zero in the wait calculation.

The default rate comes from `config.RATE_LIMIT` (5 req/s, below SEC's published ceiling).

---

## The client

### SECClient

```python
class SECClient:
    def __init__(self, user_agent=USER_AGENT, rate_limit=RATE_LIMIT, max_retries=MAX_RETRIES): ...
    async def fetch(self, url: str) -> tuple[bytes, dict[str, Any]]: ...
    async def fetch_json(self, url: str) -> tuple[dict[str, Any], dict[str, Any]]: ...
    async def close(self) -> None: ...
    async def __aenter__(self) -> SECClient: ...
    async def __aexit__(self, *args: Any) -> None: ...
```

Async HTTP client. Validates the user agent at construction, owns a `RateLimiter`, wraps `urllib.request` in `asyncio.to_thread` for async compatibility.

**`fetch(url)`**. Returns `(content_bytes, headers_dict)`. Delegates to `_fetch_with_retry`.

**`fetch_json(url)`**. Wraps `fetch`, decodes UTF-8 (or Latin-1 on fallback), parses as JSON, returns `(parsed, headers)`.

**`close()`**. No-op. Kept for API compatibility with past implementations that held persistent resources. The stdlib client is stateless across calls.

**`__aenter__` / `__aexit__`**. Makes `SECClient` usable as an async context manager. Doesn't do much (close is a no-op) but keeps callers polymorphic with code that does need cleanup.

---

## Private internals (worth knowing about)

### `_fetch_with_retry(url)`

`edgarpack/sec/client.py:114`. The retry loop. Runs up to `max_retries` attempts. Each iteration:

1. Acquire a rate limiter request slot.
2. Call `_fetch_sync` inside `asyncio.to_thread`.
3. On network error (`TimeoutError`, `OSError`, `URLError`): retry with exponential backoff starting at 1s, capped at 10s.
4. On SEC traffic-limit 429 pages: raise `SECRateLimitError` with cooldown guidance.
5. On other 429 or 5xx responses: read `Retry-After` header via `_parse_retry_after`, wait the larger of the current backoff or that value, then retry.
6. On 4xx (non-429): raise `HTTPError` immediately.
7. On 2xx: return `(content, headers)`.

Raises `RuntimeError("unreachable")` if the loop exits normally, which it never should.

### `_fetch_sync(url)`

`edgarpack/sec/client.py:145`. The actual HTTP call. Builds a `urllib.request.Request` with two headers: `User-Agent` (from `EDGARPACK_USER_AGENT`) and `Accept-Encoding: gzip`. Uses a single `timeout = max(CONNECT_TIMEOUT, READ_TIMEOUT)` because urllib doesn't separate the two. Returns `(content_bytes, headers_dict, status_int)`.

Catches `urllib.error.HTTPError` and extracts status/headers/body manually. Without this catch, a 4xx would raise before the retry loop could inspect it. Lets `URLError` propagate (it's retryable).

### `_maybe_gunzip(content, headers)`

`edgarpack/sec/client.py:174`. If `Content-Encoding: gzip` is set, decompresses the content. Any exception during decompression is swallowed and raw content is returned. Unusual for EdgarPack (usually errors are explicit), but makes the client robust against servers that advertise gzip and lie.

### `_parse_retry_after(headers)`

`edgarpack/sec/client.py:183`. Parses `Retry-After` in either format: plain integer seconds or HTTP-date. Returns the number of seconds to wait, clamped to `[0, 60]` so a misbehaving server can't stall the client indefinitely.

---

## The per-loop singleton

### get_client()

```python
async def get_client() -> SECClient: ...
```

`edgarpack/sec/client.py:207`. Returns the `SECClient` for the current event loop, creating one on first access. Storage is a module-level `WeakKeyDictionary[EventLoop, SECClient]` guarded by a `threading.Lock`.

**Why per-loop instead of a module singleton**: event loops can span threads in async code that mixes `asyncio.run()` calls with `asyncio.to_thread()`. A client's internal `asyncio.Lock` is loop-bound and breaks if used from a different loop. Keying by loop guarantees each loop has its own lock and its own rate-limit budget.

**Why a WeakKeyDictionary**: when a loop is garbage-collected, its client goes with it. No cleanup required.

---

## Invariants

- A client can only be created if `EDGARPACK_USER_AGENT` is set. Enforced in `__init__` at line 80. SEC requires this header.
- The rate limiter is held during `fetch` but released before any retry sleep. Enforced in `_fetch_with_retry` at line 118.
- The retry loop always exits via `return`, `raise`, or (unreachable) the final `RuntimeError`. Enforced by the structure of the loop at line 117.
- `_parse_retry_after` clamps to `[0, 60]`. Enforced at line 199 to bound worst-case wait time.

---

## What this module does not do

- **It does not cache responses.** Caching is the caller's concern; see `sec/cache.py` (referenced in [`ref-cache.md`](ref-cache.md)) and the various call sites in `sec/xbrl.py`, `sec/submissions.py`, and `sec/tickers.py`.
- **It does not follow redirects explicitly.** `urllib.request.urlopen` handles them by default. If a request lands somewhere unexpected, the `url` in the `HTTPError` will reflect the final resolved URL, not what was originally passed.
- **It does not manage auth or cookies.** SEC endpoints are open; no session management is required.
- **It does not know about specific endpoints.** Callers build their own URLs from `config.SEC_DATA_BASE` and `config.SEC_ARCHIVES_BASE`.
