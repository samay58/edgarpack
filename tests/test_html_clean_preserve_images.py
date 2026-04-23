"""Ensure html_clean can preserve <img> tags for registration-class filings."""

from edgarpack.parse.html_clean import clean_html

HTML = """
<html><body>
<p>Our flagship product is the CS-3.</p>
<img src="figure-1-cs3-photo.jpg" alt="Photograph of the Cerebras CS-3 system"/>
<p>Performance scales linearly.</p>
<img src="figure-2-tam-chart.png" alt="AI inference TAM chart"/>
</body></html>
"""


def test_default_strips_images():
    out = clean_html(HTML)
    assert "<img" not in out.lower()


def test_preserve_images_keeps_img_tags():
    out = clean_html(HTML, preserve_images=True)
    assert out.lower().count("<img") == 2
    assert "figure-1-cs3-photo.jpg" in out
    assert "figure-2-tam-chart.png" in out


def test_preserve_images_keeps_alt_text():
    out = clean_html(HTML, preserve_images=True)
    assert "Photograph of the Cerebras CS-3 system" in out
