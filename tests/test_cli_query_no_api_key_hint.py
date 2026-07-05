"""When `query` on a pre-IPO filer finds no periodic data AND the S-1
extraction path fails because ANTHROPIC_API_KEY is missing, print a single
helpful stderr line pointing the user to `which`. Do not crash."""

from types import SimpleNamespace

from edgarpack.cli import (
    _registration_extraction_failure_message,
    _render_query_extraction_failed_hint,
    _render_query_no_api_key_hint,
)


def test_hint_mentions_anthropic_key():
    msg = _render_query_no_api_key_hint()
    assert "ANTHROPIC_API_KEY" in msg


def test_hint_mentions_edgarpack_which_as_alternative():
    msg = _render_query_no_api_key_hint()
    assert "edgarpack which" in msg


def test_hint_fits_on_one_line_when_wrapped_by_terminal():
    msg = _render_query_no_api_key_hint()
    assert "\n" not in msg


def _result_with_diagnostics(diags):
    return SimpleNamespace(diagnostics=diags)


def test_extraction_failure_message_reports_runtime_failure():
    # Fix 2 (CLI): a runtime call failure surfaces its diagnostic message so the
    # user learns the extraction failed and can retry.
    result = _result_with_diagnostics(
        [
            SimpleNamespace(
                metric="extraction", message="registration extraction llm_call_failed: 429"
            )
        ]
    )
    msg = _registration_extraction_failure_message([result])
    assert msg is not None and "llm_call_failed" in msg
    hint = _render_query_extraction_failed_hint(msg)
    assert "Retry" in hint
    assert "\n" not in hint


def test_extraction_failure_message_skips_missing_key():
    # The missing-key case is handled by the no_api_key hint, so the
    # extraction-failed path must not double-report it.
    result = _result_with_diagnostics(
        [SimpleNamespace(metric="extraction", message="registration extraction no_api_key")]
    )
    assert _registration_extraction_failure_message([result]) is None
