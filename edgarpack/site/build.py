"""Static site generator for filing packs."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .templates import (
    CompanyRow,
    FilingRow,
    artifacts_list,
    companies_index,
    company_index,
    content_page,
    filing_overview,
    html_doc,
    link,
    sections_list,
)


@dataclass(frozen=True)
class PackInfo:
    cik: str
    accession: str
    company_name: str
    form_type: str
    filing_date: str
    tokens_total: int
    source_url: str | None
    sections: list[dict[str, Any]]
    artifacts: dict[str, str]
    pack_dir: Path


def build_site(packs_dir: Path, out_dir: Path, base_url: str | None = None) -> dict[str, Any]:
    """Build a static HTML site from a directory of EdgarPack packs."""
    packs_dir = packs_dir.resolve()
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    packs = _scan_packs(packs_dir)
    by_cik: dict[str, list[PackInfo]] = {}
    for p in packs:
        by_cik.setdefault(p.cik, []).append(p)

    # Copy packs and generate per-filing pages.
    for cik, items in by_cik.items():
        for pack in items:
            target_dir = out_dir / cik / pack.accession
            _copy_pack_dir(pack.pack_dir, target_dir)
            _write_filing_pages(pack, target_dir)

        # Company page (listing)
        company_name = items[0].company_name if items else f"CIK {cik}"
        filings = sorted(items, key=lambda p: p.filing_date, reverse=True)
        rows = [
            FilingRow(
                form_type=p.form_type,
                filing_date=p.filing_date,
                accession=p.accession,
                href=f"{p.accession}/index.html",
            )
            for p in filings
        ]
        body = company_index(company_name=company_name, cik=cik, rows=rows)
        html = html_doc(
            title=f"{company_name} ({cik})",
            header_left=link("../index.html", "← Companies"),
            header_right="",
            body=body,
        )
        (out_dir / cik).mkdir(parents=True, exist_ok=True)
        (out_dir / cik / "index.html").write_text(html, encoding="utf-8")

    # Root index
    company_rows: list[CompanyRow] = []
    for cik, items in sorted(by_cik.items(), key=lambda kv: kv[0]):
        if not items:
            continue
        company_name = items[0].company_name
        # Summary: show up to 3 most recent filings
        filings = sorted(items, key=lambda p: p.filing_date, reverse=True)[:3]
        summary = " · ".join(f"{p.form_type} {p.filing_date}" for p in filings)
        company_rows.append(
            CompanyRow(
                name=company_name,
                cik=cik,
                filings_summary=summary,
                href=f"{cik}/index.html",
            )
        )

    body = companies_index(company_rows)
    html = html_doc(
        title="EdgarPack",
        header_left=link("index.html", "EDGARPACK"),
        header_right="",
        body=body,
    )
    (out_dir / "index.html").write_text(html, encoding="utf-8")

    total_bytes = _dir_size_bytes(out_dir)
    return {
        "companies": len(by_cik),
        "filings": len(packs),
        "out_dir": str(out_dir),
        "total_bytes": total_bytes,
    }


def _scan_packs(packs_dir: Path) -> list[PackInfo]:
    packs: list[PackInfo] = []
    if not packs_dir.exists():
        return packs

    for cik_dir in packs_dir.iterdir():
        if not cik_dir.is_dir():
            continue
        for acc_dir in cik_dir.iterdir():
            if not acc_dir.is_dir():
                continue
            manifest_path = acc_dir / "manifest.json"
            if not manifest_path.exists():
                continue
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                continue

            filing = manifest.get("filing", {}) or {}
            source = manifest.get("source", {}) or {}

            cik = str(filing.get("cik") or cik_dir.name)
            accession = str(filing.get("accession") or acc_dir.name)

            packs.append(
                PackInfo(
                    cik=cik,
                    accession=accession,
                    company_name=str(filing.get("company_name") or f"CIK {cik}"),
                    form_type=str(filing.get("form_type") or "Unknown"),
                    filing_date=str(filing.get("filing_date") or ""),
                    tokens_total=int(manifest.get("tokens_total") or 0),
                    source_url=source.get("url"),
                    sections=list(manifest.get("sections") or []),
                    artifacts=dict(manifest.get("artifacts") or {}),
                    pack_dir=acc_dir,
                )
            )

    return packs


def _copy_pack_dir(src: Path, dst: Path) -> None:
    def _ignore(path: str, names: list[str]) -> set[str]:
        ignored = {".DS_Store", "__pycache__", ".pytest_cache"}
        return {n for n in names if n in ignored}

    # Copy raw pack artifacts so downloads work offline.
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=_ignore)


def _write_filing_pages(pack: PackInfo, out_pack_dir: Path) -> None:
    cik = pack.cik
    accession = pack.accession

    # Overview (from manifest)
    meta_lines = [
        f"{pack.form_type} · Filed {pack.filing_date}",
        f"CIK: {cik} · Accession: {accession}",
        f"Tokens: {pack.tokens_total:,}",
    ]

    # Sections list (with token counts)
    section_items: list[tuple[str, str, str | None]] = []
    # Full filing link
    section_items.append(("■ Full Filing", "full.html", f"{pack.tokens_total:,}"))

    for s in pack.sections:
        sid = str(s.get("id") or "")
        title = str(s.get("title") or sid)
        tokens = s.get("tokens_approx")
        tokens_str = f"{int(tokens):,}" if isinstance(tokens, int) else None
        href = f"sections/{_section_page_name(sid)}.html"
        section_items.append((title, href, tokens_str))

    sections_html = sections_list(section_items)

    # Artifacts list (raw)
    artifacts = []
    for rel in sorted(pack.artifacts.keys()):
        artifacts.append((rel, rel))
    # Always include these if present, even if older manifests didn't hash them.
    for rel in ["manifest.json", "llms.txt", "filing.full.md"]:
        if (out_pack_dir / rel).exists() and rel not in pack.artifacts:
            artifacts.append((rel, rel))

    artifacts_html = artifacts_list(artifacts)

    overview = filing_overview(
        heading=f"{pack.form_type} · {pack.filing_date}",
        meta_lines=meta_lines,
        sections_html=sections_html,
        artifacts_html=artifacts_html,
        source_url=pack.source_url,
    )

    overview_html = html_doc(
        title=f"{pack.company_name} {pack.form_type} ({pack.filing_date})",
        header_left=link("../index.html", f"← {pack.company_name}"),
        header_right="",
        body=overview,
    )
    out_pack_dir.mkdir(parents=True, exist_ok=True)
    (out_pack_dir / "index.html").write_text(overview_html, encoding="utf-8")

    # Full filing page
    full_md_path = out_pack_dir / "filing.full.md"
    full_md = full_md_path.read_text(encoding="utf-8") if full_md_path.exists() else ""
    full_html_body = content_page(
        title=f"{pack.form_type} · Full Filing",
        stats=[f"Tokens: {pack.tokens_total:,}", f"Chars: {len(full_md):,}"],
        html=_markdown_to_html(full_md),
    )
    full_html = html_doc(
        title=f"{pack.company_name} {pack.form_type} Full",
        header_left=link("index.html", f"← {pack.company_name}"),
        header_right=f"{link('filing.full.md', 'Raw MD')}",
        body=full_html_body,
    )
    (out_pack_dir / "full.html").write_text(full_html, encoding="utf-8")

    # Section pages
    sections_dir = out_pack_dir / "sections"
    sections_dir.mkdir(parents=True, exist_ok=True)
    for s in pack.sections:
        sid = str(s.get("id") or "")
        title = str(s.get("title") or sid)
        md_path = out_pack_dir / str(s.get("path") or f"sections/{sid}.md")
        md = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
        tokens = s.get("tokens_approx")
        tokens_str = f"{int(tokens):,}" if isinstance(tokens, int) else "?"

        body = content_page(
            title=title,
            stats=[f"{tokens_str} tokens · {len(md):,} chars"],
            html=_markdown_to_html(md),
        )
        page = html_doc(
            title=f"{pack.company_name} {pack.form_type} {title}",
            header_left=link("../index.html", "← Overview"),
            header_right=f"{link('../full.html', 'Full')} {link(_section_md_href(sid), 'Raw MD')}",
            body=body,
        )
        (sections_dir / f"{_section_page_name(sid)}.html").write_text(page, encoding="utf-8")


def _section_page_name(section_id: str) -> str:
    sid = section_id.strip()
    if sid.startswith(("10k_", "10q_")):
        # Drop the form/part prefix to keep URLs shorter.
        i = sid.find("_item")
        if i != -1:
            return sid[i + 1 :]
    if sid.startswith("8k_item_"):
        return sid.replace("8k_", "", 1)
    return sid


def _section_md_href(section_id: str) -> str:
    # Raw markdown stays in sections/{id}.md
    return f"../sections/{section_id}.md"


def _markdown_to_html(md: str) -> str:
    """Minimal Markdown → HTML converter (CommonMark-ish subset).

    The goal is readable, deterministic output, not perfect rendering.
    """
    md = md.replace("\r\n", "\n").replace("\r", "\n")
    lines = md.split("\n")

    out: list[str] = []

    def flush_paragraph(buf: list[str]) -> None:
        if not buf:
            return
        text = " ".join(s.strip() for s in buf if s.strip())
        if text:
            out.append(f"<p>{_inline(text)}</p>")
        buf.clear()

    i = 0
    in_code = False
    code_buf: list[str] = []
    para_buf: list[str] = []

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Code fences
        if stripped.startswith("```"):
            flush_paragraph(para_buf)
            if not in_code:
                in_code = True
                code_buf = []
            else:
                code_text = "\n".join(code_buf)
                out.append(f"<pre><code>{_escape_block(code_text)}</code></pre>")
                in_code = False
            i += 1
            continue

        if in_code:
            code_buf.append(line)
            i += 1
            continue

        # Horizontal rule
        if stripped == "---":
            flush_paragraph(para_buf)
            out.append("<hr>")
            i += 1
            continue

        # Table (GFM)
        if _looks_like_table_start(lines, i):
            flush_paragraph(para_buf)
            table_lines: list[str] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i])
                i += 1
            out.append(_table_to_html(table_lines))
            continue

        # Headings
        if stripped.startswith("#"):
            flush_paragraph(para_buf)
            level = len(stripped) - len(stripped.lstrip("#"))
            level = min(max(level, 1), 6)
            text = stripped[level:].strip()
            out.append(f"<h{level}>{_inline(text)}</h{level}>")
            i += 1
            continue

        # Unordered list
        if stripped.startswith(("- ", "* ")):
            flush_paragraph(para_buf)
            out.append("<ul>")
            while i < len(lines):
                s = lines[i].strip()
                if not s.startswith(("- ", "* ")):
                    break
                item_text = s[2:].strip()
                out.append(f"<li>{_inline(item_text)}</li>")
                i += 1
            out.append("</ul>")
            continue

        # Ordered list
        if _looks_like_ordered_list_item(stripped):
            flush_paragraph(para_buf)
            out.append("<ol>")
            while i < len(lines):
                s = lines[i].strip()
                if not _looks_like_ordered_list_item(s):
                    break
                # Split at first ". "
                dot = s.find(".")
                item_text = s[dot + 1 :].lstrip()
                out.append(f"<li>{_inline(item_text)}</li>")
                i += 1
            out.append("</ol>")
            continue

        # Blockquote
        if stripped.startswith(">"):
            flush_paragraph(para_buf)
            out.append("<blockquote>")
            while i < len(lines):
                s = lines[i].rstrip()
                if not s.lstrip().startswith(">"):
                    break
                q = s.lstrip()[1:].lstrip()
                if q:
                    out.append(f"<p>{_inline(q)}</p>")
                i += 1
            out.append("</blockquote>")
            continue

        # Blank line ends paragraph
        if not stripped:
            flush_paragraph(para_buf)
            i += 1
            continue

        # Default: paragraph text
        para_buf.append(line)
        i += 1

    flush_paragraph(para_buf)
    if in_code:
        code_text = "\n".join(code_buf)
        out.append(f"<pre><code>{_escape_block(code_text)}</code></pre>")

    return "\n".join(out)


def _escape_block(text: str) -> str:
    # Block escaping (pre/code) – keep newlines.
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _inline(text: str) -> str:
    # Placeholder-based inline renderer (escape-by-default).
    replacements: list[str] = []

    def stash(html: str) -> str:
        token = f"@@{len(replacements)}@@"
        replacements.append(html)
        return token

    text = _re_sub(r"`([^`]+)`", text, lambda m: stash(f"<code>{_escape_block(m.group(1))}</code>"))

    # Links
    def _link_repl(match) -> str:
        href = _safe_href(match.group(2))
        label = match.group(1)
        if not href:
            return label
        return stash(f'<a href="{_escape_attr(href)}">{_escape_block(label)}</a>')

    text = _re_sub(r"\[([^\]]+)\]\(([^)]+)\)", text, _link_repl)
    # Bold
    text = _re_sub(
        r"\*\*([^*]+)\*\*",
        text,
        lambda m: stash(f"<strong>{_escape_block(m.group(1))}</strong>"),
    )

    escaped = _escape_block(text)
    for idx, html in enumerate(replacements):
        escaped = escaped.replace(f"@@{idx}@@", html)
    return escaped


def _escape_attr(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def _safe_href(href: str) -> str | None:
    if href is None:
        return None
    cleaned = href.strip()
    if not cleaned:
        return None
    lowered = cleaned.lower()
    if lowered.startswith(("javascript:", "data:", "vbscript:")):
        return None
    return cleaned


def _re_sub(pattern: str, text: str, fn) -> str:
    import re

    return re.sub(pattern, fn, text, flags=re.DOTALL)


def _looks_like_ordered_list_item(line: str) -> bool:
    import re

    return bool(re.match(r"^\d+\.\s+", line))


def _looks_like_table_start(lines: list[str], i: int) -> bool:
    if i + 1 >= len(lines):
        return False
    header = lines[i].strip()
    sep = lines[i + 1].strip()
    if not header.startswith("|") or not sep.startswith("|"):
        return False
    # Separator row contains --- columns
    return "---" in sep


def _table_to_html(table_lines: list[str]) -> str:
    # Basic GFM table parsing.
    rows = []
    for line in table_lines:
        if not line.strip().startswith("|"):
            continue
        parts = [p.strip() for p in line.strip().strip("|").split("|")]
        rows.append(parts)

    if len(rows) < 2:
        return "<pre>" + _escape_block("\n".join(table_lines)) + "</pre>"

    header = rows[0]
    body_rows = [r for r in rows[2:]] if len(rows) >= 3 else []

    out = ["<table>", "<thead>", "<tr>"]
    for h in header:
        out.append(f"<th>{_inline(h)}</th>")
    out.extend(["</tr>", "</thead>", "<tbody>"])
    for r in body_rows:
        out.append("<tr>")
        for c in r:
            out.append(f"<td>{_inline(c)}</td>")
        out.append("</tr>")
    out.extend(["</tbody>", "</table>"])
    return "\n".join(out)


def _dir_size_bytes(path: Path) -> int:
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            total += p.stat().st_size
    return total
