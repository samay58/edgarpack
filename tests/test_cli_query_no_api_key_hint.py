"""When `query` on a pre-IPO filer finds no periodic data AND the S-1
extraction path fails because ANTHROPIC_API_KEY is missing, print a single
helpful stderr line pointing the user to `which`. Do not crash."""

from edgarpack.cli import _render_query_no_api_key_hint


def test_hint_mentions_anthropic_key():
    msg = _render_query_no_api_key_hint()
    assert "ANTHROPIC_API_KEY" in msg


def test_hint_mentions_edgarpack_which_as_alternative():
    msg = _render_query_no_api_key_hint()
    assert "edgarpack which" in msg


def test_hint_fits_on_one_line_when_wrapped_by_terminal():
    msg = _render_query_no_api_key_hint()
    assert "\n" not in msg
