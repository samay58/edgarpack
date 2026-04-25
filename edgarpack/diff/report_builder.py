"""Build report-ready diff models from filing packs."""

from __future__ import annotations

import difflib
import re
from collections import defaultdict, deque
from pathlib import Path

from ..pack.manifest import load_manifest_dict
from .models import ChangeType, ParagraphDelta
from .report_models import (
    DiffReport,
    EvidenceAnchor,
    FilingSourceRef,
    ParagraphGroup,
    ReportParagraphDelta,
    ReportSectionDelta,
    SectionSourceRef,
    TextSpan,
)
from .section_diff import diff_filings
from .text_diff import _split_paragraphs

_TOKEN_RE = re.compile(r"\w+|\s+|[^\w\s]+", re.UNICODE)


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(text)


def build_text_spans(old_text: str, new_text: str) -> tuple[list[TextSpan], list[TextSpan]]:
    """Return deterministic old/new token spans that reconstruct the inputs."""
    old_tokens = _tokens(old_text)
    new_tokens = _tokens(new_text)
    matcher = difflib.SequenceMatcher(None, old_tokens, new_tokens, autojunk=False)
    old_spans: list[TextSpan] = []
    new_spans: list[TextSpan] = []

    for tag, old_start, old_end, new_start, new_end in matcher.get_opcodes():
        old_piece = "".join(old_tokens[old_start:old_end])
        new_piece = "".join(new_tokens[new_start:new_end])
        if tag == "equal":
            if old_piece:
                old_spans.append(TextSpan(side="old", op="equal", text=old_piece))
            if new_piece:
                new_spans.append(TextSpan(side="new", op="equal", text=new_piece))
        elif tag == "replace":
            if old_piece:
                old_spans.append(TextSpan(side="old", op="replace", text=old_piece))
            if new_piece:
                new_spans.append(TextSpan(side="new", op="replace", text=new_piece))
        elif tag == "delete":
            if old_piece:
                old_spans.append(TextSpan(side="old", op="delete", text=old_piece))
        elif tag == "insert":
            if new_piece:
                new_spans.append(TextSpan(side="new", op="insert", text=new_piece))

    return old_spans, new_spans


class _ParagraphLocation:
    def __init__(self, index: int, text: str, char_start: int, char_end: int) -> None:
        self.index = index
        self.text = text
        self.char_start = char_start
        self.char_end = char_end


def _filing_ref(pack_dir: Path, manifest: dict) -> FilingSourceRef:
    filing = manifest.get("filing", {})
    source = manifest.get("source", {})
    return FilingSourceRef(
        accession=filing.get("accession", ""),
        cik=filing.get("cik", ""),
        company_name=filing.get("company_name", ""),
        form_type=filing.get("form_type", ""),
        filing_date=filing.get("filing_date", ""),
        source_url=source.get("url"),
        pack_dir=str(pack_dir),
    )


def _sections_by_id(manifest: dict) -> dict[str, dict]:
    return {
        section["id"]: section
        for section in manifest.get("sections", [])
        if isinstance(section, dict) and "id" in section
    }


def _section_ref(section: dict | None) -> SectionSourceRef | None:
    if section is None:
        return None
    return SectionSourceRef(
        section_id=section.get("id", ""),
        title=section.get("title", ""),
        path=section.get("path", ""),
        char_start=section.get("char_start", 0),
        char_end=section.get("char_end", 0),
        sha256=section.get("sha256", ""),
    )


def _section_text(pack_dir: Path, section: dict | None) -> str:
    if section is None:
        return ""
    path = section.get("path")
    if not path:
        return ""
    section_path = pack_dir / path
    if not section_path.exists():
        return ""
    return section_path.read_text(encoding="utf-8")


def _infer_before_section(
    before_dir: Path,
    before_sections: dict[str, dict],
    delta_paragraphs: list[ParagraphDelta],
) -> dict | None:
    old_paragraphs = [delta.old_text for delta in delta_paragraphs if delta.old_text]
    if not old_paragraphs:
        return None

    candidates: list[tuple[int, int, str, dict]] = []
    for section_id, section in before_sections.items():
        text = _section_text(before_dir, section)
        matched = [paragraph for paragraph in old_paragraphs if paragraph in text]
        if matched:
            candidates.append(
                (
                    len(matched),
                    sum(len(paragraph) for paragraph in matched),
                    section_id,
                    section,
                )
            )

    if not candidates:
        return None
    candidates.sort(key=lambda candidate: (-candidate[0], -candidate[1], candidate[2]))
    return candidates[0][3]


def _paragraph_locations(text: str) -> dict[str, deque[_ParagraphLocation]]:
    """Map split paragraph text to source offsets in the original section text."""
    locations: dict[str, deque[_ParagraphLocation]] = defaultdict(deque)
    search_start = 0
    for index, paragraph in enumerate(_split_paragraphs(text), start=1):
        char_start = text.find(paragraph, search_start)
        if char_start == -1:
            char_start = text.find(paragraph)
        if char_start == -1:
            continue
        char_end = char_start + len(paragraph)
        locations[paragraph].append(_ParagraphLocation(index, paragraph, char_start, char_end))
        search_start = char_end
    return locations


def _anchor(
    source: FilingSourceRef,
    section_ref: SectionSourceRef | None,
    locations: dict[str, deque[_ParagraphLocation]],
    text: str | None,
) -> EvidenceAnchor | None:
    if section_ref is None or text is None:
        return None
    matching_locations = locations.get(text)
    if not matching_locations:
        return None
    location = matching_locations.popleft()
    return EvidenceAnchor(
        accession=source.accession,
        section_id=section_ref.section_id,
        section_path=section_ref.path,
        paragraph_index=location.index,
        char_start=location.char_start,
        char_end=location.char_end,
        chunk_id=None,
    )


def _report_paragraphs(
    deltas: list[ParagraphDelta],
    before_source: FilingSourceRef,
    after_source: FilingSourceRef,
    old_ref: SectionSourceRef | None,
    new_ref: SectionSourceRef | None,
    old_locations: dict[str, deque[_ParagraphLocation]],
    new_locations: dict[str, deque[_ParagraphLocation]],
) -> list[ReportParagraphDelta]:
    paragraphs: list[ReportParagraphDelta] = []
    for delta in deltas:
        old_spans: list[TextSpan] = []
        new_spans: list[TextSpan] = []
        if delta.change_type == ChangeType.MODIFIED and delta.old_text and delta.new_text:
            old_spans, new_spans = build_text_spans(delta.old_text, delta.new_text)

        paragraphs.append(
            ReportParagraphDelta(
                change_type=delta.change_type,
                old_anchor=_anchor(before_source, old_ref, old_locations, delta.old_text),
                new_anchor=_anchor(after_source, new_ref, new_locations, delta.new_text),
                old_text=delta.old_text,
                new_text=delta.new_text,
                old_spans=old_spans,
                new_spans=new_spans,
                similarity=delta.similarity,
                old_word_count=delta.old_word_count,
                new_word_count=delta.new_word_count,
            )
        )
    return paragraphs


def _simple_groups(paragraphs: list[ReportParagraphDelta]) -> list[ParagraphGroup]:
    groups: list[ParagraphGroup] = []
    for paragraph in paragraphs:
        kind = "context" if paragraph.change_type == ChangeType.UNCHANGED else "changed"
        groups.append(ParagraphGroup(kind=kind, paragraphs=[paragraph]))
    return groups


def build_pair_report(before_dir: Path, after_dir: Path) -> DiffReport:
    """Build a static pair report from two filing packs."""
    before_manifest = load_manifest_dict(before_dir, on_missing="raise")
    after_manifest = load_manifest_dict(after_dir, on_missing="raise")
    before_source = _filing_ref(before_dir, before_manifest)
    after_source = _filing_ref(after_dir, after_manifest)
    before_sections = _sections_by_id(before_manifest)
    after_sections = _sections_by_id(after_manifest)
    diff = diff_filings(before_dir, after_dir)

    sections: list[ReportSectionDelta] = []
    for delta in diff.section_deltas:
        before_section = before_sections.get(delta.section_id)
        if before_section is None:
            before_section = _infer_before_section(
                before_dir,
                before_sections,
                delta.paragraph_deltas,
            )
        after_section = after_sections.get(delta.section_id)
        old_ref = _section_ref(before_section)
        new_ref = _section_ref(after_section)
        old_text = _section_text(before_dir, before_section)
        new_text = _section_text(after_dir, after_section)
        paragraphs = _report_paragraphs(
            delta.paragraph_deltas,
            before_source,
            after_source,
            old_ref,
            new_ref,
            _paragraph_locations(old_text),
            _paragraph_locations(new_text),
        )
        sections.append(
            ReportSectionDelta(
                section_id=delta.section_id,
                title=delta.title,
                change_type=delta.change_type,
                old_ref=old_ref,
                new_ref=new_ref,
                paragraphs_added=delta.paragraphs_added,
                paragraphs_removed=delta.paragraphs_removed,
                paragraphs_modified=delta.paragraphs_modified,
                paragraphs_unchanged=delta.paragraphs_unchanged,
                change_intensity=delta.change_intensity,
                interest_score=delta.interest_score,
                groups=_simple_groups(paragraphs),
            )
        )

    return DiffReport(
        report_kind="pair",
        before_source=before_source,
        after_source=after_source,
        chunk_status="missing",
        sections_unchanged=diff.sections_unchanged,
        sections_modified=diff.sections_modified,
        sections_added=diff.sections_added,
        sections_removed=diff.sections_removed,
        overall_change_intensity=diff.overall_change_intensity,
        sections=sections,
    )
