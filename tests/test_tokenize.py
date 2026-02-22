"""Tests for tokenizer fallback behavior."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from edgarpack.parse.tokenize import count_tokens, estimate_tokens, truncate_to_tokens


class TestTokenizeFallback(unittest.TestCase):
    def test_count_tokens_falls_back_when_encoder_errors(self) -> None:
        text = "offline encoding fallback" * 8
        with (
            patch("edgarpack.parse.tokenize.tiktoken", object()),
            patch("edgarpack.parse.tokenize.get_encoder", side_effect=RuntimeError("offline")),
        ):
            self.assertEqual(count_tokens(text), estimate_tokens(text))

    def test_truncate_falls_back_when_encoder_errors(self) -> None:
        text = "x" * 200
        with (
            patch("edgarpack.parse.tokenize.tiktoken", object()),
            patch("edgarpack.parse.tokenize.get_encoder", side_effect=RuntimeError("offline")),
        ):
            truncated = truncate_to_tokens(text, max_tokens=10)
            self.assertEqual(truncated, text[:40])


if __name__ == "__main__":
    unittest.main()
