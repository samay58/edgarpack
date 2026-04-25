# Static Filing Diff Reports Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic, static HTML filing diff reports for pair diffs and S-1 registration timelines without changing the existing diff algorithm.

**Architecture:** Keep `diff_filings()` as the alignment source of truth. Add an additive report model and builder that enrich existing `DiffResult` objects with paragraph anchors, inline spans, chunk status, and context groups. Add a pure-Python static HTML renderer and wire it into `edgarpack diff --format html --out` and `edgarpack timeline --series registration --format html --out`.

**Tech Stack:** Python 3.11+, Pydantic v2, stdlib `difflib`, stdlib `html`, pytest, ruff. No new runtime dependencies and no JavaScript in generated reports.

---

## Safety Rules

- Work in a dedicated git worktree. Do not implement in the current dirty checkout.
- Do not alter the existing paragraph/section alignment algorithm in `edgarpack/diff/text_diff.py` or `edgarpack/diff/section_diff.py` except for import-only changes that tests force.
- Do not add generated findings, LLM summaries, or claim fields.
- Do not mutate packs during report generation. Missing chunks stay missing.
- Write each failing test before production code.
- Commit after each green task.
- Push before declaring work complete.

## File Map

- Create: `edgarpack/diff/report_models.py` — Pydantic models for report sources, anchors, spans, grouped paragraphs, pair reports, and timeline reports.
- Create: `edgarpack/diff/report_builder.py` — converts `DiffResult` plus pack manifests/sections into `DiffReport`; includes paragraph indexing, span generation, context grouping, and chunk lookup.
- Create: `edgarpack/diff/html_report.py` — static HTML/CSS renderer for pair reports and registration timeline indexes.
- Modify: `edgarpack/cli.py` — add `--format html`, `--out`, pair-report generation, and registration timeline report generation.
- Create: `tests/test_diff_report.py` — report model, builder, span, anchor, chunk status, and HTML-renderer tests.
- Modify: `tests/test_cli_registration_timeline_render.py` — CLI coverage for registration timeline HTML output.
- Modify: `tests/test_diff.py` only if needed to protect existing text/json behavior or reuse helpers.

## Task 0: Dedicated Worktree And Baseline

**Files:**
- No code files.

- [ ] **Step 1: Create a clean implementation worktree**

Run:

```bash
git fetch origin
git worktree add /tmp/edgarpack-static-diff-report -b feature/static-diff-report origin/main
cd /tmp/edgarpack-static-diff-report
```

Expected: new worktree on `feature/static-diff-report`.

- [ ] **Step 2: Install dependencies**

Run:

```bash
uv pip install -e ".[dev,china]"
```

Expected: install succeeds. If `uv.lock` changes before code edits, stop and report it.

- [ ] **Step 3: Run focused baseline**

Run:

```bash
uv run pytest tests/test_diff.py tests/test_cli_registration_timeline_render.py -q
uv run ruff check edgarpack/diff edgarpack/cli.py tests/test_diff.py tests/test_cli_registration_timeline_render.py
```

Expected: both commands pass before any implementation edits.

## Task 1: Report Models And Inline Span Generation

**Files:**
- Create: `edgarpack/diff/report_models.py`
- Create: `edgarpack/diff/report_builder.py`
- Create: `tests/test_diff_report.py`

- [ ] **Step 1: Write failing tests for report models and inline spans**

Create `tests/test_diff_report.py` with:

```python
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
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_diff_report.py -q
```

Expected: FAIL with `ModuleNotFoundError` for `edgarpack.diff.report_builder` or `edgarpack.diff.report_models`.

- [ ] **Step 3: Add report models**

Create `edgarpack/diff/report_models.py`:

```python
"""Models for static filing diff reports."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .models import ChangeType

ChunkStatus = Literal["available", "missing", "partial"]
ParagraphGroupKind = Literal["changed", "context", "collapsed"]
ReportKind = Literal["pair", "timeline_pair"]
SpanOp = Literal["equal", "insert", "delete", "replace"]
SpanSide = Literal["old", "new"]


class FilingSourceRef(BaseModel):
    accession: str
    cik: str = ""
    company_name: str = ""
    form_type: str = ""
    filing_date: str = ""
    source_url: str | None = None
    pack_dir: str


class SectionSourceRef(BaseModel):
    section_id: str
    title: str
    path: str
    char_start: int = 0
    char_end: int = 0
    sha256: str = ""


class EvidenceAnchor(BaseModel):
    accession: str
    section_id: str
    section_path: str
    paragraph_index: int
    char_start: int
    char_end: int
    chunk_id: str | None = None


class TextSpan(BaseModel):
    side: SpanSide
    op: SpanOp
    text: str


class ReportParagraphDelta(BaseModel):
    change_type: ChangeType
    old_anchor: EvidenceAnchor | None = None
    new_anchor: EvidenceAnchor | None = None
    old_text: str | None = None
    new_text: str | None = None
    old_spans: list[TextSpan] = Field(default_factory=list)
    new_spans: list[TextSpan] = Field(default_factory=list)
    similarity: float = 0.0
    old_word_count: int = 0
    new_word_count: int = 0


class ParagraphGroup(BaseModel):
    kind: ParagraphGroupKind
    paragraphs: list[ReportParagraphDelta] = Field(default_factory=list)
    collapsed_count: int = 0
    collapsed_word_count: int = 0


class ReportSectionDelta(BaseModel):
    section_id: str
    title: str
    change_type: ChangeType
    old_ref: SectionSourceRef | None = None
    new_ref: SectionSourceRef | None = None
    paragraphs_added: int = 0
    paragraphs_removed: int = 0
    paragraphs_modified: int = 0
    paragraphs_unchanged: int = 0
    change_intensity: float = 0.0
    interest_score: float = 0.0
    groups: list[ParagraphGroup] = Field(default_factory=list)


class DiffReport(BaseModel):
    report_kind: ReportKind = "pair"
    before_source: FilingSourceRef
    after_source: FilingSourceRef
    chunk_status: ChunkStatus = "missing"
    sections_unchanged: int = 0
    sections_modified: int = 0
    sections_added: int = 0
    sections_removed: int = 0
    overall_change_intensity: float = 0.0
    sections: list[ReportSectionDelta] = Field(default_factory=list)


class TimelineReportEntry(BaseModel):
    accession: str
    form_type: str
    filing_date: str
    pack_dir: str


class TimelineTransition(BaseModel):
    index: int
    before: TimelineReportEntry
    after: TimelineReportEntry
    output_file: str
    sections_added: int = 0
    sections_removed: int = 0
    sections_modified: int = 0
    sections_unchanged: int = 0
    overall_change_intensity: float = 0.0


class TimelineReport(BaseModel):
    cik: str
    entries: list[TimelineReportEntry] = Field(default_factory=list)
    transitions: list[TimelineTransition] = Field(default_factory=list)
```

- [ ] **Step 4: Add minimal span builder**

Create `edgarpack/diff/report_builder.py`:

```python
"""Build report-ready diff models from filing packs."""

from __future__ import annotations

import difflib
import re

from .report_models import TextSpan

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
```

- [ ] **Step 5: Run tests to verify green**

Run:

```bash
uv run pytest tests/test_diff_report.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add edgarpack/diff/report_models.py edgarpack/diff/report_builder.py tests/test_diff_report.py
git commit -m "feat(diff): add report models and text spans"
```

## Task 2: Pack Metadata, Paragraph Anchors, And Chunk Status

**Files:**
- Modify: `edgarpack/diff/report_builder.py`
- Modify: `tests/test_diff_report.py`

- [ ] **Step 1: Write failing tests for paragraph anchors and missing chunks**

Append to `tests/test_diff_report.py`:

```python
import hashlib
import json
from pathlib import Path

from edgarpack.diff.report_builder import build_pair_report


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
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_diff_report.py::test_build_pair_report_adds_source_refs_and_paragraph_offsets -q
```

Expected: FAIL with `ImportError` for `build_pair_report`.

- [ ] **Step 3: Implement pair report builder and paragraph indexing**

Append/replace `edgarpack/diff/report_builder.py` with the existing `build_text_spans()` plus these definitions:

```python
import json
from dataclasses import dataclass
from pathlib import Path

from .models import ChangeType, ParagraphDelta
from .section_diff import diff_filings
from .text_diff import _split_paragraphs
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


@dataclass(frozen=True)
class ParagraphLocation:
    text: str
    paragraph_index: int
    char_start: int
    char_end: int


def _load_manifest(pack_dir: Path) -> dict:
    return json.loads((pack_dir / "manifest.json").read_text(encoding="utf-8"))


def _filing_ref(pack_dir: Path, manifest: dict) -> FilingSourceRef:
    filing = manifest.get("filing", {})
    source = manifest.get("source", {})
    return FilingSourceRef(
        accession=str(filing.get("accession", "")),
        cik=str(filing.get("cik", "")),
        company_name=str(filing.get("company_name", "")),
        form_type=str(filing.get("form_type", "")),
        filing_date=str(filing.get("filing_date", "")),
        source_url=source.get("url") if isinstance(source.get("url"), str) else None,
        pack_dir=str(pack_dir),
    )


def _sections_by_id(manifest: dict) -> dict[str, dict]:
    return {str(s.get("id", "")): s for s in manifest.get("sections", [])}


def _section_ref(section: dict | None) -> SectionSourceRef | None:
    if not section:
        return None
    return SectionSourceRef(
        section_id=str(section.get("id", "")),
        title=str(section.get("title", "")),
        path=str(section.get("path", "")),
        char_start=int(section.get("char_start", 0) or 0),
        char_end=int(section.get("char_end", 0) or 0),
        sha256=str(section.get("sha256", "")),
    )


def _section_text(pack_dir: Path, section: dict | None) -> str:
    if not section:
        return ""
    path = section.get("path")
    if not isinstance(path, str) or not path:
        return ""
    full_path = pack_dir / path
    if not full_path.exists():
        return ""
    return full_path.read_text(encoding="utf-8")


def _paragraph_locations(text: str) -> list[ParagraphLocation]:
    locations: list[ParagraphLocation] = []
    search_from = 0
    for idx, para in enumerate(_split_paragraphs(text), start=1):
        start = text.find(para, search_from)
        if start < 0:
            start = search_from
        end = start + len(para)
        locations.append(
            ParagraphLocation(
                text=para,
                paragraph_index=idx,
                char_start=start,
                char_end=end,
            )
        )
        search_from = end
    return locations


def _locate_paragraph(
    locations: list[ParagraphLocation],
    text: str | None,
    used: set[int],
) -> ParagraphLocation | None:
    if text is None:
        return None
    for loc in locations:
        if loc.paragraph_index not in used and loc.text == text:
            used.add(loc.paragraph_index)
            return loc
    return None


def _anchor(
    source: FilingSourceRef,
    section_ref: SectionSourceRef | None,
    loc: ParagraphLocation | None,
) -> EvidenceAnchor | None:
    if section_ref is None or loc is None:
        return None
    return EvidenceAnchor(
        accession=source.accession,
        section_id=section_ref.section_id,
        section_path=section_ref.path,
        paragraph_index=loc.paragraph_index,
        char_start=loc.char_start,
        char_end=loc.char_end,
    )


def _report_paragraphs(
    deltas: list[ParagraphDelta],
    before_source: FilingSourceRef,
    after_source: FilingSourceRef,
    old_ref: SectionSourceRef | None,
    new_ref: SectionSourceRef | None,
    old_locations: list[ParagraphLocation],
    new_locations: list[ParagraphLocation],
) -> list[ReportParagraphDelta]:
    old_used: set[int] = set()
    new_used: set[int] = set()
    paragraphs: list[ReportParagraphDelta] = []
    for delta in deltas:
        old_loc = _locate_paragraph(old_locations, delta.old_text, old_used)
        new_loc = _locate_paragraph(new_locations, delta.new_text, new_used)
        old_spans: list[TextSpan] = []
        new_spans: list[TextSpan] = []
        if delta.change_type == ChangeType.MODIFIED and delta.old_text and delta.new_text:
            old_spans, new_spans = build_text_spans(delta.old_text, delta.new_text)
        paragraphs.append(
            ReportParagraphDelta(
                change_type=delta.change_type,
                old_anchor=_anchor(before_source, old_ref, old_loc),
                new_anchor=_anchor(after_source, new_ref, new_loc),
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
    for para in paragraphs:
        if para.change_type == ChangeType.UNCHANGED:
            groups.append(ParagraphGroup(kind="context", paragraphs=[para]))
        else:
            groups.append(ParagraphGroup(kind="changed", paragraphs=[para]))
    return groups


def build_pair_report(before_dir: Path, after_dir: Path) -> DiffReport:
    before_manifest = _load_manifest(before_dir)
    after_manifest = _load_manifest(after_dir)
    before_source = _filing_ref(before_dir, before_manifest)
    after_source = _filing_ref(after_dir, after_manifest)
    before_sections = _sections_by_id(before_manifest)
    after_sections = _sections_by_id(after_manifest)
    diff = diff_filings(before_dir, after_dir)

    sections: list[ReportSectionDelta] = []
    for delta in diff.section_deltas:
        before_section = before_sections.get(delta.section_id)
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
```

- [ ] **Step 4: Run focused test**

Run:

```bash
uv run pytest tests/test_diff_report.py::test_build_pair_report_adds_source_refs_and_paragraph_offsets -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add edgarpack/diff/report_builder.py tests/test_diff_report.py
git commit -m "feat(diff): build anchored pair reports"
```

## Task 3: Chunk Lookup And Context Collapsing

**Files:**
- Modify: `edgarpack/diff/report_builder.py`
- Modify: `tests/test_diff_report.py`

- [ ] **Step 1: Write failing tests for available chunks and collapsed context**

Append to `tests/test_diff_report.py`:

```python
def _write_chunks(pack: Path, section_id: str, body: str, chunk_id: str) -> None:
    optional = pack / "optional"
    optional.mkdir(exist_ok=True)
    payload = {
        "chunk_id": chunk_id,
        "section_id": section_id,
        "chunk_index": 0,
        "text": body,
        "char_start": 0,
        "char_end": len(body),
        "tokens": len(body.split()),
    }
    (optional / "chunks.ndjson").write_text(json.dumps(payload) + "\n", encoding="utf-8")


def test_build_pair_report_maps_chunk_ids_when_chunks_cover_paragraph(tmp_path) -> None:
    before_body = "Intro paragraph.\n\nOld customer concentration disclosure."
    after_body = "Intro paragraph.\n\nNew customer concentration disclosure."
    before = _write_pack(tmp_path, "S1-001", before_body)
    after = _write_pack(tmp_path, "S1A-002", after_body)
    _write_chunks(before, "s1_risk_factors", before_body, "c-before")
    _write_chunks(after, "s1_risk_factors", after_body, "c-after")

    report = build_pair_report(before, after)

    assert report.chunk_status == "available"
    changed = [
        p
        for section in report.sections
        for group in section.groups
        for p in group.paragraphs
        if p.change_type.value == "modified"
    ][0]
    assert changed.old_anchor is not None
    assert changed.new_anchor is not None
    assert changed.old_anchor.chunk_id == "c-before"
    assert changed.new_anchor.chunk_id == "c-after"


def test_build_pair_report_collapses_long_unchanged_runs(tmp_path) -> None:
    unchanged = "\n\n".join(f"Unchanged paragraph {i}." for i in range(1, 8))
    before = _write_pack(tmp_path, "S1-001", f"{unchanged}\n\nOld risk text.")
    after = _write_pack(tmp_path, "S1A-002", f"{unchanged}\n\nNew risk text.")

    report = build_pair_report(before, after)

    groups = report.sections[0].groups
    collapsed = [g for g in groups if g.kind == "collapsed"]
    assert collapsed
    assert collapsed[0].collapsed_count >= 3
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest \
  tests/test_diff_report.py::test_build_pair_report_maps_chunk_ids_when_chunks_cover_paragraph \
  tests/test_diff_report.py::test_build_pair_report_collapses_long_unchanged_runs \
  -q
```

Expected: FAIL because chunk IDs are not mapped and long unchanged runs are not collapsed.

- [ ] **Step 3: Add chunk lookup and context grouping**

Update `edgarpack/diff/report_builder.py`:

```python
@dataclass(frozen=True)
class ChunkLocation:
    chunk_id: str
    section_id: str
    char_start: int
    char_end: int


def _load_chunks(pack_dir: Path) -> list[ChunkLocation]:
    path = pack_dir / "optional" / "chunks.ndjson"
    if not path.exists():
        return []
    chunks: list[ChunkLocation] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        data = json.loads(line)
        chunks.append(
            ChunkLocation(
                chunk_id=str(data.get("chunk_id", "")),
                section_id=str(data.get("section_id", "")),
                char_start=int(data.get("char_start", 0) or 0),
                char_end=int(data.get("char_end", 0) or 0),
            )
        )
    return chunks


def _chunk_id_for(
    chunks: list[ChunkLocation],
    section_id: str,
    loc: ParagraphLocation | None,
) -> str | None:
    if loc is None:
        return None
    for chunk in chunks:
        if (
            chunk.section_id == section_id
            and chunk.char_start <= loc.char_start
            and loc.char_end <= chunk.char_end
        ):
            return chunk.chunk_id
    return None
```

Change `_anchor()` signature and call sites:

```python
def _anchor(
    source: FilingSourceRef,
    section_ref: SectionSourceRef | None,
    loc: ParagraphLocation | None,
    chunks: list[ChunkLocation],
) -> EvidenceAnchor | None:
    if section_ref is None or loc is None:
        return None
    return EvidenceAnchor(
        accession=source.accession,
        section_id=section_ref.section_id,
        section_path=section_ref.path,
        paragraph_index=loc.paragraph_index,
        char_start=loc.char_start,
        char_end=loc.char_end,
        chunk_id=_chunk_id_for(chunks, section_ref.section_id, loc),
    )
```

Replace `_report_paragraphs()` with:

```python
def _report_paragraphs(
    deltas: list[ParagraphDelta],
    before_source: FilingSourceRef,
    after_source: FilingSourceRef,
    old_ref: SectionSourceRef | None,
    new_ref: SectionSourceRef | None,
    old_locations: list[ParagraphLocation],
    new_locations: list[ParagraphLocation],
    old_chunks: list[ChunkLocation],
    new_chunks: list[ChunkLocation],
) -> list[ReportParagraphDelta]:
    old_used: set[int] = set()
    new_used: set[int] = set()
    paragraphs: list[ReportParagraphDelta] = []
    for delta in deltas:
        old_loc = _locate_paragraph(old_locations, delta.old_text, old_used)
        new_loc = _locate_paragraph(new_locations, delta.new_text, new_used)
        old_spans: list[TextSpan] = []
        new_spans: list[TextSpan] = []
        if delta.change_type == ChangeType.MODIFIED and delta.old_text and delta.new_text:
            old_spans, new_spans = build_text_spans(delta.old_text, delta.new_text)
        paragraphs.append(
            ReportParagraphDelta(
                change_type=delta.change_type,
                old_anchor=_anchor(before_source, old_ref, old_loc, old_chunks),
                new_anchor=_anchor(after_source, new_ref, new_loc, new_chunks),
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
```

Replace `_simple_groups()` with:

```python
def _group_paragraphs(
    paragraphs: list[ReportParagraphDelta],
    context_window: int = 1,
) -> list[ParagraphGroup]:
    groups: list[ParagraphGroup] = []
    i = 0
    while i < len(paragraphs):
        para = paragraphs[i]
        if para.change_type != ChangeType.UNCHANGED:
            groups.append(ParagraphGroup(kind="changed", paragraphs=[para]))
            i += 1
            continue

        run_start = i
        while i < len(paragraphs) and paragraphs[i].change_type == ChangeType.UNCHANGED:
            i += 1
        run = paragraphs[run_start:i]
        if len(run) <= context_window * 2:
            groups.extend(ParagraphGroup(kind="context", paragraphs=[p]) for p in run)
            continue

        head = run[:context_window]
        tail = run[-context_window:]
        middle = run[context_window:-context_window]
        groups.extend(ParagraphGroup(kind="context", paragraphs=[p]) for p in head)
        groups.append(
            ParagraphGroup(
                kind="collapsed",
                collapsed_count=len(middle),
                collapsed_word_count=sum(
                    max(p.old_word_count, p.new_word_count) for p in middle
                ),
            )
        )
        groups.extend(ParagraphGroup(kind="context", paragraphs=[p]) for p in tail)
    return groups
```

In `build_pair_report()`, load chunks once:

```python
before_chunks = _load_chunks(before_dir)
after_chunks = _load_chunks(after_dir)
if before_chunks and after_chunks:
    chunk_status = "available"
elif before_chunks or after_chunks:
    chunk_status = "partial"
else:
    chunk_status = "missing"
```

Pass chunks to `_report_paragraphs()` and use `_group_paragraphs(paragraphs)`.

- [ ] **Step 4: Run tests**

Run:

```bash
uv run pytest tests/test_diff_report.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add edgarpack/diff/report_builder.py tests/test_diff_report.py
git commit -m "feat(diff): map chunks and collapse context"
```

## Task 4: Static Pair HTML Renderer

**Files:**
- Create: `edgarpack/diff/html_report.py`
- Modify: `tests/test_diff_report.py`

- [ ] **Step 1: Write failing renderer test**

Append to `tests/test_diff_report.py`:

```python
from edgarpack.diff.html_report import render_pair_report_html


def test_render_pair_report_html_escapes_text_and_emits_static_report(tmp_path) -> None:
    before = _write_pack(
        tmp_path,
        "S1-001",
        "Intro paragraph.\n\nOld <script>alert('x')</script> risk text.",
    )
    after = _write_pack(
        tmp_path,
        "S1A-002",
        "Intro paragraph.\n\nNew <b>risk</b> text.",
    )

    report = build_pair_report(before, after)
    html = render_pair_report_html(report, reproduce_command="edgarpack diff --format html")

    assert "<script" not in html.lower()
    assert "&lt;script&gt;" in html
    assert "&lt;b&gt;risk&lt;/b&gt;" in html
    assert "edgarpack" in html
    assert "S1-001" in html and "S1A-002" in html
    assert "section-rail" in html
    assert "diff-pane" in html
    assert "evidence-line" in html
    assert "chunk status" in html.lower()
    assert "Reproduce" in html
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
uv run pytest tests/test_diff_report.py::test_render_pair_report_html_escapes_text_and_emits_static_report -q
```

Expected: FAIL with `ModuleNotFoundError` for `edgarpack.diff.html_report`.

- [ ] **Step 3: Add pair HTML renderer**

Create `edgarpack/diff/html_report.py`:

```python
"""Static HTML rendering for filing diff reports."""

from __future__ import annotations

from html import escape

from .models import ChangeType
from .report_models import DiffReport, ParagraphGroup, ReportParagraphDelta, TextSpan

_CSS = """
:root {
  --paper: #f4efdf;
  --surface: #fffdf6;
  --ink: #1d1b17;
  --muted: #6f6a5e;
  --rule: #dfd6bd;
  --add-bg: #eef8eb;
  --add-ink: #2f6846;
  --del-bg: #f9e8e8;
  --del-ink: #8c3838;
  --code: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  --sans: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  --serif: Georgia, "Times New Roman", serif;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--paper); color: var(--ink); font-family: var(--sans); }
a { color: #315da8; text-decoration: none; }
a:focus { outline: 2px solid #315da8; outline-offset: 2px; }
.topbar { display: flex; justify-content: space-between; gap: 1rem; padding: .9rem 1.4rem; border-bottom: 1px solid var(--rule); font-family: var(--code); font-size: .85rem; }
.brand { font-family: var(--sans); font-weight: 700; margin-right: 1rem; }
.pair-hero { padding: 2.5rem 1.6rem 2rem; border-bottom: 1px solid var(--rule); background: var(--surface); }
.crumbs, .stats, .evidence-line, .footer-label { color: var(--muted); font-family: var(--code); font-size: .82rem; }
h1 { margin: .7rem 0 1rem; font-size: clamp(2rem, 4vw, 3.3rem); letter-spacing: .02em; }
.layout { display: grid; grid-template-columns: 21rem minmax(0, 1fr); align-items: start; }
.section-rail { position: sticky; top: 0; min-height: 100vh; padding: 1.7rem 1.4rem; border-right: 1px solid var(--rule); background: rgba(255, 253, 246, .72); }
.rail-title { margin: 0 0 1.3rem; font-weight: 700; color: var(--muted); }
.rail-row { display: grid; grid-template-columns: 4.8rem 1fr auto auto; gap: .65rem; padding: .55rem 0; border-bottom: 1px solid rgba(223, 214, 189, .6); font-size: .9rem; }
.rail-id { font-family: var(--code); color: var(--muted); overflow-wrap: anywhere; }
.rail-added { color: var(--add-ink); font-family: var(--code); }
.rail-removed { color: var(--del-ink); font-family: var(--code); }
.diff-pane { min-width: 0; }
.section-hunk { border-bottom: 1px solid var(--rule); }
.hunk-header { display: flex; justify-content: space-between; gap: 1rem; padding: 1rem 1.8rem; background: rgba(244, 239, 223, .82); border-bottom: 1px solid var(--rule); }
.hunk-title { margin: 0; font-size: 1rem; }
.paragraph-row { display: grid; grid-template-columns: 4rem 3rem minmax(0, 1fr); border-bottom: 1px solid rgba(223, 214, 189, .55); background: var(--surface); }
.gutter { padding: 1rem .7rem; border-right: 1px solid rgba(223, 214, 189, .7); color: var(--muted); font-family: var(--code); text-align: right; }
.marker { padding: 1rem .7rem; border-right: 1px solid rgba(223, 214, 189, .7); font-family: var(--code); text-align: center; }
.body { min-width: 0; }
.prose { padding: 1rem 1.6rem; font-family: var(--serif); font-size: 1.2rem; line-height: 1.65; }
.old { background: var(--del-bg); color: var(--del-ink); }
.new { background: var(--add-bg); color: var(--ink); }
.context { background: var(--surface); }
.op-delete, .op-replace.old-span { background: rgba(140, 56, 56, .16); text-decoration: line-through; }
.op-insert, .op-replace.new-span { background: rgba(47, 104, 70, .17); }
.evidence-line { display: flex; flex-wrap: wrap; gap: 1rem; padding: .65rem 1.6rem; border-top: 1px solid rgba(223, 214, 189, .55); background: #fbf7ea; }
details.collapsed { padding: .8rem 1.6rem; color: var(--muted); font-family: var(--code); border-bottom: 1px solid rgba(223, 214, 189, .55); }
.provenance-footer { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 2rem; padding: 2rem 1.6rem; border-top: 1px solid var(--rule); font-family: var(--code); font-size: .86rem; }
pre { margin: .4rem 0 0; padding: .9rem; background: var(--surface); border: 1px solid var(--rule); overflow: auto; }
@media (max-width: 900px) {
  .layout { grid-template-columns: 1fr; }
  .section-rail { position: static; min-height: auto; border-right: 0; border-bottom: 1px solid var(--rule); }
  .paragraph-row { grid-template-columns: 3.2rem 2.6rem minmax(0, 1fr); }
  .provenance-footer { grid-template-columns: 1fr; }
}
@media print {
  .topbar, .section-rail { position: static; }
  a { color: inherit; text-decoration: underline; }
}
"""


def _span_html(span: TextSpan) -> str:
    side_class = "old-span" if span.side == "old" else "new-span"
    return f'<span class="op-{span.op} {side_class}">{escape(span.text)}</span>'


def _prose_html(para: ReportParagraphDelta, side: str) -> str:
    if side == "old":
        spans = para.old_spans
        text = para.old_text
        cls = "old"
    else:
        spans = para.new_spans
        text = para.new_text
        cls = "new"
    content = "".join(_span_html(span) for span in spans) if spans else escape(text or "")
    return f'<div class="prose {cls}">{content}</div>'


def _anchor_html(para: ReportParagraphDelta) -> str:
    anchor = para.new_anchor or para.old_anchor
    if anchor is None:
        return '<div class="evidence-line"><span>chunk status missing</span></div>'
    chunk = anchor.chunk_id or "missing"
    return (
        '<div class="evidence-line">'
        f"<span>accession {escape(anchor.accession)}</span>"
        f"<span>section {escape(anchor.section_id)}</span>"
        f"<span>paragraph {anchor.paragraph_index}</span>"
        f"<span>offset {anchor.char_start}-{anchor.char_end}</span>"
        f"<span>chunk {escape(chunk)}</span>"
        f'<a href="{escape(anchor.section_path)}">pack</a>'
        "</div>"
    )


def _paragraph_html(para: ReportParagraphDelta) -> str:
    marker = {
        ChangeType.ADDED: "+",
        ChangeType.REMOVED: "-",
        ChangeType.MODIFIED: "~",
        ChangeType.UNCHANGED: ".",
    }[para.change_type]
    anchor = para.new_anchor or para.old_anchor
    para_index = anchor.paragraph_index if anchor else 0
    blocks: list[str] = []
    if para.change_type in {ChangeType.REMOVED, ChangeType.MODIFIED, ChangeType.UNCHANGED}:
        blocks.append(_prose_html(para, "old"))
    if para.change_type in {ChangeType.ADDED, ChangeType.MODIFIED}:
        blocks.append(_prose_html(para, "new"))
    blocks.append(_anchor_html(para))
    return (
        '<div class="paragraph-row">'
        f'<div class="gutter">¶ {para_index}</div>'
        f'<div class="marker">{marker}</div>'
        f'<div class="body">{"".join(blocks)}</div>'
        "</div>"
    )


def _group_html(group: ParagraphGroup) -> str:
    if group.kind == "collapsed":
        return (
            '<details class="collapsed">'
            f"<summary>{group.collapsed_count} unchanged paragraphs · "
            f"{group.collapsed_word_count} words collapsed</summary>"
            "</details>"
        )
    return "".join(_paragraph_html(para) for para in group.paragraphs)


def render_pair_report_html(report: DiffReport, reproduce_command: str = "") -> str:
    sections_nav = "\n".join(
        '<a class="rail-row" href="#section-{sid}">'
        '<span class="rail-id">{sid}</span><span>{title}</span>'
        '<span class="rail-added">+{added}</span><span class="rail-removed">-{removed}</span>'
        "</a>".format(
            sid=escape(section.section_id),
            title=escape(section.title),
            added=section.paragraphs_added,
            removed=section.paragraphs_removed,
        )
        for section in report.sections
        if section.change_type != ChangeType.UNCHANGED
    )
    section_html = "\n".join(
        '<section class="section-hunk" id="section-{sid}">'
        '<header class="hunk-header">'
        '<h2 class="hunk-title">{title}</h2>'
        '<a href="#section-{sid}">copy permalink</a>'
        "</header>"
        "{groups}"
        "</section>".format(
            sid=escape(section.section_id),
            title=escape(section.title),
            groups="".join(_group_html(group) for group in section.groups),
        )
        for section in report.sections
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(report.before_source.accession)} -> {escape(report.after_source.accession)}</title>
  <style>{_CSS}</style>
</head>
<body>
  <header class="topbar">
    <div><span class="brand">edgarpack</span> diff --format html</div>
    <nav><a href="#provenance">provenance</a></nav>
  </header>
  <section class="pair-hero">
    <div class="crumbs">pair report · {escape(report.before_source.company_name)} · chunk status {escape(report.chunk_status)}</div>
    <h1>{escape(report.before_source.accession)} -> {escape(report.after_source.accession)}</h1>
    <div class="stats">+{report.sections_added} sections · -{report.sections_removed} sections · ~{report.sections_modified} modified · {report.overall_change_intensity:.1%} intensity</div>
  </section>
  <main class="layout">
    <aside class="section-rail" aria-label="Changed sections">
      <p class="rail-title">{report.sections_modified + report.sections_added + report.sections_removed} changed sections</p>
      {sections_nav}
    </aside>
    <div class="diff-pane">{section_html}</div>
  </main>
  <footer class="provenance-footer" id="provenance">
    <div><div class="footer-label">SEC EDGAR</div><p><a href="{escape(report.before_source.source_url or '#')}">{escape(report.before_source.source_url or 'missing')}</a></p><p><a href="{escape(report.after_source.source_url or '#')}">{escape(report.after_source.source_url or 'missing')}</a></p></div>
    <div><div class="footer-label">Local pack files</div><p>{escape(report.before_source.pack_dir)}</p><p>{escape(report.after_source.pack_dir)}</p></div>
    <div><div class="footer-label">Reproduce</div><pre>{escape(reproduce_command)}</pre></div>
  </footer>
</body>
</html>
"""
```

- [ ] **Step 4: Run tests**

Run:

```bash
uv run pytest tests/test_diff_report.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add edgarpack/diff/html_report.py tests/test_diff_report.py
git commit -m "feat(diff): render static pair html reports"
```

## Task 5: Wire `diff --format html --out`

**Files:**
- Modify: `edgarpack/cli.py`
- Modify: `tests/test_diff_report.py`

- [ ] **Step 1: Write failing CLI tests for pair HTML output and missing `--out`**

Append to `tests/test_diff_report.py`:

```python
import subprocess
import sys


def test_cli_diff_html_writes_report_to_out_path(tmp_path) -> None:
    before = _write_pack(tmp_path, "S1-001", "Old customer disclosure.")
    after = _write_pack(tmp_path, "S1A-002", "New customer disclosure.")
    out = tmp_path / "report.html"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "edgarpack.cli",
            "diff",
            "--before",
            str(before),
            "--after",
            str(after),
            "--format",
            "html",
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert out.exists()
    html = out.read_text(encoding="utf-8")
    assert "diff-pane" in html
    assert "S1-001" in html and "S1A-002" in html
    assert "Wrote HTML diff report" in result.stdout


def test_cli_diff_html_requires_out_path(tmp_path) -> None:
    before = _write_pack(tmp_path, "S1-001", "Old customer disclosure.")
    after = _write_pack(tmp_path, "S1A-002", "New customer disclosure.")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "edgarpack.cli",
            "diff",
            "--before",
            str(before),
            "--after",
            str(after),
            "--format",
            "html",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "--out is required" in result.stderr
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest \
  tests/test_diff_report.py::test_cli_diff_html_writes_report_to_out_path \
  tests/test_diff_report.py::test_cli_diff_html_requires_out_path \
  -q
```

Expected: FAIL because `html` is not an accepted format.

- [ ] **Step 3: Add CLI arguments**

In `edgarpack/cli.py`, update the `diff` parser:

```python
p_diff.add_argument(
    "--format",
    dest="output_format",
    choices=["summary", "full", "json", "html"],
    default="summary",
    help="Output format (default: summary)",
)
p_diff.add_argument(
    "--out",
    "-o",
    type=Path,
    help="Output path for --format html",
)
```

- [ ] **Step 4: Add HTML branch in `_cmd_diff`**

In `_cmd_diff`, after pack directory validation and before `diff_filings()` JSON/text handling, add:

```python
if args.output_format == "html":
    out_path = getattr(args, "out", None)
    if out_path is None:
        print("error: --out is required when --format html", file=sys.stderr)
        return 2
    from .diff.html_report import render_pair_report_html
    from .diff.report_builder import build_pair_report

    report = build_pair_report(before_dir, after_dir)
    command = (
        "edgarpack diff "
        f"--before {before_dir} --after {after_dir} --format html --out {out_path}"
    )
    html = render_pair_report_html(report, reproduce_command=command)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"Wrote HTML diff report to {out_path}")
    return 0
```

Keep the existing `result = diff_filings(before_dir, after_dir)` path for non-HTML formats.

- [ ] **Step 5: Run focused tests**

Run:

```bash
uv run pytest tests/test_diff_report.py -q
uv run pytest tests/test_diff.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add edgarpack/cli.py tests/test_diff_report.py
git commit -m "feat(cli): add html diff reports"
```

## Task 6: Registration Timeline HTML Index And Pair Pages

**Files:**
- Modify: `edgarpack/diff/html_report.py`
- Modify: `edgarpack/cli.py`
- Modify: `tests/test_cli_registration_timeline_render.py`

- [ ] **Step 1: Write failing registration timeline HTML test**

Append to `tests/test_cli_registration_timeline_render.py`:

```python
def test_registration_timeline_html_writes_index_and_pair_pages(tmp_path):
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
            )
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
                "We depend on a single customer for the majority of revenue.",
            ),
            (
                "s1_dilution",
                "sections/dilution.md",
                "Dilution",
                "Investors will experience immediate dilution.",
            ),
        ],
    )
    out_dir = tmp_path / "report"

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
    index = out_dir / "index.html"
    pair = out_dir / "pair-001.html"
    assert index.exists()
    assert pair.exists()
    assert "pair-001.html" in index.read_text(encoding="utf-8")
    assert "diff-pane" in pair.read_text(encoding="utf-8")
    assert "Wrote HTML registration timeline report" in result.stdout
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
uv run pytest tests/test_cli_registration_timeline_render.py::test_registration_timeline_html_writes_index_and_pair_pages -q
```

Expected: FAIL because `timeline` has no `--format` argument.

- [ ] **Step 3: Add timeline CLI arguments**

In `edgarpack/cli.py`, add to the timeline parser after `--series`:

```python
p_timeline.add_argument(
    "--format",
    dest="output_format",
    choices=["text", "html"],
    default="text",
    help="Output format (default: text)",
)
p_timeline.add_argument(
    "--out",
    "-o",
    type=Path,
    help="Output directory for --format html",
)
```

- [ ] **Step 4: Add timeline index renderer**

Append to `edgarpack/diff/html_report.py`:

```python
from .report_models import TimelineReport


def render_timeline_index_html(report: TimelineReport) -> str:
    rows = "\n".join(
        '<li><a href="{file}">pair {idx:03d}: {before} -> {after}</a> '
        '<span class="stats">+{added} -{removed} ~{modified} · {intensity:.1%}</span></li>'.format(
            file=escape(t.output_file),
            idx=t.index,
            before=escape(t.before.accession),
            after=escape(t.after.accession),
            added=t.sections_added,
            removed=t.sections_removed,
            modified=t.sections_modified,
            intensity=t.overall_change_intensity,
        )
        for t in report.transitions
    )
    filings = "\n".join(
        f"<li>{escape(e.filing_date)} · {escape(e.form_type)} · {escape(e.accession)}</li>"
        for e in report.entries
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Registration timeline {escape(report.cik)}</title>
  <style>{_CSS}</style>
</head>
<body>
  <header class="topbar"><div><span class="brand">edgarpack</span> timeline --series registration --format html</div></header>
  <section class="pair-hero">
    <div class="crumbs">registration timeline</div>
    <h1>CIK {escape(report.cik)}</h1>
    <div class="stats">{len(report.entries)} filings · {len(report.transitions)} transitions</div>
  </section>
  <main class="layout">
    <aside class="section-rail"><p class="rail-title">Filing trail</p><ol>{filings}</ol></aside>
    <section class="diff-pane section-hunk"><header class="hunk-header"><h2 class="hunk-title">Pair reports</h2></header><ol>{rows}</ol></section>
  </main>
</body>
</html>
"""
```

- [ ] **Step 5: Add registration HTML branch**

In `_render_registration_timeline(args)`, after `entries` is validated and before printing text output, add:

```python
if getattr(args, "output_format", "text") == "html":
    out_dir = getattr(args, "out", None)
    if out_dir is None:
        print("error: --out is required when --format html", file=sys.stderr)
        return 2
    from .diff.html_report import render_pair_report_html, render_timeline_index_html
    from .diff.report_builder import build_pair_report
    from .diff.report_models import TimelineReport, TimelineReportEntry, TimelineTransition

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    timeline_entries = [
        TimelineReportEntry(
            accession=e.accession,
            form_type=e.form_type,
            filing_date=e.filing_date,
            pack_dir=str(e.pack_dir),
        )
        for e in entries
    ]
    transitions: list[TimelineTransition] = []
    for idx, (before, after) in enumerate(zip(entries, entries[1:], strict=False), start=1):
        pair_file = f"pair-{idx:03d}.html"
        report = build_pair_report(before.pack_dir, after.pack_dir)
        html = render_pair_report_html(
            report,
            reproduce_command=(
                "edgarpack timeline "
                f"--series registration --cik {args.cik} --packs {pack_root} "
                f"--format html --out {out_dir}"
            ),
        )
        (out_dir / pair_file).write_text(html, encoding="utf-8")
        transitions.append(
            TimelineTransition(
                index=idx,
                before=timeline_entries[idx - 1],
                after=timeline_entries[idx],
                output_file=pair_file,
                sections_added=report.sections_added,
                sections_removed=report.sections_removed,
                sections_modified=report.sections_modified,
                sections_unchanged=report.sections_unchanged,
                overall_change_intensity=report.overall_change_intensity,
            )
        )
    timeline = TimelineReport(cik=args.cik, entries=timeline_entries, transitions=transitions)
    (out_dir / "index.html").write_text(render_timeline_index_html(timeline), encoding="utf-8")
    print(f"Wrote HTML registration timeline report to {out_dir}")
    return 0
```

- [ ] **Step 6: Annual timeline unsupported guard**

In `_cmd_timeline(args)`, before the annual async path:

```python
if getattr(args, "output_format", "text") == "html":
    print("error: --format html is currently supported only with --series registration", file=sys.stderr)
    return 2
```

This guard must run only after the `series == "registration"` branch has had a chance to handle HTML.

- [ ] **Step 7: Run timeline tests**

Run:

```bash
uv run pytest tests/test_cli_registration_timeline_render.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

Run:

```bash
git add edgarpack/cli.py edgarpack/diff/html_report.py tests/test_cli_registration_timeline_render.py
git commit -m "feat(cli): add registration timeline html reports"
```

## Task 7: Visual Fidelity Pass Against Paper Baseline

**Files:**
- Modify: `edgarpack/diff/html_report.py`
- Modify: `tests/test_diff_report.py`

- [ ] **Step 1: Write structural visual contract test**

Append to `tests/test_diff_report.py`:

```python
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
```

- [ ] **Step 2: Run test**

Run:

```bash
uv run pytest tests/test_diff_report.py::test_pair_report_html_uses_approved_visual_structure -q
```

Expected: PASS if earlier renderer used the planned classes. If it fails, update only `html_report.py` structure and CSS to match the visual contract.

- [ ] **Step 3: Manual visual smoke on local Cerebras packs**

Run:

```bash
uv run edgarpack timeline \
  --series registration \
  --cik 0002021728 \
  --packs ./packs \
  --format html \
  --out /tmp/cerebras-s1-report
```

Expected: command exits 0 and writes `/tmp/cerebras-s1-report/index.html` plus pair pages. If there are fewer than two local registration packs, run the CLI test fixture path instead and report that local smoke could not use real packs.

- [ ] **Step 4: Inspect generated HTML for forbidden patterns**

Run:

```bash
rg -n "<script|Customer concentration risk worsened|more concerned about China|Management softened" /tmp/cerebras-s1-report || true
```

Expected: no matches.

- [ ] **Step 5: Commit visual refinements if changed**

If Step 2 or Step 3 required changes:

```bash
git add edgarpack/diff/html_report.py tests/test_diff_report.py
git commit -m "polish(diff): align html report with visual baseline"
```

If no changes were required, do not create an empty commit.

## Task 8: Final Regression, Bead Update, And Push

**Files:**
- Modify: `.beads/issues.jsonl`

- [ ] **Step 1: Run focused gates**

Run:

```bash
uv run ruff check .
uv run pytest tests/test_diff.py tests/test_diff_report.py tests/test_cli_registration_timeline_render.py -q
```

Expected: PASS.

- [ ] **Step 2: Run full offline suite if shared parser/manifest/diff internals changed**

If implementation touched anything beyond `edgarpack/diff/report_models.py`, `edgarpack/diff/report_builder.py`, `edgarpack/diff/html_report.py`, `edgarpack/cli.py`, and the named tests, run:

```bash
uv run pytest -q
```

Expected: PASS. If not run, state why in the final handoff.

- [ ] **Step 3: Update bead status**

Run:

```bash
bd update edgarpack-nqy --status in_progress
bd sync
```

Expected: bead remains `in_progress` unless the user explicitly wants it closed after this first implementation. Do not close if vNext `trace` remains broader than the current Observatory HTML report.

- [ ] **Step 4: Pull, push, and verify status**

Run:

```bash
git pull --rebase
git push -u origin feature/static-diff-report
git status --short --untracked-files=all
```

Expected: branch pushes successfully. Status is clean in the implementation worktree.

- [ ] **Step 5: Final handoff**

Report:

- files changed
- commits created
- exact test commands and results
- path to generated HTML report
- whether full offline suite was run
- remaining work, especially the deferred vNext `trace` command and generated findings layer
