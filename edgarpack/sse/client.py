"""Download PDFs from the SSE disclosure platform."""

import hashlib
import time
from pathlib import Path
from urllib.parse import urlparse

_LAST_REQUEST_TIME: float = 0.0
_MIN_INTERVAL: float = 1.0  # 1 req/s conservative rate limit


def _rate_limit() -> None:
    global _LAST_REQUEST_TIME
    now = time.monotonic()
    elapsed = now - _LAST_REQUEST_TIME
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    _LAST_REQUEST_TIME = time.monotonic()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def download_sse_pdf(url: str, cache_dir: Path) -> Path:
    """Download a PDF from SSE and cache locally.

    Returns the local path to the cached PDF.
    """
    url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
    filename = Path(urlparse(url).path).name or f"{url_hash}.pdf"
    cached = cache_dir / "sse" / url_hash / filename

    if cached.exists():
        return cached

    cached.parent.mkdir(parents=True, exist_ok=True)

    try:
        import httpx
    except ImportError as e:
        raise ImportError(
            "httpx is required for SSE downloads. Install with: uv pip install httpx"
        ) from e

    _rate_limit()
    with httpx.Client(timeout=120.0, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()

    cached.write_bytes(resp.content)
    return cached
