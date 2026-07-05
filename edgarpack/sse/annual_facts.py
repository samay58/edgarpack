"""Deterministic fact extraction for SSE listed-company annual reports."""

from __future__ import annotations

import json
import re
import warnings
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
    is_ratio: bool = False


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
        is_ratio=True,
    ),
)

# Only the numbered 第二节 (company profile / key financials) section carries the
# trustworthy 主要会计数据 and 主要财务指标 tables. Everything else (MD&A, ESG,
# the parent-company financial statements in 第十节) is out of scope: label
# substring matches there are coincidental, not the disclosed metric.
_KEY_TABLE_SECTION_PREFIX = "annual_s02"

_YEAR_PATTERN = re.compile(r"(20\d{2})年")
_PCT_COLUMN_PATTERN = re.compile(r"增减|变动")
_RATIO_LABEL_PATTERN = re.compile(r"占.{0,20}比例")
_BREAKDOWN_PREFIXES = ("其中：", "其中:")

_UNIT_SCALE_PATTERN = re.compile(r"单位[:：]\s*(?:人民币)?(百万元|万元|千元|元)")
_UNIT_SCALE_FACTORS: dict[str, float] = {
    "元": 1.0,
    "千元": 1e3,
    "万元": 1e4,
    "百万元": 1e6,
}
_UNIT_SCALE_LOOKBACK_LINES = 15

_YOY_TOLERANCE_PP = 1.5


def _clean_cell(cell: str) -> str:
    text = re.sub(r"<br\s*/?>", "", cell, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&nbsp;", " ")
    text = text.replace("`", "")
    return re.sub(r"\s+", "", text).strip()


def _is_table_line(stripped: str) -> bool:
    return len(stripped) >= 2 and stripped.startswith("|") and stripped.endswith("|")


def _is_separator_row(stripped: str) -> bool:
    return bool(re.fullmatch(r"\|?[\s:\-|]+\|?", stripped))


def _split_row(line: str) -> list[str]:
    stripped = line.strip()
    if not _is_table_line(stripped):
        return []
    if _is_separator_row(stripped):
        return []
    # Slice off exactly one leading/trailing pipe rather than str.strip("|"),
    # which eats every consecutive pipe and silently drops an empty corner
    # cell in SZSE-style headers like "||2025年|2024年|...", misaligning
    # every column index that follows.
    return [_clean_cell(cell) for cell in stripped[1:-1].split("|")]


def _parse_year(cell: str) -> int | None:
    match = _YEAR_PATTERN.search(cell)
    if not match:
        return None
    return int(match.group(1))


def _parse_number(cell: str) -> float | None:
    text = cell.replace(",", "").replace("，", "").replace("%", "").replace("`", "").strip()
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


def _percent_column_index(cells: list[str]) -> int | None:
    for idx, cell in enumerate(cells):
        if _PCT_COLUMN_PATTERN.search(cell):
            return idx
    return None


def _is_ratio_row(label: str) -> bool:
    return bool(_RATIO_LABEL_PATTERN.search(label))


def _table_priority(header_cells: list[str]) -> int:
    """0 (key) for the 主要会计数据 table, 1 (other) for anything else.

    On a conflict between candidates for the same (concept, fiscal_year), the
    key table wins; equal-priority conflicts are dropped instead of guessing.
    """
    if header_cells and "主要会计数据" in header_cells[0]:
        return 0
    return 1


def _find_unit_scale(lines: list[str], header_index: int) -> float | None:
    start = max(0, header_index - _UNIT_SCALE_LOOKBACK_LINES)
    for line in reversed(lines[start:header_index]):
        match = _UNIT_SCALE_PATTERN.search(_clean_cell(line))
        if match:
            return _UNIT_SCALE_FACTORS[match.group(1)]
    return None


@dataclass(frozen=True)
class _Candidate:
    concept: str
    label: str
    unit: str
    fiscal_year: int
    priority: int
    point: dict[str, Any]


def _resolve_candidates(candidates: list[_Candidate]) -> dict[str, dict[str, Any]]:
    """Collapse candidates to at most one point per (concept, unit, fiscal_year).

    Document order never decides a conflict: the key-table candidate wins
    over lower-priority candidates, and a genuine tie between equal-priority
    candidates is dropped entirely (fail closed) rather than picking whichever
    was found first.
    """
    groups: dict[tuple[str, str, int], list[_Candidate]] = {}
    for candidate in candidates:
        key = (candidate.concept, candidate.unit, candidate.fiscal_year)
        groups.setdefault(key, []).append(candidate)

    cas: dict[str, dict[str, Any]] = {}
    for (concept, unit, fiscal_year), group in groups.items():
        best_priority = min(candidate.priority for candidate in group)
        best = [candidate for candidate in group if candidate.priority == best_priority]
        if len(best) > 1:
            warnings.warn(
                f"Conflicting candidates for {concept} FY{fiscal_year}: "
                f"dropping {len(best)} equal-priority values",
                stacklevel=2,
            )
            continue
        winner = best[0]
        concept_info = cas.setdefault(concept, {"label": winner.label, "units": {}})
        concept_info["units"].setdefault(unit, []).append(winner.point)

    return cas


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
    accession = f"{stock_code}_{filing_date.isoformat()}"
    candidates: list[_Candidate] = []

    for section in sections:
        if not str(section.id).startswith(_KEY_TABLE_SECTION_PREFIX):
            continue

        lines = str(section.content).splitlines()
        current_years: dict[int, int] = {}
        current_priority = 1
        current_pct_idx: int | None = None
        current_unit_scale: float | None = None
        unit_missing_warned = False

        i = 0
        while i < len(lines):
            stripped = lines[i].strip()

            if not _is_table_line(stripped):
                # Leaving a table entirely (prose, heading, blank line) always
                # ends the current year/table context.
                current_years = {}
                current_priority = 1
                current_pct_idx = None
                current_unit_scale = None
                unit_missing_warned = False
                i += 1
                continue

            if _is_separator_row(stripped):
                i += 1
                continue

            cells = _split_row(lines[i])
            if not cells:
                i += 1
                continue

            next_stripped = lines[i + 1].strip() if i + 1 < len(lines) else ""
            years = _year_columns(cells)
            starts_new_table = _is_separator_row(next_stripped) or bool(years)

            if starts_new_table:
                # A new table start (a proper header row, or any row carrying
                # recognized years) resets the year map. A quarterly header
                # with no years resets to empty so its data rows extract
                # nothing, instead of inheriting the previous table's years.
                current_years = years
                current_priority = _table_priority(cells)
                current_pct_idx = _percent_column_index(cells)
                current_unit_scale = _find_unit_scale(lines, i)
                unit_missing_warned = False
                i += 1
                continue

            if not current_years:
                i += 1
                continue

            row_label = cells[0]
            if any(row_label.startswith(prefix) for prefix in _BREAKDOWN_PREFIXES):
                i += 1
                continue
            row_is_ratio = _is_ratio_row(row_label)

            row_raw: dict[int, float] = {}
            for idx in current_years:
                if idx >= len(cells):
                    continue
                raw = _parse_number(cells[idx])
                if raw is not None:
                    row_raw[idx] = raw

            skip_years: set[int] = set()
            if current_pct_idx is not None and not row_is_ratio and current_pct_idx < len(cells):
                stated_pct = _parse_number(cells[current_pct_idx])
                if stated_pct is not None:
                    idx_before = [
                        idx for idx in current_years if idx < current_pct_idx and idx in row_raw
                    ]
                    for idx_a in idx_before:
                        year_a = current_years[idx_a]
                        for idx_b in idx_before:
                            if idx_a == idx_b:
                                continue
                            year_b = current_years[idx_b]
                            if year_b != year_a - 1:
                                continue
                            val_prior = row_raw[idx_b]
                            if val_prior == 0:
                                continue
                            computed_pct = (row_raw[idx_a] - val_prior) / val_prior * 100
                            if abs(computed_pct - stated_pct) > _YOY_TOLERANCE_PP:
                                warnings.warn(
                                    f"YoY cross-check failed for {row_label} "
                                    f"{year_a}/{year_b}: computed {computed_pct:.2f}% "
                                    f"vs stated {stated_pct}%, dropping both years",
                                    stacklevel=2,
                                )
                                skip_years.add(year_a)
                                skip_years.add(year_b)

            for spec in _METRICS:
                if spec.label_contains not in row_label:
                    continue
                if row_is_ratio and not spec.is_ratio:
                    continue
                if spec.unit == "CNY" and current_unit_scale is None:
                    if not unit_missing_warned:
                        warnings.warn(
                            f"No recognized 单位 marker found near table for "
                            f"{row_label!r}; skipping CNY facts from this table",
                            stacklevel=2,
                        )
                        unit_missing_warned = True
                    continue
                scale = 1.0
                if spec.unit == "CNY" and current_unit_scale is not None:
                    scale = current_unit_scale
                for idx, fiscal_year in current_years.items():
                    if fiscal_year in skip_years or idx not in row_raw:
                        continue
                    value = (row_raw[idx] * scale) / spec.divide_by
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
                    candidates.append(
                        _Candidate(
                            concept=spec.concept,
                            label=spec.label,
                            unit=spec.unit,
                            fiscal_year=fiscal_year,
                            priority=current_priority,
                            point=point,
                        )
                    )

            i += 1

    cas = _resolve_candidates(candidates)
    if not any(info.get("units") for info in cas.values()):
        return None

    payload = {
        "source": "SSE",
        "exchange": "SSE",
        "stock_code": stock_code,
        "company": company_name,
        "source_url": source_url,
        "source_document": "optional/source.pdf",
        "facts": {"cas": cas},
    }
    facts_path = pack_dir / "facts.json"
    facts_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return facts_path
