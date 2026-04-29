"""Tests for HTML → markdown rendering."""

import unittest
from pathlib import Path

from edgarpack.parse.md_render import _normalize_output, render_markdown

FIXTURES = Path(__file__).parent / "fixtures"


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

    def test_renders_table_with_colspan(self) -> None:
        html = (
            "<table>"
            "<tr><th colspan='2'>Merged Header</th><th>C</th></tr>"
            "<tr><td>A1</td><td>A2</td><td>A3</td></tr>"
            "</table>"
        )
        md = render_markdown(html)
        # The merged header should expand to fill 2 columns
        rows = [line for line in md.strip().split("\n") if line.startswith("|")]
        # Header row should have 3 pipe-separated cells
        header_cells = [c.strip() for c in rows[0].split("|") if c.strip()]
        self.assertEqual(len(header_cells), 3)
        # Data row should also have 3 cells
        data_cells = [c.strip() for c in rows[2].split("|") if c.strip()]
        self.assertEqual(len(data_cells), 3)

    def test_renders_table_with_rowspan(self) -> None:
        html = (
            "<table>"
            "<tr><th>Category</th><th>Value</th></tr>"
            "<tr><td rowspan='2'>Assets</td><td>100</td></tr>"
            "<tr><td>200</td></tr>"
            "</table>"
        )
        md = render_markdown(html)
        rows = [line for line in md.strip().split("\n") if line.startswith("|")]
        # Both data rows should have 2 cells each
        for row in rows[2:]:
            cells = [c.strip() for c in row.split("|") if c.strip()]
            self.assertEqual(len(cells), 2)
        # "Assets" should appear in both rows
        self.assertEqual(md.count("Assets"), 2)

    def test_renders_tsm_2006_table_with_zero_colspan(self) -> None:
        html = (FIXTURES / "tsm_2006_malformed_span_table.html").read_text(encoding="utf-8")
        md = render_markdown(html)
        self.assertIn("Within one year", md)
        self.assertIn("NT$71,820.9", md)
        self.assertIn("US$", md)
        self.assertIn("2,149.0", md)

    def test_unwraps_empty_href_link(self) -> None:
        html = '<a href="">click here</a>'
        md = render_markdown(html)
        self.assertIn("click here", md)
        self.assertNotIn("[click here]()", md)

    def test_drops_empty_text_link(self) -> None:
        html = '<a href="https://example.com">   </a>'
        md = render_markdown(html)
        self.assertNotIn("[](", md)
        self.assertNotIn("example.com", md)

    def test_unwraps_javascript_link(self) -> None:
        html = '<a href="javascript:void(0)">click</a>'
        md = render_markdown(html)
        self.assertIn("click", md)
        self.assertNotIn("[click]", md)

    def test_unwraps_bare_hash_link(self) -> None:
        html = '<a href="#">top</a>'
        md = render_markdown(html)
        self.assertIn("top", md)
        self.assertNotIn("[top](#)", md)

    def test_preserves_space_around_bold(self) -> None:
        html = "<p>the <strong>bold</strong> word</p>"
        md = render_markdown(html)
        self.assertIn("the **bold** word", md)
        self.assertNotIn("the**bold**word", md)

    def test_preserves_space_around_italic(self) -> None:
        html = "<p>the <em>italic</em> word</p>"
        md = render_markdown(html)
        self.assertIn("the *italic* word", md)
        self.assertNotIn("the*italic*word", md)


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
