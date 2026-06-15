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


def test_f1_anchor_detected_with_curly_apostrophe():
    title = "Management’s Discussion and Analysis of Financial Condition and Results of Operations"
    md = f"# {title}\n\nBody text.\n"
    assert [m.title for m in find_sections(md, "F-1")] == [title]


@pytest.mark.parametrize(
    "anchor",
    [
        "Summary",
        "The Offering",
        "Summary Financial and Other Information",
        "Cautionary Statement Regarding Forward-Looking Statements",
        "Special Note Regarding Forward-Looking Statements",
        "Presentation of Financial and Other Information",
        "Non-GAAP Financial Measures",
        "Industry and Market Data",
        "Glossary of Certain Terms",
        "Exchange Rate Information",
        "Enforcement of Civil Liabilities",
        "Enforcement of Judgments",
        "Dividend Policy",
        "Corporate Reorganization",
        "Operating and Financial Review and Prospects",
        "Management",
        "Management and Executive Remuneration",
        "Related Party Transactions",
        "Principal Shareholders",
        "Principal and Selling Shareholders",
        "Description of Share Capital",
        "Description of Share Capital and Articles of Association",
        "Comparison of Swiss Corporate Law and U.S. Corporate Law",
        "Ordinary Shares Eligible for Future Sale",
        "Taxation",
        "Material Tax Considerations",
        "Expenses of the Offering",
        "Expenses Related to the Offering",
        "Legal Matters",
        "Experts",
        "Where You Can Find More Information",
        "Where You Can Find Additional Information",
        "Index to Financial Statements",
    ],
)
def test_f1_foreign_issuer_anchor_detected(anchor: str):
    md = f"# {anchor}\n\nBody text for {anchor}.\n"
    titles = [m.title for m in find_sections(md, "F-1")]
    assert titles == [anchor]
