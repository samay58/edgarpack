"""Tests for the static site generator."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from edgarpack.site.build import _markdown_to_html, build_site


class TestSiteBuild(unittest.TestCase):
    def test_build_site_writes_indexes_and_pages(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            packs = Path(td) / "packs"
            out = Path(td) / "site"

            cik = "0000000001"
            accession = "0000000001-24-000001"
            pack_dir = packs / cik / accession
            (pack_dir / "sections").mkdir(parents=True, exist_ok=True)

            (pack_dir / "filing.full.md").write_text("# Title\n\nBody\n", encoding="utf-8")
            (pack_dir / "filing.full.en.md").write_text("# Title EN\n\nBody EN\n", encoding="utf-8")
            (pack_dir / "llms.txt").write_text("# Test\n", encoding="utf-8")
            (pack_dir / "sections" / "sec1.md").write_text("## Sec\n\nText\n", encoding="utf-8")
            (pack_dir / "sections" / "sec1.en.md").write_text(
                "## Sec EN\n\nText EN\n", encoding="utf-8"
            )

            manifest = {
                "schema_version": 1,
                "parser_version": "0.1.0",
                "generated_at": "2024-01-15T00:00:00Z",
                "source": {"url": "https://example.test", "fetched_at": "2024-01-15T00:00:00Z"},
                "filing": {
                    "cik": cik,
                    "accession": accession,
                    "form_type": "10-K",
                    "filing_date": "2024-01-15",
                    "company_name": "Test Co",
                },
                "sections": [
                    {
                        "id": "sec1",
                        "title": "Section 1",
                        "path": "sections/sec1.md",
                        "char_start": 0,
                        "char_end": 10,
                        "tokens_approx": 3,
                        "sha256": "0" * 64,
                    }
                ],
                "artifacts": {"filing.full.md": "0" * 64, "filing.full.en.md": "1" * 64},
                "warnings": [],
                "tokens_total": 3,
            }
            (pack_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

            report = build_site(packs, out)
            self.assertEqual(report["companies"], 1)
            self.assertEqual(report["filings"], 1)

            self.assertTrue((out / "index.html").exists())
            self.assertTrue((out / cik / "index.html").exists())
            self.assertTrue((out / cik / accession / "index.html").exists())
            self.assertTrue((out / cik / accession / "full.html").exists())
            self.assertTrue((out / cik / accession / "full.en.html").exists())
            self.assertTrue((out / cik / accession / "sections" / "sec1.html").exists())
            self.assertTrue((out / cik / accession / "sections" / "sec1.en.html").exists())

    def test_markdown_to_html_sanitizes_links(self) -> None:
        md = "Click [bad](javascript:alert(1)) and [ok](https://example.com)."
        html = _markdown_to_html(md)
        self.assertNotIn("javascript:", html.lower())
        self.assertIn("https://example.com", html)

    def test_markdown_to_html_normalizes_repeated_form_10k_summary_toc_line(self) -> None:
        md = (
            "> Item 16. ................ Item 16. / Item 16. / Form 10-K Summary / "
            "Form 10-K Summary / Form 10-K Summary / 83 / 83 / 83\n\nBody\n"
        )

        html = _markdown_to_html(md)

        self.assertIn("Item 16. Form 10-K Summary", html)
        self.assertNotIn("Form 10-K Summary / Form 10-K Summary", html)

    def test_static_site_wraps_financial_tables_for_scanning(self) -> None:
        html = _markdown_to_html(
            "\n".join(
                [
                    "| Maturity | Cost | Fair value |",
                    "| --- | ---: | ---: |",
                    "| Series A \\| preferred | $1,000 | $990 |",
                    "| One year or less | $35,108 | $34,952 |",
                    "| Total | $85,589 | $84,259 |",
                ]
            )
        )

        self.assertIn('<div class="table-scroll">', html)
        self.assertIn("<table>", html)
        self.assertIn("<td>Series A | preferred</td>", html)
        self.assertIn('<td class="num">$85,589</td>', html)

    def test_reader_pages_normalize_legacy_repeated_section_titles(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            packs = Path(td) / "packs"
            out = Path(td) / "site"

            cik = "0001045810"
            accession = "0001045810-25-000023"
            pack_dir = packs / cik / accession
            (pack_dir / "sections").mkdir(parents=True, exist_ok=True)

            raw_title = "/ Form 10-K Summary / Form 10-K Summary / Form 10-K Summary / 83 / 83 / 83"
            section_id = "10k_partiv_item16_form_10k_summary_form_10k"
            (pack_dir / "filing.full.md").write_text("# Filing\n", encoding="utf-8")
            (pack_dir / "sections" / f"{section_id}.md").write_text(
                f"Item 16. {raw_title}\n\nBody\n",
                encoding="utf-8",
            )

            manifest = {
                "schema_version": 1,
                "source": {},
                "filing": {
                    "cik": cik,
                    "accession": accession,
                    "form_type": "10-K",
                    "filing_date": "2025-02-18",
                    "company_name": "NVIDIA CORP",
                },
                "sections": [
                    {
                        "id": section_id,
                        "title": raw_title,
                        "path": f"sections/{section_id}.md",
                        "tokens_approx": 2,
                        "sha256": "0" * 64,
                    }
                ],
                "artifacts": {},
                "tokens_total": 2,
            }
            (pack_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

            build_site(packs, out)

            overview = (out / cik / accession / "index.html").read_text(encoding="utf-8")
            section_page = (
                out / cik / accession / "sections" / "item16_form_10k_summary_form_10k.html"
            ).read_text(encoding="utf-8")

            self.assertIn("Form 10-K Summary", overview)
            self.assertNotIn(raw_title, overview)
            self.assertIn("<h1>Form 10-K Summary</h1>", section_page)
            self.assertNotIn(raw_title, section_page)
            self.assertNotIn("(Chinese)", overview)


if __name__ == "__main__":
    unittest.main()
