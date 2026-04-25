"""Static HTML rendering for filing diff reports."""

from __future__ import annotations

import posixpath
from html import escape
from urllib.parse import quote, urlsplit

from .models import ChangeType
from .report_models import (
    DiffReport,
    EvidenceAnchor,
    ParagraphGroup,
    ReportParagraphDelta,
    TextSpan,
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


def _prose_html(para: ReportParagraphDelta, side: str, css_class: str) -> str:
    if side == "old":
        spans = para.old_spans
        text = para.old_text
    else:
        spans = para.new_spans
        text = para.new_text
    content = "".join(_span_html(span) for span in spans) if spans else escape(text or "")
    return f'<div class="prose {css_class}">{content}</div>'


def _anchor_bits(anchor: EvidenceAnchor | None, label: str, source_url: str | None) -> list[str]:
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
    pack_href = _safe_relative_href(anchor.section_path)
    if pack_href is not None:
        bits.append(f'<a href="{pack_href}">{label} pack</a>')
    else:
        bits.append(f"<span>{label} pack path omitted</span>")
    return bits


def _evidence_html(
    para: ReportParagraphDelta,
    before_source_url: str | None,
    after_source_url: str | None,
) -> str:
    bits: list[str] = []
    if para.change_type in {ChangeType.REMOVED, ChangeType.MODIFIED, ChangeType.UNCHANGED}:
        bits.extend(_anchor_bits(para.old_anchor, "old", before_source_url))
    if para.change_type in {ChangeType.ADDED, ChangeType.MODIFIED}:
        bits.extend(_anchor_bits(para.new_anchor, "new", after_source_url))
    if not bits:
        bits.append("<span>chunk status missing</span>")
    return f'<div class="evidence-line">{"".join(bits)}</div>'


def _paragraph_html(
    para: ReportParagraphDelta,
    before_source_url: str | None,
    after_source_url: str | None,
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
    blocks.append(_evidence_html(para, before_source_url, after_source_url))
    return (
        '<div class="paragraph-row">'
        f'<div class="gutter">p{para_index}</div>'
        f'<div class="marker {marker_class}">{marker}</div>'
        f'<div class="body">{"".join(blocks)}</div>'
        "</div>"
    )


def _group_html(
    group: ParagraphGroup,
    before_source_url: str | None,
    after_source_url: str | None,
) -> str:
    if group.kind == "collapsed":
        return (
            '<details class="collapsed">'
            f"<summary>{group.collapsed_count} unchanged paragraphs, "
            f"{group.collapsed_word_count} words collapsed</summary>"
            "</details>"
        )
    return "".join(
        _paragraph_html(para, before_source_url, after_source_url)
        for para in group.paragraphs
    )


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
    hero_meta = (
        f"pair report - {company_name} - "
        f"chunk status {escape(report.chunk_status)}"
    )
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
