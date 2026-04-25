from __future__ import annotations

import hashlib
import json
from pathlib import Path

from edgarpack.diff.report_builder import build_pair_report, build_text_spans
from edgarpack.diff.report_models import ChangeType, EvidenceAnchor, TextSpan


def test_evidence_anchor_carries_section_paragraph_offset_and_optional_chunk() -> None:
    anchor = EvidenceAnchor(
        accession="S1A-002",
        section_id="s1_risk_factors",
        section_path="sections/risk_factors.md",
        paragraph_index=4,
        char_start=1184,
        char_end=1612,
        chunk_id="c-04-117",
    )

    assert anchor.accession == "S1A-002"
    assert anchor.section_id == "s1_risk_factors"
    assert anchor.paragraph_index == 4
    assert anchor.char_start == 1184
    assert anchor.char_end == 1612
    assert anchor.chunk_id == "c-04-117"


def test_build_text_spans_is_deterministic_and_preserves_changed_words() -> None:
    old = "We depend on a single customer for a material portion of revenue."
    new = (
        "We depend on a single customer for the majority of revenue "
        "and that customer may reduce orders materially."
    )

    old_spans, new_spans = build_text_spans(old, new)

    assert old_spans == build_text_spans(old, new)[0]
    assert new_spans == build_text_spans(old, new)[1]
    assert all(isinstance(span, TextSpan) for span in old_spans + new_spans)
    assert "".join(span.text for span in old_spans) == old
    assert "".join(span.text for span in new_spans) == new
    assert any(span.op == "replace" and "material portion" in span.text for span in old_spans)
    assert any(span.op == "replace" and "majority" in span.text for span in new_spans)


def test_change_type_is_reexported_for_report_models() -> None:
    assert ChangeType.ADDED.value == "added"


def _write_pack(
    root: Path,
    accession: str,
    body: str,
    *,
    section_id: str = "s1_risk_factors",
    title: str = "Risk Factors",
    source_url: str = "https://www.sec.gov/example.htm",
) -> Path:
    pack = root / accession
    section_path = pack / "sections" / f"{section_id}.md"
    section_path.parent.mkdir(parents=True, exist_ok=True)
    section_path.write_text(body, encoding="utf-8")
    manifest = {
        "source": {"url": source_url, "fetched_at": "2026-04-17T00:00:00Z"},
        "filing": {
            "accession": accession,
            "cik": "0002021728",
            "company_name": "Cerebras Systems Inc.",
            "form_type": "S-1",
            "filing_date": "2026-04-17",
        },
        "sections": [
            {
                "id": section_id,
                "title": title,
                "path": f"sections/{section_id}.md",
                "char_start": 0,
                "char_end": len(body),
                "tokens_approx": len(body.split()),
                "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
            }
        ],
    }
    (pack / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return pack


def test_build_pair_report_adds_source_refs_and_paragraph_offsets(tmp_path) -> None:
    before = _write_pack(
        tmp_path,
        "S1-001",
        "Intro paragraph.\n\nWe depend on a single customer for a material portion of revenue.",
        source_url="https://www.sec.gov/before.htm",
    )
    after = _write_pack(
        tmp_path,
        "S1A-002",
        (
            "Intro paragraph.\n\n"
            "We depend on a single customer for the majority of revenue "
            "and that customer may reduce orders materially."
        ),
        source_url="https://www.sec.gov/after.htm",
    )

    report = build_pair_report(before, after)

    assert report.before_source.accession == "S1-001"
    assert report.before_source.source_url == "https://www.sec.gov/before.htm"
    assert report.after_source.accession == "S1A-002"
    assert report.after_source.source_url == "https://www.sec.gov/after.htm"
    assert report.chunk_status == "missing"
    changed = [
        p
        for section in report.sections
        for group in section.groups
        for p in group.paragraphs
        if p.change_type.value == "modified"
    ][0]
    assert changed.old_anchor is not None
    assert changed.new_anchor is not None
    assert changed.old_anchor.paragraph_index == 2
    assert changed.new_anchor.paragraph_index == 2
    assert changed.old_anchor.char_start == len("Intro paragraph.\n\n")
    assert changed.new_anchor.char_start == len("Intro paragraph.\n\n")
    assert changed.old_anchor.chunk_id is None
    assert changed.new_anchor.chunk_id is None
    assert changed.old_spans
    assert changed.new_spans
