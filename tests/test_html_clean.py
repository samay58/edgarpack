"""Tests for HTML cleaning."""

import unittest

from edgarpack.parse.html_clean import clean_html, extract_text, is_hidden_element, is_hidden_style


class TestCleanHTML(unittest.TestCase):
    def test_removes_script_tags_and_content(self) -> None:
        html = '<p>Text</p><script>alert("bad")</script><p>More</p>'
        result = clean_html(html)
        self.assertNotIn("<script", result.lower())
        self.assertNotIn("alert", result)
        self.assertIn("<p>", result)
        self.assertIn("Text", result)
        self.assertIn("More", result)

    def test_removes_style_tags_and_content(self) -> None:
        html = '<style>.foo { color: red; }</style><p>Content</p>'
        result = clean_html(html)
        self.assertNotIn("<style", result.lower())
        self.assertNotIn(".foo", result)
        self.assertIn("Content", result)

    def test_removes_noscript(self) -> None:
        html = "<noscript>Enable JS</noscript><p>Content</p>"
        result = clean_html(html)
        self.assertNotIn("Enable JS", result)
        self.assertIn("Content", result)

    def test_removes_hidden_display_none(self) -> None:
        html = '<div style="display: none">Hidden</div><p>Visible</p>'
        result = clean_html(html)
        self.assertNotIn("Hidden", result)
        self.assertIn("Visible", result)

    def test_strips_class_id_style_attributes(self) -> None:
        html = '<p class="x" id="y" style="color: red">Text</p>'
        result = clean_html(html)
        self.assertNotIn("class=", result)
        self.assertNotIn("id=", result)
        self.assertNotIn("style=", result)
        self.assertIn("Text", result)

    def test_strips_event_handlers(self) -> None:
        html = '<button onclick="doSomething()">Click</button>'
        result = clean_html(html)
        self.assertNotIn("onclick", result.lower())
        self.assertIn("Click", result)

    def test_preserves_basic_structure(self) -> None:
        html = "<div><p>Paragraph</p><ul><li>Item</li></ul></div>"
        result = clean_html(html)
        self.assertIn("<p>", result)
        self.assertIn("<ul>", result)
        self.assertIn("<li>", result)


class TestHiddenDetection(unittest.TestCase):
    def test_is_hidden_style_display_none(self) -> None:
        self.assertTrue(is_hidden_style("display: none"))

    def test_is_hidden_style_visibility_hidden(self) -> None:
        self.assertTrue(is_hidden_style("visibility:hidden"))

    def test_is_hidden_style_opacity_zero(self) -> None:
        self.assertTrue(is_hidden_style("opacity: 0"))

    def test_is_hidden_element_hidden_attribute(self) -> None:
        self.assertTrue(is_hidden_element({"hidden": ""}))

    def test_is_hidden_element_aria_hidden(self) -> None:
        self.assertTrue(is_hidden_element({"aria-hidden": "true"}))

    def test_not_hidden_normal(self) -> None:
        self.assertFalse(is_hidden_element({"style": "color: blue"}))


class TestExtractText(unittest.TestCase):
    def test_extracts_basic_text(self) -> None:
        html = "<p>Hello <strong>world</strong>!</p>"
        text = extract_text(html)
        self.assertIn("Hello", text)
        self.assertIn("world", text)

    def test_excludes_hidden_text(self) -> None:
        html = '<p>Visible</p><div style="display:none">Hidden</div>'
        text = extract_text(html)
        self.assertIn("Visible", text)
        self.assertNotIn("Hidden", text)

    def test_excludes_script_content(self) -> None:
        html = "<p>Text</p><script>var x = 1;</script>"
        text = extract_text(html)
        self.assertIn("Text", text)
        self.assertNotIn("var x", text)


if __name__ == "__main__":
    unittest.main()

