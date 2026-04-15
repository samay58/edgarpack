"""Unit tests for the wrapped-label preprocessor in edgarpack.hk.extract.

The preprocessor joins a label line to the next line when the label wraps
across a newline, which happens in MiniMax's prospectus for 'Research and
development / expenses' and similar rows.
"""

from __future__ import annotations

from edgarpack.hk.extract import _merge_wrapped_labels


def test_merges_rd_label_across_newline():
    lines = [
        "Research and development",
        "expenses /H1118/H1118 (10,560) - (70,002) -",
    ]
    merged = _merge_wrapped_labels(lines)
    assert len(merged) == 1
    assert merged[0].startswith("Research and development expenses")
    assert "(10,560)" in merged[0]
    assert "(70,002)" in merged[0]


def test_does_not_merge_when_line_contains_amounts():
    lines = [
        "Research and development (10,560)",
        "expenses (70,002)",
    ]
    merged = _merge_wrapped_labels(lines)
    assert merged == lines, "rows with digits on both lines are real separate rows"


def test_does_not_merge_when_next_line_starts_with_capital_word():
    lines = [
        "Research and development",
        "Total operating expenses 50,000",
    ]
    merged = _merge_wrapped_labels(lines)
    assert merged == lines, "uppercase continuation word is a new row, not a wrap"


def test_preserves_unrelated_lines():
    lines = [
        "Year ended 31 December",
        "2022 2023 2024",
        "Revenue 100 200 300",
    ]
    assert _merge_wrapped_labels(lines) == lines


def test_merges_only_when_line1_matches_known_label_prefix():
    lines = [
        "Arbitrary free text",
        "continuation of arbitrary 1,234",
    ]
    # Not a known label prefix => no merge.
    assert _merge_wrapped_labels(lines) == lines
