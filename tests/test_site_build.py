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
            (pack_dir / "llms.txt").write_text("# Test\n", encoding="utf-8")
            (pack_dir / "sections" / "sec1.md").write_text("## Sec\n\nText\n", encoding="utf-8")

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
                "artifacts": {"filing.full.md": "0" * 64},
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
            self.assertTrue((out / cik / accession / "sections" / "sec1.html").exists())

    def test_markdown_to_html_sanitizes_links(self) -> None:
        md = "Click [bad](javascript:alert(1)) and [ok](https://example.com)."
        html = _markdown_to_html(md)
        self.assertNotIn("javascript:", html.lower())
        self.assertIn("https://example.com", html)


if __name__ == "__main__":
    unittest.main()
