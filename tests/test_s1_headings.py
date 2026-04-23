"""Tests for TOC-anchor-driven S-1 heading injection.

The module turns `<a href="#anchor_id">Section Title</a>` TOC links plus
body `id="anchor_id"` markers into explicit `<h2>Section Title</h2>` tags
so the downstream sectionizer can recognize section boundaries.
"""

from __future__ import annotations

import pytest

from edgarpack.parse.s1_headings import extract_toc_sections, inject_s1_headings


def test_extract_toc_sections_basic():
    html = """
    <div>Table of Contents</div>
    <a href="#s_summary">Prospectus Summary</a>
    <a href="#s_risk">Risk Factors</a>
    <a href="#s_use">Use of Proceeds</a>
    """
    assert extract_toc_sections(html) == [
        ("s_summary", "Prospectus Summary"),
        ("s_risk", "Risk Factors"),
        ("s_use", "Use of Proceeds"),
    ]


def test_extract_strips_leader_dots_and_entities():
    html = '<a href="#s_mda">Management&#8217;s Discussion ....... 90</a>'
    # Leader dots collapse, page number drops, entities decode.
    assert extract_toc_sections(html) == [("s_mda", "Management’s Discussion 90")]


def test_extract_ignores_page_numbers_and_roman_numerals():
    html = """
    <a href="#a1">1</a>
    <a href="#a2">iii</a>
    <a href="#a3">vii</a>
    <a href="#a4">Prospectus Summary</a>
    """
    assert extract_toc_sections(html) == [("a4", "Prospectus Summary")]


def test_extract_ignores_blacklist_titles():
    html = """
    <a href="#a1">Table of Contents</a>
    <a href="#a2">top</a>
    <a href="#a3">Next</a>
    <a href="#a4">Business</a>
    """
    assert extract_toc_sections(html) == [("a4", "Business")]


def test_extract_dedupes_by_anchor():
    # Same anchor referenced from TOC and from a body cross-reference.
    html = """
    <a href="#s_risk">Risk Factors</a>
    <a href="#s_risk">see Risk Factors above</a>
    """
    assert extract_toc_sections(html) == [("s_risk", "Risk Factors")]


def test_inject_adds_h2_before_target_id():
    html = """
    <a href="#sum">Prospectus Summary</a>
    <div id="sum"><p>We are Cerebras.</p></div>
    """
    out = inject_s1_headings(html)
    assert '<h2>Prospectus Summary</h2><div id="sum">' in out


def test_inject_handles_multiple_sections():
    html = """
    <a href="#sum">Prospectus Summary</a>
    <a href="#risk">Risk Factors</a>
    <div id="sum"><p>We are Cerebras.</p></div>
    <div id="risk"><p>Investing involves risk.</p></div>
    """
    out = inject_s1_headings(html)
    assert out.count("<h2>") == 2
    assert "<h2>Prospectus Summary</h2>" in out
    assert "<h2>Risk Factors</h2>" in out


def test_inject_escapes_html_entities_in_title():
    # Titles that contain angle brackets or ampersands must not break the HTML.
    html = """
    <a href="#s">Revenue &amp; Growth &lt;5%</a>
    <div id="s">body</div>
    """
    out = inject_s1_headings(html)
    # The title text is HTML-escaped: & stays &amp;, < stays &lt;
    assert "<h2>Revenue &amp; Growth &lt;5%</h2>" in out


def test_inject_is_noop_when_no_toc_links():
    html = "<div>Plain content with no anchors.</div>"
    assert inject_s1_headings(html) == html


def test_inject_is_noop_when_anchor_has_no_body_target():
    html = '<a href="#ghost">Ghost Section</a><div>other body</div>'
    # The anchor is never targeted in the body, so no injection happens
    # and the HTML is unchanged aside from whitespace.
    out = inject_s1_headings(html)
    assert "<h2>" not in out


def test_inject_injects_only_once_per_anchor():
    # Same anchor appears twice in the body (unusual but possible).
    html = """
    <a href="#risk">Risk Factors</a>
    <div id="risk">first</div>
    <div id="risk">second</div>
    """
    out = inject_s1_headings(html)
    assert out.count("<h2>Risk Factors</h2>") == 1


@pytest.mark.parametrize(
    "title_form",
    [
        "Prospectus Summary",
        "PROSPECTUS SUMMARY",
        "prospectus summary",
    ],
)
def test_inject_preserves_title_casing(title_form: str):
    html = f'<a href="#s">{title_form}</a><div id="s">body</div>'
    out = inject_s1_headings(html)
    assert f"<h2>{title_form}</h2>" in out
