"""Static HTML rendering for filing diff reports."""

from __future__ import annotations

import posixpath
import re
from html import escape
from pathlib import Path
from urllib.parse import quote, urlsplit

from .models import ChangeType
from .report_models import (
    DiffReport,
    EvidenceAnchor,
    ParagraphGroup,
    ReportParagraphDelta,
    ReportSectionDelta,
    TextSpan,
    TimelineReport,
)

# Below this paragraph-pair Jaccard similarity the old/new texts are effectively
# different paragraphs (pairs under 0.5 were admitted by the overlap rescue, not
# token overlap); render them stacked instead of as an inline word-level redline.
_UNIFIED_VIEW_MIN_SIMILARITY = 0.5

_CSS = """
:root {
  --paper: #f7f3e8;
  --surface: #fffdf8;
  --ink: #1f1d18;
  --muted: #6d675c;
  --faint: #9a937f;
  --rule: #ddd3bd;
  --rule-soft: #eae2cf;
  --add-bg: #eef6ee;
  --add-ink: #285d3d;
  --add-mark: #d7ecda;
  --del-bg: #f9ecea;
  --del-ink: #8a3d35;
  --del-mark: #f3d8d3;
  --focus: #1c5d99;
  --serif: Georgia, "Times New Roman", serif;
  --code: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  --sans: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
* { box-sizing: border-box; }
html { scroll-behavior: auto; }
body {
  margin: 0;
  background: var(--paper);
  color: var(--ink);
  font-family: var(--sans);
  line-height: 1.45;
}
a { color: var(--focus); text-decoration-thickness: .08em; text-underline-offset: .18em; }
a:focus-visible, summary:focus-visible {
  outline: 3px solid var(--focus);
  outline-offset: 3px;
}
.topbar {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  padding: .9rem 1.4rem;
  border-bottom: 1px solid var(--rule);
  background: var(--surface);
  font-family: var(--code);
  font-size: .84rem;
}
.brand {
  margin-right: .75rem;
  color: var(--ink);
  font-family: var(--sans);
  font-weight: 700;
}
.pair-hero {
  padding: 2.2rem 1.6rem 1.8rem;
  border-bottom: 1px solid var(--rule);
  background: var(--surface);
}
.crumbs, .footer-label {
  color: var(--muted);
  font-family: var(--code);
  font-size: .8rem;
}
h1 {
  margin: .35rem 0 .3rem;
  font-family: var(--serif);
  font-size: clamp(1.7rem, 3vw, 2.5rem);
  font-weight: 650;
  letter-spacing: 0;
}
.pair-line {
  margin: 0 0 .9rem;
  font-size: 1.05rem;
  color: var(--ink);
}
.pair-line .arrow { color: var(--faint); padding: 0 .3rem; }
.stats {
  display: flex;
  flex-wrap: wrap;
  gap: .4rem .6rem;
  color: var(--muted);
  font-family: var(--code);
  font-size: .8rem;
}
.stats span {
  padding: .22rem .6rem;
  border: 1px solid var(--rule-soft);
  border-radius: 999px;
  background: var(--paper);
}
.layout {
  display: grid;
  grid-template-columns: 19rem minmax(0, 1fr);
  align-items: start;
}
.section-rail {
  position: sticky;
  top: 0;
  max-height: 100vh;
  overflow-y: auto;
  padding: 1.4rem 1.15rem 2rem;
  border-right: 1px solid var(--rule);
  background: #fbf7ee;
}
.rail-title {
  margin: 0 0 .9rem;
  color: var(--muted);
  font-size: .8rem;
  font-family: var(--code);
  text-transform: uppercase;
  letter-spacing: .06em;
}
.rail-row {
  display: block;
  padding: .55rem .1rem .6rem;
  border-bottom: 1px solid var(--rule-soft);
  color: var(--ink);
  font-size: .88rem;
  text-decoration: none;
}
.rail-row:hover { background: #f4eedd; }
.rail-row .rail-name { display: block; line-height: 1.3; }
.rail-counts {
  display: flex;
  gap: .55rem;
  margin-top: .25rem;
  font-family: var(--code);
  font-size: .74rem;
}
.rail-added { color: var(--add-ink); }
.rail-removed { color: var(--del-ink); }
.rail-modified { color: #725b16; }
.rail-bar {
  height: 3px;
  margin-top: .35rem;
  border-radius: 2px;
  background: var(--rule-soft);
  overflow: hidden;
}
.rail-bar i {
  display: block;
  height: 100%;
  background: #b09a55;
}
.diff-pane { min-width: 0; }
.section-hunk {
  border-bottom: 1px solid var(--rule);
  scroll-margin-top: 3.2rem;
}
.hunk-header {
  position: sticky;
  top: 0;
  z-index: 2;
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 1rem;
  padding: .85rem 1.6rem;
  border-bottom: 1px solid var(--rule);
  background: #f0eadc;
}
.hunk-title { margin: 0; font-family: var(--serif); font-size: 1.15rem; font-weight: 650; }
.hunk-meta {
  color: var(--muted);
  font-family: var(--code);
  font-size: .78rem;
  white-space: nowrap;
}
.hunk-meta .rail-added { color: var(--add-ink); }
.hunk-meta .rail-removed { color: var(--del-ink); }
.paragraph-row {
  display: grid;
  grid-template-columns: 4.6rem minmax(0, 1fr);
  border-bottom: 1px solid var(--rule-soft);
  background: var(--surface);
}
.gutter {
  padding: 1rem .65rem 1rem .9rem;
  border-right: 1px solid var(--rule-soft);
  color: var(--faint);
  font-family: var(--code);
  font-size: .78rem;
  text-align: right;
  white-space: nowrap;
}
.gutter .marker-added { color: var(--add-ink); font-weight: 700; }
.gutter .marker-removed { color: var(--del-ink); font-weight: 700; }
.gutter .marker-modified { color: #725b16; font-weight: 700; }
.body { min-width: 0; }
.prose {
  padding: .95rem 1.6rem .8rem;
  font-family: var(--serif);
  font-size: 1.05rem;
  line-height: 1.62;
  overflow-wrap: anywhere;
}
.prose.new { border-left: 3px solid var(--add-ink); background: var(--add-bg); }
.prose.old {
  border-left: 3px solid var(--del-ink);
  background: var(--del-bg);
  color: var(--muted);
}
.prose.context {
  background: var(--surface);
  color: var(--muted);
  font-size: .95rem;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.prose.unified { background: var(--surface); }
.prose del {
  background: var(--del-mark);
  color: var(--del-ink);
  text-decoration-line: line-through;
  text-decoration-thickness: .07em;
}
.prose ins { background: var(--add-mark); text-decoration: none; }
.rewrite-badge {
  display: inline-block;
  margin: .8rem 1.6rem 0;
  padding: .1rem .55rem;
  border: 1px solid var(--rule);
  border-radius: 999px;
  color: var(--muted);
  font-family: var(--code);
  font-size: .72rem;
}
.moved-badge { color: #725b16; }
.financial-table-wrap {
  max-width: 100%;
  margin: .35rem 0;
  overflow-x: auto;
}
.financial-table {
  width: 100%;
  min-width: 100%;
  border-collapse: collapse;
  font-family: var(--sans);
  font-size: .94rem;
  line-height: 1.35;
  table-layout: auto;
}
.financial-table th,
.financial-table td {
  padding: .45rem .6rem;
  border: 1px solid var(--rule);
  background: var(--surface);
  text-align: left;
  vertical-align: top;
  white-space: normal;
  overflow-wrap: anywhere;
}
.financial-table th {
  background: #f0eadc;
  color: var(--muted);
  font-weight: 700;
}
.financial-table td.num {
  font-variant-numeric: tabular-nums;
  text-align: right;
  white-space: nowrap;
}
.financial-ledger {
  margin: .35rem 0;
  font-size: .88rem;
  line-height: 1.45;
}
.old-span, .new-span { border-radius: 2px; }
.op-delete, .op-replace.old-span {
  background: var(--del-mark);
  text-decoration-line: line-through;
  text-decoration-thickness: .07em;
}
.op-insert, .op-replace.new-span { background: var(--add-mark); }
.op-equal { background: transparent; }
.evidence-line {
  display: flex;
  flex-wrap: wrap;
  gap: .35rem .85rem;
  padding: .3rem 1.6rem .7rem;
  color: var(--faint);
  font-family: var(--code);
  font-size: .72rem;
}
.evidence-line a { color: var(--muted); }
.evidence-line span { overflow-wrap: anywhere; }
details.collapsed {
  padding: .7rem 1.6rem;
  border-bottom: 1px solid var(--rule-soft);
  background: #fbf7ee;
  color: var(--muted);
  font-family: var(--code);
  font-size: .8rem;
}
details.collapsed summary { cursor: pointer; }
.provenance-footer {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 2rem;
  padding: 2rem 1.6rem;
  border-top: 1px solid var(--rule);
  background: var(--surface);
  font-family: var(--code);
  font-size: .86rem;
}
.provenance-footer p {
  margin: .45rem 0 0;
  overflow-wrap: anywhere;
}
.timeline-main {
  max-width: 72rem;
  margin: 0 auto;
  padding: 1.5rem;
}
.timeline-list {
  display: grid;
  gap: 1rem;
  margin: 0;
  padding: 0;
  list-style: none;
}
.timeline-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 1rem;
  padding: 1rem;
  border: 1px solid var(--rule);
  border-radius: 8px;
  background: var(--surface);
}
.timeline-row h2 {
  margin: 0 0 .45rem;
  font-size: 1rem;
}
.timeline-meta {
  color: var(--muted);
  font-family: var(--code);
  font-size: .82rem;
  overflow-wrap: anywhere;
}
.timeline-stats {
  color: var(--muted);
  font-family: var(--code);
  font-size: .86rem;
  white-space: nowrap;
}
pre {
  margin: .5rem 0 0;
  padding: .85rem;
  border: 1px solid var(--rule);
  background: #fbf7ee;
  overflow: auto;
  white-space: pre-wrap;
}
@media (max-width: 900px) {
  .layout { grid-template-columns: 1fr; }
  .section-rail {
    position: static;
    max-height: none;
    border-right: 0;
    border-bottom: 1px solid var(--rule);
  }
  .paragraph-row { grid-template-columns: 3.4rem minmax(0, 1fr); }
  .prose { padding: .95rem 1rem .7rem; }
  .evidence-line { padding: .3rem 1rem .65rem; }
  .provenance-footer { grid-template-columns: 1fr; }
  .timeline-row { grid-template-columns: 1fr; }
  .timeline-stats { white-space: normal; }
}
@media print {
  body { background: #fff; }
  .topbar, .section-rail, .hunk-header { position: static; }
  a { color: inherit; text-decoration: underline; }
  .section-hunk, .paragraph-row { break-inside: avoid; }
}
@media (prefers-reduced-motion: reduce) {
  * { scroll-behavior: auto; }
}
"""

_BARE_PAGE_NUMBER_RE = re.compile(r"\d{1,4}")


def _is_artifact_text(text: str) -> bool:
    """True for page-break debris that should not render as a paragraph.

    Standalone thematic breaks, "Table of Contents" page markers, and bare page
    numbers survive in some packs (see docs/BACKLOG.md, diff precision findings).
    Filtering here is display-only; JSON output and counts are untouched.
    """
    stripped = text.strip()
    if not stripped:
        return True
    if all(part == "---" for part in stripped.split()):
        return True
    if stripped.lower() == "table of contents":
        return True
    return _BARE_PAGE_NUMBER_RE.fullmatch(stripped) is not None


def _paragraph_is_artifact(para: ReportParagraphDelta) -> bool:
    texts = [text for text in (para.old_text, para.new_text) if text is not None]
    if not texts:
        return True
    return all(_is_artifact_text(text) for text in texts)


def _span_html(span: TextSpan) -> str:
    side_class = "old-span" if span.side == "old" else "new-span"
    op_class = {
        "equal": "op-equal",
        "insert": "op-insert",
        "delete": "op-delete",
        "replace": "op-replace",
    }.get(span.op, "op-equal")
    return f'<span class="{op_class} {side_class}">{escape(span.text)}</span>'


def _merge_spans(
    old_spans: list[TextSpan],
    new_spans: list[TextSpan],
) -> list[tuple[str, str]]:
    """Interleave parallel opcode-ordered spans into one (kind, text) stream.

    Kinds: "equal", "del", "ins". Equal text is emitted once. The merge is total:
    any leftover spans flush as del/ins, so output always covers both inputs.
    """
    merged: list[tuple[str, str]] = []
    i = 0
    j = 0
    while i < len(old_spans) or j < len(new_spans):
        old = old_spans[i] if i < len(old_spans) else None
        new = new_spans[j] if j < len(new_spans) else None
        if old is not None and old.op == "delete":
            merged.append(("del", old.text))
            i += 1
            continue
        if new is not None and new.op == "insert":
            merged.append(("ins", new.text))
            j += 1
            continue
        if old is not None and new is not None and old.op == "equal" and new.op == "equal":
            merged.append(("equal", old.text))
            i += 1
            j += 1
            continue
        if old is not None and old.op == "replace":
            merged.append(("del", old.text))
            i += 1
            if new is not None and new.op == "replace":
                merged.append(("ins", new.text))
                j += 1
            continue
        if new is not None and new.op == "replace":
            merged.append(("ins", new.text))
            j += 1
            continue
        if old is not None:
            merged.append(("del", old.text))
            i += 1
        elif new is not None:
            merged.append(("ins", new.text))
            j += 1
    return merged


def _unified_html(para: ReportParagraphDelta) -> str:
    pieces: list[str] = []
    for kind, text in _merge_spans(para.old_spans, para.new_spans):
        if kind == "equal":
            pieces.append(escape(text))
        elif kind == "del":
            pieces.append(f"<del>{escape(text)}</del>")
        else:
            pieces.append(f"<ins>{escape(text)}</ins>")
    return f'<div class="prose unified">{"".join(pieces)}</div>'


def _is_numeric_cell(text: str) -> bool:
    cleaned = text.strip().replace(",", "")
    return bool(cleaned) and bool(re.fullmatch(r"[$€£¥]?\(?-?\d+(?:\.\d+)?%?\)?", cleaned))


def _is_escaped_pipe(line: str, index: int) -> bool:
    backslashes = 0
    position = index - 1
    while position >= 0 and line[position] == "\\":
        backslashes += 1
        position -= 1
    return backslashes % 2 == 1


def _strip_outer_table_delimiters(line: str) -> str:
    trimmed = line.strip()
    if trimmed.startswith("|"):
        trimmed = trimmed[1:]
    if trimmed.endswith("|") and not _is_escaped_pipe(trimmed, len(trimmed) - 1):
        trimmed = trimmed[:-1]
    return trimmed


def _split_table_row(line: str) -> list[str]:
    cells: list[str] = []
    cell = ""
    raw = _strip_outer_table_delimiters(line)
    for index, char in enumerate(raw):
        if char == "|" and not _is_escaped_pipe(raw, index):
            cells.append(cell.strip().replace(r"\|", "|"))
            cell = ""
            continue
        cell += char
    cells.append(cell.strip().replace(r"\|", "|"))
    return cells


def _is_gfm_separator_cell(text: str) -> bool:
    return re.fullmatch(r":?-{3,}:?", text.strip()) is not None


def _is_gfm_table(text: str) -> bool:
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if len(lines) < 3:
        return False
    if "|" not in lines[0] or "|" not in lines[1]:
        return False

    header = _split_table_row(lines[0])
    separators = _split_table_row(lines[1])
    body_rows = [_split_table_row(line) for line in lines[2:]]
    if not header or len(header) != len(separators):
        return False
    return all(_is_gfm_separator_cell(cell) for cell in separators) and all(
        len(row) == len(header) for row in body_rows
    )


def _table_block_html(text: str) -> str:
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    rows = [_split_table_row(line) for line in lines]
    header = rows[0]
    body_rows = rows[2:]
    out = [
        '<div class="financial-table-wrap"><table class="financial-table">',
        "<thead>",
        "<tr>",
    ]
    for cell in header:
        out.append(f"<th>{escape(cell)}</th>")
    out.extend(["</tr>", "</thead>", "<tbody>"])
    for row in body_rows:
        out.append("<tr>")
        for cell in row:
            cls = ' class="num"' if _is_numeric_cell(cell) else ""
            out.append(f"<td{cls}>{escape(cell)}</td>")
        out.append("</tr>")
    out.extend(["</tbody>", "</table></div>"])
    return "".join(out)


def _is_flattened_financial_ledger(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 3:
        return False
    slash_lines = sum(1 for line in lines if line.count("/") >= 2)
    dotted_lines = sum(1 for line in lines if "..." in line)
    money_or_paren_lines = sum(1 for line in lines if "$" in line or ("(" in line and ")" in line))
    return slash_lines >= 2 and (dotted_lines >= 1 or money_or_paren_lines >= 1)


def _clean_ledger_text(text: str) -> str:
    lines = []
    for line in text.strip().splitlines():
        stripped = line.strip()
        if stripped.startswith(">"):
            stripped = stripped[1:].lstrip()
        stripped = stripped.replace("**", "")
        if stripped:
            lines.append(stripped)
    return "\n".join(lines)


def _paragraph_content_html(text: str) -> str:
    if _is_gfm_table(text):
        return _table_block_html(text)
    if _is_flattened_financial_ledger(text):
        return f'<pre class="financial-ledger">{escape(_clean_ledger_text(text))}</pre>'
    return escape(text)


def _single_side_for_paragraph(para: ReportParagraphDelta) -> str | None:
    if para.change_type == ChangeType.ADDED:
        return "new"
    if para.change_type in {ChangeType.REMOVED, ChangeType.UNCHANGED}:
        return "old"
    return None


def _side_text_and_spans(para: ReportParagraphDelta, side: str) -> tuple[str, list[TextSpan]]:
    if side == "old":
        return para.old_text or "", para.old_spans
    return para.new_text or "", para.new_spans


def _table_sequence_end(paragraphs: list[ReportParagraphDelta], start: int) -> int:
    first = paragraphs[start]
    side = _single_side_for_paragraph(first)
    if side is None:
        return start

    first_text, first_spans = _side_text_and_spans(first, side)
    if first_spans or "|" not in first_text:
        return start

    lines: list[str] = []
    index = start
    while index < len(paragraphs):
        para = paragraphs[index]
        if para.change_type != first.change_type:
            break
        text, spans = _side_text_and_spans(para, side)
        if spans or "|" not in text:
            break
        lines.append(text.strip())
        index += 1

    if len(lines) < 3 or not _is_gfm_table("\n".join(lines)):
        return start
    return index


def _safe_http_href(url: str | None) -> str | None:
    if not url:
        return None
    candidate = url.strip()
    parsed = urlsplit(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return escape(candidate, quote=True)


def _safe_relative_href(path: str) -> str | None:
    candidate = path.strip().replace("\\", "/")
    if not candidate or "\x00" in candidate:
        return None
    parsed = urlsplit(candidate)
    if parsed.scheme or parsed.netloc or candidate.startswith(("/", "#")):
        return None

    normalized = posixpath.normpath(candidate)
    if normalized in {"", ".", ".."} or normalized.startswith("../") or "/../" in normalized:
        return None
    return escape(quote(normalized, safe="/._-~"), quote=True)


def _safe_pack_file_href(pack_dir: str, section_path: str) -> str | None:
    candidate = section_path.strip().replace("\\", "/")
    if not candidate or "\x00" in candidate:
        return None
    parsed = urlsplit(candidate)
    if parsed.scheme or parsed.netloc or candidate.startswith(("/", "#")):
        return None

    normalized = posixpath.normpath(candidate)
    if normalized in {"", ".", ".."} or normalized.startswith("../") or "/../" in normalized:
        return None

    try:
        pack_root = Path(pack_dir).expanduser().resolve(strict=False)
        target = (pack_root / normalized).resolve(strict=False)
        target.relative_to(pack_root)
    except (OSError, ValueError):
        return None
    return escape(target.as_uri(), quote=True)


def _prose_html(para: ReportParagraphDelta, side: str, css_class: str) -> str:
    if side == "old":
        spans = para.old_spans
        text = para.old_text
    else:
        spans = para.new_spans
        text = para.new_text
    raw_text = text or ""
    content = (
        _paragraph_content_html(raw_text)
        if _is_gfm_table(raw_text) or _is_flattened_financial_ledger(raw_text)
        else "".join(_span_html(span) for span in spans)
        if spans
        else escape(raw_text)
    )
    return f'<div class="prose {css_class}">{content}</div>'


def _anchor_bits(
    anchor: EvidenceAnchor | None,
    label: str,
    source_url: str | None,
    pack_dir: str,
) -> list[str]:
    if anchor is None:
        return [f"<span>{label} chunk missing</span>"]
    chunk_id = anchor.chunk_id or "missing"
    detail = escape(
        f"{label}: accession {anchor.accession} | section {anchor.section_id} | "
        f"paragraph {anchor.paragraph_index} | offset {anchor.char_start}-{anchor.char_end} | "
        f"chunk {chunk_id}",
        quote=True,
    )
    bits = [f'<span title="{detail}">{label} ¶{anchor.paragraph_index}</span>']
    source_href = _safe_http_href(source_url)
    if source_href is not None:
        bits.append(f'<a href="{source_href}" title="{detail}">{label} source</a>')
    else:
        bits.append(f"<span>{label} source missing</span>")
    pack_href = _safe_pack_file_href(pack_dir, anchor.section_path)
    if pack_href is not None:
        bits.append(f'<a href="{pack_href}" title="{detail}">{label} pack</a>')
    else:
        bits.append(f"<span>{label} pack path omitted</span>")
    return bits


def _evidence_html(
    para: ReportParagraphDelta,
    before_source_url: str | None,
    after_source_url: str | None,
    before_pack_dir: str,
    after_pack_dir: str,
) -> str:
    bits: list[str] = []
    if para.change_type in {ChangeType.REMOVED, ChangeType.MODIFIED, ChangeType.MOVED}:
        bits.extend(_anchor_bits(para.old_anchor, "old", before_source_url, before_pack_dir))
    if para.change_type in {ChangeType.ADDED, ChangeType.MODIFIED, ChangeType.MOVED}:
        bits.extend(_anchor_bits(para.new_anchor, "new", after_source_url, after_pack_dir))
    if not bits:
        bits.append("<span>chunk status missing</span>")
    return f'<div class="evidence-line">{"".join(bits)}</div>'


def _marker_for(change_type: ChangeType) -> tuple[str, str]:
    return {
        ChangeType.ADDED: ("+", "marker-added"),
        ChangeType.REMOVED: ("-", "marker-removed"),
        ChangeType.MODIFIED: ("~", "marker-modified"),
        ChangeType.MOVED: ("&#8645;", "marker-modified"),
        ChangeType.UNCHANGED: ("", "marker-context"),
    }[change_type]


def _paragraph_html(
    para: ReportParagraphDelta,
    before_source_url: str | None,
    after_source_url: str | None,
    before_pack_dir: str,
    after_pack_dir: str,
) -> str:
    marker, marker_class = _marker_for(para.change_type)
    anchor = para.new_anchor or para.old_anchor
    para_index = anchor.paragraph_index if anchor else 0
    blocks: list[str] = []
    if para.change_type == ChangeType.UNCHANGED:
        blocks.append(_prose_html(para, "old", "context"))
    elif para.change_type == ChangeType.REMOVED:
        blocks.append(_prose_html(para, "old", "old"))
    elif para.change_type == ChangeType.ADDED:
        blocks.append(_prose_html(para, "new", "new"))
    else:
        if para.change_type == ChangeType.MOVED:
            blocks.append('<span class="rewrite-badge moved-badge">moved</span>')
        raw_old = para.old_text or ""
        raw_new = para.new_text or ""
        structured = (
            _is_gfm_table(raw_old)
            or _is_gfm_table(raw_new)
            or _is_flattened_financial_ledger(raw_old)
            or _is_flattened_financial_ledger(raw_new)
        )
        if (
            not structured
            and para.old_spans
            and para.new_spans
            and para.similarity >= _UNIFIED_VIEW_MIN_SIMILARITY
        ):
            blocks.append(_unified_html(para))
        else:
            if not structured:
                blocks.append(
                    f'<span class="rewrite-badge">rewritten · {para.similarity:.0%} similar</span>'
                )
            blocks.append(_prose_html(para, "old", "old"))
            blocks.append(_prose_html(para, "new", "new"))
    if para.change_type != ChangeType.UNCHANGED:
        blocks.append(
            _evidence_html(
                para,
                before_source_url,
                after_source_url,
                before_pack_dir,
                after_pack_dir,
            )
        )
    marker_html = f'<span class="{marker_class}">{marker}</span> ' if marker else ""
    return (
        '<div class="paragraph-row">'
        f'<div class="gutter">{marker_html}¶{para_index}</div>'
        f'<div class="body">{"".join(blocks)}</div>'
        "</div>"
    )


def _table_sequence_html(
    paragraphs: list[ReportParagraphDelta],
    before_source_url: str | None,
    after_source_url: str | None,
    before_pack_dir: str,
    after_pack_dir: str,
) -> str:
    first = paragraphs[0]
    side = _single_side_for_paragraph(first)
    if side is None:
        return ""
    marker, marker_class = _marker_for(first.change_type)
    css_class = {
        ChangeType.ADDED: "new",
        ChangeType.REMOVED: "old",
        ChangeType.UNCHANGED: "context",
    }[first.change_type]
    anchor = first.new_anchor or first.old_anchor
    para_index = anchor.paragraph_index if anchor else 0
    table_text = "\n".join(_side_text_and_spans(para, side)[0].strip() for para in paragraphs)
    evidence = ""
    if first.change_type != ChangeType.UNCHANGED:
        evidence = _evidence_html(
            first,
            before_source_url,
            after_source_url,
            before_pack_dir,
            after_pack_dir,
        )
    marker_html = f'<span class="{marker_class}">{marker}</span> ' if marker else ""
    return (
        '<div class="paragraph-row">'
        f'<div class="gutter">{marker_html}¶{para_index}</div>'
        f'<div class="body"><div class="prose {css_class}">'
        f"{_table_block_html(table_text)}</div>{evidence}</div>"
        "</div>"
    )


def _group_html(
    group: ParagraphGroup,
    before_source_url: str | None,
    after_source_url: str | None,
    before_pack_dir: str,
    after_pack_dir: str,
) -> str:
    if group.kind == "collapsed":
        return (
            '<details class="collapsed">'
            f"<summary>{group.collapsed_count} unchanged paragraphs, "
            f"{group.collapsed_word_count} words collapsed</summary>"
            "</details>"
        )
    html: list[str] = []
    index = 0
    while index < len(group.paragraphs):
        if _paragraph_is_artifact(group.paragraphs[index]):
            index += 1
            continue
        table_end = _table_sequence_end(group.paragraphs, index)
        if table_end > index:
            html.append(
                _table_sequence_html(
                    group.paragraphs[index:table_end],
                    before_source_url,
                    after_source_url,
                    before_pack_dir,
                    after_pack_dir,
                )
            )
            index = table_end
            continue
        html.append(
            _paragraph_html(
                group.paragraphs[index],
                before_source_url,
                after_source_url,
                before_pack_dir,
                after_pack_dir,
            )
        )
        index += 1
    return "".join(html)


def _ranked_changed_sections(report: DiffReport) -> list[ReportSectionDelta]:
    changed = [
        section for section in report.sections if section.change_type != ChangeType.UNCHANGED
    ]
    return sorted(changed, key=lambda section: (-section.interest_score, section.section_id))


def _section_nav_html(report: DiffReport) -> str:
    sections = _ranked_changed_sections(report)
    max_score = max((section.interest_score for section in sections), default=0.0)
    rows = []
    for section in sections:
        section_id = escape(section.section_id, quote=True)
        title = escape(section.title)
        width = 0 if max_score <= 0 else round(100 * section.interest_score / max_score)
        moved_rail = (
            f'<span class="rail-modified">&#8645;{section.paragraphs_moved}</span>'
            if section.paragraphs_moved
            else ""
        )
        rows.append(
            f'<a class="rail-row" href="#section-{section_id}">'
            f'<span class="rail-name">{title}</span>'
            '<span class="rail-counts">'
            f'<span class="rail-added">+{section.paragraphs_added}</span>'
            f'<span class="rail-removed">-{section.paragraphs_removed}</span>'
            f'<span class="rail-modified">~{section.paragraphs_modified}</span>'
            f"{moved_rail}</span>"
            f'<span class="rail-bar"><i style="width:{width}%"></i></span>'
            "</a>"
        )
    if rows:
        return "\n".join(rows)
    return '<p class="crumbs">No changed sections.</p>'


def _section_html(report: DiffReport) -> str:
    sections = []
    for section in _ranked_changed_sections(report):
        section_id = escape(section.section_id, quote=True)
        groups = "".join(
            _group_html(
                group,
                report.before_source.source_url,
                report.after_source.source_url,
                report.before_source.pack_dir,
                report.after_source.pack_dir,
            )
            for group in section.groups
        )
        title = escape(section.title)
        moved_meta = f"&#8645;{section.paragraphs_moved} · " if section.paragraphs_moved else ""
        sections.append(
            f'<section class="section-hunk" id="section-{section_id}">'
            '<header class="hunk-header">'
            f'<h2 class="hunk-title">{title}</h2>'
            '<div class="hunk-meta">'
            f'<span class="rail-added">+{section.paragraphs_added}</span> '
            f'<span class="rail-removed">-{section.paragraphs_removed}</span> '
            f"~{section.paragraphs_modified} · "
            f"{moved_meta}"
            f"{section.change_intensity:.0%} intensity</div>"
            "</header>"
            f"{groups}"
            "</section>"
        )
    return "\n".join(sections)


def _source_link(url: str | None) -> str:
    safe_url = _safe_http_href(url)
    if safe_url is None:
        return '<p><span aria-label="missing source url">missing</span></p>'
    return f'<p><a href="{safe_url}">{escape(url or "")}</a></p>'


def _filing_label(form_type: str, filing_date: str, accession: str) -> str:
    bits = [bit for bit in (form_type, f"filed {filing_date}" if filing_date else "") if bit]
    label = " ".join(bits)
    return escape(label) if label else escape(accession)


def render_pair_report_html(report: DiffReport, reproduce_command: str = "") -> str:
    """Render a static, script-free HTML report for one filing pair."""
    before = report.before_source
    after = report.after_source
    before_accession = escape(before.accession)
    after_accession = escape(after.accession)
    company_name = escape(after.company_name or before.company_name) or before_accession
    sections_nav = _section_nav_html(report)
    section_html = _section_html(report)
    changed_sections = _ranked_changed_sections(report)
    total_added = sum(section.paragraphs_added for section in changed_sections)
    total_removed = sum(section.paragraphs_removed for section in changed_sections)
    total_modified = sum(section.paragraphs_modified for section in changed_sections)
    pair_line = (
        f"{_filing_label(before.form_type, before.filing_date, before.accession)}"
        '<span class="arrow">&rarr;</span>'
        f"{_filing_label(after.form_type, after.filing_date, after.accession)}"
    )
    stats_chips = (
        f"<span>{len(changed_sections)} sections changed</span>"
        f"<span>+{total_added} / -{total_removed} / ~{total_modified} paragraphs</span>"
        f"<span>{report.overall_change_intensity:.0%} overall intensity</span>"
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{company_name}: {before_accession} -&gt; {after_accession}</title>
  <style>{_CSS}</style>
</head>
<body>
  <header class="topbar">
    <div><span class="brand">edgarpack</span> diff --format html</div>
    <nav aria-label="Report"><a href="#provenance">provenance</a></nav>
  </header>
  <section class="pair-hero">
    <div class="crumbs">{before_accession} &rarr; {after_accession}</div>
    <h1>{company_name}</h1>
    <p class="pair-line">{pair_line}</p>
    <div class="stats">{stats_chips}</div>
  </section>
  <main class="layout">
    <aside class="section-rail" aria-label="Changed sections">
      <p class="rail-title">{len(changed_sections)} changed sections, most changed first</p>
      {sections_nav}
    </aside>
    <div class="diff-pane">{section_html}</div>
  </main>
  <footer class="provenance-footer" id="provenance">
    <div>
      <div class="footer-label">SEC EDGAR</div>
      {_source_link(before.source_url)}
      {_source_link(after.source_url)}
    </div>
    <div>
      <div class="footer-label">Local pack files - chunk status {escape(report.chunk_status)}</div>
      <p>{escape(before.pack_dir)}</p>
      <p>{escape(after.pack_dir)}</p>
    </div>
    <div>
      <div class="footer-label">Reproduce</div>
      <pre>{escape(reproduce_command)}</pre>
    </div>
  </footer>
</body>
</html>
"""


def render_timeline_index_html(report: TimelineReport) -> str:
    """Render a static HTML index for a registration filing timeline."""
    cik = escape(report.cik)
    transition_rows: list[str] = []
    for transition in report.transitions:
        href = _safe_relative_href(transition.output_file)
        before_accession = escape(transition.before.accession)
        after_accession = escape(transition.after.accession)
        before_meta = (
            f"{escape(transition.before.form_type)} filed {escape(transition.before.filing_date)}"
        )
        after_meta = (
            f"{escape(transition.after.form_type)} filed {escape(transition.after.filing_date)}"
        )
        title = f"{before_accession} -&gt; {after_accession}"
        title_html = f'<a href="{href}">{title}</a>' if href is not None else title
        transition_rows.append(
            '<li class="timeline-row">'
            "<div>"
            f"<h2>{title_html}</h2>"
            f'<div class="timeline-meta">{before_meta} -&gt; {after_meta}</div>'
            f'<div class="timeline-meta">{escape(transition.before.pack_dir)} -&gt; '
            f"{escape(transition.after.pack_dir)}</div>"
            "</div>"
            '<div class="timeline-stats">'
            f"+{transition.sections_added} "
            f"-{transition.sections_removed} "
            f"~{transition.sections_modified} "
            f"={transition.sections_unchanged}<br>"
            f"{transition.overall_change_intensity:.1%} intensity"
            "</div>"
            "</li>"
        )
    rows_html = "\n".join(transition_rows) or '<li class="crumbs">No filing pairs.</li>'
    filing_count = len(report.entries)
    pair_count = len(report.transitions)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Registration timeline {cik}</title>
  <style>{_CSS}</style>
</head>
<body>
  <header class="topbar">
    <div><span class="brand">edgarpack</span> timeline --series registration --format html</div>
  </header>
  <section class="pair-hero">
    <div class="crumbs">registration timeline</div>
    <h1>Registration timeline for CIK {cik}</h1>
    <div class="stats"><span>{filing_count} filings</span>
      <span>{pair_count} filing pairs</span></div>
  </section>
  <main class="timeline-main">
    <ol class="timeline-list">
      {rows_html}
    </ol>
  </main>
</body>
</html>
"""
