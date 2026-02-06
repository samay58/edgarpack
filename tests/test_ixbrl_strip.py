"""Tests for iXBRL stripping."""

import unittest

from edgarpack.parse.ixbrl_strip import has_ixbrl, strip_ixbrl


class TestStripIXBRL(unittest.TestCase):
    def test_removes_ix_nonfraction_preserves_text(self) -> None:
        html = (
            '<p>Revenue: <ix:nonFraction name="us-gaap:Revenues">119575000000</ix:nonFraction></p>'
        )
        result = strip_ixbrl(html)
        self.assertNotIn("ix:nonFraction", result)
        self.assertIn("119575000000", result)
        self.assertIn("<p>Revenue:", result)

    def test_removes_ix_nonnumeric_preserves_text(self) -> None:
        html = '<ix:nonNumeric name="dei:EntityRegistrantName">Apple Inc.</ix:nonNumeric>'
        result = strip_ixbrl(html)
        self.assertNotIn("ix:nonNumeric", result)
        self.assertIn("Apple Inc.", result)

    def test_removes_nested_ixbrl(self) -> None:
        html = (
            '<ix:continuation id="c1">'
            '<ix:nonFraction name="a">100</ix:nonFraction>'
            '<ix:nonNumeric name="b">Text</ix:nonNumeric>'
            "</ix:continuation>"
        )
        result = strip_ixbrl(html)
        self.assertNotIn("ix:", result.lower())
        self.assertIn("100", result)
        self.assertIn("Text", result)

    def test_removes_xmlns_declarations(self) -> None:
        html = (
            '<html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL" '
            'xmlns:xbrli="http://www.xbrl.org/2003/instance">'
            "<body>Content</body></html>"
        )
        result = strip_ixbrl(html)
        self.assertNotIn("xmlns:ix", result)
        self.assertNotIn("xbrli", result.lower())
        self.assertIn("Content", result)

    def test_preserves_non_ixbrl_content(self) -> None:
        html = "<p>Regular <strong>HTML</strong> content</p>"
        result = strip_ixbrl(html)
        self.assertEqual(result, html)

    def test_handles_multiple_namespaces(self) -> None:
        html = "<dei:DocumentType>10-K</dei:DocumentType><us-gaap:Revenues>100</us-gaap:Revenues>"
        result = strip_ixbrl(html)
        self.assertNotIn("dei:", result)
        self.assertNotIn("us-gaap:", result)
        self.assertIn("10-K", result)
        self.assertIn("100", result)


class TestHasIXBRL(unittest.TestCase):
    def test_detects_ix_prefix(self) -> None:
        self.assertTrue(has_ixbrl("<ix:nonFraction>100</ix:nonFraction>"))

    def test_detects_xbrli_prefix(self) -> None:
        self.assertTrue(has_ixbrl("<xbrli:context>...</xbrli:context>"))

    def test_detects_xmlns_declaration(self) -> None:
        self.assertTrue(has_ixbrl('<html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL">'))

    def test_no_false_positive(self) -> None:
        self.assertFalse(has_ixbrl("<html><body><p>Normal content</p></body></html>"))


if __name__ == "__main__":
    unittest.main()

