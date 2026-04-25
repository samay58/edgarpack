"""End-to-end behavioral test for `timeline --series=registration` output.

Builds a minimal two-pack fixture (S-1 and S-1/A with one modified section and
one added section) and verifies the CLI renders a meaningful redline summary.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


def _pack(
    root: Path,
    accession: str,
    form_type: str,
    filing_date: str,
    cik: str,
    sections: list[tuple[str, str, str, str]],
) -> Path:
    """Build a pack dir with a manifest.json plus per-section markdown.

    Each section tuple is (id, path, title, body_text).
    """
    pack = root / accession
    pack.mkdir(parents=True, exist_ok=True)
    sections_dir = pack / "sections"
    sections_dir.mkdir(exist_ok=True)

    manifest_sections: list[dict] = []
    combined: list[str] = []
    for sid, path, title, body in sections:
        (pack / path).parent.mkdir(parents=True, exist_ok=True)
        (pack / path).write_text(body, encoding="utf-8")
        sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
        manifest_sections.append({"id": sid, "path": path, "title": title, "sha256": sha})
        combined.append(f"# {title}\n\n{body}")

    (pack / "filing.full.md").write_text("\n\n".join(combined), encoding="utf-8")

    manifest = {
        "schema_version": 1,
        "filing": {
            "accession": accession,
            "form_type": form_type,
            "filing_date": filing_date,
            "cik": cik,
            "company_name": "Cerebras Systems Inc",
        },
        "sections": manifest_sections,
        "parser_version": "test",
    }
    (pack / "manifest.json").write_text(json.dumps(manifest))
    return pack


def test_registration_timeline_renders_redline_summary(tmp_path):
    cik = "0002021728"
    packs_root = tmp_path / "packs" / cik

    _pack(
        packs_root,
        accession="S1-001",
        form_type="S-1",
        filing_date="2025-09-30",
        cik=cik,
        sections=[
            (
                "s1_risk_factors",
                "sections/risk_factors.md",
                "Risk Factors",
                "We depend on a single customer for a material portion of revenue.",
            ),
            (
                "s1_use_of_proceeds",
                "sections/use_of_proceeds.md",
                "Use of Proceeds",
                "We intend to use the net proceeds for research and development.",
            ),
        ],
    )
    _pack(
        packs_root,
        accession="S1A-002",
        form_type="S-1/A",
        filing_date="2025-10-15",
        cik=cik,
        sections=[
            (
                "s1_risk_factors",
                "sections/risk_factors.md",
                "Risk Factors",
                "We depend on a single customer for the majority of revenue and "
                "that customer may reduce orders materially.",
            ),
            (
                "s1_use_of_proceeds",
                "sections/use_of_proceeds.md",
                "Use of Proceeds",
                "We intend to use the net proceeds for research and development.",
            ),
            (
                "s1_dilution",
                "sections/dilution.md",
                "Dilution",
                "Investors will experience immediate dilution of $12.50 per share.",
            ),
        ],
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "edgarpack.cli",
            "timeline",
            "--series",
            "registration",
            "--cik",
            cik,
            "--packs",
            str(tmp_path / "packs"),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    out = result.stdout

    assert "Registration timeline for CIK 0002021728" in out
    assert "S1-001" in out and "S1A-002" in out
    assert "intensity" in out.lower()
    # The dilution section was added; risk-factors was modified. Both should
    # appear in the ranked changed-section list.
    assert "Dilution" in out
    assert "Risk Factors" in out


def test_registration_timeline_html_writes_index_and_pair_pages(tmp_path):
    cik = "0002021728"
    packs_root = tmp_path / "packs" / cik
    out_dir = tmp_path / "report"

    _pack(
        packs_root,
        accession="S1-001",
        form_type="S-1",
        filing_date="2025-09-30",
        cik=cik,
        sections=[
            (
                "s1_risk_factors",
                "sections/risk_factors.md",
                "Risk Factors",
                "We depend on a single customer for a material portion of revenue.",
            ),
        ],
    )
    _pack(
        packs_root,
        accession="S1A-002",
        form_type="S-1/A",
        filing_date="2025-10-15",
        cik=cik,
        sections=[
            (
                "s1_risk_factors",
                "sections/risk_factors.md",
                "Risk Factors",
                "We depend on a single customer for the majority of revenue and "
                "that customer may reduce orders materially.",
            ),
        ],
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "edgarpack.cli",
            "timeline",
            "--series",
            "registration",
            "--cik",
            cik,
            "--packs",
            str(tmp_path / "packs"),
            "--format",
            "html",
            "--out",
            str(out_dir),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Wrote HTML registration timeline report" in result.stdout

    index_path = out_dir / "index.html"
    pair_path = out_dir / "pair-001.html"
    assert index_path.exists()
    assert pair_path.exists()

    index_html = index_path.read_text(encoding="utf-8")
    pair_html = pair_path.read_text(encoding="utf-8")
    assert 'href="pair-001.html"' in index_html
    assert 'class="diff-pane"' in pair_html
