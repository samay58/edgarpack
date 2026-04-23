"""Download and optionally describe images embedded in registration-class filings.

Only activated for S-1 / S-1-A / F-1 / F-1-A / 424B* / FWP packs. Periodic
filings (10-K / 10-Q / 8-K) drop images unchanged.

VLM description is opt-in via the --describe-images CLI flag and requires the
optional `anthropic` dependency (install via `pip install edgarpack[vlm]`).
Descriptions are cached on disk keyed by sha256(image_bytes) so re-harvests
never re-bill.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
from pathlib import Path

from ..sec.client import get_client

# SEC HTML is messy: src attributes may be double-quoted, single-quoted, or
# occasionally unquoted. Match all three to avoid silently dropping images.
_IMG_SRC_RE = re.compile(
    r"""<img\s+[^>]*?src\s*=\s*(?:"([^"]+)"|'([^']+)'|([^\s>"']+))""",
    re.IGNORECASE,
)

_VLM_PROMPT = (
    "Extract in under 75 words: what this figure shows "
    "(chart type, product shot, org chart, etc.); any numeric claims stated "
    "on the image (market size, growth rates, customer counts, performance "
    "benchmarks); and the one-line thesis the figure supports. If the image "
    "is decorative, say so."
)


def extract_image_urls(html: str) -> list[str]:
    """Return the raw src values of every <img> tag in document order."""
    if not html:
        return []
    # findall returns a tuple of groups when the pattern has multiple groups.
    # Exactly one of the three quote-style groups is non-empty per match.
    return [next(filter(None, groups)) for groups in _IMG_SRC_RE.findall(html)]


def _local_filename(src: str) -> str:
    """Pick a safe local filename from a URL or relative path."""
    parsed = urllib.parse.urlparse(src)
    name = Path(parsed.path).name or Path(src).name or "image"
    safe = re.sub(r"[^A-Za-z0-9._\-]", "_", name)
    return safe or "image"


async def _fetch_bytes(url: str) -> bytes:
    client = await get_client()
    body, _headers = await client.fetch(url)
    return body


async def download_assets(
    base_url: str,
    html: str,
    out_dir: Path,
) -> dict[str, str]:
    """Download every <img> referenced in `html` into <out_dir>/assets/.

    Returns a mapping from the original src string to a repo-relative local
    path of the form "assets/<filename>" suitable for embedding in markdown.
    """
    out_dir = Path(out_dir)
    assets_dir = out_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    mapping: dict[str, str] = {}
    for src in extract_image_urls(html):
        abs_url = urllib.parse.urljoin(base_url, src)
        try:
            blob = await _fetch_bytes(abs_url)
        except Exception:
            continue
        filename = _local_filename(src)
        target = assets_dir / filename
        if target.exists() and target.read_bytes() != blob:
            h = hashlib.sha256(blob).hexdigest()[:8]
            target = assets_dir / f"{target.stem}-{h}{target.suffix}"
        target.write_bytes(blob)
        mapping[src] = f"assets/{target.name}"
    return mapping


async def _vlm_describe(image_path: Path) -> str:
    """Call Anthropic vision on the image. Isolated so tests can monkeypatch."""
    try:
        import base64

        from anthropic import AsyncAnthropic
    except ImportError as exc:
        raise RuntimeError(
            "Image description requires the `anthropic` package. "
            "Install with `pip install edgarpack[vlm]`."
        ) from exc

    client = AsyncAnthropic()
    blob = Path(image_path).read_bytes()
    b64 = base64.standard_b64encode(blob).decode("ascii")
    suffix = Path(image_path).suffix.lower().lstrip(".")
    media_type = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "gif": "image/gif",
        "webp": "image/webp",
    }.get(suffix, "image/jpeg")

    msg = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": b64},
                    },
                    {"type": "text", "text": _VLM_PROMPT},
                ],
            }
        ],
    )
    return "".join(
        block.text for block in msg.content if getattr(block, "type", "") == "text"
    ).strip()


async def describe_asset(image_path: Path, cache_path: Path | None = None) -> str:
    """Return a short description of an image, caching by sha256 content hash."""
    image_path = Path(image_path)
    blob = image_path.read_bytes()
    digest = hashlib.sha256(blob).hexdigest()

    cache: dict[str, str] = {}
    if cache_path and cache_path.exists():
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            cache = {}

    if digest in cache:
        return cache[digest]

    description = await _vlm_describe(image_path)
    cache[digest] = description
    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    return description
