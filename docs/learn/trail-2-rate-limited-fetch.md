# Trail 2: A single SEC fetch

Time: about 8 minutes.

Every SEC request eventually goes through `SECClient`. The client does three jobs:

- require a real user agent;
- pace request starts so EdgarPack does not burst at the SEC;
- retry the failures that can reasonably recover.

Caching sits next to the call sites, not inside `SECClient`. That separation is easy to miss.

## Try it

Run one normal SEC-backed query:

```bash
edgarpack query NVDA revenue --period lfy
```

Run it again:

```bash
edgarpack query NVDA revenue --period lfy
```

The second run may be faster if the cache was cold before the first run. The important thing to notice is boring: the user-facing answer should be the same. Cache hits should change how much work EdgarPack does, not what the number means.

Now force a fresh fetch:

```bash
edgarpack query NVDA revenue --period lfy --force
```

That bypasses the cached SEC lookup for the companyfacts path. Use it when you are debugging fetch behavior, not as a normal habit.

If the command complains about `EDGARPACK_USER_AGENT`, set it before trying SEC calls:

```bash
export EDGARPACK_USER_AGENT="Your Name your.email@example.com"
```

## The caller checks the cache

Companyfacts is a good example. The call site builds the SEC URL, opens a `DiskCache`, checks for cached bytes unless `force=True`, then calls the client only on a miss.

That means different endpoints can use different freshness rules. Companyfacts can have a normal TTL. Filing files can be cached indefinitely because a published accession does not change. A caller that needs fresh bytes can skip the cache check and call the client directly.

## The client is per event loop

`get_client()` returns one client for the current asyncio event loop. The map is a weak dictionary keyed by event loop, so loops can be cleaned up without leaking clients.

That design avoids two bad outcomes:

- sharing one client across event loops, which can break locks;
- creating a new client for every request, which defeats the rate limiter.

The constructor refuses to run without `EDGARPACK_USER_AGENT`. The SEC requires callers to identify themselves. EdgarPack fails early instead of sending anonymous requests and leaving the user to interpret a 403.

## Request pacing is no-burst

The rate limiter reserves request slots under a lock, then sleeps outside the lock:

```text
take the lock
  -> compare now to the next available slot
  -> reserve the slot after that
release the lock
sleep if this caller arrived early
```

The first request can go immediately. The next request waits for its slot. Waiting callers do not block each other from reserving later slots.

EdgarPack defaults below the SEC ceiling. If you raise the rate, you may hit a 429 and spend more time in cooldown than you saved.

## The HTTP call is stdlib

The client uses `urllib.request`, wrapped in `asyncio.to_thread()`. It sends `User-Agent` and `Accept-Encoding: gzip`, reads bytes and headers, and returns them to the async retry loop.

There is no third-party HTTP dependency in this path. The cost is some plain plumbing. The benefit is that the rate limit and retry behavior live in EdgarPack code where you can inspect them.

If the server says the response is gzip, EdgarPack tries to decompress it. If decompression fails, it returns the raw bytes. That is a narrow tolerance for bad headers, not a general "swallow errors" policy.

## Retry rules

Network errors retry with exponential backoff, capped at ten seconds.

Status 429 and 5xx responses retry too, with `Retry-After` honored when present. If the response is the SEC traffic-limit page, EdgarPack raises a specific rate-limit error with a cooldown hint.

Other 4xx responses fail immediately. Waiting will not fix a missing accession or forbidden URL.

## Cache writes are atomic

When a call site caches a response, `DiskCache.put()` writes both the payload and metadata through temporary files and `os.replace()`. It also uses a per-key lock, so two threads writing the same URL serialize while unrelated URLs can proceed.

A reader should never see a half-written cache file. It either sees the old content, the new content, or no cache hit.

## In the code

- `edgarpack/sec/xbrl.py:29` shows the companyfacts call site checking `DiskCache` before using the client.
- `edgarpack/sec/client.py:241` is `get_client()`.
- `edgarpack/sec/client.py:82` requires `EDGARPACK_USER_AGENT` in `SECClient.__init__()`.
- `edgarpack/sec/client.py:56` defines the no-burst `RateLimiter`.
- `edgarpack/sec/client.py:122` handles retry and rate-limit behavior.
- `edgarpack/sec/client.py:171` performs the stdlib HTTP call.
- `edgarpack/sec/client.py:200` handles gzip.
- `edgarpack/sec/client.py:217` parses `Retry-After`.
- `edgarpack/sec/cache.py:87` reads cached bytes; `edgarpack/sec/cache.py:118` writes cached bytes and metadata.
- `edgarpack/sec/cache.py:62` and `edgarpack/sec/cache.py:75` are the atomic write helpers.
