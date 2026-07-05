"""has_registration_pack_for_cik must accept registration-family amendments.

Before this fix, a form_type="F-1" exists-check normalized to "F-1" and
compared it for exact equality against an existing pack's normalized form
type. An existing F-1/A pack normalizes to "F-1/A", which never equals
"F-1", so the exists-check reported false and the registration shortcut
redundantly rebuilt the original F-1 on every invocation.
"""

from __future__ import annotations

import json
from pathlib import Path

from edgarpack.query.s1_financials import has_registration_pack_for_cik


def _write_pack(root: Path, accession: str, form_type: str, cik: str = "0002021728") -> Path:
    pack = root / accession
    pack.mkdir(parents=True, exist_ok=True)
    (pack / "filing.full.md").write_text("# Selected Financial Data\n\nRevenue 1", encoding="utf-8")
    (pack / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "filing": {
                    "accession": accession,
                    "form_type": form_type,
                    "filing_date": "2024-09-30",
                    "cik": cik,
                    "company_name": "Neutron Holdings, Inc.",
                },
                "sections": [],
                "parser_version": "test",
            }
        ),
        encoding="utf-8",
    )
    return pack


def test_f1_amendment_pack_satisfies_f1_exists_check(tmp_path):
    _write_pack(tmp_path, "0001628280-24-000099", "F-1/A")

    assert has_registration_pack_for_cik("0002021728", tmp_path, form_type="F-1")


def test_s1_amendment_pack_satisfies_s1_exists_check(tmp_path):
    _write_pack(tmp_path, "0001628280-24-000010", "S-1/A")

    assert has_registration_pack_for_cik("0002021728", tmp_path, form_type="S-1")


def test_f1_exists_check_does_not_match_s1_family(tmp_path):
    _write_pack(tmp_path, "0001628280-24-000010", "S-1/A")

    assert not has_registration_pack_for_cik("0002021728", tmp_path, form_type="F-1")


def test_exact_accession_pin_still_bypasses_family_matching(tmp_path):
    _write_pack(tmp_path, "0001628280-24-000099", "F-1/A")

    assert has_registration_pack_for_cik(
        "0002021728",
        tmp_path,
        form_type="F-1",
        accession="0001628280-24-000099",
    )
    assert not has_registration_pack_for_cik(
        "0002021728",
        tmp_path,
        form_type="F-1",
        accession="0000000000-00-000000",
    )
