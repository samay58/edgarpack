from __future__ import annotations

from edgarpack.diff.report_builder import build_text_spans
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
