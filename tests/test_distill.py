from __future__ import annotations

import csv
import json
from pathlib import Path

from edgarpack.cli import main
from edgarpack.distill import check_distill_bundle
from edgarpack.query.s1_financials import SCHEMA_VERSION, source_sha256_for_pack

_S1_TEXT = """\
# Prospectus Summary

We estimate the total addressable market at $150 billion.

# Use of Proceeds

We intend to use approximately $150.0 million for research and development.

# Dilution

You will experience immediate dilution of $12.50 per share.

# Principal Stockholders

Acme Capital LP             12,500,000       18.4%

# Underwriting

The lock-up period will be 180 days from the date of this prospectus.
"""


def _write_s1_pack(root: Path, accession: str = "0001628280-26-032523") -> Path:
    pack = root / "packs" / "0001699963" / accession
    sections = pack / "sections"
    sections.mkdir(parents=True)
    (pack / "filing.full.md").write_text(_S1_TEXT, encoding="utf-8")
    (sections / "s1_itemother_prospectus_summary.md").write_text(
        "# Prospectus Summary\n\nWe estimate the total addressable market at $150 billion.\n",
        encoding="utf-8",
    )
    (sections / "s1_itemother_use_of_proceeds.md").write_text(
        "# Use of Proceeds\n\n"
        "We intend to use approximately $150.0 million for research and development.\n",
        encoding="utf-8",
    )
    (sections / "s1_itemother_dilution.md").write_text(
        "# Dilution\n\nYou will experience immediate dilution of $12.50 per share.\n",
        encoding="utf-8",
    )
    (sections / "s1_itemother_principal.md").write_text(
        "# Principal Stockholders\n\nAcme Capital LP             12,500,000       18.4%\n",
        encoding="utf-8",
    )
    (sections / "s1_itemother_underwriting.md").write_text(
        "# Underwriting\n\n"
        "The lock-up period will be 180 days from the date of this prospectus.\n",
        encoding="utf-8",
    )
    manifest = {
        "parser_version": "test",
        "source": {"url": "https://www.sec.gov/example"},
        "filing": {
            "accession": accession,
            "form_type": "S-1",
            "filing_date": "2026-05-08",
            "cik": "0001699963",
            "company_name": "Neutron Holdings, Inc.",
        },
        "sections": [
            {
                "id": "s1_itemother_prospectus_summary",
                "title": "Prospectus Summary",
                "path": "sections/s1_itemother_prospectus_summary.md",
                "char_start": 0,
                "char_end": 10,
                "tokens_approx": 10,
                "sha256": "a",
            },
            {
                "id": "s1_itemother_use_of_proceeds",
                "title": "Use of Proceeds",
                "path": "sections/s1_itemother_use_of_proceeds.md",
                "char_start": 10,
                "char_end": 20,
                "tokens_approx": 10,
                "sha256": "b",
            },
            {
                "id": "s1_itemother_summary_consolidated",
                "title": "Summary Consolidated Financial Data",
                "path": "sections/s1_itemother_summary_consolidated.md",
                "char_start": 20,
                "char_end": 30,
                "tokens_approx": 10,
                "sha256": "c",
            },
        ],
    }
    (pack / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (pack / "s1_financials.json").write_text(
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "accession": accession,
                "extracted_at": "2026-05-12T00:00:00Z",
                "extraction_status": "ok",
                "source_sha256": source_sha256_for_pack(pack),
                "model": "deterministic-test",
                "facts": [
                    {
                        "accession": accession,
                        "fiscal_year": 2025,
                        "period_end": "2025-12-31",
                        "metric": "revenue",
                        "value_cents": 88_671_900_000,
                        "currency": "USD",
                        "is_audited": True,
                        "is_pro_forma": False,
                        "pro_forma_note": None,
                        "fiscal_period": "FY",
                        "source_text": "Revenue was $886.7 million in 2025.",
                        "section_id": "s1_itemother_summary_consolidated",
                        "chunk_id": "chunk-001",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return pack


def test_distill_run_writes_expected_files_and_checks(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pack = _write_s1_pack(tmp_path)

    rc = main(["distill", "run", "lime-s1", "--pack", str(pack)])

    assert rc == 0
    out = tmp_path / "reports" / "lime-s1"
    for name in (
        "index.md",
        "findings.csv",
        "metrics.csv",
        "evidence.jsonl",
        "gaps.csv",
        "filing-map.md",
        "run-log.md",
        "bundle.json",
    ):
        assert (out / name).exists(), name

    result = check_distill_bundle(out)
    assert result.ok, result.errors

    findings = list(csv.DictReader((out / "findings.csv").open(newline="", encoding="utf-8")))
    metrics = list(csv.DictReader((out / "metrics.csv").open(newline="", encoding="utf-8")))
    assert any(row["topic"] == "use of proceeds" for row in findings)
    assert metrics[0]["metric"] == "revenue"
    assert metrics[0]["period"] == "FY2025"
    assert "ev-" in metrics[0]["evidence_ids"]


def test_distill_run_resolves_accession_under_packs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_s1_pack(tmp_path, accession="test-accession")

    rc = main(
        [
            "distill",
            "run",
            "resolved",
            "--company",
            "Neutron Holdings",
            "--accession",
            "test-accession",
        ]
    )

    assert rc == 0
    assert (tmp_path / "reports" / "resolved" / "bundle.json").exists()


def test_distill_run_missing_pack_prints_build_hint(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    rc = main(
        [
            "distill",
            "run",
            "missing",
            "--company",
            "Neutron Holdings",
            "--accession",
            "nope",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert "Pack for accession nope not found" in captured.err
    assert "edgarpack build" in captured.err


def test_distill_run_refuses_overwrite_without_force(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pack = _write_s1_pack(tmp_path)

    assert main(["distill", "run", "lime-s1", "--pack", str(pack)]) == 0
    assert main(["distill", "run", "lime-s1", "--pack", str(pack)]) == 2
    assert main(["distill", "run", "lime-s1", "--pack", str(pack), "--force"]) == 0


def test_distill_check_fails_unknown_evidence_reference(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pack = _write_s1_pack(tmp_path)
    assert main(["distill", "run", "lime-s1", "--pack", str(pack)]) == 0
    out = tmp_path / "reports" / "lime-s1"
    findings_path = out / "findings.csv"
    text = findings_path.read_text(encoding="utf-8")
    findings_path.write_text(text.replace("ev-0001", "ev-missing"), encoding="utf-8")

    result = check_distill_bundle(out)

    assert not result.ok
    assert any("unknown evidence id ev-missing" in error for error in result.errors)
