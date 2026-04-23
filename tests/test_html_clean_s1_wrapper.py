"""Regression test: SEC print-layout page wrappers use font-size:0 as a CSS
reset. clean_html previously treated that as a hidden-text signal and
discarded the entire subtree, collapsing multi-megabyte S-1 filings to
a few hundred characters. The hidden-style detector now requires
font-size:0 to co-occur with another size-zeroing signal before hiding.
"""

from pathlib import Path

from edgarpack.parse.html_clean import clean_html, is_hidden_style

FIXTURE = Path(__file__).parent / "fixtures" / "s1_font_size_zero_wrapper.html"


def test_font_size_zero_alone_is_not_hidden():
    # Cerebras's S-1 page wrapper; real style string from the filing.
    wrapper = (
        "background-color:#FFFFFF;border:1px solid #CCCC;content-visibility:auto;"
        "float:none;font-size:0;height:792pt;margin:10px auto 10px auto;"
        "overflow:hidden;padding:0;position:relative;width:612pt"
    )
    assert not is_hidden_style(wrapper), (
        "font-size:0 alongside real width/height on a page wrapper must NOT "
        "be treated as hidden. Regression guard against the Cerebras bug."
    )


def test_font_size_zero_with_width_zero_is_still_hidden():
    # The genuine hidden-text trick: zero-size everything at once.
    hidden = "font-size:0;width:0;height:0;overflow:hidden"
    assert is_hidden_style(hidden), (
        "When font-size:0 co-occurs with width:0 and height:0 we still "
        "want to treat the element as hidden (classic SEO cloaking)."
    )


def test_font_size_zero_with_width_zero_only_is_still_hidden():
    # width:0 alone has always flagged hidden; keep that behavior.
    assert is_hidden_style("width:0")


def test_font_size_zero_with_height_zero_only_is_still_hidden():
    # height:0 alone has always flagged hidden; keep that behavior.
    assert is_hidden_style("height:0")


def test_cerebras_style_wrapper_preserves_inner_text():
    html = FIXTURE.read_text(encoding="utf-8")
    out = clean_html(html)
    assert "Prospectus Summary" in out
    assert "Cerebras Systems" in out
    assert "addressable market at $150 billion" in out
    # And the output should be substantially longer than the stripped
    # 2-line case that triggered this bug.
    assert len(out) > 200, (
        f"Cleaned output collapsed to {len(out)} chars; the Cerebras "
        "page-wrapper div is still being stripped."
    )
