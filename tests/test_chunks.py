"""Tests for semantic chunk generation."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from edgarpack.pack.chunks import chunk_section


class TestChunkBoundaries(unittest.TestCase):
    def test_boundaries_avoid_mid_word_splits(self) -> None:
        content = (
            "Revenue grew year over year. Margins expanded quarter over quarter. " * 80
        ).strip()
        chunks = chunk_section("sec", content, min_tokens=20, max_tokens=60)

        self.assertGreater(len(chunks), 1)
        for chunk in chunks[:-1]:
            end = chunk.char_end
            self.assertLess(end, len(content))
            self.assertTrue(
                content[end - 1].isspace() or content[end - 1] in ".!?" or content[end].isspace()
            )

    @patch("edgarpack.pack.chunks.has_tiktoken", return_value=False)
    @patch("edgarpack.pack.chunks.count_tokens", side_effect=lambda text: max(1, len(text) // 4))
    def test_hard_split_fallback_produces_valid_chunks(
        self,
        _mock_count_tokens,
        _mock_has_tiktoken,
    ) -> None:
        content = "x" * 5000
        chunks = chunk_section("sec", content, min_tokens=5, max_tokens=20)

        self.assertTrue(chunks)
        prev_end = 0
        for chunk in chunks:
            self.assertTrue(chunk.text)
            self.assertEqual(chunk.char_start, prev_end)
            self.assertGreater(chunk.char_end, chunk.char_start)
            self.assertLessEqual(chunk.char_end, len(content))
            prev_end = chunk.char_end

    def test_chunk_ids_are_deterministic(self) -> None:
        content = ("Paragraph one.\n\nParagraph two.\n\nParagraph three.\n\n" * 60).strip()
        first = chunk_section("sec", content, min_tokens=25, max_tokens=70)
        second = chunk_section("sec", content, min_tokens=25, max_tokens=70)

        self.assertEqual([c.chunk_id for c in first], [c.chunk_id for c in second])
        self.assertEqual([c.char_start for c in first], [c.char_start for c in second])
        self.assertEqual([c.char_end for c in first], [c.char_end for c in second])

    def test_empty_section_returns_no_chunks(self) -> None:
        self.assertEqual(chunk_section("sec", ""), [])


if __name__ == "__main__":
    unittest.main()
