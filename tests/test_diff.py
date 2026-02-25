"""Tests for the diff engine."""

import json
import tempfile
from pathlib import Path

from edgarpack.diff.models import ChangeType
from edgarpack.diff.section_diff import diff_filings
from edgarpack.diff.text_diff import _jaccard, _split_paragraphs, diff_paragraphs

# --- text_diff tests ---


def test_jaccard_identical():
    assert _jaccard("hello world", "hello world") == 1.0


def test_jaccard_disjoint():
    assert _jaccard("hello world", "foo bar") == 0.0


def test_jaccard_partial():
    sim = _jaccard("hello world foo", "hello world bar")
    assert 0.3 < sim < 0.8


def test_jaccard_empty():
    assert _jaccard("", "") == 1.0
    assert _jaccard("hello", "") == 0.0


def test_split_paragraphs():
    text = "First paragraph.\n\nSecond paragraph.\n\n\nThird paragraph."
    paras = _split_paragraphs(text)
    assert len(paras) == 3
    assert paras[0] == "First paragraph."
    assert paras[1] == "Second paragraph."
    assert paras[2] == "Third paragraph."


def test_diff_paragraphs_identical():
    text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
    deltas = diff_paragraphs(text, text)
    assert all(d.change_type == ChangeType.UNCHANGED for d in deltas)
    assert len(deltas) == 3


def test_diff_paragraphs_added():
    old = "Paragraph one.\n\nParagraph two."
    new = "Paragraph one.\n\nParagraph two.\n\nBrand new paragraph."
    deltas = diff_paragraphs(old, new)
    added = [d for d in deltas if d.change_type == ChangeType.ADDED]
    assert len(added) == 1
    assert "Brand new" in added[0].new_text


def test_diff_paragraphs_removed():
    old = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
    new = "Paragraph one.\n\nParagraph three."
    deltas = diff_paragraphs(old, new)
    removed = [d for d in deltas if d.change_type == ChangeType.REMOVED]
    assert len(removed) == 1
    assert "two" in removed[0].old_text


def test_diff_paragraphs_modified():
    old = "The company faces significant risk from export controls.\n\nOther risk factors apply."
    new = (
        "The company faces major risk from new export control regulations."
        "\n\nOther risk factors apply."
    )
    deltas = diff_paragraphs(old, new)
    modified = [d for d in deltas if d.change_type == ChangeType.MODIFIED]
    assert len(modified) == 1
    assert modified[0].similarity > 0.4


# --- section_diff tests ---


def _create_pack(
    pack_dir: Path,
    accession: str,
    filing_date: str,
    company_name: str,
    form_type: str,
    sections: dict[str, str],
) -> None:
    """Create a minimal pack directory for testing."""
    pack_dir.mkdir(parents=True, exist_ok=True)
    sections_dir = pack_dir / "sections"
    sections_dir.mkdir(exist_ok=True)

    from edgarpack.pack.manifest import compute_sha256

    section_list = []
    for sid, content in sections.items():
        section_path = sections_dir / f"{sid}.md"
        section_path.write_text(content, encoding="utf-8")
        section_list.append(
            {
                "id": sid,
                "title": sid.replace("_", " ").title(),
                "path": f"sections/{sid}.md",
                "char_start": 0,
                "char_end": len(content),
                "tokens_approx": len(content.split()),
                "sha256": compute_sha256(content),
            }
        )

    manifest = {
        "schema_version": 1,
        "filing": {
            "cik": "0001045810",
            "accession": accession,
            "form_type": form_type,
            "filing_date": filing_date,
            "company_name": company_name,
        },
        "sections": section_list,
        "artifacts": {},
        "warnings": [],
        "tokens_total": sum(s["tokens_approx"] for s in section_list),
    }
    (pack_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def test_diff_filings_identical():
    with tempfile.TemporaryDirectory() as tmp:
        sections = {
            "10k_parti_item1_business": "This is the business section.\n\nIt has two paragraphs.",
            "10k_parti_item1a_risk_factors": "Risk factors are discussed here.",
        }
        before_dir = Path(tmp) / "before"
        after_dir = Path(tmp) / "after"
        _create_pack(before_dir, "acc-001", "2024-01-01", "Test Corp", "10-K", sections)
        _create_pack(after_dir, "acc-002", "2025-01-01", "Test Corp", "10-K", sections)

        result = diff_filings(before_dir, after_dir)
        assert result.sections_unchanged == 2
        assert result.sections_modified == 0
        assert result.overall_change_intensity == 0.0


def test_diff_filings_modified():
    with tempfile.TemporaryDirectory() as tmp:
        before_sections = {
            "10k_parti_item1_business": "Old business description.\n\nOld second paragraph.",
            "10k_parti_item1a_risk_factors": "Original risk factors.",
        }
        after_sections = {
            "10k_parti_item1_business": (
                "New business description with changes.\n\nOld second paragraph."
            ),
            "10k_parti_item1a_risk_factors": "Original risk factors.",
        }

        before_dir = Path(tmp) / "before"
        after_dir = Path(tmp) / "after"
        _create_pack(before_dir, "acc-001", "2024-01-01", "Test Corp", "10-K", before_sections)
        _create_pack(after_dir, "acc-002", "2025-01-01", "Test Corp", "10-K", after_sections)

        result = diff_filings(before_dir, after_dir)
        assert result.sections_unchanged == 1  # risk factors unchanged
        assert result.sections_modified == 1  # business modified
        assert result.overall_change_intensity > 0


def test_diff_filings_added_section():
    with tempfile.TemporaryDirectory() as tmp:
        before_sections = {
            "10k_parti_item1_business": "Business section.",
        }
        after_sections = {
            "10k_parti_item1_business": "Business section.",
            "10k_parti_item1a_risk_factors": "New risk section.",
        }

        before_dir = Path(tmp) / "before"
        after_dir = Path(tmp) / "after"
        _create_pack(before_dir, "acc-001", "2024-01-01", "Test Corp", "10-K", before_sections)
        _create_pack(after_dir, "acc-002", "2025-01-01", "Test Corp", "10-K", after_sections)

        result = diff_filings(before_dir, after_dir)
        assert result.sections_added == 1
        assert result.sections_unchanged == 1


def test_diff_filings_removed_section():
    with tempfile.TemporaryDirectory() as tmp:
        before_sections = {
            "10k_parti_item1_business": "Business section.",
            "10k_parti_item1a_risk_factors": "Old risk section.",
        }
        after_sections = {
            "10k_parti_item1_business": "Business section.",
        }

        before_dir = Path(tmp) / "before"
        after_dir = Path(tmp) / "after"
        _create_pack(before_dir, "acc-001", "2024-01-01", "Test Corp", "10-K", before_sections)
        _create_pack(after_dir, "acc-002", "2025-01-01", "Test Corp", "10-K", after_sections)

        result = diff_filings(before_dir, after_dir)
        assert result.sections_removed == 1
