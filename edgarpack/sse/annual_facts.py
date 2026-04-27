"""Deterministic fact extraction for SSE listed-company annual reports."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AnnualMetricSpec:
    label_contains: str
    concept: str
    label: str
    unit: str
    divide_by: float = 1.0


_METRICS: tuple[AnnualMetricSpec, ...] = (
    AnnualMetricSpec("营业收入", "Revenue", "Revenue", "CNY"),
    AnnualMetricSpec(
        "归属于上市公司股东的净利润",
        "ProfitLoss",
        "Net income attributable to shareholders",
        "CNY",
    ),
    AnnualMetricSpec(
        "经营活动产生的现金流量净额",
        "NetCashProvidedByUsedInOperatingActivities",
        "Net cash from operating activities",
        "CNY",
    ),
    AnnualMetricSpec(
        "研发投入占营业收入的比例",
        "ResearchAndDevelopmentIntensity",
        "R&D intensity",
        "pure",
        divide_by=100.0,
    ),
)


def _clean_cell(cell: str) -> str:
    text = re.sub(r"<br\s*/?>", "", cell, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&nbsp;", " ")
    return re.sub(r"\s+", "", text).strip()


def _split_row(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return []
    if re.fullmatch(r"\|?[\s:\-|]+\|?", stripped):
        return []
    return [_clean_cell(cell) for cell in stripped.strip("|").split("|")]


def _parse_year(cell: str) -> int | None:
    match = re.search(r"(20\d{2})年", cell)
    if not match:
        return None
    return int(match.group(1))


def _parse_number(cell: str) -> float | None:
    text = cell.replace(",", "").replace("，", "").replace("%", "").strip()
    text = text.replace("−", "-")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    return float(match.group(0))


def _year_columns(cells: list[str]) -> dict[int, int]:
    years: dict[int, int] = {}
    for idx, cell in enumerate(cells):
        year = _parse_year(cell)
        if year is not None:
            years[idx] = year
    return years


def write_annual_facts(
    pack_dir: Path,
    sections: list[Any],
    *,
    stock_code: str,
    company_name: str,
    filing_date: date,
    source_url: str,
) -> Path | None:
    """Write deterministic CAS facts from annual-report key financial tables.

    Returns the written ``facts.json`` path, or ``None`` when no target rows
    were found. Callers should treat ``None`` as a non-fatal build warning.
    """
    facts: dict[str, dict[str, Any]] = {"cas": {}}
    accession = f"{stock_code}_{filing_date.isoformat()}"

    for section in sections:
        current_years: dict[int, int] = {}
        for line in str(section.content).splitlines():
            cells = _split_row(line)
            if not cells:
                continue
            years = _year_columns(cells)
            if years:
                current_years = years
                continue
            if not current_years:
                continue

            row_label = cells[0]
            for spec in _METRICS:
                if spec.label_contains not in row_label:
                    continue
                for idx, fiscal_year in current_years.items():
                    if idx >= len(cells):
                        continue
                    raw = _parse_number(cells[idx])
                    if raw is None:
                        continue
                    value = raw / spec.divide_by
                    point = {
                        "start": f"{fiscal_year}-01-01",
                        "end": f"{fiscal_year}-12-31",
                        "val": value,
                        "fy": fiscal_year,
                        "fp": "FY",
                        "form": "ANNUAL-REPORT",
                        "accn": accession,
                        "filed": filing_date.isoformat(),
                        "frame": f"CY{fiscal_year}",
                        "source_url": source_url,
                        "source_document": "optional/source.pdf",
                        "section_id": section.id,
                        "matched_label": row_label,
                        "extraction_method": "regex:annual_table",
                    }
                    concept_info = facts["cas"].setdefault(
                        spec.concept,
                        {"label": spec.label, "units": {spec.unit: []}},
                    )
                    concept_info.setdefault("units", {}).setdefault(spec.unit, []).append(point)

    if not any(info.get("units") for info in facts["cas"].values()):
        return None

    payload = {
        "source": "SSE",
        "exchange": "SSE",
        "stock_code": stock_code,
        "company": company_name,
        "source_url": source_url,
        "source_document": "optional/source.pdf",
        "facts": facts,
    }
    facts_path = pack_dir / "facts.json"
    facts_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return facts_path
