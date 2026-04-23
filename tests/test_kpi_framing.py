"""Tests for the framing-metric pattern group (TAM / market size / CAGR)."""

from edgarpack.query.kpi_discover import extract_framing_claims


def test_tam_dollar_pattern():
    text = "We estimate the total addressable market at $150 billion."
    hits = extract_framing_claims(text)
    assert any(h.metric_kind == "framing" for h in hits)
    assert any("$150" in h.claim for h in hits)


def test_addressable_market_pattern():
    text = "The addressable market for AI inference is approximately $90 billion."
    hits = extract_framing_claims(text)
    assert any(h.metric_kind == "framing" for h in hits)


def test_cagr_pattern():
    text = "The market is growing at 34% CAGR through 2030."
    hits = extract_framing_claims(text)
    assert any(h.metric_kind == "framing" for h in hits)
    assert any("34%" in h.claim for h in hits)


def test_billion_opportunity_pattern():
    text = "This represents a $500 billion opportunity for our company."
    hits = extract_framing_claims(text)
    assert any(h.metric_kind == "framing" for h in hits)


def test_no_framing_in_boilerplate_text():
    text = "This prospectus contains forward-looking statements within the meaning of Section 27A."
    hits = extract_framing_claims(text)
    assert hits == []
