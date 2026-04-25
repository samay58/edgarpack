from __future__ import annotations

import hashlib
import json
from pathlib import Path

from edgarpack.diff.html_report import render_pair_report_html
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


def _write_pack_sections(
    root: Path,
    accession: str,
    sections: list[tuple[str, str, str]],
) -> Path:
    pack = root / accession
    (pack / "sections").mkdir(parents=True, exist_ok=True)
    manifest_sections: list[dict[str, object]] = []
    for section_id, title, body in sections:
        section_path = pack / "sections" / f"{section_id}.md"
        section_path.write_text(body, encoding="utf-8")
        manifest_sections.append(
            {
                "id": section_id,
                "title": title,
                "path": f"sections/{section_id}.md",
                "char_start": 0,
                "char_end": len(body),
                "tokens_approx": len(body.split()),
                "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
            }
        )
    manifest = {
        "source": {"url": "https://www.sec.gov/example.htm"},
        "filing": {
            "accession": accession,
            "cik": "0002021728",
            "company_name": "Cerebras Systems Inc.",
            "form_type": "S-1",
            "filing_date": "2026-04-17",
        },
        "sections": manifest_sections,
    }
    (pack / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return pack


def _write_chunks(pack: Path, chunks: list[dict[str, object]]) -> None:
    chunks_path = pack / "optional" / "chunks.ndjson"
    chunks_path.parent.mkdir(parents=True, exist_ok=True)
    chunks_path.write_text(
        "\n".join(json.dumps(chunk) for chunk in chunks) + "\n",
        encoding="utf-8",
    )


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


def test_build_pair_report_maps_available_chunks_to_fully_covered_anchors(
    tmp_path,
) -> None:
    old_intro = "Intro paragraph."
    old_changed = "We depend on a single customer for a material portion of revenue."
    new_changed = (
        "We depend on a single customer for the majority of revenue "
        "and that customer may reduce orders materially."
    )
    before = _write_pack(tmp_path, "S1-001", f"{old_intro}\n\n{old_changed}")
    after = _write_pack(tmp_path, "S1A-002", f"{old_intro}\n\n{new_changed}")
    changed_start = len(f"{old_intro}\n\n")
    _write_chunks(
        before,
        [
            {
                "chunk_id": "before-risk-2",
                "section_id": "s1_risk_factors",
                "char_start": changed_start,
                "char_end": changed_start + len(old_changed),
            }
        ],
    )
    _write_chunks(
        after,
        [
            {
                "chunk_id": "after-risk-2",
                "section_id": "s1_risk_factors",
                "char_start": changed_start,
                "char_end": changed_start + len(new_changed),
            }
        ],
    )

    report = build_pair_report(before, after)

    assert report.chunk_status == "available"
    changed = [
        paragraph
        for section in report.sections
        for group in section.groups
        for paragraph in group.paragraphs
        if paragraph.change_type == ChangeType.MODIFIED
    ][0]
    assert changed.old_anchor is not None
    assert changed.old_anchor.chunk_id == "before-risk-2"
    assert changed.new_anchor is not None
    assert changed.new_anchor.chunk_id == "after-risk-2"


def test_build_pair_report_marks_chunk_status_partial_when_one_side_has_chunks(
    tmp_path,
) -> None:
    old_body = "We depend on one customer."
    new_body = "We depend on one customer and continued orders."
    before = _write_pack(tmp_path, "S1-001", old_body)
    after = _write_pack(tmp_path, "S1A-002", new_body)
    _write_chunks(
        before,
        [
            {
                "chunk_id": "before-risk-1",
                "section_id": "s1_risk_factors",
                "char_start": 0,
                "char_end": len(old_body),
            }
        ],
    )

    report = build_pair_report(before, after)

    assert report.chunk_status == "partial"


def test_build_pair_report_marks_chunk_status_partial_for_uncovered_changed_anchor(
    tmp_path,
) -> None:
    before = _write_pack(tmp_path, "S1-001", "Old customer disclosure.")
    after = _write_pack(tmp_path, "S1A-002", "New customer disclosure.")
    _write_chunks(
        before,
        [
            {
                "chunk_id": "before-unrelated",
                "section_id": "s1_risk_factors",
                "char_start": 0,
                "char_end": 1,
            }
        ],
    )
    _write_chunks(
        after,
        [
            {
                "chunk_id": "after-unrelated",
                "section_id": "s1_risk_factors",
                "char_start": 0,
                "char_end": 1,
            }
        ],
    )

    report = build_pair_report(before, after)

    assert report.chunk_status == "partial"
    changed = [
        paragraph
        for section in report.sections
        for group in section.groups
        for paragraph in group.paragraphs
        if paragraph.change_type == ChangeType.MODIFIED
    ][0]
    assert changed.old_anchor is not None
    assert changed.old_anchor.chunk_id is None
    assert changed.new_anchor is not None
    assert changed.new_anchor.chunk_id is None


def test_build_pair_report_ignores_malformed_optional_chunk_rows(tmp_path) -> None:
    before = _write_pack(tmp_path, "S1-001", "Old customer disclosure.")
    after = _write_pack(tmp_path, "S1A-002", "New customer disclosure.")
    chunks_path = before / "optional" / "chunks.ndjson"
    chunks_path.parent.mkdir(parents=True, exist_ok=True)
    chunks_path.write_text(
        "\n".join(
            [
                "{not json",
                json.dumps(["not", "object"]),
                json.dumps({"chunk_id": "missing-section"}),
                json.dumps(
                    {
                        "chunk_id": "bad-offset",
                        "section_id": "s1_risk_factors",
                        "char_start": "x",
                        "char_end": 10,
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    report = build_pair_report(before, after)

    assert report.chunk_status == "missing"


def test_build_pair_report_collapses_long_unchanged_context_runs(tmp_path) -> None:
    before_paragraphs = [
        "Stable paragraph one.",
        "Stable paragraph two.",
        "Stable paragraph three.",
        "Stable paragraph four.",
        "Stable paragraph five.",
        "We rely on one customer for revenue.",
        "Stable paragraph six.",
        "Stable paragraph seven.",
        "Stable paragraph eight.",
    ]
    after_paragraphs = [
        "Stable paragraph one.",
        "Stable paragraph two.",
        "Stable paragraph three.",
        "Stable paragraph four.",
        "Stable paragraph five.",
        "We rely on one customer for revenue and continued orders.",
        "Stable paragraph six.",
        "Stable paragraph seven.",
        "Stable paragraph eight.",
    ]
    before = _write_pack(tmp_path, "S1-001", "\n\n".join(before_paragraphs))
    after = _write_pack(tmp_path, "S1A-002", "\n\n".join(after_paragraphs))

    report = build_pair_report(before, after, context_window=1)

    groups = report.sections[0].groups
    assert [group.kind for group in groups] == ["context", "collapsed", "context", "changed"]
    assert groups[0].paragraphs[0].old_text == "Stable paragraph one."
    assert groups[1].collapsed_count == 6
    assert groups[1].collapsed_word_count == 18
    assert groups[2].paragraphs[0].old_text == "Stable paragraph eight."
    assert groups[3].paragraphs[0].change_type == ChangeType.MODIFIED


def test_build_pair_report_preserves_old_anchors_for_fallback_matched_sections(
    tmp_path,
) -> None:
    old_section_id = "10k_partii_item7_managements_discussion"
    new_section_id = "10k_parti_item7_managements_discussion"
    repeated = "Repeated disclosure."
    old_changed = "We generated revenue from one major customer and rely on continued orders."
    new_changed = (
        "We generated revenue from one major customer and rely on continued orders, "
        "but demand may decline."
    )
    old_body = f"{repeated}\n\n{repeated}\n\n{old_changed}"
    new_body = f"{repeated}\n\n{repeated}\n\n{new_changed}"
    before = _write_pack(
        tmp_path,
        "10K-001",
        old_body,
        section_id=old_section_id,
        title="Management's Discussion and Analysis",
    )
    after = _write_pack(
        tmp_path,
        "10K-002",
        new_body,
        section_id=new_section_id,
        title="Management's Discussion and Analysis",
    )

    report = build_pair_report(before, after)

    section = report.sections[0]
    assert section.section_id == new_section_id
    assert section.old_ref is not None
    assert section.old_ref.section_id == old_section_id
    assert section.old_ref.path == f"sections/{old_section_id}.md"
    assert section.new_ref is not None
    assert section.new_ref.section_id == new_section_id

    paragraphs = [paragraph for group in section.groups for paragraph in group.paragraphs]
    changed = [
        paragraph for paragraph in paragraphs if paragraph.change_type.value == "modified"
    ][0]
    assert changed.old_anchor is not None
    assert changed.old_anchor.section_id == old_section_id
    assert changed.old_anchor.section_path == f"sections/{old_section_id}.md"
    assert changed.old_anchor.paragraph_index == 3
    assert changed.old_anchor.char_start == len(f"{repeated}\n\n{repeated}\n\n")
    assert changed.new_anchor is not None
    assert changed.new_anchor.section_id == new_section_id
    assert changed.new_anchor.char_start == len(f"{repeated}\n\n{repeated}\n\n")

    repeated_context = [
        paragraph
        for paragraph in paragraphs
        if paragraph.change_type.value == "unchanged" and paragraph.old_text == repeated
    ]
    assert [paragraph.old_anchor.paragraph_index for paragraph in repeated_context] == [1, 2]
    assert [paragraph.old_anchor.char_start for paragraph in repeated_context] == [
        0,
        len(f"{repeated}\n\n"),
    ]


def test_build_pair_report_does_not_infer_ambiguous_old_section(tmp_path) -> None:
    old_section_id = "10k_partii_item7_managements_discussion"
    new_section_id = "10k_parti_item7_managements_discussion"
    unrelated_section_id = "10k_parti_item1_business"
    old_body = "We rely on one customer for revenue."
    before = _write_pack_sections(
        tmp_path,
        "10K-001",
        [
            (old_section_id, "Management's Discussion and Analysis", old_body),
            (unrelated_section_id, "Business", old_body),
        ],
    )
    after = _write_pack(
        tmp_path,
        "10K-002",
        "We rely on one customer for revenue and continued orders.",
        section_id=new_section_id,
        title="Management's Discussion and Analysis",
    )

    report = build_pair_report(before, after)

    section = next(section for section in report.sections if section.section_id == new_section_id)
    assert section.old_ref is None
    changed = [
        paragraph
        for group in section.groups
        for paragraph in group.paragraphs
        if paragraph.change_type.value == "modified"
    ][0]
    assert changed.old_anchor is None
    assert changed.old_text == old_body


def test_render_pair_report_html_escapes_text_and_emits_static_report(
    tmp_path,
) -> None:
    before = _write_pack(
        tmp_path,
        "S1-001",
        "\n\n".join(
            [
                "Intro paragraph.",
                "Stable paragraph one.",
                "Stable paragraph two.",
                "Stable paragraph three.",
                "Stable paragraph four.",
                "Stable paragraph five.",
                "Old <script>alert('x')</script> risk text.",
            ]
        ),
        source_url="https://www.sec.gov/before?x=<script>",
    )
    after = _write_pack(
        tmp_path,
        "S1A-002",
        "\n\n".join(
            [
                "Intro paragraph.",
                "Stable paragraph one.",
                "Stable paragraph two.",
                "Stable paragraph three.",
                "Stable paragraph four.",
                "Stable paragraph five.",
                "New <b>risk</b> text.",
            ]
        ),
        source_url="https://www.sec.gov/after?x=<b>",
    )

    report = build_pair_report(before, after)
    html = render_pair_report_html(
        report,
        reproduce_command="edgarpack diff --format html --out <report>",
    )

    assert "<script" not in html.lower()
    assert "&lt;script&gt;" in html
    assert "&lt;b&gt;risk&lt;/b&gt;" in html
    assert "--out &lt;report&gt;" in html
    assert "edgarpack" in html
    assert "S1-001" in html and "S1A-002" in html
    assert "topbar" in html
    assert "pair-hero" in html
    assert "section-rail" in html
    assert "diff-pane" in html
    assert "section-hunk" in html
    assert "paragraph-row" in html
    assert "evidence-line" in html
    assert "provenance-footer" in html
    assert "chunk status" in html.lower()
    assert "Reproduce" in html
    assert "<details" in html and "<summary" in html
    assert "--paper" in html and "--serif" in html and "--code" in html
    assert "<script" not in html.lower()
