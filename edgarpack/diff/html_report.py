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
    TextSpan,
    TimelineReport,
)

_CSS = """
:root {
  --paper: #f5f0e4;
  --surface: #fffdf8;
  --ink: #1f1d18;
  --muted: #6d675c;
  --rule: #d9cfb9;
  --add-bg: #edf7ee;
  --add-ink: #285d3d;
  --del-bg: #f8e9e7;
  --del-ink: #843c36;
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
  padding: 2.4rem 1.6rem 2rem;
  border-bottom: 1px solid var(--rule);
  background: var(--surface);
}
.crumbs, .stats, .evidence-line, .footer-label {
  color: var(--muted);
  font-family: var(--code);
  font-size: .82rem;
}
h1 {
  margin: .7rem 0 1rem;
  font-size: clamp(2rem, 4vw, 3.25rem);
  font-weight: 750;
  letter-spacing: 0;
}
.layout {
  display: grid;
  grid-template-columns: 21rem minmax(0, 1fr);
  align-items: start;
}
.section-rail {
  position: sticky;
  top: 0;
  min-height: 100vh;
  padding: 1.5rem 1.25rem;
  border-right: 1px solid var(--rule);
  background: #fbf7ee;
}
.rail-title {
  margin: 0 0 1rem;
  color: var(--muted);
  font-weight: 700;
}
.rail-row {
  display: grid;
  grid-template-columns: minmax(4.8rem, auto) 1fr auto auto;
  gap: .65rem;
  padding: .58rem 0;
  border-bottom: 1px solid #e7dec9;
  font-size: .9rem;
}
.rail-id {
  color: var(--muted);
  font-family: var(--code);
  overflow-wrap: anywhere;
}
.rail-added { color: var(--add-ink); font-family: var(--code); }
.rail-removed { color: var(--del-ink); font-family: var(--code); }
.diff-pane { min-width: 0; }
.section-hunk {
  border-bottom: 1px solid var(--rule);
  scroll-margin-top: 1rem;
}
.hunk-header {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  padding: 1rem 1.6rem;
  border-bottom: 1px solid var(--rule);
  background: #f0eadc;
}
.hunk-title { margin: 0; font-size: 1rem; }
.hunk-meta {
  color: var(--muted);
  font-family: var(--code);
  font-size: .8rem;
  white-space: nowrap;
}
.paragraph-row {
  display: grid;
  grid-template-columns: 4.4rem 3rem minmax(0, 1fr);
  border-bottom: 1px solid #e8dfca;
  background: var(--surface);
}
.gutter {
  padding: 1rem .7rem;
  border-right: 1px solid #e2d8c0;
  color: var(--muted);
  font-family: var(--code);
  text-align: right;
}
.marker {
  padding: 1rem .7rem;
  border-right: 1px solid #e2d8c0;
  font-family: var(--code);
  text-align: center;
}
.marker-added { color: var(--add-ink); }
.marker-removed { color: var(--del-ink); }
.marker-modified { color: #725b16; }
.body { min-width: 0; }
.prose {
  padding: 1rem 1.6rem;
  font-family: var(--serif);
  font-size: 1.12rem;
  line-height: 1.65;
  overflow-wrap: anywhere;
}
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
.old { background: var(--del-bg); color: var(--del-ink); }
.new { background: var(--add-bg); color: var(--ink); }
.context { background: var(--surface); color: var(--ink); }
.op-delete, .op-replace.old-span {
  background: #efd0cc;
  text-decoration-line: line-through;
  text-decoration-thickness: .08em;
}
.op-insert, .op-replace.new-span { background: #d8eddc; }
.op-equal { background: transparent; }
.evidence-line {
  display: flex;
  flex-wrap: wrap;
  gap: .45rem 1rem;
  padding: .65rem 1.6rem;
  border-top: 1px solid #e8dfca;
  background: #fbf7ee;
}
.evidence-line span { overflow-wrap: anywhere; }
details.collapsed {
  padding: .85rem 1.6rem;
  border-bottom: 1px solid #e8dfca;
  background: #fbf7ee;
  color: var(--muted);
  font-family: var(--code);
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
    min-height: auto;
    border-right: 0;
    border-bottom: 1px solid var(--rule);
  }
  .paragraph-row { grid-template-columns: 3.5rem 2.6rem minmax(0, 1fr); }
  .prose { padding: .95rem 1rem; }
  .provenance-footer { grid-template-columns: 1fr; }
  .timeline-row { grid-template-columns: 1fr; }
  .timeline-stats { white-space: normal; }
}
@media print {
  body { background: #fff; }
  .topbar, .section-rail { position: static; }
  a { color: inherit; text-decoration: underline; }
  .section-hunk, .paragraph-row { break-inside: avoid; }
}
@media (prefers-reduced-motion: reduce) {
  * { scroll-behavior: auto; }
}
"""


def _span_html(span: TextSpan) -> str:
    side_class = "old-span" if span.side == "old" else "new-span"
    op_class = {
        "equal": "op-equal",
        "insert": "op-insert",
        "delete": "op-delete",
        "replace": "op-replace",
    }.get(span.op, "op-equal")
    return f'<span class="{op_class} {side_class}">{escape(span.text)}</span>'


def _is_numeric_cell(text: str) -> bool:
    cleaned = text.strip().replace(",", "")
    return bool(cleaned) and bool(
        re.fullmatch(r"[$€£¥]?\(?-?\d+(?:\.\d+)?%?\)?", cleaned)
    )


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
    money_or_paren_lines = sum(
        1 for line in lines if "$" in line or ("(" in line and ")" in line)
    )
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
    bits = [
        f"<span>{label} accession {escape(anchor.accession)}</span>",
        f"<span>{label} section {escape(anchor.section_id)}</span>",
        f"<span>{label} paragraph {anchor.paragraph_index}</span>",
        f"<span>{label} offset {anchor.char_start}-{anchor.char_end}</span>",
        f"<span>{label} chunk {escape(chunk_id)}</span>",
    ]
    source_href = _safe_http_href(source_url)
    if source_href is not None:
        bits.append(f'<a href="{source_href}">{label} source</a>')
    else:
        bits.append(f"<span>{label} source missing</span>")
    pack_href = _safe_pack_file_href(pack_dir, anchor.section_path)
    if pack_href is not None:
        bits.append(f'<a href="{pack_href}">{label} pack</a>')
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
    if para.change_type in {ChangeType.REMOVED, ChangeType.MODIFIED, ChangeType.UNCHANGED}:
        bits.extend(_anchor_bits(para.old_anchor, "old", before_source_url, before_pack_dir))
    if para.change_type in {ChangeType.ADDED, ChangeType.MODIFIED}:
        bits.extend(_anchor_bits(para.new_anchor, "new", after_source_url, after_pack_dir))
    if not bits:
        bits.append("<span>chunk status missing</span>")
    return f'<div class="evidence-line">{"".join(bits)}</div>'


def _paragraph_html(
    para: ReportParagraphDelta,
    before_source_url: str | None,
    after_source_url: str | None,
    before_pack_dir: str,
    after_pack_dir: str,
) -> str:
    marker, marker_class = {
        ChangeType.ADDED: ("+", "marker-added"),
        ChangeType.REMOVED: ("-", "marker-removed"),
        ChangeType.MODIFIED: ("~", "marker-modified"),
        ChangeType.UNCHANGED: (".", "marker-context"),
    }[para.change_type]
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
        blocks.append(_prose_html(para, "old", "old"))
        blocks.append(_prose_html(para, "new", "new"))
    blocks.append(
        _evidence_html(
            para,
            before_source_url,
            after_source_url,
            before_pack_dir,
            after_pack_dir,
        )
    )
    return (
        '<div class="paragraph-row">'
        f'<div class="gutter">p{para_index}</div>'
        f'<div class="marker {marker_class}">{marker}</div>'
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
    marker, marker_class, css_class = {
        ChangeType.ADDED: ("+", "marker-added", "new"),
        ChangeType.REMOVED: ("-", "marker-removed", "old"),
        ChangeType.UNCHANGED: (".", "marker-context", "context"),
    }[first.change_type]
    anchor = first.new_anchor or first.old_anchor
    para_index = anchor.paragraph_index if anchor else 0
    table_text = "\n".join(_side_text_and_spans(para, side)[0].strip() for para in paragraphs)
    evidence = "".join(
        _evidence_html(
            para,
            before_source_url,
            after_source_url,
            before_pack_dir,
            after_pack_dir,
        )
        for para in paragraphs
    )
    return (
        '<div class="paragraph-row">'
        f'<div class="gutter">p{para_index}</div>'
        f'<div class="marker {marker_class}">{marker}</div>'
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


def _section_nav_html(report: DiffReport) -> str:
    rows = []
    for section in report.sections:
        if section.change_type == ChangeType.UNCHANGED:
            continue
        section_id = escape(section.section_id, quote=True)
        section_id_text = escape(section.section_id)
        title = escape(section.title)
        rows.append(
            f'<a class="rail-row" href="#section-{section_id}">'
            f'<span class="rail-id">{section_id_text}</span>'
            f"<span>{title}</span>"
            f'<span class="rail-added">+{section.paragraphs_added}</span>'
            f'<span class="rail-removed">-{section.paragraphs_removed}</span>'
            "</a>"
        )
    if rows:
        return "\n".join(rows)
    return '<p class="crumbs">No changed sections.</p>'


def _section_html(report: DiffReport) -> str:
    sections = []
    for section in report.sections:
        if section.change_type == ChangeType.UNCHANGED:
            continue
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
        sections.append(
            f'<section class="section-hunk" id="section-{section_id}">'
            '<header class="hunk-header">'
            f'<h2 class="hunk-title">{title}</h2>'
            f'<div class="hunk-meta">+{section.paragraphs_added} '
            f"-{section.paragraphs_removed} ~{section.paragraphs_modified}</div>"
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


def render_pair_report_html(report: DiffReport, reproduce_command: str = "") -> str:
    """Render a static, script-free HTML report for one filing pair."""
    changed_count = report.sections_added + report.sections_removed + report.sections_modified
    before_accession = escape(report.before_source.accession)
    after_accession = escape(report.after_source.accession)
    company_name = escape(report.after_source.company_name or report.before_source.company_name)
    sections_nav = _section_nav_html(report)
    section_html = _section_html(report)
    hero_meta = f"pair report - {company_name} - chunk status {escape(report.chunk_status)}"
    hero_stats = (
        f"+{report.sections_added} sections - "
        f"-{report.sections_removed} sections - "
        f"~{report.sections_modified} modified - "
        f"{report.overall_change_intensity:.1%} intensity"
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{before_accession} -&gt; {after_accession}</title>
  <style>{_CSS}</style>
</head>
<body>
  <header class="topbar">
    <div><span class="brand">edgarpack</span> diff --format html</div>
    <nav aria-label="Report"><a href="#provenance">provenance</a></nav>
  </header>
  <section class="pair-hero">
    <div class="crumbs">{hero_meta}</div>
    <h1>{before_accession} -&gt; {after_accession}</h1>
    <div class="stats">{hero_stats}</div>
  </section>
  <main class="layout">
    <aside class="section-rail" aria-label="Changed sections">
      <p class="rail-title">{changed_count} changed sections</p>
      {sections_nav}
    </aside>
    <div class="diff-pane">{section_html}</div>
  </main>
  <footer class="provenance-footer" id="provenance">
    <div>
      <div class="footer-label">SEC EDGAR</div>
      {_source_link(report.before_source.source_url)}
      {_source_link(report.after_source.source_url)}
    </div>
    <div>
      <div class="footer-label">Local pack files</div>
      <p>{escape(report.before_source.pack_dir)}</p>
      <p>{escape(report.after_source.pack_dir)}</p>
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
    <div class="stats">{filing_count} filings - {pair_count} filing pairs</div>
  </section>
  <main class="timeline-main">
    <ol class="timeline-list">
      {rows_html}
    </ol>
  </main>
</body>
</html>
"""
