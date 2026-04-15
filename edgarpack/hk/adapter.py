from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..china.extract.pdf_extract import extract_pdf_pages
from . import load_section_map
from .acquire import HKFilingRef, download_pdf

_COMPANY_META: dict[str, dict[str, str]] = {
    "00700": {
        "name": "Tencent Holdings",
        "reporting_currency": "CNY",
        "accounting_standard": "HKFRS",
    },
    "03690": {
        "name": "Meituan",
        "reporting_currency": "CNY",
        "accounting_standard": "HKFRS",
    },
    "09988": {
        "name": "Alibaba Group (HK)",
        "reporting_currency": "CNY",
        "accounting_standard": "IFRS",
    },
    "09618": {
        "name": "JD.com (HK)",
        "reporting_currency": "CNY",
        "accounting_standard": "IFRS",
    },
    "00100": {
        "name": "MiniMax Group Inc.",
        "reporting_currency": "USD",
        "accounting_standard": "HKFRS",
    },
    "02513": {
        "name": "Zhipu (Knowledge Atlas Technology)",
        "reporting_currency": "CNY",
        "accounting_standard": "HKFRS",
    },
}


@dataclass(frozen=True)
class PackRef:
    path: Path
    stock_code: str
    fiscal_year: int


def _download_pdf(ref: HKFilingRef, out: Path) -> Path:
    download_pdf(ref, out)
    return out


def build_hk_pack(ref: HKFilingRef, out_dir: Path) -> PackRef:
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = out_dir / f"{ref.stock_code}_{ref.fiscal_year}.pdf"
    _download_pdf(ref, pdf_path)

    pages = extract_pdf_pages(str(pdf_path))
    section_map = load_section_map()

    sections: list[dict] = []
    unmapped_counter = 0
    current: dict | None = None

    for page in pages:
        page_lines = page.text.split("\n")
        buf: list[str] = []
        for line in page_lines:
            normalized = line.strip().upper().rstrip(".")
            mapped = section_map.get(normalized) if normalized else None
            if mapped:
                if current and buf:
                    current["text"] += "\n" + "\n".join(buf)
                    current["page_end"] = page.page
                if current:
                    sections.append(current)
                current = {
                    "section_id": mapped,
                    "text": line,
                    "page_start": page.page,
                    "page_end": page.page,
                }
                buf = []
            else:
                buf.append(line)

        if buf:
            if current is None:
                unmapped_counter += 1
                current = {
                    "section_id": f"hkex_unmapped_{unmapped_counter:03d}",
                    "text": "\n".join(buf),
                    "page_start": page.page,
                    "page_end": page.page,
                }
            else:
                current["text"] += "\n" + "\n".join(buf)
                current["page_end"] = page.page

    if current:
        sections.append(current)

    merged: list[dict] = []
    for s in sections:
        if merged and merged[-1]["section_id"] == s["section_id"]:
            merged[-1]["text"] += "\n" + s["text"]
            merged[-1]["page_end"] = s["page_end"]
        else:
            merged.append(s)
    sections = merged

    name_counts: dict[str, int] = {}
    for s in sections:
        sid = s["section_id"]
        name_counts[sid] = name_counts.get(sid, 0) + 1
        if name_counts[sid] > 1:
            s["section_id"] = f"{sid}_{name_counts[sid]:02d}"

    sections_dir = out_dir / "sections"
    sections_dir.mkdir(exist_ok=True)
    for s in sections:
        (sections_dir / f"{s['section_id']}.md").write_text(s["text"] + "\n")

    with (out_dir / "chunks.ndjson").open("w") as f:
        for s in sections:
            f.write(json.dumps(s) + "\n")

    meta = _COMPANY_META.get(ref.stock_code, {})
    manifest = {
        "source": "HKEX",
        "stock_code": ref.stock_code,
        "fiscal_year": ref.fiscal_year,
        "company": meta.get("name", ref.stock_code),
        "reporting_currency": meta.get("reporting_currency", "CNY"),
        "accounting_standard": meta.get("accounting_standard", "HKFRS"),
        "pdf_url": ref.pdf_url,
        "announcement_date": ref.announcement_date,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))

    return PackRef(path=out_dir, stock_code=ref.stock_code, fiscal_year=ref.fiscal_year)
