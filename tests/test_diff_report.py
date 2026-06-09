from __future__ import annotations

import hashlib
import json
from pathlib import Path

from edgarpack.cli import main
from edgarpack.diff.html_report import render_pair_report_html
from edgarpack.diff.report_builder import build_pair_report, build_text_spans
from edgarpack.diff.report_models import ChangeType, EvidenceAnchor, TextSpan
from edgarpack.parse.sectionize import sectionize


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


def _write_sectionized_10k_pack(root: Path, accession: str, markdown: str) -> Path:
    sections = [
        (section.id, section.title, section.content)
        for section in sectionize(markdown, "10-K")
        if not section.id.startswith("unknown")
    ]
    return _write_pack_sections(root, accession, sections)


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
    changed = [paragraph for paragraph in paragraphs if paragraph.change_type.value == "modified"][
        0
    ]
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
    assert "old source" in html and "new source" in html
    assert (before / "sections" / "s1_risk_factors.md").resolve().as_uri() in html
    assert (after / "sections" / "s1_risk_factors.md").resolve().as_uri() in html
    assert "<script" not in html.lower()


def test_pair_report_html_renders_markdown_table_as_semantic_table(tmp_path) -> None:
    before = _write_pack(tmp_path, "S1-001", "Old disclosure.")
    after = _write_pack(
        tmp_path,
        "S1A-002",
        "\n\n".join(
            [
                "Debt maturity table:",
                "| Maturity | Cost | Fair value |",
                "| --- | ---: | ---: |",
                "| Series A \\| preferred | $1,000 | $990 |",
                "| One year or less | $35,108 | $34,952 |",
                "| Total | $85,589 | $84,259 |",
            ]
        ),
    )

    html = render_pair_report_html(build_pair_report(before, after))

    assert '<div class="financial-table-wrap">' in html
    assert '<table class="financial-table">' in html
    assert "<th>Maturity</th>" in html
    assert "<td>Series A | preferred</td>" in html
    assert '<td class="num">$85,589</td>' in html
    assert "| Maturity | Cost | Fair value |" not in html


def test_pair_report_html_renders_modified_markdown_table_as_semantic_table(tmp_path) -> None:
    before = _write_pack(
        tmp_path,
        "S1-001",
        "\n".join(
            [
                "| Segment | Revenue |",
                "| --- | ---: |",
                "| Product hardware | $10 |",
                "| Services support | $4 |",
            ]
        ),
    )
    after = _write_pack(
        tmp_path,
        "S1A-002",
        "\n".join(
            [
                "| Segment | Revenue |",
                "| --- | ---: |",
                "| Platform subscriptions | $12 |",
                "| Managed AI consulting | $5 |",
            ]
        ),
    )

    html = render_pair_report_html(build_pair_report(before, after))

    assert html.count('<table class="financial-table">') == 2
    assert '<td class="num">$10</td>' in html
    assert '<td class="num">$12</td>' in html
    assert "<td>Platform subscriptions</td>" in html
    assert "| Segment | Revenue |" not in html


def test_pair_report_html_renders_flattened_financial_block_as_ledger(tmp_path) -> None:
    before = _write_pack(tmp_path, "S1-001", "Old disclosure.")
    after = _write_pack(
        tmp_path,
        "S1A-002",
        "\n\n".join(
            [
                "Unrealized losses table:",
                "> **Less than 12 Months**\n>"
                "\n> Less than 12 Months / 12 Months or Greater / Total\n"
                "> U.S. government and agency securities ... $ / 37,177 / $ / (1,462 / )\n"
                "> Total ................................... $ / 42,736 / $ / (1,625 / )",
            ]
        ),
    )

    html = render_pair_report_html(build_pair_report(before, after))

    assert '<pre class="financial-ledger">' in html
    assert "U.S. government and agency securities" in html
    assert "&gt; U.S. government" not in html


def test_pair_report_html_uses_approved_visual_structure(tmp_path) -> None:
    before = _write_pack(tmp_path, "24-044118", "Old customer disclosure.")
    after = _write_pack(tmp_path, "24-046732", "New customer disclosure.")

    html = render_pair_report_html(build_pair_report(before, after), reproduce_command="cmd")

    for token in (
        "topbar",
        "pair-hero",
        "section-rail",
        "diff-pane",
        "section-hunk",
        "paragraph-row",
        "evidence-line",
        "provenance-footer",
        "--paper",
        "--serif",
        "--code",
    ):
        assert token in html
    assert "dashboard" not in html.lower()
    assert "gradient" not in html.lower()


def test_render_pair_report_html_rejects_unsafe_hrefs(tmp_path) -> None:
    before = _write_pack(
        tmp_path,
        "S1-001",
        "Old customer disclosure.",
        source_url="javascript:alert(1)",
    )
    after = _write_pack(
        tmp_path,
        "S1A-002",
        "New customer disclosure.",
        source_url="data:text/html,<b>x</b>",
    )
    report = build_pair_report(before, after)
    changed = [
        paragraph
        for section in report.sections
        for group in section.groups
        for paragraph in group.paragraphs
        if paragraph.change_type == ChangeType.MODIFIED
    ][0]
    assert changed.old_anchor is not None
    assert changed.new_anchor is not None
    changed.old_anchor.section_path = "javascript:alert(1)"
    changed.new_anchor.section_path = "../secret.md"

    html = render_pair_report_html(report)

    assert 'href="javascript:' not in html.lower()
    assert 'href="data:' not in html.lower()
    assert 'href="../secret.md"' not in html
    assert "source missing" in html
    assert "pack path omitted" in html


def test_render_pair_report_html_omits_unchanged_empty_hunks(tmp_path) -> None:
    before = _write_pack_sections(
        tmp_path,
        "S1-001",
        [
            ("s1_business", "Business", "Stable business disclosure."),
            ("s1_risk_factors", "Risk Factors", "Old customer disclosure."),
        ],
    )
    after = _write_pack_sections(
        tmp_path,
        "S1A-002",
        [
            ("s1_business", "Business", "Stable business disclosure."),
            ("s1_risk_factors", "Risk Factors", "New customer disclosure."),
        ],
    )

    html = render_pair_report_html(build_pair_report(before, after))

    assert "Risk Factors" in html
    assert "Business" not in html


def test_static_report_rail_uses_clean_10k_sectionized_titles(tmp_path) -> None:
    before_md = (
        "Part I\n\n"
        "Item 1. Business\n"
        "Stable business disclosure.\n\n"
        "Item 1A. Risk Factors\n"
        "Old risk disclosure.\n"
    )
    after_md = (
        "Table of Contents\n\n"
        "> **Page / Page / Page**\n"
        ">\n"
        "> Part I / Part I / Part I\n"
        "> Item 1. ................................. Item 1. / Item 1. / "
        "Business / Business / Business / 4 / 4 / 4\n"
        "> Item 1A. ................................ Item 1A. / Item 1A. / "
        "Risk Factors / Risk Factors / Risk Factors / 12 / 12 / 12\n\n"
        "---\n\n"
        "Part I\n\n"
        "Item 1. Business\n"
        "Stable business disclosure.\n\n"
        "Item 1A. Risk Factors\n"
        "New risk disclosure with export-control exposure.\n"
    )
    before = _write_sectionized_10k_pack(tmp_path, "10K-001", before_md)
    after = _write_sectionized_10k_pack(tmp_path, "10K-002", after_md)

    html = render_pair_report_html(build_pair_report(before, after))

    assert "10k_parti_item1a_risk_factors" in html
    assert "Risk Factors" in html
    assert "10k_parti_item1_item_1_business_business" not in html
    assert "risk_factors_risk_factors" not in html
    assert "/ Item 1A." not in html
    assert (after / "sections" / "10k_parti_item1a_risk_factors.md").resolve().as_uri() in html


def test_cli_diff_format_html_writes_static_report(tmp_path, capsys) -> None:
    before = _write_pack(
        tmp_path,
        "S1-001",
        "We depend on a single customer for a material portion of revenue.",
    )
    after = _write_pack(
        tmp_path,
        "S1A-002",
        (
            "We depend on a single customer for the majority of revenue "
            "and that customer may reduce orders materially."
        ),
    )
    report_path = tmp_path / "reports" / "report.html"

    rc = main(
        [
            "diff",
            "--before",
            str(before),
            "--after",
            str(after),
            "--format",
            "html",
            "--out",
            str(report_path),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 0
    assert "Wrote HTML diff report" in captured.out
    assert str(report_path) in captured.out
    assert captured.err == ""
    html = report_path.read_text(encoding="utf-8")
    assert "S1-001" in html
    assert "S1A-002" in html
    assert "majority" in html
    assert "edgarpack diff --before" in html


def test_moved_paragraph_renders_with_badge_and_spans(tmp_path) -> None:
    old = "\n\n".join([
        "Xray risk about supplier concentration and component lead times in great detail today.",
        "Yankee risk about customer concentration with two customers over half of total revenue.",
    ])
    new = "\n\n".join([
        "Yankee risk about customer concentration with three customers over half of total revenue.",
        "Xray risk about supplier concentration and component lead times in great detail tomorrow.",
    ])
    before = _write_pack(tmp_path, "S1-001", old)
    after = _write_pack(tmp_path, "S1A-002", new)
    report = build_pair_report(before, after)
    moved = [
        paragraph
        for section in report.sections
        for group in section.groups
        for paragraph in group.paragraphs
        if paragraph.change_type == ChangeType.MOVED
    ]
    assert len(moved) == 1
    assert moved[0].old_spans and moved[0].new_spans  # spans built for moved pairs
    html = render_pair_report_html(report)
    assert "moved-badge" in html
    assert "<ins>" in html and "<del>" in html  # unified redline rendered


def test_cli_diff_format_html_requires_out(tmp_path, capsys) -> None:
    before = _write_pack(tmp_path, "S1-001", "Old customer disclosure.")
    after = _write_pack(tmp_path, "S1A-002", "New customer disclosure.")

    rc = main(
        [
            "diff",
            "--before",
            str(before),
            "--after",
            str(after),
            "--format",
            "html",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert "--out is required" in captured.err
