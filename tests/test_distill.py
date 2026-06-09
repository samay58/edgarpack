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


def _default_facts(accession: str) -> list[dict[str, object]]:
    return [
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
    ]


def _write_s1_pack(
    root: Path,
    accession: str = "0001628280-26-032523",
    *,
    form_type: str = "S-1",
    filing_date: str = "2026-05-08",
    facts: list[dict[str, object]] | None = None,
) -> Path:
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
        "# Underwriting\n\nThe lock-up period will be 180 days from the date of this prospectus.\n",
        encoding="utf-8",
    )
    manifest = {
        "parser_version": "test",
        "source": {"url": "https://www.sec.gov/example"},
        "filing": {
            "accession": accession,
            "form_type": form_type,
            "filing_date": filing_date,
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
                "facts": facts if facts is not None else _default_facts(accession),
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


def test_distill_non_registration_pack_gets_single_accurate_gap(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pack = _write_s1_pack(tmp_path, form_type="10-K")

    rc = main(["distill", "run", "tenk", "--pack", str(pack)])

    assert rc == 0
    out = tmp_path / "reports" / "tenk"
    gaps = list(csv.DictReader((out / "gaps.csv").open(newline="", encoding="utf-8")))
    assert [gap["status"] for gap in gaps] == ["unsupported_form"]
    assert gaps[0]["id"] == "gap-0001"
    # Empty row files still carry their schema header.
    findings_header = (out / "findings.csv").read_text(encoding="utf-8").splitlines()[0]
    assert "statement" in findings_header
    result = check_distill_bundle(out)
    assert result.ok, result.errors


def test_distill_metric_without_source_text_is_needs_review(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    facts = _default_facts("0001628280-26-032523")
    facts[0]["source_text"] = None
    pack = _write_s1_pack(tmp_path, facts=facts)

    rc = main(["distill", "run", "noquote", "--pack", str(pack)])

    assert rc == 0
    out = tmp_path / "reports" / "noquote"
    metrics = list(csv.DictReader((out / "metrics.csv").open(newline="", encoding="utf-8")))
    assert metrics[0]["status"] == "needs_review"
    assert "no quoted source text" in metrics[0]["notes"]
    records = [
        json.loads(line)
        for line in (out / "evidence.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    metric_record = next(r for r in records if r["kind"] == "metric")
    assert metric_record["text"].startswith("No source text captured")
    assert metric_record["metadata"]["quoted_from_filing"] is False
    gaps = list(csv.DictReader((out / "gaps.csv").open(newline="", encoding="utf-8")))
    assert any(gap["area"] == "metric_locators" for gap in gaps)


def test_distill_window_anchors_on_snapshot_years_not_filing_year(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    accession = "0001628280-26-032523"
    base = _default_facts(accession)[0]
    facts: list[dict[str, object]] = []
    for year in (2022, 2023, 2024):
        fact = dict(base)
        fact.update(fiscal_year=year, period_end=f"{year}-12-31")
        facts.append(fact)
    for year in (2024, 2025):
        fact = dict(base)
        fact.update(fiscal_year=year, period_end=f"{year}-09-30", fiscal_period="Q3")
        facts.append(fact)
    pack = _write_s1_pack(tmp_path, filing_date="2026-02-15", facts=facts)

    rc = main(["distill", "run", "window", "--pack", str(pack)])

    assert rc == 0
    out = tmp_path / "reports" / "window"
    metrics = list(csv.DictReader((out / "metrics.csv").open(newline="", encoding="utf-8")))
    assert len(metrics) == 5
    gaps = list(csv.DictReader((out / "gaps.csv").open(newline="", encoding="utf-8")))
    assert not any(gap["area"] == "metric_window" for gap in gaps)


def test_distill_run_rejects_non_pack_directory(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    not_a_pack = tmp_path / "notapack"
    not_a_pack.mkdir()

    rc = main(["distill", "run", "bad", "--pack", str(not_a_pack)])

    captured = capsys.readouterr()
    assert rc == 2
    assert "not a filing pack" in captured.err


def test_distill_check_fails_counts_mismatch(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pack = _write_s1_pack(tmp_path)
    assert main(["distill", "run", "lime-s1", "--pack", str(pack)]) == 0
    out = tmp_path / "reports" / "lime-s1"
    bundle = json.loads((out / "bundle.json").read_text(encoding="utf-8"))
    bundle["counts"]["metrics"] += 1
    (out / "bundle.json").write_text(json.dumps(bundle), encoding="utf-8")

    result = check_distill_bundle(out)

    assert not result.ok
    assert any("counts.metrics" in error for error in result.errors)


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
