"""HTML templates for the static site generator."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from html import escape

from .styles import CSS


def html_doc(title: str, header_left: str, header_right: str, body: str) -> str:
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
    return f'<a href="{escape(href, quote=True)}">{escape(text)}</a>'


def monospace(text: str) -> str:
    return f'<span class="mono">{escape(text)}</span>'


def h1(text: str) -> str:
    return f"<h1>{escape(text)}</h1>"


def h2(text: str) -> str:
    return f"<h2>{escape(text)}</h2>"


def para(text: str) -> str:
    return f"<p>{escape(text)}</p>"


def rule() -> str:
    return '<div class="rule"></div>'


@dataclass(frozen=True)
class CompanyRow:
    name: str
    cik: str
    filings_summary: str
    href: str


def companies_index(rows: Iterable[CompanyRow]) -> str:
    lines = [h2("COMPANIES"), "<ul>"]
    for r in rows:
        lines.append(
            "<li>"
            f"{link(r.href, f'{r.name} ({r.cik})')}"
            f'<div class="muted">{escape(r.filings_summary)}</div>'
            "</li>"
        )
    lines.append("</ul>")
    return "\n".join(lines)


@dataclass(frozen=True)
class FilingRow:
    form_type: str
    filing_date: str
    accession: str
    href: str


def company_index(company_name: str, cik: str, rows: Iterable[FilingRow]) -> str:
    lines = [
        h2("FILINGS"),
        f'<div class="muted">{escape(company_name)} ({escape(cik)})</div>',
        "<ul>",
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
    lines = [h2("ARTIFACTS"), "<ul>"]
    for text, href in items:
        lines.append(f"<li>{link(href, text)}</li>")
    lines.append("</ul>")
    return "\n".join(lines)


def sections_list(items: Iterable[tuple[str, str, str | None]]) -> str:
    """Items: (label, href, tokens)."""
    lines = [h2("SECTIONS"), "<ul>"]
    for label, href, tokens in items:
        tok = f' <span class="muted">{escape(tokens)}</span>' if tokens else ""
        lines.append(f"<li>{link(href, label)}{tok}</li>")
    lines.append("</ul>")
    return "\n".join(lines)


def content_page(title: str, stats: list[str], html: str) -> str:
    lines = [h1(title)]
    for s in stats:
        lines.append(f'<div class="muted">{escape(s)}</div>')
    lines.append(rule())
    lines.append(html)
    return "\n".join(lines)
