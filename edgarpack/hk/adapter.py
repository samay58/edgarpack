from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from ..china.extract.pdf_extract import extract_pdf_pages
from . import load_section_map
from .acquire import HKFilingRef, download_pdf, extract_filing_metadata
from .toc import HKSectioningError, Section, slice_sections

__all__ = ["PackRef", "HKSectioningError", "build_hk_pack"]


@dataclass(frozen=True)
class PackRef:
    path: Path
    stock_code: str
    fiscal_year: int


def _download_pdf(ref: HKFilingRef, out: Path, *, client: httpx.Client | None = None) -> Path:
    download_pdf(ref, out, client=client)
    return out


def _dedupe_section_id(section_id: str, counts: dict[str, int]) -> str:
    counts[section_id] = counts.get(section_id, 0) + 1
    if counts[section_id] == 1:
        return section_id
    return f"{section_id}_{counts[section_id]:02d}"


def _write_sections(out_dir: Path, sections: list[Section]) -> list[dict[str, Any]]:
    sections_dir = out_dir / "sections"
    sections_dir.mkdir(exist_ok=True)
    counts: dict[str, int] = {}
    records: list[dict[str, Any]] = []
    for section in sections:
        assert section.section_id is not None
        section_id = _dedupe_section_id(section.section_id, counts)
        (sections_dir / f"{section_id}.md").write_text(section.text + "\n")
        records.append(
            {
                "section_id": section_id,
                "text": section.text,
                "page_start": section.start_index + 1,
                "page_end": section.end_index,
            }
        )
    return records


def build_hk_pack(
    ref: HKFilingRef,
    out_dir: Path,
    *,
    company_name: str,
    dual_counter_codes: Sequence[str] | None = None,
    client: httpx.Client | None = None,
) -> PackRef:
    """Acquire, section and write an HKEX pack for one annual report.

    The currency, accounting standard and (best-effort) legal name come from the
    filing itself via `extract_filing_metadata`; `company_name` is the search
    row's short name used when the filing does not disclose a legal name.
    Raises HKSectioningError when the statements cannot be located: the pack is
    not written rather than emitting an unusable one.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = out_dir / f"{ref.stock_code}_{ref.fiscal_year}.pdf"
    _download_pdf(ref, pdf_path, client=client)

    page_texts = [page.text for page in extract_pdf_pages(str(pdf_path))]
    section_map = load_section_map()

    sections = slice_sections(page_texts, section_map)
    records = _write_sections(out_dir, sections)

    with (out_dir / "chunks.ndjson").open("w") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")

    meta = extract_filing_metadata(pdf_path)
    manifest: dict[str, Any] = {
        "source": "HKEX",
        "stock_code": ref.stock_code,
        "fiscal_year": ref.fiscal_year,
        "company": meta.legal_name or company_name,
        "reporting_currency": meta.currency,
        "accounting_standard": meta.accounting_standard,
        "pdf_url": ref.pdf_url,
        "announcement_date": ref.announcement_date,
    }
    if meta.standard_note is not None:
        manifest["accounting_standard_citation"] = meta.standard_note
    codes = [code for code in (dual_counter_codes or ()) if code]
    if len(codes) > 1:
        manifest["dual_counter_codes"] = codes
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))

    return PackRef(path=out_dir, stock_code=ref.stock_code, fiscal_year=ref.fiscal_year)
