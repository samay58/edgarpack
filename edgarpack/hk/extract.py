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
}

_SECTION_METRICS: dict[str, list[str]] = {
    "hkex_income_statement": ["revenue", "gross_profit", "operating_income", "net_income"],
    "hkex_comprehensive_income": ["net_income"],
    "hkex_balance_sheet": [
        "total_assets",
        "total_liabilities",
        "total_equity",
        "cash_and_equivalents",
    ],
    "hkex_cash_flow": [],
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
}


@dataclass(frozen=True)
class HKFact:
    metric: str
    concept: str
    value: int | float
    unit: str
    section_id: str
    extraction_method: ExtractionMethod
    matched_label: str


def _strip_filler(line: str) -> str:
    return re.sub(r"/H\d+", " ", line)


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
    lines = text.split("\n")

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

                if len(cols) > fy_col:
                    val = cols[fy_col]
                    if val is not None:
                        return HKFact(
                            metric=metric,
                            concept=_CONCEPT_NAME.get(metric, metric),
                            value=val,
                            unit="USD",
                            section_id=section_id,
                            extraction_method="regex",
                            matched_label=label,
                        )

            # Fallback: single-value inline format
            val2 = _parse_inline_single(line)
            if val2 is not None:
                return HKFact(
                    metric=metric,
                    concept=_CONCEPT_NAME.get(metric, metric),
                    value=val2,
                    unit="USD",
                    section_id=section_id,
                    extraction_method="regex",
                    matched_label=label,
                )
    return None


_MUST_BE_POSITIVE: frozenset[str] = frozenset({
    "revenue",
    "total_assets",
    "total_liabilities",
    "cash_and_equivalents",
    "shares_outstanding_basic",
    "shares_outstanding_diluted",
})


def extract_with_regex(
    text: str,
    section_id: str,
    standard: AccountingStandard,
) -> list[HKFact]:
    if section_id not in _FINANCIAL_SECTIONS:
        return []

    metrics = _SECTION_METRICS.get(section_id, [])
    if not metrics:
        return []

    fy_col = _find_fy_col(text, 2024)
    interleaved = _is_interleaved(text)
    n_years = _count_years(text)
    multiplier = _detect_multiplier(text)

    out: list[HKFact] = []
    for metric in metrics:
        fact = _extract_metric_from_section(text, section_id, metric, fy_col, interleaved, n_years)
        if fact:
            scaled_val = fact.value * multiplier
            if fact.metric in _MUST_BE_POSITIVE and scaled_val < 0:
                continue
            out.append(
                HKFact(
                    metric=fact.metric,
                    concept=fact.concept,
                    value=scaled_val,
                    unit=fact.unit,
                    section_id=fact.section_id,
                    extraction_method=fact.extraction_method,
                    matched_label=fact.matched_label,
                )
            )
    return out


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
        raw_facts = extract_with_regex(text, section_id, standard)
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
                )
            )

    if llm_fallback:
        from .llm_extract import fill_missing_with_llm

        all_facts = fill_missing_with_llm(all_facts, sections_dir, standard, accession)

    nested: dict = {standard.lower(): {}}
    for fact in all_facts:
        concept_key = fact.concept
        nested[standard.lower()].setdefault(
            concept_key,
            {"label": concept_key, "units": {currency: []}},
        )
        nested[standard.lower()][concept_key]["units"].setdefault(currency, []).append(
            {
                "start": f"{fy}-01-01",
                "end": f"{fy}-12-31",
                "val": fact.value,
                "fy": fy,
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
