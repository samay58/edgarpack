"""Tests for the registration-class assets pipeline (download + optional describe)."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from edgarpack.pack.assets import (
    describe_asset,
    download_assets,
    extract_image_urls,
)

HTML = """
<img src="figure-1.jpg" alt="CS-3 photo"/>
<img src="https://www.sec.gov/Archives/foo/figure-2.png" alt="Chart"/>
"""


def test_extract_image_urls_finds_both_absolute_and_relative():
    urls = extract_image_urls(HTML)
    assert "figure-1.jpg" in urls
    assert "https://www.sec.gov/Archives/foo/figure-2.png" in urls


@pytest.mark.parametrize(
    "html,expected",
    [
        ("<img src='fig.png' alt='x'/>", "fig.png"),
        ("<img src=fig.png alt=x>", "fig.png"),
        ('<img src = "fig.png" alt = "x"/>', "fig.png"),
    ],
)
def test_extract_image_urls_handles_quote_variants(html: str, expected: str):
    assert extract_image_urls(html) == [expected]


@pytest.mark.asyncio
async def test_download_assets_writes_files_and_returns_map(tmp_path):
    async def fake_fetch(url):
        return b"\x89PNG\r\n\x1a\nfakebytes"

    with patch("edgarpack.pack.assets._fetch_bytes", new=AsyncMock(side_effect=fake_fetch)):
        mapping = await download_assets(
            base_url="https://www.sec.gov/Archives/foo/",
            html=HTML,
            out_dir=tmp_path,
        )

    assert "figure-1.jpg" in mapping
    local = tmp_path / mapping["figure-1.jpg"]
    assert local.exists()
    assert local.read_bytes().startswith(b"\x89PNG")


@pytest.mark.asyncio
async def test_describe_asset_caches_by_hash(tmp_path, monkeypatch):
    image = tmp_path / "fig.png"
    image.write_bytes(b"fakebytes")
    cache = tmp_path / ".descriptions.json"

    calls = {"n": 0}

    async def fake_vlm(_path):
        calls["n"] += 1
        return "A bar chart showing TAM growth."

    monkeypatch.setattr("edgarpack.pack.assets._vlm_describe", fake_vlm)

    first = await describe_asset(image, cache_path=cache)
    second = await describe_asset(image, cache_path=cache)

    assert first == "A bar chart showing TAM growth."
    assert second == first
    assert calls["n"] == 1

    on_disk = json.loads(cache.read_text())
    assert any(v == first for v in on_disk.values())
