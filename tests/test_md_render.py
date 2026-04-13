"""Tests for HTML → markdown rendering."""

import unittest

from edgarpack.parse.md_render import _normalize_output, render_markdown


class TestRenderMarkdown(unittest.TestCase):
    def test_renders_headings(self) -> None:
        html = "<h1>Title</h1><h2>Subtitle</h2><h3>Section</h3>"
        md = render_markdown(html)
        self.assertIn("# Title", md)
        self.assertIn("## Subtitle", md)
        self.assertIn("### Section", md)

    def test_renders_paragraphs(self) -> None:
        html = "<p>First paragraph.</p><p>Second paragraph.</p>"
        md = render_markdown(html)
        self.assertIn("First paragraph.", md)
        self.assertIn("Second paragraph.", md)
        self.assertIn("\n\n", md)

    def test_renders_strong_emphasis_links_code(self) -> None:
        html = (
            '<p><strong>Bold</strong> <em>Em</em> <a href="https://x">Link</a> <code>cmd</code></p>'
        )
        md = render_markdown(html)
        self.assertIn("**Bold**", md)
        self.assertIn("*Em*", md)
        self.assertIn("[Link](https://x)", md)
        self.assertIn("`cmd`", md)

    def test_renders_code_block(self) -> None:
        html = '<pre>function hello() {\\n  console.log("hi");\\n}</pre>'
        md = render_markdown(html)
        self.assertIn("```", md)
        self.assertIn("function hello()", md)

    def test_renders_lists(self) -> None:
        md = render_markdown("<ul><li>A</li><li>B</li></ul>")
        self.assertIn("- A", md)
        self.assertIn("- B", md)

    def test_renders_nested_unordered_list(self) -> None:
        html = "<ul><li>A<ul><li>A1</li><li>A2</li></ul></li><li>B</li></ul>"
        md = render_markdown(html)
        self.assertIn("- A", md)
        self.assertIn("  - A1", md)
        self.assertIn("  - A2", md)
        self.assertIn("- B", md)

    def test_renders_nested_ordered_list(self) -> None:
        html = "<ol><li>First<ol><li>Sub 1</li><li>Sub 2</li></ol></li><li>Second</li></ol>"
        md = render_markdown(html)
        self.assertIn("1. First", md)
        self.assertIn("  1. Sub 1", md)
        self.assertIn("  2. Sub 2", md)
        self.assertIn("2. Second", md)

    def test_renders_deeply_nested_list(self) -> None:
        html = "<ul><li>L1<ul><li>L2<ul><li>L3</li></ul></li></ul></li></ul>"
        md = render_markdown(html)
        self.assertIn("- L1", md)
        self.assertIn("  - L2", md)
        self.assertIn("    - L3", md)

    def test_renders_table(self) -> None:
        html = "<table><tr><th>Name</th><th>Value</th></tr><tr><td>A</td><td>1</td></tr></table>"
        md = render_markdown(html)
        self.assertIn("|", md)
        self.assertIn("Name", md)
        self.assertIn("---", md)

    def test_inserts_separators_for_divs(self) -> None:
        html = "<div>One</div><div>Two</div>"
        md = render_markdown(html)
        # Should not concatenate the words.
        self.assertIn("One", md)
        self.assertIn("Two", md)
        self.assertNotIn("OneTwo", md)


class TestNormalizeOutput(unittest.TestCase):
    def test_collapses_multiple_blank_lines(self) -> None:
        md = "Para 1\n\n\n\n\nPara 2"
        result = _normalize_output(md)
        self.assertNotIn("\n\n\n", result)
        self.assertIn("\n\n", result)

    def test_normalizes_line_endings(self) -> None:
        md = "Line 1\r\nLine 2\rLine 3"
        result = _normalize_output(md)
        self.assertNotIn("\r\n", result)
        self.assertNotIn("\r", result)


if __name__ == "__main__":
    unittest.main()
