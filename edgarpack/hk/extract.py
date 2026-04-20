from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ..query.metric_map import AccountingStandard

ExtractionMethod = Literal["regex", "learned:llm"]

_FINANCIAL_SECTIONS = {
    "hkex_income_statement",
    "hkex_balance_sheet",
    "hkex_cash_flow",
    "hkex_comprehensive_income",
    "hkex_equity_changes",
}

_PROSE_LABELS: dict[str, list[str]] = {
    "revenue": [
        "total revenue",
        "revenue",
        "turnover",
        "net revenues",
        "net revenue",
    ],
    "gross_profit": [
        "gross profit",
        "gross (loss)/profit",
        "gross loss/profit",
        "gross profit/(loss)",
    ],
    "operating_income": [
        "profit/(loss) from operations",
        "loss from operations",
        "profit from operations",
        "operating profit",
        "operating loss",
    ],
    "net_income": [
        "loss for the year/period",
        "profit for the year/period",
        "loss for the year",
        "profit for the year",
        "profit/(loss) for the year",
        "net loss",
        "net income",
        "net profit",
    ],
    "total_assets": [
        "total assets",
    ],
    "total_liabilities": [
        "total liabilities",
    ],
    "total_equity": [
        "total equity",
        "total deficits",
        "total equity - deficit",
        "total equity/(deficit)",
    ],
    "cash_and_equivalents": [
        "cash and cash equivalents",
        "cash at bank and on hand",
        "cash and bank balances",
        "bank balances and cash",
    ],
    "rd_expense": [
        "research and development expenses",
        "research and development expense",
        "research and development costs",
        "research and development",
    ],
    "operating_cash_flow": [
        "net cash (used in)/generated from operating activities",
        "net cash flows used in operating activities",
        "net cash flows generated from operating activities",
        "net cash used in operating activities",
        "net cash generated from operating activities",
        "cash (used in)/generated from operations",
        "cash used in operations",
        "cash generated from operations",
    ],
}

_SECTION_METRICS: dict[str, list[str]] = {
    "hkex_income_statement": [
        "revenue",
        "gross_profit",
        "operating_income",
        "net_income",
        "rd_expense",
    ],
    "hkex_comprehensive_income": ["net_income"],
    "hkex_balance_sheet": [
        "total_assets",
        "total_liabilities",
        "total_equity",
        "cash_and_equivalents",
    ],
    "hkex_cash_flow": ["operating_cash_flow"],
    "hkex_equity_changes": [],
}


def _scope_for_section(section_id: str) -> set[str] | None:
    metrics = _SECTION_METRICS.get(section_id)
    if metrics is None:
        return None
    return set(metrics)


_CONCEPT_NAME: dict[str, str] = {
    "revenue": "Revenue",
    "gross_profit": "GrossProfit",
    "operating_income": "OperatingIncomeLoss",
    "net_income": "ProfitLoss",
    "total_assets": "TotalAssets",
    "total_liabilities": "TotalLiabilities",
    "total_equity": "TotalEquity",
    "cash_and_equivalents": "CashAndCashEquivalents",
    "rd_expense": "ResearchAndDevelopmentExpense",
    "operating_cash_flow": "NetCashProvidedByUsedInOperatingActivities",
}


# Sentinel used by the regex/LLM extractors for any fact that is not
# naturally in its own unit (e.g. "headcount"). `extract_facts_from_pack`
# overwrites this with the filing's `reporting_currency` during assembly,
# so no caller should see `_UNIT_PENDING` in final facts.json output.
_UNIT_PENDING = "__pending__"


@dataclass(frozen=True)
class HKFact:
    metric: str
    concept: str
    value: int | float
    unit: str
    section_id: str
    extraction_method: ExtractionMethod
    matched_label: str
    fiscal_year: int = 0


def _strip_filler(line: str) -> str:
    return re.sub(r"/H\d+", " ", line)


def _merge_wrapped_labels(lines: list[str]) -> list[str]:
    """Join a label line to the next line when a known label wraps.

    Applies only when:
      * line N, after filler strip, is a strict prefix of at least one known
        label in _PROSE_LABELS (the stripped content is shorter than the label
        and the label starts with the stripped content),
      * line N contains no digits outside filler tokens,
      * line N+1 begins with a lowercase word or a filler token.
    """
    all_labels: list[str] = []
    for labels in _PROSE_LABELS.values():
        all_labels.extend(label.lower() for label in labels)

    def _is_label_prefix(text: str) -> bool:
        t = text.lower()
        for label in all_labels:
            if label.startswith(t) and len(t) < len(label):
                return True
        return False

    merged: list[str] = []
    skip_next = False
    for i, line in enumerate(lines):
        if skip_next:
            skip_next = False
            continue
        stripped = _strip_filler(line).strip()
        if not stripped:
            merged.append(line)
            continue
        has_digits = bool(re.search(r"\d", stripped))
        if not has_digits and _is_label_prefix(stripped) and i + 1 < len(lines):
            next_line = lines[i + 1]
            next_stripped = _strip_filler(next_line).strip()
            if next_stripped and next_stripped[0].islower():
                merged.append(f"{line.rstrip()} {next_line.lstrip()}")
                skip_next = True
                continue
        merged.append(line)
    return merged


def _detect_multiplier(text: str) -> int:
    """Return the scale factor declared in the section header (1000 or 1000000)."""
    header = text[:800]
    if re.search(r"in millions\b", header, re.IGNORECASE):
        return 1_000_000
    if re.search(r"in thousands\b", header, re.IGNORECASE):
        return 1_000
    if re.search(r"['\u2019\u2018]000\b", header):
        return 1_000
    return 1


def _is_interleaved(text: str) -> bool:
    """True when the section uses interleaved (amount, %) column pairs."""
    return bool(re.search(r"(?:US\$|HK\$|RMB)\s+%", text[:800]))


def _find_fy_col(text: str, target_year: int) -> int:
    years = [int(m) for m in re.findall(r"\b(20\d\d)\b", text[:500])]
    if target_year in years:
        return years.index(target_year)
    return -1


def _count_years(text: str) -> int:
    years = [int(m) for m in re.findall(r"\b(20\d\d)\b", text[:500])]
    return len(years)


def _parse_columns_plain(line: str) -> list[int | float | None]:
    """Extract column values from a plain (amount-only) table row."""
    cleaned = _strip_filler(line)
    cols: list[int | float | None] = []
    pat = re.compile(
        r"(\([\d,]+\.[\d]+\))"
        r"|(\([\d,]+\))"
        r"|([–\-]{1,2}(?!\d))"
        r"|([\d]{1,3}(?:,[\d]{3})+(?![,\d]))"
    )
    for m in pat.finditer(cleaned):
        if m.group(1):
            pass
        elif m.group(2):
            cols.append(-int(m.group(2)[1:-1].replace(",", "")))
        elif m.group(3):
            cols.append(None)
        elif m.group(4):
            cols.append(int(m.group(4).replace(",", "")))
    return cols


def _parse_columns_interleaved(line: str, n_years: int) -> list[int | float | None]:
    """Parse an interleaved (amount, pct) table row.

    Each year slot is one pair. Zero-years: (dash, dash). Non-zero: (amount, pct)
    where pct is either a skipped decimal or a dash.
    """
    cleaned = _strip_filler(line)
    pat = re.compile(
        r"(\([\d,]+\.[\d]+\))"
        r"|(\([\d,]+\))"
        r"|([–\-]{1,2}(?!\d))"
        r"|([\d]{1,3}(?:,[\d]{3})+(?![,\d]))"
    )
    raw: list[tuple[str, int | None]] = []
    for m in pat.finditer(cleaned):
        if m.group(1):
            pass
        elif m.group(2):
            raw.append(("amount", -int(m.group(2)[1:-1].replace(",", ""))))
        elif m.group(3):
            raw.append(("dash", None))
        elif m.group(4):
            raw.append(("amount", int(m.group(4).replace(",", ""))))

    results: list[int | float | None] = []
    idx = 0
    for _ in range(n_years):
        if idx >= len(raw):
            results.append(None)
            continue
        tok_type, tok_val = raw[idx]
        if tok_type == "dash":
            if idx + 1 < len(raw) and raw[idx + 1][0] == "dash":
                results.append(None)
                idx += 2
            else:
                results.append(None)
                idx += 1
        else:
            results.append(tok_val)
            idx += 1
            # Consume trailing pct-dash if present
            if idx < len(raw) and raw[idx][0] == "dash":
                idx += 1
    return results


def _parse_inline_single(line: str) -> int | float | None:
    """Extract a single value when the line ends with an amount (inline currency format)."""
    cleaned = _strip_filler(line)
    m = re.search(r"\(?([\d,]+(?:\.\d+)?)\)?$", cleaned.strip())
    if not m:
        return None
    raw = m.group(1).replace(",", "")
    is_neg = "(" in m.group(0) and ")" in m.group(0)
    val: int | float = float(raw) if "." in raw else int(raw)
    return -val if is_neg else val


def _extract_metric_from_section(
    text: str,
    section_id: str,
    metric: str,
    fy_col: int,
    interleaved: bool,
    n_years: int,
) -> HKFact | None:
    lines = _merge_wrapped_labels(text.split("\n"))

    for label in _PROSE_LABELS.get(metric, []):
        pat = re.compile(rf"^\s*{re.escape(label)}\b", re.IGNORECASE)
        for line in lines:
            stripped = _strip_filler(line)
            if not pat.match(stripped):
                continue

            if fy_col >= 0:
                if interleaved:
                    cols = _parse_columns_interleaved(line, n_years)
                else:
                    cols = _parse_columns_plain(line)

                if cols:
                    # Column grid parsed: trust its answer (including None for
                    # dashes). Do not fall back to inline single-value parsing,
                    # which would otherwise pick up trailing percentage tokens
                    # on an adjacent column.
                    if len(cols) > fy_col:
                        val = cols[fy_col]
                        if val is not None:
                            return HKFact(
                                metric=metric,
                                concept=_CONCEPT_NAME.get(metric, metric),
                                value=val,
                                unit=_UNIT_PENDING,
                                section_id=section_id,
                                extraction_method="regex",
                                matched_label=label,
                            )
                    continue

            # Fallback: single-value inline format
            val2 = _parse_inline_single(line)
            if val2 is not None:
                return HKFact(
                    metric=metric,
                    concept=_CONCEPT_NAME.get(metric, metric),
                    value=val2,
                    unit=_UNIT_PENDING,
                    section_id=section_id,
                    extraction_method="regex",
                    matched_label=label,
                )
    return None


_MUST_BE_POSITIVE: frozenset[str] = frozenset(
    {
        "revenue",
        "total_assets",
        "total_liabilities",
        "cash_and_equivalents",
        "shares_outstanding_basic",
        "shares_outstanding_diluted",
    }
)

# Expense-style metrics disclosed with parenthesized negative values in HKEX
# prospectuses. Normalize to the unsigned magnitude so downstream ratios
# (r_and_d_intensity, operating_margin) match SEC convention.
_STORE_AS_MAGNITUDE: frozenset[str] = frozenset({"rd_expense"})


def _extract_inline_single_year(
    text: str,
    section_id: str,
    metrics: list[str],
    multiplier: int,
) -> list[HKFact]:
    """Fallback extractor for sections with no column-year header."""
    out: list[HKFact] = []
    lines = _merge_wrapped_labels(text.split("\n"))
    for metric in metrics:
        for label in _PROSE_LABELS.get(metric, []):
            pat = re.compile(rf"^\s*{re.escape(label)}\b", re.IGNORECASE)
            fact: HKFact | None = None
            for line in lines:
                stripped = _strip_filler(line)
                if not pat.match(stripped):
                    continue
                val = _parse_inline_single(line)
                if val is None:
                    continue
                scaled_val = val * multiplier
                if metric in _MUST_BE_POSITIVE and scaled_val < 0:
                    continue
                if metric in _STORE_AS_MAGNITUDE:
                    scaled_val = abs(scaled_val)
                fact = HKFact(
                    metric=metric,
                    concept=_CONCEPT_NAME.get(metric, metric),
                    value=scaled_val,
                    unit=_UNIT_PENDING,
                    section_id=section_id,
                    extraction_method="regex",
                    matched_label=label,
                )
                break
            if fact is not None:
                out.append(fact)
                break
    return out


def extract_with_regex(
    text: str,
    section_id: str,
    standard: AccountingStandard,
    max_fy: int | None = None,
) -> list[HKFact]:
    if section_id not in _FINANCIAL_SECTIONS:
        return []

    metrics = _SECTION_METRICS.get(section_id, [])
    if not metrics:
        return []

    raw_years = [int(y) for y in re.findall(r"\b(20\d\d)\b", text[:500])]

    # Keep first-occurrence of each year (duplicates are typically interim
    # period columns reusing the same calendar year) and drop years that
    # exceed the audited fiscal year upper bound.
    seen: set[int] = set()
    year_cols: list[tuple[int, int]] = []  # (fy_idx, year)
    for idx, year in enumerate(raw_years):
        if year in seen:
            continue
        if max_fy is not None and year > max_fy:
            continue
        seen.add(year)
        year_cols.append((idx, year))

    # No year header detected: fall back to legacy single-value inline
    # extraction, emitting facts with fiscal_year=0 so the caller can
    # stamp the pack-level fiscal year.
    if not year_cols:
        if not raw_years:
            return _extract_inline_single_year(text, section_id, metrics, _detect_multiplier(text))
        return []

    interleaved = _is_interleaved(text)
    n_years = len(raw_years)
    multiplier = _detect_multiplier(text)

    out: list[HKFact] = []
    for fy_idx, year in year_cols:
        for metric in metrics:
            fact = _extract_metric_from_section(
                text, section_id, metric, fy_idx, interleaved, n_years
            )
            if fact is None:
                continue
            scaled_val = fact.value * multiplier
            if fact.metric in _MUST_BE_POSITIVE and scaled_val < 0:
                continue
            if fact.metric in _STORE_AS_MAGNITUDE:
                scaled_val = abs(scaled_val)
            out.append(
                HKFact(
                    metric=fact.metric,
                    concept=fact.concept,
                    value=scaled_val,
                    unit=fact.unit,
                    section_id=fact.section_id,
                    extraction_method=fact.extraction_method,
                    matched_label=fact.matched_label,
                    fiscal_year=year,
                )
            )
    return out


def extract_headcount_from_pack(pack_dir: Path) -> HKFact | None:
    import logging

    from ..sec.headcount_text import HEADCOUNT_MAX, HEADCOUNT_MIN, HEADCOUNT_PATTERN

    logger = logging.getLogger(__name__)
    sections_dir = pack_dir / "sections"
    if not sections_dir.exists():
        return None

    for section_file in sorted(sections_dir.glob("*.md")):
        text = section_file.read_text()
        for m in HEADCOUNT_PATTERN.finditer(text):
            raw = m.group(1).replace(",", "")
            try:
                value = int(raw)
            except ValueError:
                continue
            if HEADCOUNT_MIN <= value <= HEADCOUNT_MAX:
                return HKFact(
                    metric="headcount",
                    concept="EntityNumberOfEmployees",
                    value=value,
                    unit="headcount",
                    section_id=section_file.stem,
                    extraction_method="regex",
                    matched_label=m.group(0),
                )
            logger.warning("headcount candidate %s out of bounds in %s", value, section_file.name)
    return None


def extract_facts_from_pack(pack_dir: Path, llm_fallback: bool = True) -> Path:
    manifest = json.loads((pack_dir / "manifest.json").read_text())
    standard: AccountingStandard = manifest["accounting_standard"]
    currency: str = manifest["reporting_currency"]
    fy: int = manifest["fiscal_year"]
    accession = f"{manifest['stock_code']}_{fy}"

    sections_dir = pack_dir / "sections"
    all_facts: list[HKFact] = []

    for section_file in sorted(sections_dir.glob("*.md")):
        stem = section_file.stem
        if re.match(r".+_\d{2}$", stem):
            section_id = stem.rsplit("_", 1)[0]
        else:
            section_id = stem

        if section_id not in _FINANCIAL_SECTIONS:
            continue

        text = section_file.read_text()
        raw_facts = extract_with_regex(text, section_id, standard, max_fy=fy)
        for f in raw_facts:
            all_facts.append(
                HKFact(
                    metric=f.metric,
                    concept=f.concept,
                    value=f.value,
                    unit=currency,
                    section_id=f.section_id,
                    extraction_method=f.extraction_method,
                    matched_label=f.matched_label,
                    fiscal_year=f.fiscal_year,
                )
            )

    headcount_fact = extract_headcount_from_pack(pack_dir)
    if headcount_fact is not None:
        all_facts.append(headcount_fact)

    if llm_fallback:
        from .llm_extract import fill_missing_with_llm

        all_facts = fill_missing_with_llm(all_facts, sections_dir, standard, accession)

    nested: dict = {standard.lower(): {}}
    for fact in all_facts:
        concept_key = fact.concept
        fact_unit = fact.unit if fact.unit == "headcount" else currency
        fact_fy = fact.fiscal_year or fy
        nested[standard.lower()].setdefault(
            concept_key,
            {"label": concept_key, "units": {}},
        )
        nested[standard.lower()][concept_key]["units"].setdefault(fact_unit, []).append(
            {
                "start": f"{fact_fy}-01-01",
                "end": f"{fact_fy}-12-31",
                "val": fact.value,
                "fy": fact_fy,
                "fp": "FY",
                "form": "Annual Report",
                "accn": accession,
                "extraction_method": fact.extraction_method,
                "section_id": fact.section_id,
            }
        )

    facts_path = pack_dir / "facts.json"
    facts_path.write_text(
        json.dumps(
            {
                "stock_code": manifest["stock_code"],
                "company": manifest["company"],
                "facts": nested,
            },
            indent=2,
        )
    )
    return facts_path
