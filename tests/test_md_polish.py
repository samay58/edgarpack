"""Tests for markdown polish pass."""

import unittest

from edgarpack.parse.md_polish import polish, _strip_toc_spam, _normalize_whitespace, _strip_broken_anchors


class TestStripTocSpam(unittest.TestCase):
    def test_keeps_first_toc_heading(self) -> None:
        md = "##### Table of Contents\n\nContent here"
        result = _strip_toc_spam(md)
        self.assertIn("Table of Contents", result)

    def test_removes_subsequent_toc_headings(self) -> None:
        md = "##### Table of Contents\n\nContent\n\n##### Table of Contents\n\nMore"
        result = _strip_toc_spam(md)
        self.assertEqual(result.count("Table of Contents"), 1)
        self.assertIn("More", result)

    def test_removes_index_headings(self) -> None:
        md = "## INDEX\n\nContent\n\n## INDEX\n\nMore"
        result = _strip_toc_spam(md)
        self.assertEqual(result.count("INDEX"), 1)

    def test_no_toc_headings_unchanged(self) -> None:
        md = "## Business\n\nContent\n\n## Risk Factors\n\nMore"
        result = _strip_toc_spam(md)
        self.assertEqual(result, md)


class TestNormalizeWhitespace(unittest.TestCase):
    def test_collapses_triple_blank_lines(self) -> None:
        md = "Para 1\n\n\n\nPara 2"
        result = _normalize_whitespace(md)
        self.assertNotIn("\n\n\n", result)
        self.assertIn("\n\n", result)

    def test_blank_line_before_heading(self) -> None:
        md = "Some text\n## Heading"
        result = _normalize_whitespace(md)
        self.assertIn("\n\n## Heading", result)

    def test_strips_trailing_whitespace(self) -> None:
        md = "Line with trailing   \nNext line"
        result = _normalize_whitespace(md)
        self.assertNotIn("   \n", result)

    def test_preserves_intentional_line_break(self) -> None:
        md = "Soft break  \nNext line"
        result = _normalize_whitespace(md)
        self.assertIn("  \n", result)

    def test_strips_leading_trailing_blank_lines(self) -> None:
        md = "\n\n\nContent\n\n\n"
        result = _normalize_whitespace(md)
        self.assertFalse(result.startswith("\n"))
        self.assertFalse(result.endswith("\n\n"))


class TestStripBrokenAnchors(unittest.TestCase):
    def test_strips_fragment_only_link(self) -> None:
        md = "See [Risk Factors](#toc890989_3) for details"
        result = _strip_broken_anchors(md)
        self.assertIn("See Risk Factors for details", result)
        self.assertNotIn("#toc", result)

    def test_preserves_full_url_links(self) -> None:
        md = "Visit [SEC](https://sec.gov) for filings"
        result = _strip_broken_anchors(md)
        self.assertIn("[SEC](https://sec.gov)", result)

    def test_preserves_toc_section_anchors(self) -> None:
        md = "##### Table of Contents\n\n[Item 1](#item1)\n[Item 2](#item2)\n\n## Item 1"
        result = _strip_broken_anchors(md)
        self.assertIn("[Item 1](#item1)", result)


class TestPolish(unittest.TestCase):
    def test_idempotent(self) -> None:
        md = "##### Table of Contents\n\nContent\n\n##### Table of Contents\n\nMore\n\n\n\n## Section"
        once = polish(md)
        twice = polish(once)
        self.assertEqual(once, twice)


if __name__ == "__main__":
    unittest.main()
