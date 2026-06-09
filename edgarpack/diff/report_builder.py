"""Build report-ready diff models from filing packs."""

from __future__ import annotations

import difflib
import json
import re
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..pack.manifest import load_manifest_dict
from .models import ChangeType, ParagraphDelta
from .report_models import (
    ChunkStatus,
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


@dataclass(frozen=True)
class _ChunkLocation:
    chunk_id: str
    section_id: str
    char_start: int
    char_end: int


class _ChunkLookup:
    def __init__(self, chunks: list[_ChunkLocation]) -> None:
        chunks_by_section: dict[str, list[_ChunkLocation]] = defaultdict(list)
        for chunk in chunks:
            chunks_by_section[chunk.section_id].append(chunk)
        for section_chunks in chunks_by_section.values():
            section_chunks.sort(
                key=lambda chunk: (
                    chunk.char_end - chunk.char_start,
                    chunk.char_start,
                    chunk.char_end,
                    chunk.chunk_id,
                )
            )
        self._chunks_by_section = dict(chunks_by_section)

    @property
    def has_chunks(self) -> bool:
        return any(self._chunks_by_section.values())

    def chunk_id_for(self, section_id: str, char_start: int, char_end: int) -> str | None:
        for chunk in self._chunks_by_section.get(section_id, []):
            if chunk.char_start <= char_start and char_end <= chunk.char_end:
                return chunk.chunk_id
        return None


def _load_chunks(pack_dir: Path) -> _ChunkLookup:
    chunks_path = pack_dir / "optional" / "chunks.ndjson"
    if not chunks_path.exists():
        return _ChunkLookup([])

    chunks: list[_ChunkLocation] = []
    for line in chunks_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        chunk_id = record.get("chunk_id")
        section_id = record.get("section_id")
        if not isinstance(chunk_id, str) or not isinstance(section_id, str):
            continue
        try:
            char_start = int(record.get("char_start", 0))
            char_end = int(record.get("char_end", 0))
        except (TypeError, ValueError):
            continue
        if char_end < char_start:
            continue
        chunks.append(
            _ChunkLocation(
                chunk_id=chunk_id,
                section_id=section_id,
                char_start=char_start,
                char_end=char_end,
            )
        )
    return _ChunkLookup(chunks)


_SectionPayload = dict[str, Any]


def _chunk_file_status(before_chunks: _ChunkLookup, after_chunks: _ChunkLookup) -> ChunkStatus:
    before_available = before_chunks.has_chunks
    after_available = after_chunks.has_chunks
    if before_available and after_available:
        return "available"
    if before_available or after_available:
        return "partial"
    return "missing"


def _chunk_status(
    before_chunks: _ChunkLookup,
    after_chunks: _ChunkLookup,
    sections: list[ReportSectionDelta],
) -> ChunkStatus:
    file_status = _chunk_file_status(before_chunks, after_chunks)
    if file_status == "missing":
        return "missing"

    anchors: list[EvidenceAnchor] = []
    for section in sections:
        for group in section.groups:
            for paragraph in group.paragraphs:
                if paragraph.change_type == ChangeType.UNCHANGED:
                    continue
                if paragraph.old_anchor is not None:
                    anchors.append(paragraph.old_anchor)
                if paragraph.new_anchor is not None:
                    anchors.append(paragraph.new_anchor)

    if not anchors:
        return file_status
    if all(anchor.chunk_id for anchor in anchors):
        return "available" if file_status == "available" else "partial"
    return "partial"


def _filing_ref(pack_dir: Path, manifest: dict[str, Any]) -> FilingSourceRef:
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


def _sections_by_id(manifest: dict[str, Any]) -> dict[str, _SectionPayload]:
    return {
        section["id"]: section
        for section in manifest.get("sections", [])
        if isinstance(section, dict) and "id" in section
    }


def _section_ref(section: _SectionPayload | None) -> SectionSourceRef | None:
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


def _section_text(pack_dir: Path, section: _SectionPayload | None) -> str:
    if section is None:
        return ""
    path = section.get("path")
    if not isinstance(path, str) or not path:
        return ""
    section_path = pack_dir / path
    if not section_path.exists():
        return ""
    return section_path.read_text(encoding="utf-8")


def _infer_before_section(
    before_dir: Path,
    before_sections: dict[str, _SectionPayload],
    delta_paragraphs: list[ParagraphDelta],
) -> _SectionPayload | None:
    old_paragraphs = [delta.old_text for delta in delta_paragraphs if delta.old_text]
    if not old_paragraphs:
        return None

    candidates: list[tuple[int, int, str, _SectionPayload]] = []
    for section_id, section in before_sections.items():
        text = _section_text(before_dir, section)
        available = Counter(_split_paragraphs(text))
        matched_count = 0
        matched_chars = 0
        for paragraph in old_paragraphs:
            if available[paragraph] <= 0:
                continue
            available[paragraph] -= 1
            matched_count += 1
            matched_chars += len(paragraph)
        if matched_count:
            candidates.append((matched_count, matched_chars, section_id, section))

    if not candidates:
        return None
    candidates.sort(key=lambda candidate: (-candidate[0], -candidate[1], candidate[2]))
    if len(candidates) > 1 and candidates[0][:2] == candidates[1][:2]:
        return None
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
    chunks: _ChunkLookup,
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
        chunk_id=chunks.chunk_id_for(
            section_ref.section_id,
            location.char_start,
            location.char_end,
        ),
    )


def _report_paragraphs(
    deltas: list[ParagraphDelta],
    before_source: FilingSourceRef,
    after_source: FilingSourceRef,
    old_ref: SectionSourceRef | None,
    new_ref: SectionSourceRef | None,
    old_locations: dict[str, deque[_ParagraphLocation]],
    new_locations: dict[str, deque[_ParagraphLocation]],
    before_chunks: _ChunkLookup,
    after_chunks: _ChunkLookup,
) -> list[ReportParagraphDelta]:
    paragraphs: list[ReportParagraphDelta] = []
    for delta in deltas:
        old_spans: list[TextSpan] = []
        new_spans: list[TextSpan] = []
        if (
            delta.change_type in {ChangeType.MODIFIED, ChangeType.MOVED}
            and delta.old_text
            and delta.new_text
        ):
            old_spans, new_spans = build_text_spans(delta.old_text, delta.new_text)

        paragraphs.append(
            ReportParagraphDelta(
                change_type=delta.change_type,
                old_anchor=_anchor(
                    before_source,
                    old_ref,
                    old_locations,
                    before_chunks,
                    delta.old_text,
                ),
                new_anchor=_anchor(
                    after_source,
                    new_ref,
                    new_locations,
                    after_chunks,
                    delta.new_text,
                ),
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


def _collapsed_word_count(paragraphs: list[ReportParagraphDelta]) -> int:
    total = 0
    for paragraph in paragraphs:
        word_count = paragraph.old_word_count or paragraph.new_word_count
        if word_count == 0:
            text = paragraph.old_text or paragraph.new_text or ""
            word_count = len(text.split())
        total += word_count
    return total


def _append_context_run(
    groups: list[ParagraphGroup],
    run: list[ReportParagraphDelta],
    context_window: int,
) -> None:
    if not run:
        return
    collapse_threshold = context_window * 2
    if len(run) <= collapse_threshold:
        groups.append(ParagraphGroup(kind="context", paragraphs=list(run)))
        return

    leading = run[:context_window]
    trailing = run[-context_window:] if context_window else []
    collapsed = run[context_window : len(run) - context_window]
    if leading:
        groups.append(ParagraphGroup(kind="context", paragraphs=leading))
    if collapsed:
        groups.append(
            ParagraphGroup(
                kind="collapsed",
                collapsed_count=len(collapsed),
                collapsed_word_count=_collapsed_word_count(collapsed),
            )
        )
    if trailing:
        groups.append(ParagraphGroup(kind="context", paragraphs=trailing))


def _context_groups(
    paragraphs: list[ReportParagraphDelta],
    context_window: int,
) -> list[ParagraphGroup]:
    groups: list[ParagraphGroup] = []
    context_run: list[ReportParagraphDelta] = []
    changed_run: list[ReportParagraphDelta] = []
    for paragraph in paragraphs:
        if paragraph.change_type == ChangeType.UNCHANGED:
            if changed_run:
                groups.append(ParagraphGroup(kind="changed", paragraphs=changed_run))
                changed_run = []
            context_run.append(paragraph)
            continue

        _append_context_run(groups, context_run, context_window)
        context_run = []
        changed_run.append(paragraph)

    _append_context_run(groups, context_run, context_window)
    if changed_run:
        groups.append(ParagraphGroup(kind="changed", paragraphs=changed_run))
    return groups


def build_pair_report(
    before_dir: Path,
    after_dir: Path,
    *,
    context_window: int = 2,
) -> DiffReport:
    """Build a static pair report from two filing packs."""
    before_manifest = load_manifest_dict(before_dir, on_missing="raise")
    after_manifest = load_manifest_dict(after_dir, on_missing="raise")
    before_source = _filing_ref(before_dir, before_manifest)
    after_source = _filing_ref(after_dir, after_manifest)
    before_sections = _sections_by_id(before_manifest)
    after_sections = _sections_by_id(after_manifest)
    before_chunks = _load_chunks(before_dir)
    after_chunks = _load_chunks(after_dir)
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
            before_chunks,
            after_chunks,
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
                paragraphs_moved=delta.paragraphs_moved,
                paragraphs_unchanged=delta.paragraphs_unchanged,
                change_intensity=delta.change_intensity,
                interest_score=delta.interest_score,
                groups=_context_groups(paragraphs, max(context_window, 0)),
            )
        )

    return DiffReport(
        report_kind="pair",
        before_source=before_source,
        after_source=after_source,
        chunk_status=_chunk_status(before_chunks, after_chunks, sections),
        sections_unchanged=diff.sections_unchanged,
        sections_modified=diff.sections_modified,
        sections_added=diff.sections_added,
        sections_removed=diff.sections_removed,
        overall_change_intensity=diff.overall_change_intensity,
        sections=sections,
    )
