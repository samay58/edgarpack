"""Tests for section detection and splitting."""

import unittest

from edgarpack.parse.sectionize import Section, find_sections, section_id, sectionize, slugify


class TestSlugify(unittest.TestCase):
    def test_basic_slug(self) -> None:
        self.assertEqual(slugify("Business Overview"), "business_overview")

    def test_keeps_underscores(self) -> None:
        s = slugify("Management's Discussion & Analysis")
        self.assertIn("_", s)

    def test_truncates_long_text(self) -> None:
        long_text = "This is a very long title that should be truncated"
        result = slugify(long_text, max_len=20)
        self.assertLessEqual(len(result), 20)


class TestSectionId(unittest.TestCase):
    def test_10k_section_id(self) -> None:
        sid = section_id("10-K", "I", "1", "Business")
        self.assertEqual(sid, "10k_parti_item1_business")

    def test_10q_section_id_without_part(self) -> None:
        sid = section_id("10-Q", None, "2", "MD&A")
        self.assertTrue(sid.startswith("10q_item2"))

    def test_8k_section_id(self) -> None:
        sid = section_id("8-K", None, "2.02", "Results of Operations")
        self.assertTrue(sid.startswith("8k_item_2_02"))

    def test_amended_form_section_id(self) -> None:
        sid = section_id("10-K/A", "I", "1", "Business")
        self.assertEqual(sid, "10k_parti_item1_business")


class TestFindSections(unittest.TestCase):
    def test_skips_toc_table_and_finds_inline_headings(self) -> None:
        md = (
            "Table of Contents\n\n"
            "| Item 1. | Financial Statements | 3 |\n"
            "| --- | --- | --- |\n"
            "| Item 2. | MD&A | 25 |\n"
            "\n"
            "Preamble text.\n"
            "2Part I. Financial InformationItem 1. Financial Statements\n"
            "Some content.\n"
            "Item 2. Management's Discussion and Analysis\n"
            "More content.\n"
            "Item 3. Quantitative and Qualitative Disclosures about Market Risk\n"
            "Item 4. Controls and Procedures\n"
            "End of Part I.\n"
            ".Part II. Other InformationItem 1. Legal Proceedings\n"
            "Item 1A. Risk Factors\n"
            "Item 2. Unregistered Sales of Equity Securities and Use of Proceeds\n"
            "Item 5. Other Information\n"
            "Item 6. Exhibits\n"
        )

        matches = find_sections(md, "10-Q")
        items = [(m.item, m.part) for m in matches if m.item != "other"]

        self.assertIn(("1", "I"), items)
        self.assertIn(("2", "I"), items)
        self.assertIn(("3", "I"), items)
        self.assertIn(("4", "I"), items)
        self.assertIn(("1", "II"), items)
        self.assertIn(("1A", "II"), items)
        self.assertIn(("2", "II"), items)
        self.assertIn(("5", "II"), items)
        self.assertIn(("6", "II"), items)

        # Ensure the first match isn't from the TOC table.
        first = next(m for m in matches if m.item != "other")
        self.assertGreater(first.char_pos, md.find("\n\n") + 2)

    def test_detects_item_headings_inside_table_cells_after_toc(self) -> None:
        md = (
            "TABLE OF CONTENTS\n\n"
            "| Item | Description | Page |\n"
            "| --- | --- | --- |\n"
            "| Item 1. | Financial Statements | 3 |\n"
            "| Item 2. | Management's Discussion and Analysis | 25 |\n"
            "\n"
            "PART I. FINANCIAL INFORMATION\n"
            "| Heading | Details |\n"
            "| --- | --- |\n"
            "| **Item 1.** Financial Statements | Condensed Consolidated Balance Sheets |\n"
            "| **Item 2.** Management's Discussion and Analysis | Results of Operations |\n"
        )

        matches = find_sections(md, "10-Q")
        items = [(m.item, m.part) for m in matches if m.item != "other"]
        self.assertIn(("1", "I"), items)
        self.assertIn(("2", "I"), items)
        # Ensure the detected sections come from content after the TOC block.
        first = next(m for m in matches if m.item in {"1", "2"})
        self.assertGreater(first.char_pos, md.find("PART I. FINANCIAL INFORMATION"))

    def test_title_truncation(self) -> None:
        long_title = "A" * 200
        md = f"ITEM 1. {long_title}\nBody\n"
        matches = find_sections(md, "10-K")
        self.assertTrue(matches)
        self.assertLessEqual(len(matches[0].title), 100)

    def test_table_cells_with_prefixed_item(self) -> None:
        md = "| 1. Item 1. Business | 3 |\n| --- | --- |\n| 2. Item 1A. Risk Factors | 5 |\n\n"
        matches = find_sections(md, "10-K")
        items = [m.item for m in matches if m.item != "other"]
        self.assertIn("1", items)
        self.assertIn("1A", items)

    def test_10k_toc_blockquote_rows_do_not_mint_duplicate_sections(self) -> None:
        md = (
            "Table of Contents\n\n"
            "> **Page / Page / Page**\n"
            ">\n"
            "> Part I / Part I / Part I\n"
            "> Item 1. ................................. Item 1. / Item 1. / "
            "Business / Business / Business / 4 / 4 / 4\n"
            "> Item 1A. ................................ Item 1A. / Item 1A. / "
            "Risk Factors / Risk Factors / Risk Factors / 12 / 12 / 12\n"
            "\n"
            "---\n\n"
            "Part I\n\n"
            "Item 1. Business\n"
            "Business body.\n\n"
            "Item 1A. Risk Factors\n"
            "Risk body.\n"
        )

        sections = sectionize(md, "10-K")
        ids = [s.id for s in sections if not s.id.startswith("unknown")]

        self.assertEqual(ids, ["10k_parti_item1_business", "10k_parti_item1a_risk_factors"])

    def test_inline_body_item_references_do_not_mint_sections(self) -> None:
        md = (
            "Part II\n\n"
            "Item 7. Management's Discussion and Analysis\n"
            "Refer to Note 13 in Part IV, Item 15 of this Annual Report on Form 10-K "
            "for additional information.\n"
            "See Item 1A. Risk Factors for additional information regarding our investments.\n"
            "The information required by Item 408(b) of Regulation S-K is incorporated "
            "by reference.\n\n"
            "Item 7A. Quantitative and Qualitative Disclosures About Market Risk\n"
            "Market risk body.\n"
        )

        matches = find_sections(md, "10-K")
        items = [(m.item, m.title) for m in matches if m.item != "other"]

        self.assertEqual(
            items,
            [
                ("7", "Management's Discussion and Analysis"),
                ("7A", "Quantitative and Qualitative Disclosures About Market Risk"),
            ],
        )

    def test_amended_8k_uses_8k_pattern(self) -> None:
        md = "ITEM 1.01 Entry into a Material Definitive Agreement\nBody\n"
        matches = find_sections(md, "8-K/A")
        self.assertTrue(any(m.item == "1.01" for m in matches))

    def test_general_form_uses_bold_headings(self) -> None:
        md = (
            "##### Table of Contents\n\n**PROSPECTUS SUMMARY** Text\n\n**RISK FACTORS** More text\n"
        )
        sections = sectionize(md, "424B4")
        titles = [s.title for s in sections]
        self.assertIn("PROSPECTUS SUMMARY", titles)
        self.assertIn("RISK FACTORS", titles)
        self.assertNotIn("Table of Contents", titles)

    def test_general_form_ignores_short_bold(self) -> None:
        md = "**S.** **Fiedler** has served as our Chief Financial Officer.\n\nMore text."
        matches = find_sections(md, "424B4")
        self.assertEqual(matches, [])

    def test_general_form_ignores_prospectus_cover(self) -> None:
        md = "**PROSPECTUS**\n\n**RISK FACTORS** Text\n"
        matches = find_sections(md, "424B4")
        titles = [m.title for m in matches]
        self.assertIn("RISK FACTORS", titles)
        self.assertNotIn("PROSPECTUS", titles)


class TestSectionize(unittest.TestCase):
    def test_unknown_section_for_no_matches(self) -> None:
        md = "Just some random content without any item headings."
        sections = sectionize(md, "10-K")
        self.assertEqual(len(sections), 1)
        self.assertTrue(sections[0].id.startswith("unknown"))
        self.assertTrue(sections[0].warnings)

    def test_splits_into_sections(self) -> None:
        md = (
            "## ITEM 1. BUSINESS\n\nWe make things.\n\n## ITEM 2. PROPERTIES\n\nWe own buildings.\n"
        )
        sections = sectionize(md, "10-K")
        self.assertTrue(all(isinstance(s, Section) for s in sections))
        self.assertGreaterEqual(len(sections), 2)

    def test_handles_duplicate_ids(self) -> None:
        md = "## ITEM 1. BUSINESS\n\nFirst.\n\n## ITEM 1. BUSINESS\n\nSecond.\n"
        sections = sectionize(md, "10-K")
        ids = [s.id for s in sections]
        self.assertEqual(len(ids), len(set(ids)))


class TestCrossRefFragmentRejection(unittest.TestCase):
    """Covers edgarpack-zfr: cross-reference sentences and exhibit citation
    fragments must not be promoted into real section titles."""

    def test_cross_ref_sentence_does_not_mint_section(self) -> None:
        """'Item 1A. Risk Factors for additional information regarding our
        investments.' is a cross-reference, not a heading. It should not mint
        a section."""
        from edgarpack.parse.sectionize import find_sections

        md = "Item 1A. Risk Factors for additional information regarding our investments.\n"
        matches = find_sections(md, "10-K")
        item_titles = [(m.item, m.title) for m in matches]
        self.assertEqual(item_titles, [])

    def test_paren_citation_does_not_mint_section(self) -> None:
        """A cell containing a regulation citation like '(b)(32)(ii) of
        Regulation S-K' should not become the title of an adjacent ITEM
        match."""
        from edgarpack.parse.sectionize import find_sections

        md = "| Item 15 | (b)(32)(ii) of Regulation S-K |\n"
        matches = find_sections(md, "10-K")
        item_titles = [(m.item, m.title) for m in matches]
        item_15 = [t for item, t in item_titles if item == "15"]
        self.assertEqual(item_15, [])

    def test_phrase_of_this_annual_report_does_not_mint_section(self) -> None:
        """'Item 7. Management's Discussion in this annual report' must
        be rejected rather than ship a cross-ref body as the MD&A title."""
        from edgarpack.parse.sectionize import find_sections

        md = "Item 7. Management's Discussion in this annual report of 2024 results.\n"
        matches = find_sections(md, "10-K")
        item_7 = [m.title for m in matches if m.item == "7"]
        self.assertEqual(item_7, [])


if __name__ == "__main__":
    unittest.main()
