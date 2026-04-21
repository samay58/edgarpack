from __future__ import annotations

import io
import unittest
from unittest.mock import patch


class TestOsc8Helper(unittest.TestCase):
    def test_osc8_wraps_url_and_label(self) -> None:
        from edgarpack.query.links import osc8

        out = osc8("https://example.test/path", "label")
        self.assertEqual(out, "\x1b]8;;https://example.test/path\x1b\\label\x1b]8;;\x1b\\")

    def test_osc8_empty_url_returns_label_untouched(self) -> None:
        from edgarpack.query.links import osc8

        self.assertEqual(osc8("", "label"), "label")


class TestSupportsOsc8(unittest.TestCase):
    def _stream(self, *, tty: bool) -> io.StringIO:
        s = io.StringIO()
        s.isatty = lambda: tty  # type: ignore[method-assign]
        return s

    def test_non_tty_returns_false(self) -> None:
        from edgarpack.query.links import supports_osc8

        self.assertFalse(supports_osc8(self._stream(tty=False)))

    def test_no_color_env_returns_false(self) -> None:
        from edgarpack.query.links import supports_osc8

        with patch.dict("os.environ", {"NO_COLOR": "1"}, clear=False):
            self.assertFalse(supports_osc8(self._stream(tty=True)))

    def test_iterm2_detected(self) -> None:
        from edgarpack.query.links import supports_osc8

        with patch.dict("os.environ", {"TERM_PROGRAM": "iTerm.app", "NO_COLOR": ""}, clear=False):
            self.assertTrue(supports_osc8(self._stream(tty=True)))

    def test_ghostty_detected(self) -> None:
        from edgarpack.query.links import supports_osc8

        with patch.dict("os.environ", {"TERM_PROGRAM": "ghostty", "NO_COLOR": ""}, clear=False):
            self.assertTrue(supports_osc8(self._stream(tty=True)))

    def test_xterm_fallback(self) -> None:
        from edgarpack.query.links import supports_osc8

        with patch.dict(
            "os.environ",
            {"TERM_PROGRAM": "", "TERM": "xterm-256color", "NO_COLOR": ""},
            clear=False,
        ):
            self.assertTrue(supports_osc8(self._stream(tty=True)))


class TestCompactUrl(unittest.TestCase):
    def test_strips_https_www(self) -> None:
        from edgarpack.query.links import compact_url

        self.assertEqual(
            compact_url(
                "https://www.sec.gov/Archives/edgar/data/1326801/000132680124000073/goog-20240629.htm#f-123"
            ),
            "sec.gov/Archives/edgar/data/1326801/000132680124000073/goog-20240629.htm#f-123",
        )

    def test_strips_https_only(self) -> None:
        from edgarpack.query.links import compact_url

        self.assertEqual(compact_url("https://sec.gov/x"), "sec.gov/x")

    def test_leaves_unknown_scheme_alone(self) -> None:
        from edgarpack.query.links import compact_url

        self.assertEqual(compact_url("ftp://example.test"), "ftp://example.test")

    def test_empty_returns_empty(self) -> None:
        from edgarpack.query.links import compact_url

        self.assertEqual(compact_url(""), "")
