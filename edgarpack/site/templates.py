"""HTML templates for the static site generator."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from html import escape

from .styles import CSS


def html_doc(title: str, header_left: str, header_right: str, body: str) -> str:
    """Render a complete HTML document with shared styles and header."""
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{escape(title)}</title>\n"
        f"<style>{CSS}</style>\n"
        "</head>\n"
        "<body>\n"
        "<header>\n"
        f"<div>{header_left}</div>\n"
        f"<nav>{header_right}</nav>\n"
        "</header>\n"
        f"{body}\n"
        "</body>\n"
        "</html>\n"
    )


def link(href: str, text: str) -> str:
    """Render an escaped anchor tag."""
    return f'<a href="{escape(href, quote=True)}">{escape(text)}</a>'


def monospace(text: str) -> str:
    """Render escaped text in the monospace style span."""
    return f'<span class="mono">{escape(text)}</span>'


def h1(text: str) -> str:
    """Render an H1 heading."""
    return f"<h1>{escape(text)}</h1>"


def h2(text: str) -> str:
    """Render an H2 heading."""
    return f"<h2>{escape(text)}</h2>"


def para(text: str) -> str:
    """Render a paragraph with escaped content."""
    return f"<p>{escape(text)}</p>"


def rule() -> str:
    """Render the standard horizontal divider block."""
    return '<div class="rule"></div>'


@dataclass(frozen=True)
class CompanyRow:
    """Row model for the root companies index."""

    name: str
    cik: str
    filings_summary: str
    href: str


def companies_index(rows: Iterable[CompanyRow]) -> str:
    """Render the companies index list with a client-side filter."""
    row_list = list(rows)
    count = len(row_list)
    lines = [
        h2("COMPANIES"),
        f'<input id="filter" type="text" placeholder="Filter by name, ticker, or CIK ({count} companies)" autofocus>',
        '<ul id="company-list" class="list">',
    ]
    for r in row_list:
        lines.append(
            "<li>"
            f"{link(r.href, f'{r.name} ({r.cik})')}"
            f'<div class="muted">{escape(r.filings_summary)}</div>'
            "</li>"
        )
    lines.append("</ul>")
    lines.append(_FILTER_JS)
    return "\n".join(lines)


_FILTER_JS = """<script>
(function() {
  var input = document.getElementById('filter');
  var items = document.querySelectorAll('#company-list li');
  input.addEventListener('input', function() {
    var q = this.value.toLowerCase();
    for (var i = 0; i < items.length; i++) {
      var text = items[i].textContent.toLowerCase();
      items[i].style.display = text.indexOf(q) !== -1 ? '' : 'none';
    }
  });
})();
</script>"""


@dataclass(frozen=True)
class FilingRow:
    """Row model for a single company filing entry."""

    form_type: str
    filing_date: str
    accession: str
    href: str


def company_index(company_name: str, cik: str, rows: Iterable[FilingRow]) -> str:
    """Render the filing list page for one company."""
    lines = [
        h2("FILINGS"),
        f'<div class="muted">{escape(company_name)} ({escape(cik)})</div>',
        '<ul class="list">',
    ]
    for r in rows:
        lines.append(
            "<li>"
            f"{link(r.href, f'{r.form_type} {r.filing_date}')}"
            f' <span class="muted">· {escape(r.accession)}</span>'
            "</li>"
        )
    lines.append("</ul>")
    return "\n".join(lines)


def filing_overview(
    heading: str,
    meta_lines: list[str],
    sections_html: str,
    artifacts_html: str,
    source_url: str | None,
) -> str:
    """Render the filing overview page body from manifest data."""
    lines = [h1(heading)]
    for m in meta_lines:
        lines.append(f'<div class="muted">{escape(m)}</div>')
    lines.append(rule())
    lines.append(sections_html)
    lines.append(rule())
    lines.append(artifacts_html)
    if source_url:
        lines.append(rule())
        lines.append(h2("SOURCE"))
        lines.append(f'<div class="muted">{escape(source_url)}</div>')
    return "\n".join(lines)


def artifacts_list(items: Iterable[tuple[str, str]]) -> str:
    """Render a list of downloadable artifact links."""
    lines = [h2("ARTIFACTS"), '<ul class="list">']
    for text, href in items:
        lines.append(f"<li>{link(href, text)}</li>")
    lines.append("</ul>")
    return "\n".join(lines)


def sections_list(items: Iterable[tuple[str, str, str | None]]) -> str:
    """Render section links with optional token counts."""
    lines = [h2("SECTIONS"), '<ul class="list">']
    for label, href, tokens in items:
        tok = f' <span class="muted">{escape(tokens)}</span>' if tokens else ""
        lines.append(f"<li>{link(href, label)}{tok}</li>")
    lines.append("</ul>")
    return "\n".join(lines)


def content_page(title: str, stats: list[str], html: str) -> str:
    """Render a content page block with title, stats, and body HTML."""
    lines = [h1(title)]
    for s in stats:
        lines.append(f'<div class="muted">{escape(s)}</div>')
    lines.append(rule())
    lines.append(html)
    return "\n".join(lines)
