"""Tests for markdown polish pass."""

import unittest

from edgarpack.parse.md_polish import (
    _normalize_headings,
    _normalize_whitespace,
    _recover_bullet_tables,
    _simplify_complex_tables,
    _simplify_empty_columns,
    _strip_bold_noise,
    _strip_broken_anchors,
    _strip_toc_spam,
    polish,
)


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


class TestStripBoldNoise(unittest.TestCase):
    def test_strips_all_bold_paragraph(self) -> None:
        md = "**This entire paragraph is bold and should not be.**"
        result = _strip_bold_noise(md)
        self.assertEqual(result, "This entire paragraph is bold and should not be.")

    def test_strips_bold_dollar_amount(self) -> None:
        md = "Revenue was **$1,234** million"
        result = _strip_bold_noise(md)
        self.assertIn("$1,234", result)
        self.assertNotIn("**$1,234**", result)

    def test_strips_bold_negative_parens(self) -> None:
        md = "Loss of **(1,234)**"
        result = _strip_bold_noise(md)
        self.assertIn("(1,234)", result)
        self.assertNotIn("**(1,234)**", result)

    def test_strips_bold_percentage(self) -> None:
        md = "Growth of **12.5%** year over year"
        result = _strip_bold_noise(md)
        self.assertNotIn("**12.5%**", result)

    def test_preserves_partial_bold_in_sentence(self) -> None:
        md = "The company **expanded operations** to new markets"
        result = _strip_bold_noise(md)
        self.assertIn("**expanded operations**", result)

    def test_strips_bold_standalone_number(self) -> None:
        md = "Total was **42,000** units"
        result = _strip_bold_noise(md)
        self.assertNotIn("**42,000**", result)


class TestRecoverBulletTables(unittest.TestCase):
    def test_converts_bullet_table_to_list(self) -> None:
        md = (
            "| | \u2022 | | First item |\n| --- | --- | --- | --- |\n| | \u2022 | | Second item |\n"
        )
        result = _recover_bullet_tables(md)
        self.assertIn("- First item", result)
        self.assertIn("- Second item", result)
        self.assertNotIn("|", result)

    def test_ignores_normal_tables(self) -> None:
        md = "| Name | Value |\n| --- | --- |\n| Alpha | 100 |\n"
        result = _recover_bullet_tables(md)
        self.assertIn("|", result)
        self.assertIn("Alpha", result)

    def test_converts_dash_bullet_table(self) -> None:
        md = "| - | Item one |\n| --- | --- |\n| - | Item two |\n"
        result = _recover_bullet_tables(md)
        self.assertIn("- Item one", result)
        self.assertIn("- Item two", result)


class TestSimplifyEmptyColumns(unittest.TestCase):
    def test_removes_all_empty_columns(self) -> None:
        md = "| | Name | | Value | |\n| --- | --- | --- | --- | --- |\n| | Alpha | | 100 | |\n"
        result = _simplify_empty_columns(md)
        lines = [row for row in result.strip().split("\n") if row.startswith("|")]
        for line in lines:
            if "---" in line:
                continue
            cells = [c.strip() for c in line.split("|") if c.strip()]
            self.assertLessEqual(len(cells), 2)

    def test_converts_single_column_to_text(self) -> None:
        md = "| | Content here | |\n| --- | --- | --- |\n| | More content | |\n"
        result = _simplify_empty_columns(md)
        self.assertIn("Content here", result)
        self.assertIn("More content", result)
        self.assertNotIn("| --- |", result)

    def test_no_empty_columns_unchanged(self) -> None:
        md = "| A | B |\n| --- | --- |\n| 1 | 2 |\n"
        result = _simplify_empty_columns(md)
        self.assertEqual(result, md)


class TestNormalizeHeadings(unittest.TestCase):
    def test_shifts_h1_to_h2(self) -> None:
        md = "# PART I\n\nContent"
        result = _normalize_headings(md)
        self.assertIn("## PART I", result)
        # Ensure no line starts with exactly one '#' (i.e., no h1 remains)
        heading_lines = [line for line in result.split("\n") if line.startswith("#")]
        for hl in heading_lines:
            self.assertFalse(hl.startswith("# ") and not hl.startswith("## "))

    def test_maintains_relative_levels(self) -> None:
        md = "# PART I\n\n## ITEM 1\n\n### Sub-section\n\nContent"
        result = _normalize_headings(md)
        self.assertIn("## PART I", result)
        self.assertIn("### ITEM 1", result)
        self.assertIn("#### Sub-section", result)

    def test_clamps_level_skips(self) -> None:
        md = "## PART I\n\n##### Deep heading\n\nContent"
        result = _normalize_headings(md)
        lines = result.split("\n")
        heading_lines = [line for line in lines if line.startswith("#")]
        first_level = len(heading_lines[0].split(" ")[0])
        second_level = len(heading_lines[1].split(" ")[0])
        self.assertLessEqual(second_level, first_level + 1)

    def test_already_normalized_unchanged(self) -> None:
        md = "## PART I\n\n### ITEM 1\n\n#### Details\n\nContent"
        result = _normalize_headings(md)
        self.assertEqual(result, md)

    def test_no_headings_unchanged(self) -> None:
        md = "Just some text\n\nMore text"
        result = _normalize_headings(md)
        self.assertEqual(result, md)


class TestSimplifyComplexTables(unittest.TestCase):
    def test_leaves_simple_table_alone(self) -> None:
        md = "| Metric | Q1 | Q2 |\n| --- | --- | --- |\n| Revenue | 100 | 200 |\n"
        result = _simplify_complex_tables(md)
        self.assertIn("| Metric |", result)

    def test_converts_wide_table_to_block(self) -> None:
        header = "| Category | Sub | 2025 Q1 | 2025 Q2 | 2024 Q1 | 2024 Q2 | 2023 Q1 | 2023 Q2 |"
        sep = "| --- | --- | --- | --- | --- | --- | --- | --- |"
        row1 = "| Revenue | Product | 100 | 200 | 80 | 150 | 60 | 120 |"
        md = f"{header}\n{sep}\n{row1}\n"
        result = _simplify_complex_tables(md)
        self.assertIn(">", result)
        self.assertNotIn("| --- |", result)

    def test_converts_long_row_table_to_block(self) -> None:
        header = "| Description | Amount | Notes |"
        sep = "| --- | --- | --- |"
        long_row = "| " + "A" * 50 + " | " + "B" * 50 + " | " + "C" * 50 + " |"
        md = f"{header}\n{sep}\n{long_row}\n"
        result = _simplify_complex_tables(md)
        self.assertIn(">", result)

    def test_preserves_content_in_block_format(self) -> None:
        header = "| A | B | C | D | E | F | G |"
        sep = "| --- | --- | --- | --- | --- | --- | --- |"
        row = "| Revenue | 100 | 200 | 300 | 400 | 500 | 600 |"
        md = f"{header}\n{sep}\n{row}\n"
        result = _simplify_complex_tables(md)
        self.assertIn("Revenue", result)
        self.assertIn("100", result)


class TestPolish(unittest.TestCase):
    def test_idempotent(self) -> None:
        md = (
            "##### Table of Contents\n\nContent\n\n"
            "##### Table of Contents\n\nMore\n\n\n\n## Section"
        )
        once = polish(md)
        twice = polish(once)
        self.assertEqual(once, twice)


class TestPolishIntegration(unittest.TestCase):
    def test_idempotent_on_realistic_input(self) -> None:
        md = (
            "##### Table of Contents\n\n"
            "[Item 1](#item1)\n\n"
            "##### Table of Contents\n\n"
            "# PART I\n\n"
            "## ITEM 1. BUSINESS\n\n"
            "**$1,234** million in revenue.\n\n"
            "See [Risk Factors](#toc123) for details.\n\n"
            "| | \u2022 | | Risk one |\n"
            "| --- | --- | --- | --- |\n"
            "| | \u2022 | | Risk two |\n\n"
            "| | Name | | Value | |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| | Alpha | | 100 | |\n\n"
            "##### Table of Contents\n\n"
            "## ITEM 1A. RISK FACTORS\n\n"
            "**This entire paragraph is bold and should not be.**\n\n"
            "\n\n\n\n"
            "More content here.\n"
        )
        once = polish(md)
        twice = polish(once)
        self.assertEqual(once, twice)

    def test_all_rules_applied(self) -> None:
        md = (
            "##### Table of Contents\n\n"
            "##### Table of Contents\n\n"
            "# PART I\n\n"
            "**$500** revenue\n\n"
            "See [details](#anchor123)\n\n"
            "| | \u2022 | | Item A |\n"
            "| --- | --- | --- | --- |\n\n"
            "| | Data | |\n"
            "| --- | --- | --- |\n\n"
            "\n\n\n\n"
        )
        result = polish(md)
        # TOC spam removed
        self.assertEqual(result.count("Table of Contents"), 1)
        # Bold stripped from dollar amount
        self.assertNotIn("**$500**", result)
        self.assertIn("$500", result)
        # Anchor stripped
        self.assertNotIn("#anchor123", result)
        self.assertIn("details", result)
        # Bullet table recovered
        self.assertIn("- Item A", result)
        # Whitespace normalized
        self.assertNotIn("\n\n\n", result)
        # Heading shifted to ##
        self.assertIn("## PART I", result)

    def test_preserves_normal_content(self) -> None:
        md = (
            "## Section Title\n\n"
            "Normal paragraph with **emphasis** on a word.\n\n"
            "| Name | Value |\n"
            "| --- | --- |\n"
            "| Alpha | 100 |\n\n"
            "- List item one\n"
            "- List item two\n"
        )
        result = polish(md)
        self.assertIn("**emphasis**", result)
        self.assertIn("| Name | Value |", result)
        self.assertIn("- List item one", result)


if __name__ == "__main__":
    unittest.main()
