"""Pack-level S-1 metrics aggregation."""

from __future__ import annotations

import json
from pathlib import Path

from edgarpack.query.kpi_discover import extract_s1_metrics_from_pack
from edgarpack.query.registration_profile import build_registration_profile

_S1_SAMPLE = """\
# Prospectus Summary

We estimate the total addressable market at $150 billion, growing at 34% CAGR.

# Use of Proceeds

We intend to use the net proceeds as follows: approximately $150.0 million for
research and development, $80.0 million for manufacturing capacity.

# Dilution

You will experience immediate dilution of $12.50 per share.

# Principal Stockholders

Name                        Shares           Percent
Acme Capital LP             12,500,000       18.4%
Founder Jane Doe             9,000,000       13.2%

# Underwriting

The lock-up period will be 180 days from the date of this prospectus.
"""


def _write_pack(
    root: Path,
    accession: str,
    form: str,
    markdown: str = _S1_SAMPLE,
) -> Path:
    pack = root / accession
    pack.mkdir(parents=True, exist_ok=True)
    (pack / "manifest.json").write_text(
        json.dumps(
            {
                "filing": {"accession": accession, "form_type": form, "cik": "0002021728"},
                "sections": [],
            }
        )
    )
    (pack / "filing.full.md").write_text(markdown)
    return pack


def test_bundle_aggregates_all_five_extractors(tmp_path):
    pack = _write_pack(tmp_path, "test-accn-1", "S-1")
    bundle = extract_s1_metrics_from_pack(pack)

    assert bundle is not None
    assert bundle.accession == "test-accn-1"
    assert bundle.form_type == "S-1"
    assert bundle.framing, "expected TAM / CAGR framing hits"
    assert bundle.use_of_proceeds, "expected use-of-proceeds items"
    assert bundle.dilution, "expected dilution claim"
    assert bundle.lockup, "expected lockup claim"
    assert bundle.principal_holders, "expected principal-holder rows"
    assert bundle.total_hits == (
        len(bundle.framing)
        + len(bundle.use_of_proceeds)
        + len(bundle.dilution)
        + len(bundle.lockup)
        + len(bundle.principal_holders)
    )


def test_registration_profile_dedupes_repeated_framing_claims(tmp_path):
    markdown = """\
# Prospectus Summary

We estimate our TAM to be approximately $69.1 billion.
We estimate our TAM to be approximately $69.1 billion.
"""
    pack = _write_pack(tmp_path, "test-accn-profile", "S-1", markdown=markdown)
    profile = build_registration_profile(pack)

    assert profile is not None
    framing = [group for group in profile.disclosures if group.label == "framing claims"]
    assert len(framing) == 1
    assert framing[0].claims == ("TAM to be approximately $69.1 billion",)


def test_bundle_scopes_use_of_proceeds_to_section_files_when_available(tmp_path):
    markdown = """\
# Summary Consolidated Financial Data

Revenue was $510.0 million for the year ended December 31, 2025.

# Use of Proceeds

We intend to use approximately $150.0 million for research and development.
"""
    pack = _write_pack(tmp_path, "test-accn-sections", "S-1", markdown=markdown)
    sections = pack / "sections"
    sections.mkdir()
    (sections / "s1_itemother_use_of_proceeds.md").write_text(
        "# Use of Proceeds\n\n"
        "We intend to use approximately $150.0 million for research and development.\n",
        encoding="utf-8",
    )

    bundle = extract_s1_metrics_from_pack(pack)

    assert bundle is not None
    assert [hit.claim for hit in bundle.use_of_proceeds] == [
        "approximately $150.0 million for research and development"
    ]


def test_bundle_returns_none_for_non_registration_form(tmp_path):
    pack = _write_pack(tmp_path, "test-accn-10k", "10-K")
    assert extract_s1_metrics_from_pack(pack) is None


def test_bundle_returns_none_when_markdown_missing(tmp_path):
    pack = tmp_path / "missing-md"
    pack.mkdir()
    (pack / "manifest.json").write_text(
        json.dumps({"filing": {"accession": "x", "form_type": "S-1"}, "sections": []})
    )
    assert extract_s1_metrics_from_pack(pack) is None


def test_bundle_returns_none_when_manifest_missing(tmp_path):
    pack = tmp_path / "missing-manifest"
    pack.mkdir()
    (pack / "filing.full.md").write_text(_S1_SAMPLE)
    assert extract_s1_metrics_from_pack(pack) is None


def test_bundle_tolerates_corrupt_manifest(tmp_path):
    pack = tmp_path / "bad-manifest"
    pack.mkdir()
    (pack / "manifest.json").write_text("{not: valid json")
    (pack / "filing.full.md").write_text(_S1_SAMPLE)
    assert extract_s1_metrics_from_pack(pack) is None
