"""Tests for insight layers."""

import json
import tempfile
from pathlib import Path

from edgarpack.insights.disclosures import detect_new_disclosures
from edgarpack.insights.language_shift import detect_language_shifts
from edgarpack.pack.manifest import compute_sha256


def _create_pack(
    pack_dir: Path,
    accession: str,
    filing_date: str,
    sections: dict[str, str],
) -> None:
    pack_dir.mkdir(parents=True, exist_ok=True)
    sections_dir = pack_dir / "sections"
    sections_dir.mkdir(exist_ok=True)

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
            "form_type": "10-K",
            "filing_date": filing_date,
            "company_name": "Test Corp",
        },
        "sections": section_list,
    }
    (pack_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def test_new_disclosure_detection():
    with tempfile.TemporaryDirectory() as tmp:
        prior_dir = Path(tmp) / "prior"
        current_dir = Path(tmp) / "current"

        prior_sections = {
            "10k_parti_item1a_risk_factors": (
                "We face competition in the semiconductor market.\n\n"
                "Our products may have defects that could harm our reputation."
            ),
        }
        current_sections = {
            "10k_parti_item1a_risk_factors": (
                "We face competition in the semiconductor market.\n\n"
                "Our products may have defects that could harm our reputation.\n\n"
                "New risk: U.S. export control regulations may restrict our ability to sell "
                "products in certain markets including China and require export licenses."
            ),
        }

        _create_pack(prior_dir, "acc-001", "2024-01-01", prior_sections)
        _create_pack(current_dir, "acc-002", "2025-01-01", current_sections)

        disclosures = detect_new_disclosures(current_dir, [prior_dir])
        assert len(disclosures) >= 1
        assert any("export control" in d.paragraph_text.lower() for d in disclosures)


def test_no_new_disclosures_when_identical():
    with tempfile.TemporaryDirectory() as tmp:
        prior_dir = Path(tmp) / "prior"
        current_dir = Path(tmp) / "current"

        sections = {
            "10k_parti_item1a_risk_factors": (
                "Standard risk factor one with enough words to meet the minimum.\n\n"
                "Standard risk factor two with enough words to meet the minimum threshold."
            ),
        }

        _create_pack(prior_dir, "acc-001", "2024-01-01", sections)
        _create_pack(current_dir, "acc-002", "2025-01-01", sections)

        disclosures = detect_new_disclosures(current_dir, [prior_dir])
        assert len(disclosures) == 0


def test_language_shift_detection():
    with tempfile.TemporaryDirectory() as tmp:
        before_dir = Path(tmp) / "before"
        after_dir = Path(tmp) / "after"

        before_sections = {
            "10k_parti_item1a_risk_factors": (
                "Original risk paragraph one.\n\n"
                "Original risk paragraph two.\n\n"
                "Original risk paragraph three.\n\n"
                "Original risk paragraph four."
            ),
        }
        after_sections = {
            "10k_parti_item1a_risk_factors": (
                "Completely rewritten risk paragraph with new language.\n\n"
                "Another totally different risk paragraph.\n\n"
                "Yet another brand new risk disclosure.\n\n"
                "Final new risk paragraph replacing all old content."
            ),
        }

        _create_pack(before_dir, "acc-001", "2024-01-01", before_sections)
        _create_pack(after_dir, "acc-002", "2025-01-01", after_sections)

        shifts = detect_language_shifts(before_dir, after_dir, threshold=0.25)
        assert len(shifts) >= 1
        assert shifts[0].change_intensity > 0.25
