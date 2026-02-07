"""Tests for pack building, manifest determinism, and chunking."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

from edgarpack.pack.chunks import chunk_section
from edgarpack.pack.manifest import compute_sha256, create_manifest, write_manifest
from edgarpack.sec.submissions import FilingMeta


class TestComputeSha256(unittest.TestCase):
    def test_hash_string(self) -> None:
        result = compute_sha256("hello world")
        self.assertEqual(
            result,
            "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9",
        )

    def test_deterministic(self) -> None:
        content = "test content for hashing"
        self.assertEqual(compute_sha256(content), compute_sha256(content))


class TestManifestDeterminism(unittest.TestCase):
    def test_create_manifest_uses_stable_timestamp(self) -> None:
        meta = FilingMeta(
            cik="0000000001",
            accession="0000000001-24-000001",
            form_type="10-Q",
            filing_date=date(2024, 1, 15),
            primary_document="doc.htm",
            company_name="Test Co",
        )

        class _S:
            id = "unknown_01"
            title = "Unknown"
            content = "Body"
            char_start = 0
            char_end = 4

        manifest = create_manifest(
            filing_meta=meta,
            sections=[_S()],
            artifacts={"filing.full.md": compute_sha256("Body")},
            warnings=[],
            tokens_total=1,
            source_url="https://example.test",
        )

        expected = datetime(2024, 1, 15, tzinfo=UTC)
        self.assertEqual(manifest.generated_at, expected)
        self.assertEqual(manifest.source.fetched_at, expected)

    def test_write_manifest_is_byte_stable(self) -> None:
        meta = FilingMeta(
            cik="0000000001",
            accession="0000000001-24-000001",
            form_type="10-Q",
            filing_date=date(2024, 1, 15),
            primary_document="doc.htm",
            company_name="Test Co",
        )

        class _S:
            id = "unknown_01"
            title = "Unknown"
            content = "Body"
            char_start = 0
            char_end = 4

        manifest = create_manifest(
            filing_meta=meta,
            sections=[_S()],
            artifacts={"filing.full.md": compute_sha256("Body")},
            warnings=["w"],
            tokens_total=1,
            source_url="https://example.test",
        )

        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            p1 = write_manifest(manifest, out)
            b1 = p1.read_bytes()
            p2 = write_manifest(manifest, out)
            b2 = p2.read_bytes()
            self.assertEqual(b1, b2)
            self.assertTrue(b1.endswith(b"\n"))


class TestChunkSection(unittest.TestCase):
    def test_small_section_single_chunk(self) -> None:
        content = "This is a small section."
        chunks = chunk_section("sec1", content, min_tokens=1, max_tokens=5000)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].char_start, 0)
        self.assertEqual(chunks[0].char_end, len(content))

    def test_chunk_boundaries_never_negative(self) -> None:
        content = ("Paragraph one.\n\n" + "Sentence. " * 200).strip()
        chunks = chunk_section("sec1", content, min_tokens=1, max_tokens=50)
        for c in chunks:
            self.assertGreaterEqual(c.char_start, 0)
            self.assertGreater(c.char_end, c.char_start)
            self.assertLessEqual(c.char_end, len(content))

    def test_prefers_chunk_meeting_min_tokens(self) -> None:
        para = ("word " * 120).strip()
        content = f"{para}\n\n{para}\n\n{para}"
        single_tokens = chunk_section(
            "tmp",
            para,
            min_tokens=1,
            max_tokens=10_000,
        )[0].tokens
        double_tokens = chunk_section(
            "tmp",
            f"{para}\n\n{para}",
            min_tokens=1,
            max_tokens=10_000,
        )[0].tokens
        min_tokens = single_tokens + 1
        max_tokens = double_tokens
        chunks = chunk_section("sec1", content, min_tokens=min_tokens, max_tokens=max_tokens)
        self.assertTrue(chunks)
        self.assertGreaterEqual(chunks[0].tokens, min_tokens)
        self.assertLessEqual(chunks[0].tokens, max_tokens)


class TestBuildPackDeterminism(unittest.IsolatedAsyncioTestCase):
    async def test_build_pack_deterministic_files(self) -> None:
        from edgarpack.pack.build import build_pack

        meta = FilingMeta(
            cik="0000000001",
            accession="0000000001-24-000001",
            form_type="10-Q",
            filing_date=date(2024, 1, 15),
            primary_document="doc.htm",
            company_name="Test Co",
        )

        html = (
            b"<html><body>"
            b"<h1>PART I</h1>"
            b"<h2>ITEM 1. BUSINESS</h2><p>A</p>"
            b"<h2>ITEM 2. MANAGEMENT'S DISCUSSION</h2><p>B</p>"
            b"<h1>PART II</h1>"
            b"<h2>ITEM 1. LEGAL PROCEEDINGS</h2><p>C</p>"
            b"</body></html>"
        )

        async def _run_once(tmp: Path) -> dict[str, bytes]:
            await build_pack(
                cik=meta.cik,
                accession=meta.accession,
                out_dir=tmp,
                with_chunks=False,
                with_xbrl=False,
                force=True,
            )
            pack_dir = tmp / meta.cik / meta.accession
            return {
                "manifest": (pack_dir / "manifest.json").read_bytes(),
                "llms": (pack_dir / "llms.txt").read_bytes(),
                "full": (pack_dir / "filing.full.md").read_bytes(),
            }

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            with (
                patch(
                    "edgarpack.pack.build.get_filing_by_accession",
                    new=AsyncMock(return_value=meta),
                ),
                patch(
                    "edgarpack.pack.build.fetch_filing_html",
                    new=AsyncMock(return_value=[("doc.htm", html)]),
                ),
            ):
                a = await _run_once(tmp)
                b = await _run_once(tmp)

        self.assertEqual(a["manifest"], b["manifest"])
        self.assertEqual(a["llms"], b["llms"])
        self.assertEqual(a["full"], b["full"])

        # Ensure llms.txt is listed in artifacts in the manifest
        manifest = json.loads(a["manifest"].decode("utf-8"))
        self.assertIn("llms.txt", manifest.get("artifacts", {}))


if __name__ == "__main__":
    unittest.main()
