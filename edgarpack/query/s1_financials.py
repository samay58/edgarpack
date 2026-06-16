"""Extract headline financial figures from pre-IPO S-1 filings.

SEC's companyfacts API is empty for pre-IPO filers (it's populated from
10-K / 10-Q / 20-F only), and Cerebras-era S-1 primary documents carry
no embedded iXBRL tags. The real numbers live in the filing's rendered
prose and tables. This module extracts them with a single Haiku 4.5
call per filing, caches the result to disk, and exposes them through
the existing `edgarpack query` surface via a fallback in
`edgarpack/query/financials.py`.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any

# Canonical slug set. Must stay in sync with METRIC_MAP in
# edgarpack/query/metric_map.py so CitedValue conversions resolve
# correctly downstream.
METRIC_SLUGS: frozenset[str] = frozenset(
    {
        "revenue",
        "gross_profit",
        "adjusted_gross_profit",
        "operating_income_loss",
        "net_income_loss",
        "operating_cash_flow",
        "capex",
        "adjusted_ebitda",
        "cash_and_equivalents",
        "total_assets",
        "stockholders_equity",
        "shares_outstanding_basic",
        "eps_basic",
    }
)


@dataclass(frozen=True)
class SnapshotFact:
    """One financial figure extracted from an S-1 filing.

    value_cents is an integer in the reporting currency's smallest unit
    (cents for USD, öre for SEK, and so on). The currency field names the
    ISO 4217 code so callers can convert later if they want; v1 renders
    native-currency only.
    """

    accession: str
    fiscal_year: int
    period_end: str  # ISO date YYYY-MM-DD
    metric: str  # member of METRIC_SLUGS
    value_cents: int
    currency: str  # ISO 4217
    is_audited: bool
    is_pro_forma: bool
    pro_forma_note: str | None
    fiscal_period: str = "FY"
    source_text: str | None = None
    section_id: str | None = None
    chunk_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SnapshotResult:
    """All extracted facts for one S-1 pack, plus extraction metadata.

    Persisted as `<pack_dir>/s1_financials.json`. `source_sha256` is the
    sha256 of the first 50KB of `<pack_dir>/filing.full.md`, used to
    invalidate the cache when the source markdown changes.
    """

    schema_version: int
    accession: str
    extracted_at: str  # ISO 8601 UTC
    extraction_status: str  # "ok" | "llm_parse_failed" | "no_financial_data_found" | "no_api_key"
    source_sha256: str
    model: str
    facts: list[SnapshotFact]

    def to_json(self) -> str:
        payload = {
            "schema_version": self.schema_version,
            "accession": self.accession,
            "extracted_at": self.extracted_at,
            "extraction_status": self.extraction_status,
            "source_sha256": self.source_sha256,
            "model": self.model,
            "facts": [f.to_dict() for f in self.facts],
        }
        return json.dumps(payload, indent=2)

    @classmethod
    def from_json(cls, raw: str) -> SnapshotResult:
        data = json.loads(raw)
        facts = [SnapshotFact(**f) for f in data.get("facts", [])]
        return cls(
            schema_version=int(data["schema_version"]),
            accession=str(data["accession"]),
            extracted_at=str(data["extracted_at"]),
            extraction_status=str(data["extraction_status"]),
            source_sha256=str(data["source_sha256"]),
            model=str(data["model"]),
            facts=facts,
        )


def _utc_iso_now() -> str:
    """Single source of truth for ISO-8601 UTC timestamps used in caches."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# S-1 filers use a handful of canonical phrasings for the financial
# summary section. Match the opening heading, stop at the next level-1
# or level-2 heading. Case-insensitive so Cerebras's "Selected Financial
# Data" and Klarna's "SELECTED FINANCIAL DATA" both fire.
_FINANCIAL_DATA_HEADINGS = [
    r"selected consolidated financial data",
    r"summary consolidated financial and other data",
    r"summary consolidated financial data",
    r"selected financial data",
    r"summary financial data",
    r"selected historical financial data",
]

_FINDATA_RE = re.compile(
    r"^\s*(?:\#{1,3}\s+)?(?:" + "|".join(_FINANCIAL_DATA_HEADINGS) + r")\b\s*$",
    re.IGNORECASE | re.MULTILINE,
)

# Section content is capped to keep the prompt well under Haiku's context
# window and to prevent runaway costs when the filing has a malformed TOC
# that absorbs 100KB+ of body text.
_SECTION_CAP_CHARS = 50_000


def find_financial_data_section(markdown: str) -> str | None:
    """Return the Selected Financial Data section body, or None if absent.

    Matches any of the canonical S-1 phrasings, truncates to 50KB, and
    stops at the next heading line so adjacent sections don't bleed in.
    """
    if not markdown:
        return None
    match = _FINDATA_RE.search(markdown)
    if not match:
        return None
    start = match.start()
    rest = markdown[start:]
    # End at the next H1/H2 heading after at least one newline of body.
    next_heading = re.search(r"\n\#{1,2}\s+\S", rest[1:])
    if next_heading is not None:
        end = 1 + next_heading.start()
        rest = rest[:end]
    return rest[:_SECTION_CAP_CHARS]


def _financial_section_texts(pack_dir: Path, markdown: str) -> list[str]:
    sections: list[str] = []
    primary = find_financial_data_section(markdown)
    if primary:
        sections.append(primary)

    sections_dir = Path(pack_dir) / "sections"
    if not sections_dir.exists():
        return sections
    name_fragments = (
        "summary_consolidated",
        "selected_financial",
        "summary_financial",
        "consolidated_statements",
        "prospectus_summary",
        "managements_discussion",
        "non_gaap",
    )
    content_markers = (
        "summary consolidated financial",
        "selected financial data",
        "consolidated statements of operations",
        "results of operations",
        "cash flows",
        "non-gaap financial measures",
    )
    for section_path in sorted(sections_dir.glob("*.md")):
        lowered = section_path.name.lower()
        try:
            text = section_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lowered_text = text.lower()
        has_name_match = any(fragment in lowered for fragment in name_fragments)
        has_content_match = any(marker in lowered_text for marker in content_markers)
        if not has_name_match and not has_content_match:
            continue

        candidates: list[str] = []
        section_primary = find_financial_data_section(text)
        if section_primary:
            candidates.append(section_primary)
        for marker in content_markers:
            marker_index = lowered_text.find(marker)
            if marker_index >= 0:
                candidates.append(text[marker_index : marker_index + _SECTION_CAP_CHARS])
        if has_name_match and not candidates:
            candidates.append(text[:_SECTION_CAP_CHARS])

        for candidate in candidates:
            if candidate.strip() and candidate not in sections:
                sections.append(candidate[:_SECTION_CAP_CHARS])
    return sections


_DETERMINISTIC_TABLE_MODEL = "deterministic-summary-table"
_YEAR_ROW_RE = re.compile(r"^((?:19|20)\d{2})(?:\s*/\s*((?:19|20)\d{2}))*$")
_YEAR_TOKEN_RE = re.compile(r"\b((?:19|20)\d{2})\b")
_INTERLEAVED_PERCENT_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b\s*/\s*%")
_SUMMARY_VALUE_TOKEN_RE = r"(?:\$?\(?\$?\d[\d,]*(?:\.\d+)?\)?|[\u2014-])"
_SUMMARY_ROW_VALUE_RE = re.compile(
    rf"(?P<left>{_SUMMARY_VALUE_TOKEN_RE})\s*/\s*(?P<right>{_SUMMARY_VALUE_TOKEN_RE})\s*$"
)
_SUMMARY_ANY_VALUE_RE = re.compile(rf"(?<![A-Za-z0-9]){_SUMMARY_VALUE_TOKEN_RE}(?![A-Za-z0-9])")
_INTERLEAVED_PERCENT_VALUE_RE = re.compile(
    r"\d[\d,]*(?:\.\d+)?\s*/\s*\d+(?:\.\d+)?\s*/\s*%\s*/\s*"
    r"\d[\d,]*(?:\.\d+)?\s*/\s*\d+(?:\.\d+)?\s*/\s*%"
)
_SUMMARY_TABLE_MAX_SCAN_LINES = 160
_PERIOD_END_LABELS = ("march 31", "june 30", "september 30", "december 31")


def _has_comparison_header_cells(cells: list[str]) -> bool:
    for cell in cells:
        normalized = re.sub(r"\s+", " ", cell).strip().lower()
        if not normalized:
            continue
        if "%" in normalized or "variance" in normalized or "change" in normalized:
            return True
        if normalized in {"amount", "$ amount", "us$ amount"}:
            return True
    return False


def _has_non_period_year_cells(cells: list[str]) -> bool:
    for cell in cells:
        normalized = re.sub(r"\s+", " ", cell).strip().lower()
        if not _YEAR_TOKEN_RE.search(normalized):
            continue
        if _YEAR_ROW_RE.fullmatch(normalized):
            continue
        allowed_markers = (
            "as of",
            "ended",
            "amounts in",
            "in thousands",
            "in millions",
            "note",
            *_PERIOD_END_LABELS,
        )
        if not any(marker in normalized for marker in allowed_markers):
            return True
    return False


def _merge_period_context_cells(
    contexts: list[str] | None,
    cells: list[str],
) -> list[str] | None:
    if not contexts or not cells:
        return contexts
    lowered_cells = [cell.lower() for cell in cells]
    if not any(label in cell for cell in lowered_cells for label in _PERIOD_END_LABELS):
        return contexts
    merged: list[str] = []
    for index, cell in enumerate(cells):
        base = contexts[index] if index < len(contexts) else contexts[-1]
        merged.append(f"{base} {cell}".strip())
    return merged


def _strip_summary_line(line: str) -> str:
    stripped = line.strip()
    if stripped.startswith(">"):
        stripped = stripped[1:].strip()
    return stripped.replace("\xa0", " ").strip()


def _summary_scale_multiplier(section_text: str) -> int:
    lowered = section_text.lower()
    if "in millions" in lowered:
        return 100_000_000
    if "in thousands" in lowered:
        return 100_000
    return 100


def _clean_summary_cell(raw: str) -> str:
    return raw.replace("*", "").replace("_", "").replace("\xa0", " ").strip()


def _split_summary_cells(line: str) -> list[str]:
    return [_clean_summary_cell(cell) for cell in _strip_summary_line(line).split("/")]


def _summary_period_from_context(year: int, context: str | None) -> tuple[str, str]:
    lowered = (context or "").lower()
    period_end_by_label = {
        "march 31": f"{year}-03-31",
        "june 30": f"{year}-06-30",
        "september 30": f"{year}-09-30",
        "december 31": f"{year}-12-31",
    }
    period_end = next(
        (end for label, end in period_end_by_label.items() if label in lowered),
        None,
    )
    if "three months ended" in lowered and period_end:
        fiscal_period = {
            "03-31": "Q1",
            "06-30": "Q2",
            "09-30": "Q3",
            "12-31": "Q4",
        }[period_end[-5:]]
        return fiscal_period, period_end
    if "six months ended" in lowered and period_end:
        return "Q2", period_end
    if "half-year ended" in lowered and period_end:
        return "Q2", period_end
    if "nine months ended" in lowered and period_end:
        return "Q3", period_end
    return "FY", f"{year}-12-31"


def _summary_columns(lines: list[str]) -> tuple[list[tuple[int, str, str]], int, int]:
    contexts: list[str] | None = None
    context_header_index: int | None = None
    for index, line in enumerate(lines):
        lowered = line.lower()
        if any(
            marker in lowered
            for marker in (
                "year ended",
                "three months ended",
                "six months ended",
                "half-year ended",
                "nine months ended",
            )
        ):
            cells = [cell for cell in _split_summary_cells(line) if cell]
            if _has_comparison_header_cells(cells):
                contexts = None
                context_header_index = None
                continue
            if cells:
                contexts = cells
                context_header_index = index
            header_columns: list[tuple[int, str, str]] = []
            for cell in cells:
                year_match = _YEAR_TOKEN_RE.search(cell)
                if year_match is None:
                    continue
                year = int(year_match.group(1))
                fiscal_period, period_end = _summary_period_from_context(year, cell)
                header_columns.append((year, fiscal_period, period_end))
            unique_header_columns = list(dict.fromkeys(header_columns))
            if len(unique_header_columns) >= 2:
                return unique_header_columns, index, index + 1
            continue

        year_tokens = [int(match.group(1)) for match in _YEAR_TOKEN_RE.finditer(line)]
        if not year_tokens:
            contexts = _merge_period_context_cells(contexts, _split_summary_cells(line))
            continue
        cells = [cell for cell in _split_summary_cells(line) if cell]
        if _has_comparison_header_cells(cells):
            contexts = None
            context_header_index = None
            continue
        if _has_non_period_year_cells(cells):
            contexts = None
            context_header_index = None
            continue
        if _INTERLEAVED_PERCENT_YEAR_RE.search(line):
            return [], 0, 0
        if "..." in line:
            prefix = line.split("...", 1)[0].strip()
            if not prefix.startswith("("):
                continue
        if not _YEAR_ROW_RE.fullmatch(line.strip()) and ("/" not in line or len(year_tokens) < 2):
            continue

        columns: list[tuple[int, str, str]] = []
        for position, year in enumerate(year_tokens):
            context = contexts[position] if contexts and position < len(contexts) else None
            fiscal_period, period_end = _summary_period_from_context(year, context)
            columns.append((year, fiscal_period, period_end))
        header_index = context_header_index if context_header_index is not None else index
        return columns, header_index, index + 1
    return [], 0, 0


def _parse_summary_number(raw: str) -> Decimal | None:
    token = raw.strip()
    if token in {"", "-", "\u2014", "--"}:
        return None
    is_negative = token.startswith("(") or token.endswith(")") or ("(" in token and ")" in token)
    token = token.replace("$", "").replace(",", "").replace("(", "").replace(")", "")
    try:
        value = Decimal(token)
    except InvalidOperation:
        return None
    return -value if is_negative else value


def _scaled_summary_cents(value: Decimal, *, metric: str, money_multiplier: int) -> int:
    multiplier = 100 if metric == "eps_basic" else money_multiplier
    return int((value * Decimal(multiplier)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _summary_metric_for_label(label: str, *, context: str | None) -> str | None:
    normalized = re.sub(r"\s+", " ", label).strip().lower()
    normalized = normalized.replace("\u2019", "'").replace("\u2013", "-")
    normalized = re.sub(r"\(\d+\)", "", normalized).strip()
    if normalized in {"revenue", "revenues", "total revenue", "total revenues"}:
        return "revenue"
    if normalized == "gross profit":
        return "gross_profit"
    if normalized == "adjusted gross profit":
        return "adjusted_gross_profit"
    if normalized in {
        "adjusted ebitda",
        "adjusted ebitda loss",
        "adjusted earnings before interest taxes depreciation and amortization",
    }:
        return "adjusted_ebitda"
    if normalized in {
        "operating loss",
        "loss from operations",
        "income (loss) from operations",
        "operating income (loss)",
        "operating income",
        "operating (loss) income",
    }:
        return "operating_income_loss"
    if normalized in {"net loss", "net income", "net income (loss)", "net (loss) income"}:
        return "net_income_loss"
    if (
        "net cash" in normalized
        and ("provided by" in normalized or "used in" in normalized)
        and "operating activities" in normalized
    ):
        return "operating_cash_flow"
    if "included in" in normalized or "accounts payable" in normalized:
        return None
    if normalized in {
        "purchases of property and equipment",
        "purchase of property and equipment",
        "capital expenditures",
    }:
        return "capex"
    if normalized.startswith("purchases of property") and "equipment" in normalized:
        return "capex"
    if context == "eps" and normalized == "basic":
        return "eps_basic"
    return None


def _summary_label_for_line(line: str) -> str:
    dot_match = re.search(r"\.{3,}", line)
    if dot_match is not None:
        prefix = line[: dot_match.start()]
    else:
        first_value = _SUMMARY_ANY_VALUE_RE.search(line)
        prefix = line[: first_value.start()] if first_value is not None else line
    prefix = prefix.replace("$", " ")
    prefix = re.sub(r"\.{3,}.*$", "", prefix).strip()
    prefix = re.sub(r"\(\d+\)", "", prefix).strip()
    if "/" in prefix:
        prefix = prefix.split("/", 1)[0].strip()
    return re.sub(r"\s+", " ", prefix).strip()


def _summary_values_for_line(line: str, column_count: int) -> list[Decimal | None]:
    if "%" in line:
        return []
    if _INTERLEAVED_PERCENT_VALUE_RE.search(line):
        return []
    line = re.sub(r"\(\d+\)", "", line)
    matches = [match.group(0) for match in _SUMMARY_ANY_VALUE_RE.finditer(line)]
    parsed = [_parse_summary_number(match) for match in matches]
    if parsed and len(parsed) % 2 == 0:
        pairs = list(zip(parsed[0::2], parsed[1::2], strict=True))
        if all(left == right for left, right in pairs):
            parsed = [left for left, _right in pairs]
    if len(parsed) == column_count:
        return parsed
    if len(parsed) > column_count:
        return []
    if 1 < len(parsed) < column_count:
        return parsed
    return []


def _compact_summary_columns(
    columns: list[tuple[int, str, str]],
    value_count: int,
) -> list[tuple[int, str, str]]:
    if len(columns) == value_count:
        return columns

    unique_years = list(dict.fromkeys(year for year, _period, _end in columns))
    has_interim = any(period != "FY" for _year, period, _end in columns)
    if has_interim and value_count >= 3 and len(unique_years) >= value_count - 1:
        interim_count = 2
        annual_count = value_count - interim_count
        annual_years = unique_years[:annual_count]
        interim_start = max(0, annual_count - 1)
        interim_years = unique_years[interim_start : interim_start + interim_count]
        compact: list[tuple[int, str, str]] = [
            (year, "FY", f"{year}-12-31") for year in annual_years
        ]
        compact.extend((year, "Q1", f"{year}-03-31") for year in interim_years)
        if len(compact) == value_count:
            return compact

    compact_unique = list(dict.fromkeys(columns))
    if len(compact_unique) == value_count:
        return compact_unique
    return columns


def _extract_summary_table_facts(section_text: str, *, accession: str) -> list[SnapshotFact]:
    """Parse common S-1 summary financial tables without an LLM.

    The parser is intentionally narrow: it only emits facts from rows with
    explicit period headers such as `2025 / 2024` or S-1 annual-plus-quarterly
    tables. Ambiguous rows are skipped.
    """
    lines = [_strip_summary_line(line) for line in section_text.splitlines()]
    money_multiplier = _summary_scale_multiplier(section_text)
    facts_by_key: dict[tuple[str, int, str, str], SnapshotFact | None] = {}
    search_index = 0
    while search_index < len(lines):
        columns, _local_header, local_start = _summary_columns(lines[search_index:])
        if not columns:
            break
        start_index = search_index + local_start
        next_columns, next_local_header, _next_local_start = _summary_columns(lines[start_index:])
        if next_columns:
            next_header_index = start_index + next_local_header
        else:
            next_header_index = len(lines)
        end_index = min(start_index + _SUMMARY_TABLE_MAX_SCAN_LINES, next_header_index)

        context: str | None = None
        for line in lines[start_index:end_index]:
            if not line:
                continue
            normalized_line = re.sub(r"\s+", " ", line).strip().lower()
            if "net income" in normalized_line and "per share" in normalized_line:
                context = "eps"
                continue
            if "net loss" in normalized_line and "per share" in normalized_line:
                context = "eps"
                continue
            if "weighted average shares" in normalized_line:
                context = "shares"
                continue
            if normalized_line.startswith("other financial information"):
                context = None

            values = _summary_values_for_line(line, len(columns))
            if not values:
                continue
            label = _summary_label_for_line(line)
            metric = _summary_metric_for_label(label, context=context)
            if metric is None:
                continue
            if metric == "eps_basic" and any(
                value is not None and abs(value) > Decimal("10000") for value in values
            ):
                continue

            row_columns = _compact_summary_columns(columns, len(values))
            if len(row_columns) != len(values):
                continue

            row_values = zip(row_columns, values, strict=True)
            for (fiscal_year, fiscal_period, period_end), value in row_values:
                if value is None:
                    continue
                value_cents = _scaled_summary_cents(
                    value,
                    metric=metric,
                    money_multiplier=money_multiplier,
                )
                if metric == "capex":
                    value_cents = abs(value_cents)
                key = (metric, fiscal_year, fiscal_period, period_end)
                fact = SnapshotFact(
                    accession=accession,
                    fiscal_year=fiscal_year,
                    period_end=period_end,
                    metric=metric,
                    value_cents=value_cents,
                    currency="USD",
                    is_audited=True,
                    is_pro_forma=False,
                    pro_forma_note=None,
                    fiscal_period=fiscal_period,
                    source_text=line,
                )
                existing = facts_by_key.get(key)
                if existing is None and key in facts_by_key:
                    continue
                if existing is not None and existing.value_cents != fact.value_cents:
                    facts_by_key[key] = None
                    continue
                facts_by_key[key] = fact
        search_index = max(end_index, start_index + 1)
    return [fact for fact in facts_by_key.values() if fact is not None]


def _supplement_cash_flow_facts_from_full_filing(
    facts: list[SnapshotFact],
    *,
    full_text: str,
    accession: str,
) -> list[SnapshotFact]:
    """Add cash-flow rows that often sit outside the S-1 summary table."""
    if not facts or not full_text:
        return facts

    supplemented = list(facts)
    seen = {
        (fact.metric, fact.fiscal_year, fact.fiscal_period, fact.period_end)
        for fact in supplemented
    }
    valid_years = {fact.fiscal_year for fact in supplemented if fact.fiscal_year}
    for fact in _extract_summary_table_facts(full_text, accession=accession):
        if fact.metric not in {"operating_cash_flow", "capex"}:
            continue
        if valid_years and fact.fiscal_year not in valid_years:
            continue
        key = (fact.metric, fact.fiscal_year, fact.fiscal_period, fact.period_end)
        if key in seen:
            continue
        supplemented.append(fact)
        seen.add(key)
    return supplemented


PROMPT_SYSTEM = (
    "You are extracting historical and pro-forma financial figures from an "
    "SEC Form S-1 filing. Return ONLY a JSON array. Do not fabricate: emit "
    "ONLY facts the filing explicitly states. Skip any figure you are less "
    "than 90% confident about."
)

_PROMPT_USER_TEMPLATE = """Return a JSON array. Each element is one fact:

{{
  "fiscal_year": 2024,
  "period_end": "2024-12-31",
  "metric": "revenue" | "gross_profit" | "adjusted_gross_profit"
          | "operating_income_loss" | "net_income_loss"
          | "operating_cash_flow" | "capex" | "adjusted_ebitda" | "cash_and_equivalents"
          | "total_assets" | "stockholders_equity"
          | "shares_outstanding_basic" | "eps_basic",
  "value_cents": 78287000000,
  "currency": "USD",
  "is_audited": true,
  "is_pro_forma": false,
  "pro_forma_note": null,
  "source_text": "Total revenue ... $1,306,404 / $671,053 / $387,067"
}}

RULES:
- Values are integers in the reporting currency's smallest unit (cents for USD).
- Do NOT scale: if the filing says "78,287" and the preamble says "in thousands"
  then value_cents = 78,287 * 1000 * 100 = 7,828,700,000.
- Losses are negative integers (e.g. "Net loss (259,251)" with "in thousands"
  becomes value_cents = -25,925,100,000).
- Per-share figures: value_cents is cents per share. "$(1.08)" becomes -108.
- Capital expenditures should be stored as a positive cash outflow. If the filing
  prints purchases of property and equipment in parentheses, return the absolute
  value.
- For net_income_loss, use the consolidated row labeled "Net income (loss)" or
  "Net income". Do not use rows labeled "attributable to shareholders",
  "attributable to controlling interests", or "attributable to non-controlling
  interests" for this metric.
- Share counts: shares_outstanding_basic uses value_cents for the count itself
  (scaled by 100). "240,123,456" shares becomes value_cents = 24,012,345,600.
- Pro-forma rows MUST set is_pro_forma=true and record the assumption verbatim
  in pro_forma_note. Historical audited rows set is_pro_forma=false.
- period_end must be ISO YYYY-MM-DD.
- fiscal_period should be "FY" for annual rows and "Q1" / "Q2" / "Q3" for interim rows.
- source_text should be the shortest verbatim row or sentence that contains the value.
- Every object must include source_text. If you cannot identify the source row or sentence,
  skip the fact.
- Return [] when the text contains no extractable financial data.

TEXT:
{text}
"""


def build_extraction_prompt(section_text: str) -> str:
    enum_line = " | ".join(f'"{s}"' for s in sorted(METRIC_SLUGS))
    return _PROMPT_USER_TEMPLATE.format(text=section_text) + (
        f"\n\n# Metric slugs allowed: {enum_line}"
    )


def _strip_code_fences(raw: str) -> str:
    s = raw.strip()
    if s.startswith("```"):
        first_newline = s.find("\n")
        if first_newline != -1:
            s = s[first_newline + 1 :]
        if s.endswith("```"):
            s = s[:-3]
    return s.strip()


_REQUIRED_KEYS = (
    "fiscal_year",
    "period_end",
    "metric",
    "value_cents",
    "currency",
    "is_audited",
    "is_pro_forma",
    "source_text",
)


def _llm_row_has_period_context(row: dict[str, object]) -> bool:
    fiscal_period = str(row.get("fiscal_period") or "FY").upper()
    period_end = str(row.get("period_end") or "")
    source_text = str(row.get("source_text") or "").lower()
    if fiscal_period != "FY":
        return True
    if period_end.endswith("-12-31"):
        return True
    annual_markers = ("year ended", "fiscal year", "annual")
    return any(marker in source_text for marker in annual_markers)


def _llm_row_has_metric_context(row: dict[str, object]) -> bool:
    metric = str(row.get("metric") or "")
    source_text = str(row.get("source_text") or "").lower()
    if metric == "net_income_loss" and "attributable to" in source_text:
        return False
    return True


MODEL_ID = "claude-haiku-4-5-20251001"
_MAX_OUTPUT_TOKENS = 8000


async def _call_haiku_extract(section_text: str) -> str:
    try:
        from anthropic import AsyncAnthropic
    except ImportError as exc:
        raise RuntimeError(
            "S-1 financial extraction requires the `anthropic` package. "
            "Install with `pip install edgarpack[vlm]` and export "
            "ANTHROPIC_API_KEY."
        ) from exc

    client = AsyncAnthropic()
    prompt = build_extraction_prompt(section_text)
    message = await client.messages.create(
        model=MODEL_ID,
        max_tokens=_MAX_OUTPUT_TOKENS,
        system=PROMPT_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    text_blocks = [
        str(getattr(block, "text", ""))
        for block in message.content
        if getattr(block, "type", "") == "text"
    ]
    return "".join(text_blocks).strip()


def parse_llm_response(raw: str, *, accession: str) -> list[SnapshotFact]:
    """Parse the model's JSON response into SnapshotFact objects.

    Drops any row missing required keys or whose metric is not in
    METRIC_SLUGS. Raises ValueError for unparseable output so callers
    can mark the extraction as failed and cache accordingly.
    """
    stripped = _strip_code_fences(raw)
    if not stripped:
        raise ValueError("invalid JSON: empty response")
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc}") from exc
    if not isinstance(payload, list):
        raise ValueError(f"expected JSON array, got {type(payload).__name__}")

    facts: list[SnapshotFact] = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        if any(k not in row for k in _REQUIRED_KEYS):
            continue
        if row.get("metric") not in METRIC_SLUGS:
            continue
        if not _llm_row_has_period_context(row):
            continue
        if not _llm_row_has_metric_context(row):
            continue
        try:
            fact = SnapshotFact(
                accession=accession,
                fiscal_year=int(row["fiscal_year"]),
                period_end=str(row["period_end"]),
                metric=str(row["metric"]),
                value_cents=int(row["value_cents"]),
                currency=str(row["currency"]),
                is_audited=bool(row["is_audited"]),
                is_pro_forma=bool(row["is_pro_forma"]),
                pro_forma_note=(
                    str(row["pro_forma_note"]) if row.get("pro_forma_note") is not None else None
                ),
                fiscal_period=str(row.get("fiscal_period") or "FY"),
                source_text=(
                    str(row["source_text"]).strip() if row.get("source_text") is not None else None
                ),
                section_id=(
                    str(row["section_id"]).strip() if row.get("section_id") is not None else None
                ),
                chunk_id=(
                    str(row["chunk_id"]).strip() if row.get("chunk_id") is not None else None
                ),
            )
        except (ValueError, TypeError):
            continue
        facts.append(fact)
    return facts


SCHEMA_VERSION = 8
_CACHE_FILENAME = "s1_financials.json"
_SOURCE_SCAN_CHARS = 50_000


def source_sha256_for_pack(pack_dir: Path) -> str:
    md_path = Path(pack_dir) / "filing.full.md"
    if not md_path.exists():
        return ""
    blob = md_path.read_text(encoding="utf-8", errors="replace")[:_SOURCE_SCAN_CHARS]
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def load_validated_snapshot(pack_dir: Path) -> tuple[SnapshotResult | None, str]:
    """Load s1_financials.json only when readable, schema-current, and fresh.

    Returns (snapshot, extraction_status) on success, else (None, reason)
    with reason in {"not_extracted", "cache_unreadable",
    "cache_stale_schema", "cache_stale_source"}. The single gatekeeper for
    every consumer of the cache (registration profile, distill).
    """
    cache = Path(pack_dir) / _CACHE_FILENAME
    if not cache.exists():
        return None, "not_extracted"
    try:
        snapshot = SnapshotResult.from_json(cache.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None, "cache_unreadable"
    if snapshot.schema_version != SCHEMA_VERSION:
        return None, "cache_stale_schema"
    if snapshot.source_sha256 != source_sha256_for_pack(pack_dir):
        return None, "cache_stale_source"
    return snapshot, snapshot.extraction_status


def _read_manifest_accession(pack_dir: Path) -> str:
    manifest = Path(pack_dir) / "manifest.json"
    if not manifest.exists():
        return pack_dir.name
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return pack_dir.name
    return str(data.get("filing", {}).get("accession", pack_dir.name))


async def extract_or_load_snapshot(pack_dir: Path, *, force: bool = False) -> SnapshotResult:
    pack_dir = Path(pack_dir)
    accession = _read_manifest_accession(pack_dir)
    source_hash = source_sha256_for_pack(pack_dir)
    cache_path = pack_dir / _CACHE_FILENAME

    if not force and cache_path.exists():
        try:
            cached = SnapshotResult.from_json(cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            cached = None
        if (
            cached is not None
            and cached.schema_version == SCHEMA_VERSION
            and cached.source_sha256 == source_hash
        ):
            return cached

    markdown = ""
    md_path = pack_dir / "filing.full.md"
    if md_path.exists():
        markdown = md_path.read_text(encoding="utf-8", errors="replace")

    financial_sections = _financial_section_texts(pack_dir, markdown)
    if not financial_sections:
        result = SnapshotResult(
            schema_version=SCHEMA_VERSION,
            accession=accession,
            extracted_at=_utc_iso_now(),
            extraction_status="no_financial_data_found",
            source_sha256=source_hash,
            model=MODEL_ID,
            facts=[],
        )
        cache_path.write_text(result.to_json(), encoding="utf-8")
        return result

    deterministic_facts: list[SnapshotFact] = []
    for section in financial_sections:
        deterministic_facts.extend(_extract_summary_table_facts(section, accession=accession))
    deduped_facts: dict[tuple[str, int, str, str], SnapshotFact | None] = {}
    for fact in deterministic_facts:
        key = (fact.metric, fact.fiscal_year, fact.fiscal_period, fact.period_end)
        existing = deduped_facts.get(key)
        if existing is None and key in deduped_facts:
            continue
        if existing is not None and existing.value_cents != fact.value_cents:
            deduped_facts[key] = None
            continue
        deduped_facts[key] = fact
    deterministic_facts = [fact for fact in deduped_facts.values() if fact is not None]
    deterministic_facts = _supplement_cash_flow_facts_from_full_filing(
        deterministic_facts,
        full_text=markdown,
        accession=accession,
    )
    if deterministic_facts:
        result = SnapshotResult(
            schema_version=SCHEMA_VERSION,
            accession=accession,
            extracted_at=_utc_iso_now(),
            extraction_status="ok",
            source_sha256=source_hash,
            model=_DETERMINISTIC_TABLE_MODEL,
            facts=deterministic_facts,
        )
        cache_path.write_text(result.to_json(), encoding="utf-8")
        return result

    try:
        raw = await _call_haiku_extract("\n\n".join(financial_sections)[:_SECTION_CAP_CHARS])
    except Exception:
        return SnapshotResult(
            schema_version=SCHEMA_VERSION,
            accession=accession,
            extracted_at=_utc_iso_now(),
            extraction_status="no_api_key",
            source_sha256=source_hash,
            model=MODEL_ID,
            facts=[],
        )

    try:
        facts = parse_llm_response(raw, accession=accession)
        status = "ok"
    except ValueError:
        facts = []
        status = "llm_parse_failed"

    result = SnapshotResult(
        schema_version=SCHEMA_VERSION,
        accession=accession,
        extracted_at=_utc_iso_now(),
        extraction_status=status,
        source_sha256=source_hash,
        model=MODEL_ID,
        facts=facts,
    )
    cache_path.write_text(result.to_json(), encoding="utf-8")
    return result


from datetime import date as _date_cls  # noqa: E402

from edgarpack.query.formula import eval_formula  # noqa: E402
from edgarpack.query.models import CitedValue, DerivedValue  # noqa: E402
from edgarpack.sec.submissions import is_registration_form  # noqa: E402


@dataclass(frozen=True)
class _RegistrationPack:
    pack_dir: Path
    accession: str
    filing_date: _date_cls
    form_type: str


@dataclass(frozen=True)
class _SnapshotCandidate:
    fact: SnapshotFact
    filing_date: _date_cls
    form_type: str


# Maps a snapshot metric slug to (unit, divisor) for CitedValue conversion.
# For monetary and per-share metrics the divisor is 100 (cents -> USD).
# For share counts the divisor is 100 (we stored count * 100 in cents).
_UNIT_FOR_METRIC: dict[str, tuple[str, int]] = {
    "revenue": ("USD", 100),
    "gross_profit": ("USD", 100),
    "adjusted_gross_profit": ("USD", 100),
    "operating_income_loss": ("USD", 100),
    "net_income_loss": ("USD", 100),
    "operating_cash_flow": ("USD", 100),
    "capex": ("USD", 100),
    "adjusted_ebitda": ("USD", 100),
    "cash_and_equivalents": ("USD", 100),
    "total_assets": ("USD", 100),
    "stockholders_equity": ("USD", 100),
    "shares_outstanding_basic": ("shares", 100),
    "eps_basic": ("USD/shares", 100),
}

# Default GAAP concept label per slug; used for the CitedValue.concept field
# on snapshot rows. Purely cosmetic, since snapshots are not sourced from
# GAAP tags, but keeps existing renderers that read .concept happy.
_DEFAULT_CONCEPTS: dict[str, str] = {
    "revenue": "Revenues",
    "gross_profit": "GrossProfit",
    "adjusted_gross_profit": "AdjustedGrossProfit",
    "operating_income_loss": "OperatingIncomeLoss",
    "net_income_loss": "NetIncomeLoss",
    "operating_cash_flow": "NetCashProvidedByUsedInOperatingActivities",
    "capex": "PaymentsToAcquirePropertyPlantAndEquipment",
    "adjusted_ebitda": "AdjustedEBITDA",
    "cash_and_equivalents": "CashAndCashEquivalentsAtCarryingValue",
    "total_assets": "Assets",
    "stockholders_equity": "StockholdersEquity",
    "shares_outstanding_basic": "WeightedAverageNumberOfSharesOutstandingBasic",
    "eps_basic": "EarningsPerShareBasic",
}

_PUBLIC_TO_SNAPSHOT_METRIC: dict[str, str] = {
    "operating_income": "operating_income_loss",
    "net_income": "net_income_loss",
    "cash": "cash_and_equivalents",
}

S1_DEFAULT_QUERY_METRICS: tuple[str, ...] = (
    "revenue",
    "gross_profit",
    "gross_margin",
    "operating_income",
    "operating_margin",
    "net_income",
    "net_margin",
    "adjusted_gross_profit",
    "adjusted_ebitda",
    "operating_cash_flow",
    "capex",
    "free_cash_flow",
    "cash_and_equivalents",
    "total_assets",
    "stockholders_equity",
    "shares_outstanding_basic",
    "eps_basic",
)

_S1_DERIVED_FORMULAS: dict[str, tuple[str, tuple[str, ...]]] = {
    "free_cash_flow": ("operating_cash_flow - capex", ("operating_cash_flow", "capex")),
    "gross_margin": ("gross_profit / revenue", ("gross_profit", "revenue")),
    "operating_margin": ("operating_income / revenue", ("operating_income", "revenue")),
    "net_margin": ("net_income / revenue", ("net_income", "revenue")),
    "fcf_margin": ("free_cash_flow / revenue", ("free_cash_flow", "revenue")),
    "capex_intensity": ("capex / revenue", ("capex", "revenue")),
}


def snapshot_fact_to_cited_value(
    fact: SnapshotFact,
    *,
    cik: str,
    company: str,
    form_type: str,
    filed: _date_cls,
    concept: str,
    public_metric: str | None = None,
) -> CitedValue:
    unit, divisor = _UNIT_FOR_METRIC[fact.metric]
    if fact.currency != "USD":
        unit = unit.replace("USD", fact.currency)
    value = fact.value_cents / divisor if divisor else fact.value_cents
    source = "s1_pro_forma" if fact.is_pro_forma else "s1_snapshot"

    try:
        period_end = _date_cls.fromisoformat(fact.period_end)
    except ValueError:
        period_end = _date_cls(fact.fiscal_year, 12, 31)

    return CitedValue(
        value=value,
        unit=unit,
        metric=public_metric or fact.metric,
        concept=concept,
        period_start=None,
        period_end=period_end,
        fiscal_year=fact.fiscal_year,
        fiscal_period=fact.fiscal_period or "FY",
        form_type=form_type,
        filed=filed,
        accession=fact.accession,
        cik=cik,
        company=company,
        source=source,
        reporting_currency=fact.currency,
        is_pro_forma=fact.is_pro_forma,
        pro_forma_note=fact.pro_forma_note,
        excerpt_text=fact.source_text or "",
    )


def pick_snapshot_fact(
    facts: list[SnapshotFact],
    *,
    metric: str,
    period: str,
) -> SnapshotFact | None:
    candidates = [f for f in facts if f.metric == metric]
    if not candidates:
        return None

    if period == "pro-forma":
        pf = [f for f in candidates if f.is_pro_forma]
        if not pf:
            return None
        pf.sort(key=lambda f: (f.fiscal_year, f.period_end), reverse=True)
        return pf[0]

    audited = [f for f in candidates if f.is_audited and not f.is_pro_forma]
    if not audited:
        return None

    if period == "mrp":
        audited.sort(key=lambda f: (f.period_end, f.fiscal_year), reverse=True)
        return audited[0]

    annual = [f for f in audited if (f.fiscal_period or "FY").upper() == "FY"]
    annual.sort(key=lambda f: (f.fiscal_year, f.period_end), reverse=True)

    if period == "lfy":
        return annual[0] if annual else None

    match_lfy_n = re.match(r"^lfy-(\d+)$", period)
    if match_lfy_n:
        offset = int(match_lfy_n.group(1))
        return annual[offset] if offset < len(annual) else None

    return None


def _parse_manifest_date(raw: object) -> _date_cls:
    try:
        return _date_cls.fromisoformat(str(raw))
    except (TypeError, ValueError):
        return _date_cls.min


def _read_registration_pack(manifest: Path, *, cik: str) -> _RegistrationPack | None:
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    filing = data.get("filing") or {}
    filing_cik = str(filing.get("cik", "")).lstrip("0")
    requested_cik = str(cik).lstrip("0")
    if filing_cik != requested_cik:
        return None
    form_type = str(filing.get("form_type", ""))
    if not is_registration_form(form_type):
        return None
    accession = str(filing.get("accession") or manifest.parent.name)
    return _RegistrationPack(
        pack_dir=manifest.parent,
        accession=accession,
        filing_date=_parse_manifest_date(filing.get("filing_date", "")),
        form_type=form_type or "S-1",
    )


def _registration_packs_for_cik(cik: str, pack_root: Path) -> list[_RegistrationPack]:
    packs: list[_RegistrationPack] = []
    for manifest in Path(pack_root).rglob("manifest.json"):
        pack = _read_registration_pack(manifest, cik=cik)
        if pack is not None:
            packs.append(pack)
    packs.sort(key=lambda p: (p.filing_date, p.accession), reverse=True)
    return packs


def has_registration_pack_for_cik(
    cik: str,
    pack_root: Path,
    *,
    form_type: str | None = None,
    accession: str | None = None,
) -> bool:
    from ..sec.submissions import normalize_form_type

    target_form = normalize_form_type(form_type) if form_type else None
    target_accession = accession.replace("-", "") if accession else None
    for pack in _registration_packs_for_cik(cik, pack_root):
        if target_form is not None and normalize_form_type(pack.form_type) != target_form:
            continue
        if target_accession is not None and pack.accession.replace("-", "") != target_accession:
            continue
        return True
    return False


def default_registration_query_metrics() -> list[str]:
    return list(S1_DEFAULT_QUERY_METRICS)


def _current_cached_snapshot(pack: _RegistrationPack) -> SnapshotResult | None:
    cache = pack.pack_dir / _CACHE_FILENAME
    if not cache.exists():
        return None
    try:
        result = SnapshotResult.from_json(cache.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return None
    if result.schema_version != SCHEMA_VERSION:
        return None
    if result.source_sha256 != source_sha256_for_pack(pack.pack_dir):
        return None
    return result


def _snapshot_candidates(
    result: SnapshotResult,
    pack: _RegistrationPack,
) -> list[_SnapshotCandidate]:
    return [
        _SnapshotCandidate(
            fact=fact,
            filing_date=pack.filing_date,
            form_type=pack.form_type,
        )
        for fact in result.facts
    ]


def _pick_snapshot_candidate(
    candidates: list[_SnapshotCandidate],
    *,
    metric: str,
    period: str,
) -> _SnapshotCandidate | None:
    metric_candidates = [c for c in candidates if c.fact.metric == metric]
    if not metric_candidates:
        return None

    if period == "pro-forma":
        pro_forma = [c for c in metric_candidates if c.fact.is_pro_forma]
        if not pro_forma:
            return None
        pro_forma.sort(
            key=lambda c: (c.fact.fiscal_year, c.fact.period_end, c.filing_date),
            reverse=True,
        )
        return pro_forma[0]

    audited = [c for c in metric_candidates if c.fact.is_audited and not c.fact.is_pro_forma]
    if not audited:
        return None

    if period == "mrp":
        audited.sort(
            key=lambda c: (c.fact.period_end, c.fact.fiscal_year, c.filing_date),
            reverse=True,
        )
        return audited[0]

    audited = [c for c in audited if (c.fact.fiscal_period or "FY").upper() == "FY"]
    if not audited:
        return None

    newest_per_period: dict[tuple[int, str], _SnapshotCandidate] = {}
    for candidate in sorted(
        audited,
        key=lambda c: (c.filing_date, c.fact.accession),
        reverse=True,
    ):
        key = (candidate.fact.fiscal_year, candidate.fact.period_end)
        newest_per_period.setdefault(key, candidate)

    ordered = sorted(
        newest_per_period.values(),
        key=lambda c: (c.fact.fiscal_year, c.fact.period_end),
        reverse=True,
    )

    if period == "lfy":
        return ordered[0] if ordered else None

    match_lfy_n = re.match(r"^lfy-(\d+)$", period)
    if match_lfy_n:
        offset = int(match_lfy_n.group(1))
        return ordered[offset] if offset < len(ordered) else None

    return None


def _resolve_concept_for_metric(metric: str) -> str:
    snapshot_metric = _snapshot_metric_for_query_metric(metric)
    if snapshot_metric in _DEFAULT_CONCEPTS:
        return _DEFAULT_CONCEPTS[snapshot_metric]
    formula = _S1_DERIVED_FORMULAS.get(metric)
    if formula is not None:
        return formula[0]
    return _DEFAULT_CONCEPTS.get(metric, metric)


def _snapshot_metric_for_query_metric(metric: str) -> str:
    return _PUBLIC_TO_SNAPSHOT_METRIC.get(metric, metric)


def _filed_date_for_candidate(
    candidate: _SnapshotCandidate,
    *,
    filed: _date_cls | None,
) -> _date_cls:
    if candidate.filing_date != _date_cls.min:
        return candidate.filing_date
    if filed is not None:
        return filed
    try:
        return _date_cls.fromisoformat(candidate.fact.period_end)
    except ValueError:
        return _date_cls.today()


def _candidate_to_cited_value(
    candidate: _SnapshotCandidate,
    *,
    public_metric: str,
    cik: str,
    company: str,
    form_type: str,
    filed: _date_cls | None,
) -> CitedValue:
    fact = candidate.fact
    return snapshot_fact_to_cited_value(
        fact,
        cik=cik,
        company=company,
        form_type=candidate.form_type or form_type,
        filed=_filed_date_for_candidate(candidate, filed=filed),
        concept=_resolve_concept_for_metric(public_metric),
        public_metric=public_metric,
    )


def _eval_s1_formula(
    formula: str,
    components: dict[str, CitedValue],
) -> float | None:
    values = {
        name: float(value.value) for name, value in components.items() if value.value is not None
    }
    return eval_formula(formula, values)


def _s1_derived_unit(metric: str) -> str:
    if metric == "free_cash_flow":
        return "USD"
    return "pure"


def _s1_value_from_candidates(
    candidates: list[_SnapshotCandidate],
    *,
    metric: str,
    period: str,
    cik: str,
    company: str,
    form_type: str,
    filed: _date_cls | None,
    resolving: set[str] | None = None,
) -> CitedValue | DerivedValue | None:
    resolving = set() if resolving is None else resolving
    if metric in resolving:
        return None

    formula = _S1_DERIVED_FORMULAS.get(metric)
    if formula is not None:
        resolving.add(metric)
        expression, component_names = formula
        components: dict[str, CitedValue] = {}
        for component_name in component_names:
            component = _s1_value_from_candidates(
                candidates,
                metric=component_name,
                period=period,
                cik=cik,
                company=company,
                form_type=form_type,
                filed=filed,
                resolving=resolving,
            )
            if component is None or component.value is None:
                resolving.discard(metric)
                return None
            components[component_name] = component

        fiscal_years = {component.fiscal_year for component in components.values()}
        period_ends = {component.period_end for component in components.values()}
        if len(fiscal_years) != 1 or len(period_ends) != 1:
            resolving.discard(metric)
            return None

        value = _eval_s1_formula(expression, components)
        if value is None:
            resolving.discard(metric)
            return None

        first_component = next(iter(components.values()))
        resolving.discard(metric)
        return DerivedValue(
            value=value,
            unit=_s1_derived_unit(metric),
            metric=metric,
            concept=expression,
            period_start=first_component.period_start,
            period_end=first_component.period_end,
            fiscal_year=first_component.fiscal_year,
            fiscal_period=first_component.fiscal_period,
            form_type=first_component.form_type,
            filed=first_component.filed,
            accession=first_component.accession,
            cik=cik,
            company=company,
            taxonomy=first_component.taxonomy,
            primary_document=first_component.primary_document,
            source=first_component.source,
            reporting_currency=first_component.reporting_currency,
            derived=True,
            components=components,
        )

    snapshot_metric = _snapshot_metric_for_query_metric(metric)
    if snapshot_metric not in METRIC_SLUGS:
        return None
    candidate = _pick_snapshot_candidate(
        candidates,
        metric=snapshot_metric,
        period=period,
    )
    if candidate is None:
        return None
    return _candidate_to_cited_value(
        candidate,
        public_metric=metric,
        cik=cik,
        company=company,
        form_type=form_type,
        filed=filed,
    )


_REGISTRATION_VALUE_SOURCES = {"s1_snapshot", "s1_pro_forma", "no_api_key"}


def _periodic_context_fiscal_years(result: Any) -> set[int]:
    years: set[int] = set()
    for value in getattr(result, "metrics", {}).values():
        values = value if isinstance(value, list) else [value]
        for item in values:
            if item is None:
                continue
            if getattr(item, "source", "") in _REGISTRATION_VALUE_SOURCES:
                continue
            fiscal_year = getattr(item, "fiscal_year", 0)
            if isinstance(fiscal_year, int) and fiscal_year > 0:
                years.add(fiscal_year)
    return years


def snapshots_for_cik(cik: str, pack_root: Path) -> list[SnapshotFact]:
    pack_root = Path(pack_root)
    out: list[SnapshotFact] = []
    for manifest in pack_root.rglob("manifest.json"):
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        filing = data.get("filing") or {}
        if str(filing.get("cik", "")).lstrip("0") != str(cik).lstrip("0"):
            continue
        if not is_registration_form(str(filing.get("form_type", ""))):
            continue
        cache = manifest.parent / _CACHE_FILENAME
        if not cache.exists():
            continue
        try:
            result = SnapshotResult.from_json(cache.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            continue
        out.extend(result.facts)
    return out


def _find_latest_registration_pack(cik: str, pack_root: Path) -> Path | None:
    """Return the newest-filing_date registration-class pack directory for a CIK."""
    packs = _registration_packs_for_cik(cik, pack_root)
    if not packs:
        return None
    return packs[0].pack_dir


async def augment_with_s1_snapshot(
    *,
    result: Any,  # QueryResult; kept as Any to avoid circular import pressure
    cik: str,
    metrics: list[str],
    period: str,
    pack_root: Path,
    company: str = "",
    form_type: str = "S-1",
    filed: _date_cls | None = None,
) -> Any:
    """Fill result.metrics cells that are still None with S-1 snapshot rows.

    When no cached snapshots exist, lazily extract from the most recent
    registration-class pack for this CIK. If that extraction fails due to
    missing ANTHROPIC_API_KEY, inject placeholder CitedValue rows with
    source="no_api_key" so the CLI can surface a helpful hint.
    """
    packs = _registration_packs_for_cik(cik, pack_root)
    if not packs:
        return result

    periodic_context_years = (
        set() if period == "pro-forma" else _periodic_context_fiscal_years(result)
    )
    latest_pack = packs[0]
    latest_result = await extract_or_load_snapshot(latest_pack.pack_dir)
    if latest_result.extraction_status == "no_api_key":
        if periodic_context_years:
            return result
        if latest_pack.filing_date != _date_cls.min:
            placeholder_date = latest_pack.filing_date
        else:
            placeholder_date = _date_cls.today()
        for metric in metrics:
            if result.metrics.get(metric) is None:
                snapshot_metric = _snapshot_metric_for_query_metric(metric)
                unit, _ = _UNIT_FOR_METRIC.get(snapshot_metric, ("USD", 100))
                result.metrics[metric] = CitedValue(
                    value=None,
                    unit=unit,
                    metric=metric,
                    concept=_resolve_concept_for_metric(metric),
                    period_end=placeholder_date,
                    fiscal_year=0,
                    fiscal_period="FY",
                    form_type=latest_pack.form_type or form_type,
                    filed=placeholder_date,
                    accession="",
                    cik=cik,
                    company=company,
                    source="no_api_key",
                )
        return result

    if not latest_result.facts:
        return result

    candidates = _snapshot_candidates(latest_result, latest_pack)
    for pack in packs[1:]:
        cached = _current_cached_snapshot(pack)
        if cached is not None:
            candidates.extend(_snapshot_candidates(cached, pack))

    if periodic_context_years:
        candidates = [
            candidate
            for candidate in candidates
            if candidate.fact.fiscal_year in periodic_context_years
        ]
        if not candidates:
            return result

    for metric in metrics:
        current = result.metrics.get(metric)
        if current is not None:
            continue
        value = _s1_value_from_candidates(
            candidates,
            metric=metric,
            period=period,
            cik=cik,
            company=company,
            form_type=form_type,
            filed=filed,
        )
        if value is not None:
            result.metrics[metric] = value
    return result
