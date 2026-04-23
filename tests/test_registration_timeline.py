"""Tests for the registration-class timeline series."""

import json
from pathlib import Path

from edgarpack.diff.timeline import build_registration_timeline


def _write_pack(root: Path, accession: str, form: str, filing_date: str) -> Path:
    pack = root / accession
    pack.mkdir(parents=True, exist_ok=True)
    manifest = {
        "filing": {
            "accession": accession,
            "form_type": form,
            "filing_date": filing_date,
            "cik": "0002021728",
        },
        "sections": [],
    }
    (pack / "manifest.json").write_text(json.dumps(manifest))
    return pack


def test_timeline_orders_by_filing_date(tmp_path):
    _write_pack(tmp_path, "A-3", "S-1/A", "2025-10-15")
    _write_pack(tmp_path, "A-1", "S-1", "2025-09-30")
    _write_pack(tmp_path, "A-4", "424B4", "2025-12-01")
    _write_pack(tmp_path, "A-2", "S-1/A", "2025-10-01")

    entries = build_registration_timeline(pack_root=tmp_path, cik="0002021728")
    accessions = [e.accession for e in entries]
    assert accessions == ["A-1", "A-2", "A-3", "A-4"]


def test_timeline_excludes_non_registration_forms(tmp_path):
    _write_pack(tmp_path, "A-1", "S-1", "2025-09-30")
    _write_pack(tmp_path, "K-1", "10-K", "2026-03-15")

    entries = build_registration_timeline(pack_root=tmp_path, cik="0002021728")
    assert [e.accession for e in entries] == ["A-1"]


def test_timeline_scopes_to_cik(tmp_path):
    _write_pack(tmp_path, "A-1", "S-1", "2025-09-30")
    other = tmp_path / "other"
    other.mkdir()
    other_pack = other / "B-1"
    other_pack.mkdir()
    (other_pack / "manifest.json").write_text(
        json.dumps(
            {
                "filing": {
                    "accession": "B-1",
                    "form_type": "S-1",
                    "filing_date": "2025-08-01",
                    "cik": "0001234567",
                },
                "sections": [],
            }
        )
    )
    entries = build_registration_timeline(pack_root=tmp_path, cik="0002021728")
    assert [e.accession for e in entries] == ["A-1"]


def test_timeline_skips_manifests_with_empty_cik(tmp_path):
    # Previously these leaked into the result because the CIK check was
    # only applied when filing_cik was truthy. Now they must be dropped.
    _write_pack(tmp_path, "A-1", "S-1", "2025-09-30")
    orphan = tmp_path / "orphan"
    orphan.mkdir()
    (orphan / "manifest.json").write_text(
        json.dumps(
            {
                "filing": {
                    "accession": "ORPHAN",
                    "form_type": "S-1",
                    "filing_date": "2025-07-01",
                    "cik": "",
                },
                "sections": [],
            }
        )
    )
    entries = build_registration_timeline(pack_root=tmp_path, cik="0002021728")
    assert [e.accession for e in entries] == ["A-1"]
