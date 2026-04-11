# Reference: sec/cache.py

`edgarpack/sec/cache.py` (167 lines)

SHA256-keyed disk cache with atomic writes. Encodes the determinism guarantee: concurrent processes can safely read and write the same URL without seeing partial data. Used by every SEC fetch path. See [Trail 2](../trail-2-rate-limited-fetch.md) for how a fetch uses the cache.

---

## Data layout on disk

```
{cache_dir}/{key[:2]}/{key[2:4]}/{key}.bin           # raw response bytes
{cache_dir}/{key[:2]}/{key[2:4]}/{key}.meta.json     # metadata: url, cached_at, size, headers
```

The key is `hashlib.sha256(url.encode()).hexdigest()`. The two-level prefix split keeps any single directory from holding too many files, which starts to matter once you've harvested a few thousand filings.

`cache_dir` comes from `config.CACHE_DIR`, which defaults to `~/.edgarpack/cache` and can be overridden via `EDGARPACK_CACHE_DIR`.

---

## DiskCache

```python
class DiskCache:
    def __init__(self, cache_dir: Path): ...
    def get(self, url: str, max_age_seconds: int | None = None) -> bytes | None: ...
    def put(self, url: str, content: bytes, headers: dict[str, Any] | None = None) -> None: ...
    def exists(self, url: str) -> bool: ...
    def clear(self, url: str) -> bool: ...
```

**`__init__(cache_dir)`**. Creates the cache directory (`parents=True`, `exist_ok=True`). Raises `RuntimeError` if the directory can't be created, with a clear message telling the user to set `EDGARPACK_CACHE_DIR` to a writable path. Happens at the boundary between "config problem" and "normal operation".

**`get(url, max_age_seconds=None)`**. Reads cached bytes for the URL. Returns `None` if the file is missing, unreadable, or (when `max_age_seconds` is set) older than the limit. Silent on errors: any failure to read the metadata or the file is treated as a cache miss. Callers treat "not in cache" and "corrupted cache" the same way: go fetch.

**`put(url, content, headers=None)`**. Writes the content and metadata atomically. Acquires a per-key lock, writes the content via `_atomic_write_bytes`, then writes the metadata via `_atomic_write_text`. If either write fails (OSError), the function returns silently. A failed cache write should never break the calling code.

**`exists(url)`**. Boolean check. Returns `True` if the content file exists on disk. Does not check staleness or metadata; callers that need freshness use `get(url, max_age_seconds=...)`.

**`clear(url)`**. Removes the content file and the metadata file. Returns `True` if anything was actually removed. Used by the `edgarpack cache --clear` CLI command and by tests.

---

## Atomic writes

### `_atomic_write_bytes(path, content)`

```python
tmp = path.with_name(f".{path.name}.{os.getpid()}.{get_ident()}.tmp")
try:
    tmp.write_bytes(content)
    os.replace(tmp, path)
finally:
    if tmp.exists():
        try:
            tmp.unlink()
        except OSError:
            pass
```

`edgarpack/sec/cache.py:55`. Writes to a tempfile in the same directory, then `os.replace(tmp, path)` which is atomic on both POSIX (rename(2)) and Windows (MoveFileEx). The tempfile name includes `pid` and thread id to prevent collisions between concurrent writers of the same URL.

The `finally` block cleans up the tempfile if the replace failed for any reason. Cleanup errors are silently ignored.

### `_atomic_write_text(path, content)`

`edgarpack/sec/cache.py:68`. Same as `_atomic_write_bytes` but uses `write_text` with UTF-8 encoding. Used for the JSON metadata file.

---

## Per-key locking

```python
_key_locks: dict[str, Lock] = {}
_key_locks_guard = Lock()
```

Class-level. Maps cache key -> `threading.Lock`. A second-level lock (`_key_locks_guard`) protects the lookup/creation of the per-key lock.

`_lock_for_key(key)` at `edgarpack/sec/cache.py:36` lazily creates a lock for a key on first access. Multiple threads writing the same URL serialize on the per-key lock. Different URLs never contend.

**Why class-level instead of instance-level**: different `DiskCache` instances pointing at the same directory should still serialize on the same key. An instance-level lock dict would allow two instances to race on the same file.

---

## Invariants

- `cache_dir` must be writable at construction time. Enforced in `__init__` at line 25.
- Writes are atomic: a reader either sees the old content or the new content, never a partial write. Enforced by `os.replace` in `_atomic_write_bytes` / `_atomic_write_text`.
- Per-key lock covers both the content write and the metadata write in `put`. Metadata cannot be out of sync with content for the duration of a write. Enforced by the `with lock:` block at line 124.
- `get` returns `None` on any failure to read. A corrupted cache is a cache miss, never an exception. Enforced by the broad `except` clauses at line 104 and 109.

---

## What this module does not do

- **It does not evict entries.** There is no LRU, no size cap, no TTL enforcement. `max_age_seconds` is checked on read, not on write; stale entries stay on disk until the user runs `edgarpack cache --clear` or deletes the directory by hand.
- **It does not handle non-URL keys.** Everything is keyed by `hashlib.sha256(url.encode())`. Callers that want a custom key build a synthetic URL-like string.
- **It does not know about HTTP semantics.** The `headers` argument to `put` is stored as opaque metadata; the cache does not inspect `Cache-Control`, `ETag`, or `Last-Modified`. TTL decisions are the caller's responsibility via the `max_age_seconds` argument to `get`.
- **It does not fsync.** On systems where `os.replace` doesn't guarantee durability without an `fsync` of the directory, a power loss between write and fsync could lose the cache entry. Acceptable for a cache; not acceptable if this were a database.
