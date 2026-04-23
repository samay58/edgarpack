"""S-1 anchor detection via the sectionizer's general-form whitelist."""

from pathlib import Path

import pytest

from edgarpack.parse.sectionize import find_sections

FIXTURE = Path(__file__).parent / "fixtures" / "cerebras_s1_sample.md"


def _titles(form: str) -> list[str]:
    md = FIXTURE.read_text(encoding="utf-8")
    return [m.title for m in find_sections(md, form)]


# Every whitelist entry that appears in the fixture. Kept in sync with
# S1_ANCHOR_TITLES in edgarpack/parse/sectionize.py.
_EXPECTED_ANCHORS = [
    "Prospectus Summary",
    "Risk Factors",
    "Use of Proceeds",
    "Capitalization",
    "Dilution",
    "Management's Discussion and Analysis",
    "Business",
    "Principal Stockholders",
    "Selling Stockholders",
    "Description of Capital Stock",
    "Underwriting",
]


@pytest.mark.parametrize("anchor", _EXPECTED_ANCHORS)
def test_s1_anchor_detected(anchor: str):
    assert any(anchor in t for t in _titles("S-1")), f"anchor {anchor!r} not found"


def test_s1a_normalizes_like_s1():
    # `/A` amendments normalize to the base form, so they share anchors.
    assert _titles("S-1") == _titles("S-1/A")
