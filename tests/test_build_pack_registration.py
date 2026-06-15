"""Tests for registration-class pack build wiring (images + render path)."""

from pathlib import Path
from unittest.mock import patch

import pytest

from edgarpack.pack.build import _process_html_files_for_form
from edgarpack.parse.sectionize import find_sections


@pytest.mark.asyncio
async def test_registration_form_preserves_images_and_rewrites_src(tmp_path):
    html = (
        '<html><body><p>Intro.</p><img src="fig1.png" alt="TAM chart"/><p>Body.</p></body></html>'
    )

    async def fake_download(base_url, html_payload, out_dir):
        (Path(out_dir) / "assets").mkdir(parents=True, exist_ok=True)
        (Path(out_dir) / "assets" / "fig1.png").write_bytes(b"x")
        return {"fig1.png": "assets/fig1.png"}

    with patch("edgarpack.pack.build.download_assets", new=fake_download):
        md = await _process_html_files_for_form(
            html_files=[("main.htm", html.encode("utf-8"))],
            base_url="https://www.sec.gov/Archives/foo/",
            form_type="S-1",
            out_dir=tmp_path,
            describe_images=False,
        )

    assert "assets/fig1.png" in md
    assert "TAM chart" in md


@pytest.mark.asyncio
async def test_periodic_form_still_strips_images(tmp_path):
    html = '<html><body><img src="logo.png"/><p>10-K body.</p></body></html>'
    md = await _process_html_files_for_form(
        html_files=[("main.htm", html.encode("utf-8"))],
        base_url="https://www.sec.gov/Archives/foo/",
        form_type="10-K",
        out_dir=tmp_path,
        describe_images=False,
    )
    assert "<img" not in md.lower()
    assert "assets/" not in md


@pytest.mark.asyncio
async def test_registration_legacy_name_anchor_becomes_section_heading(tmp_path):
    html = """
    <html><body>
      <table>
        <tr><td><a href="#rom393891_7"><font>PROSPECTUS SUMMARY</font></a></td></tr>
        <tr><td><a href="#rom393891_10"><font>RISK FACTORS</font></a></td></tr>
      </table>
      <p align="center"><b><a name="rom393891_7"></a>PROSPECTUS SUMMARY</b></p>
      <p>Summary body.</p>
      <p align="center"><b><a name="rom393891_10"></a>RISK FACTORS</b></p>
      <p>Risk body.</p>
    </body></html>
    """
    md = await _process_html_files_for_form(
        html_files=[("main.htm", html.encode("utf-8"))],
        base_url="https://www.sec.gov/Archives/foo/",
        form_type="F-1",
        out_dir=tmp_path,
        describe_images=False,
    )

    titles = [match.title for match in find_sections(md, "F-1")]
    assert titles == ["PROSPECTUS SUMMARY", "RISK FACTORS"]
