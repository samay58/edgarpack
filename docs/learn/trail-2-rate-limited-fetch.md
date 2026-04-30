# Trail 2: What happens during a single SEC HTTP call

**Time**: ~8 minutes
**Prereq**: none, but [Trail 0](trail-0-full-loop.md) introduces where this fits in the big picture.
**Covers**: `sec/client.py`, `sec/cache.py`, `config.py`

Every path through EdgarPack that touches the SEC goes through one function: `SECClient.fetch`. The client enforces the rate limit, retries on throttles, caches responses atomically, and hands bytes back to the caller. This trail walks a single fetch from call to return so you understand the seam every higher-level module depends on.

---

## 1. The entry point

A caller writes:

```python
client = await get_client()
content, headers = await client.fetch(url)
```

`get_client` at `edgarpack/sec/client.py:207` is a per-event-loop singleton. It looks up the current `asyncio` event loop and returns the `SECClient` registered against it, or creates one if there isn't one yet. The mapping is a `WeakKeyDictionary[EventLoop, SECClient]`, so when a loop gets garbage-collected its client goes with it.

Why per-loop? Because event loops can span threads in async code that mixes `asyncio.run()` calls with `asyncio.to_thread()`. A singleton keyed by loop avoids the two most common bugs: sharing a client across loops (breaks internal locks) and creating a new client per request (defeats the rate limiter).

The constructor checks that `EDGARPACK_USER_AGENT` is set and raises `ValueError` immediately if not. SEC requires the header on every request; skipping this check would produce inscrutable 403s from the SEC later.

**Code**: `edgarpack/sec/client.py:207` (`get_client`), `edgarpack/sec/client.py:71-87` (`SECClient.__init__`)

---

## 2. The cache check happens outside the client

`client.fetch` itself does **not** check the cache. Caching is a concern for each call site, not the client. The pattern you see across the codebase looks like:

```python
cache = DiskCache(CACHE_DIR)
if not force:
    cached = cache.get(url, max_age_seconds=86400)
    if cached is not None:
        return json.loads(cached)

data, headers = await client.fetch_json(url)
cache.put(url, json.dumps(data).encode(), headers)
```

See `edgarpack/sec/xbrl.py:24-43` for a concrete example. Every fetch path that cares about caching does this dance itself. Some paths (like `fetch_file` in `sec/archives.py`) wrap it in a helper; others call directly.

Keeping the cache out of the client means two things:

1. Different endpoints can have different TTLs. Ticker maps cache for 24 hours, companyfacts for 24 hours, filing index for much longer, filing files indefinitely (they're immutable once SEC publishes them).
2. A caller that needs to bypass cache can just skip the check and call the client directly. No flag to plumb through.

**Code**: `edgarpack/sec/xbrl.py:24-43` (example call site)

---

## 3. Inside `DiskCache.get`

`DiskCache.get` at `edgarpack/sec/cache.py:81` looks up the cached bytes for a URL:

1. Compute the SHA256 of the URL bytes -> hex string = cache key.
2. Map the key to a path: `{cache_dir}/{key[:2]}/{key[2:4]}/{key}.bin`. The two-level prefix split keeps any single directory from holding too many files.
3. If the file doesn't exist, return `None`.
4. If `max_age_seconds` was passed, read the sibling `{key}.meta.json` file to get `cached_at`, compute age against `datetime.now(UTC)`, return `None` if too old.
5. Otherwise return the raw bytes.

Cache misses are silent: any error reading the file or parsing the metadata also returns `None`. The caller treats "not in cache" and "cache is corrupted" the same way. Go fetch.

**Code**: `edgarpack/sec/cache.py:81` (`get`)

---

## 4. The rate limiter

If the cache was missed, control flows to `client.fetch` -> `_fetch_with_retry` at `edgarpack/sec/client.py:114`. The first thing it does every attempt is call `await self._rate_limiter.acquire()`.

`RateLimiter` at `edgarpack/sec/client.py:42` is a no-burst pacer:

```python
async def acquire(self) -> None:
    async with self._lock:
        now = time.monotonic()
        wait_time = max(0.0, self._next_available_at - now)
        scheduled_at = max(now, self._next_available_at)
        self._next_available_at = scheduled_at + self._interval

    if wait_time > 0:
        await asyncio.sleep(wait_time)
```

Walk through it at `rate=5`:

- The first caller can proceed immediately.
- Each acquire reserves the next request slot.
- The next caller waits until that slot, so startup bursts do not happen.
- Sleeping happens outside the lock, so waiting callers do not block each other from reserving future slots.

10 requests per second is the SEC's published ceiling. EdgarPack defaults to 5 requests per second to leave headroom for other activity sharing the same outbound IP. If you bump the rate you risk getting a 429, which triggers the cooldown path and probably slows you down anyway.

**Code**: `edgarpack/sec/client.py:42-62` (`RateLimiter`)

---

## 5. The actual HTTP call

After acquiring a token, `_fetch_with_retry` calls `_fetch_sync` inside `asyncio.to_thread`:

```python
content, headers, status = await asyncio.to_thread(self._fetch_sync, url)
```

`_fetch_sync` at `edgarpack/sec/client.py:145` uses `urllib.request` from the stdlib. It constructs a GET request with two headers:

- `User-Agent`: the value from `EDGARPACK_USER_AGENT`
- `Accept-Encoding: gzip`

Reads the response body, extracts status code and headers, returns `(content, headers, status)`. If the request raised `HTTPError`, it extracts whatever it can from the error object (status code, headers, body) and returns those instead of raising. `URLError` propagates up (it's a retryable network condition).

The gzip handling happens at `_maybe_gunzip` (line 174): if `Content-Encoding: gzip` is set, decompress, otherwise pass through. A decompression failure is silently ignored and the raw content is returned. Unusual for EdgarPack (usually errors are explicit), but it makes the client robust against servers that advertise gzip and lie.

Why stdlib `urllib` instead of `httpx` or `requests`? The README says it: "stdlib HTTP keeps deployment predictable." No pinned transitive deps, no async-context pitfalls, no surprise version bumps. The rate-limit behavior is fully visible in EdgarPack's code, not buried in a third-party client's config. The cost is a slightly more verbose implementation that doesn't get async for free, hence the `asyncio.to_thread` wrapper.

**Code**: `edgarpack/sec/client.py:145-171` (`_fetch_sync`), `edgarpack/sec/client.py:174-180` (`_maybe_gunzip`)

---

## 6. Retry logic

Back in `_fetch_with_retry`, the loop sorts failures into three categories and handles each differently.

Network errors (`TimeoutError`, `OSError`, `URLError`) retry up to `max_retries` times with exponential backoff. Backoff starts at 1s and doubles each failure, capped at 10s. On the final attempt, the function re-raises.

SEC traffic-limit pages (status 429 with the threshold HTML) raise `SECRateLimitError` immediately with a 10-minute cooldown hint, because continuing requests can extend the timeout. Other 429/5xx responses get the `Retry-After` header treatment. `_parse_retry_after` handles both formats (a plain seconds integer and an HTTP-date) and clamps the result to `[0, 60]` seconds so a misbehaving server can't stall the client forever. The loop waits the larger of the current backoff or `retry_after`, then retries.

Other 4xx responses raise `HTTPError` immediately with the url, status, headers, and content. No retry. A 404 or 403 isn't going to get better by waiting.

On a successful response (2xx or 3xx that got followed), the function returns `(content, headers)` and control goes back to the caller.

**Code**: `edgarpack/sec/client.py:114-143` (`_fetch_with_retry`), `edgarpack/sec/client.py:183-199` (`_parse_retry_after`)

---

## 7. Store the response atomically

If the call site that invoked `client.fetch` was caching, the next thing it does is:

```python
cache.put(url, content, headers)
```

`DiskCache.put` at `edgarpack/sec/cache.py:112` does four things:

1. Resolve the cache key path.
2. Take a per-key `Lock` from `_key_locks` (class-level dict of locks, guarded by `_key_locks_guard`). Two threads writing the same URL serialize on this lock; different URLs don't contend.
3. Write the content via `_atomic_write_bytes`: write to a tempfile named `.{key}.bin.{pid}.{tid}.tmp`, then `os.replace(tmp, path)`. `os.replace` is atomic on both POSIX and Windows.
4. Write the metadata the same way, to a sibling file `{key}.meta.json` with `url`, `cached_at`, `size`, `headers`.

The atomic write pattern matters because concurrent processes might try to cache the same URL. Without atomicity, a reader could see a half-written file. With it, a reader either sees the old content or the new content, never a partial write.

**Code**: `edgarpack/sec/cache.py:55-79` (`_atomic_write_bytes`, `_atomic_write_text`), `edgarpack/sec/cache.py:112-140` (`put`)

---

## 8. Return

The call site gets `(content, headers)`, returns whatever it was building (parsed JSON, HTML bytes, whatever), and the chain unwinds. The cache is now warmed for the next call with the same URL.

**Code**: none. The return path is just Python going back up the stack.

---

## Recap

The SEC fetch seam is four short files. `client.py` holds the token-bucket rate limiter and the retry loop around stdlib urllib. `cache.py` holds a SHA256-keyed on-disk cache with atomic writes and per-key locks. `config.py` holds the constants (`RATE_LIMIT`, timeouts, cache directory). Every higher-level module calls `get_client()`, optionally consults a `DiskCache`, and otherwise doesn't know or care that any of this exists. The three design choices that shape the whole seam: use stdlib to keep deployment predictable, cache atomically so concurrent processes don't corrupt each other, and release the rate limiter lock before sleeping so the limit is a ceiling rather than a chokepoint. If you're going to modify anything in this area, read these three files in full. They're small, and each line is carrying weight.
