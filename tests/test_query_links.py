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


class TestRenderCitationLinesRouting(unittest.TestCase):
    def _record(self) -> dict[str, object]:
        return {
            "form_type": "10-K",
            "fiscal_label": "FY2024",
            "period": "2024-06-29",
            "accession": "0001652044-24-000073",
            "filed": "2024-07-31",
            "primary_link": (
                "https://www.sec.gov/Archives/edgar/data/1652044/"
                "000165204424000073/goog-20240629.htm#f-123"
            ),
            "primary_link_type": "source_excerpt",
        }

    def test_no_separate_link_line_in_output(self) -> None:
        from edgarpack.cli import _render_citation_lines

        with patch("edgarpack.query.links.supports_osc8", return_value=False):
            lines = _render_citation_lines("C1", self._record(), show_links="primary", width=120)
        joined = "\n".join(lines)
        self.assertNotIn("link(source_excerpt)", joined)
        # Fallback appends compact URL to footer id line.
        self.assertIn("sec.gov/Archives", joined)
        self.assertNotIn("https://www.", joined)

    def test_osc8_wrap_when_terminal_supports(self) -> None:
        from edgarpack.cli import _render_citation_lines

        with patch("edgarpack.query.links.supports_osc8", return_value=True):
            lines = _render_citation_lines("C1", self._record(), show_links="primary", width=120)
        joined = "\n".join(lines)
        self.assertIn("\x1b]8;;", joined)
        # In OSC-8 mode, only the hyperlink payload carries the URL; no
        # compact-url fallback is appended inline. The URL appears exactly
        # once (inside the OSC-8 escape sequence).
        self.assertEqual(joined.count("sec.gov/Archives"), 1)

    def test_show_links_all_includes_compact_url(self) -> None:
        from edgarpack.cli import _render_citation_lines

        record = self._record()
        record["links"] = {
            "source_excerpt": record["primary_link"],
            "canonical": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=1652044",
        }
        with patch("edgarpack.query.links.supports_osc8", return_value=True):
            lines = _render_citation_lines("C1", record, show_links="all", width=120)
        joined = "\n".join(lines)
        self.assertIn("sec.gov/cgi-bin", joined)

    def test_show_links_none_prints_marker_only(self) -> None:
        from edgarpack.cli import _render_citation_lines

        with patch("edgarpack.query.links.supports_osc8", return_value=True):
            lines = _render_citation_lines("C1", self._record(), show_links="none", width=120)
        joined = "\n".join(lines)
        self.assertNotIn("\x1b]8;;", joined)
        self.assertNotIn("sec.gov", joined)
