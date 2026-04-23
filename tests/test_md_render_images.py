"""Ensure rendered markdown rewrites <img src> to local paths with a caption line."""

from edgarpack.parse.md_render import render_markdown

HTML_WITH_IMG = """
<html><body>
<p>Intro paragraph.</p>
<img src="figure-1.jpg" alt="CS-3 system photo"/>
<p>Trailing paragraph.</p>
</body></html>
"""


def test_render_with_asset_map_rewrites_src_to_local_path():
    asset_map = {"figure-1.jpg": "assets/figure-1.jpg"}
    md = render_markdown(HTML_WITH_IMG, asset_map=asset_map)
    assert "![" in md
    assert "assets/figure-1.jpg" in md


def test_render_with_asset_map_emits_alt_as_caption_line():
    asset_map = {"figure-1.jpg": "assets/figure-1.jpg"}
    md = render_markdown(HTML_WITH_IMG, asset_map=asset_map)
    assert "CS-3 system photo" in md


def test_render_without_asset_map_does_not_crash():
    md = render_markdown(HTML_WITH_IMG)
    assert isinstance(md, str)
