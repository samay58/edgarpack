"""Deterministic parser for the S-1 summary financial table.

Reads the "Selected / Summary Consolidated Financial Data" section (and a few
related sections) and emits `SnapshotFact` rows without an LLM. The parser is
intentionally narrow: it only trusts rows with explicit period headers and
fails closed on ambiguous shapes (percent-change columns, prose year mentions,
ambiguous presentation currency) so a guess never becomes a citation.
"""

from __future__ import annotations

import re
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

from .snapshot import SnapshotFact

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


_MONTH_TO_NUM: dict[str, int] = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sept": 9,
    "sep": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}
_MONTH_DAY_RE = re.compile(
    r"\b(" + "|".join(sorted(_MONTH_TO_NUM, key=len, reverse=True)) + r")\.?\s+(\d{1,2})\b",
    re.IGNORECASE,
)


def _month_day_period_end(year: int, context: str) -> str | None:
    """Return an ISO period_end from a "<month> <day>" phrase, or None.

    Recognizes any month name (not just quarter-end months) and validates the
    day against the calendar so an unparseable phrase yields no fabricated date.
    """
    match = _MONTH_DAY_RE.search(context)
    if match is None:
        return None
    month = _MONTH_TO_NUM[match.group(1).lower()]
    day = int(match.group(2))
    try:
        datetime(year, month, day)
    except ValueError:
        return None
    return f"{year}-{month:02d}-{day:02d}"


def _summary_period_from_context(year: int, context: str | None) -> tuple[str, str] | None:
    """Classify a summary column's fiscal period from its header context.

    Interim contexts ("three/six/nine months ended") never classify as FY and
    require a parseable month-day: when the interim marker is present but the
    month-day is missing, returns None so the caller drops the column rather
    than fabricating a period. Annual columns carry a stated fiscal-year-end
    month-day when the context names one ("year ended March 31" -> -03-31);
    a bare year with no month-day still classifies as FY (the year token is
    the citation for the row) but carries an absent period end ("") rather
    than a fabricated December 31, since non-calendar filers exist.
    """
    lowered = (context or "").lower()
    period_end = _month_day_period_end(year, lowered)
    if "three months ended" in lowered:
        if period_end is None:
            return None
        quarter = ((int(period_end[5:7]) - 1) // 3) + 1
        return f"Q{quarter}", period_end
    if "six months ended" in lowered or "half-year ended" in lowered:
        if period_end is None:
            return None
        return "Q2", period_end
    if "nine months ended" in lowered:
        if period_end is None:
            return None
        return "Q3", period_end
    if period_end is None:
        return "FY", ""
    return "FY", period_end


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
                resolved = _summary_period_from_context(year, cell)
                if resolved is None:
                    continue
                fiscal_period, period_end = resolved
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

        # When the month-day sits inside the year cell itself (e.g. a balance
        # sheet header "September 30, 2023 / September 30, 2022"), the merged
        # `contexts` from a preceding header line is absent; fold the cell text
        # into the per-column context so the stated period end is honored.
        year_cells = [cell for cell in cells if _YEAR_TOKEN_RE.search(cell)]
        aligned_cells = year_cells if len(year_cells) == len(year_tokens) else None
        columns: list[tuple[int, str, str]] = []
        unparseable_period = False
        for position, year in enumerate(year_tokens):
            base_context = contexts[position] if contexts and position < len(contexts) else None
            cell_context = aligned_cells[position] if aligned_cells is not None else None
            merged_context = " ".join(part for part in (base_context, cell_context) if part) or None
            resolved = _summary_period_from_context(year, merged_context)
            if resolved is None:
                unparseable_period = True
                break
            fiscal_period, period_end = resolved
            columns.append((year, fiscal_period, period_end))
        if unparseable_period:
            # An interim column with no parseable month-day is an uncited
            # period; skip this row and keep scanning for a stated header.
            continue
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
    annual_by_year = {year: (year, period, end) for year, period, end in columns if period == "FY"}
    interim_by_year = {year: (year, period, end) for year, period, end in columns if period != "FY"}
    if interim_by_year and value_count >= 3 and len(unique_years) >= value_count - 1:
        interim_count = 2
        annual_count = value_count - interim_count
        annual_years = unique_years[:annual_count]
        interim_start = max(0, annual_count - 1)
        interim_years = unique_years[interim_start : interim_start + interim_count]
        # Derive each compacted column from an actual parsed column rather than
        # fabricating a Q1/-03-31 stub; drop the compaction if a real column is
        # missing for a needed year.
        compact: list[tuple[int, str, str]] = []
        for year in annual_years:
            annual_col = annual_by_year.get(year)
            if annual_col is not None:
                compact.append(annual_col)
        for year in interim_years:
            interim_col = interim_by_year.get(year)
            if interim_col is not None:
                compact.append(interim_col)
        if len(compact) == value_count:
            return compact

    compact_unique = list(dict.fromkeys(columns))
    if len(compact_unique) == value_count:
        return compact_unique
    return columns


_PRESENTATION_CURRENCY_WORDS: dict[str, str] = {
    "rmb": "CNY",
    "renminbi": "CNY",
    "cny": "CNY",
    "eur": "EUR",
    "euro": "EUR",
    "euros": "EUR",
    "sek": "SEK",
    "gbp": "GBP",
    "jpy": "JPY",
    "yen": "JPY",
    "hkd": "HKD",
    "chf": "CHF",
    "cad": "CAD",
    "aud": "AUD",
    "sgd": "SGD",
}

# A presentation-currency phrase names a currency next to a scale marker, e.g.
# "expressed in thousands of RMB" or "in millions of EUR". Restricting to this
# shape avoids treating an incidental currency mention in prose as the table's
# presentation currency.
_PRESENTATION_CURRENCY_RE = re.compile(
    r"(?:expressed\s+in|amounts\s+in|in)\s+"
    r"(?:thousands|millions|billions)?\s*(?:of\s+)?"
    r"(" + "|".join(sorted(_PRESENTATION_CURRENCY_WORDS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


def _detect_presentation_currency(section_text: str) -> str | None:
    """Return the ISO-4217 presentation currency for a summary section.

    Returns "USD" when no non-USD presentation marker is present, the ISO code
    when exactly one non-USD currency is named, or None when a marker is
    present but ambiguous (multiple currencies) so the caller can fail closed.
    """
    found = {
        _PRESENTATION_CURRENCY_WORDS[match.group(1).lower()]
        for match in _PRESENTATION_CURRENCY_RE.finditer(section_text)
    }
    if not found:
        return "USD"
    if len(found) == 1:
        return next(iter(found))
    return None


def _extract_summary_table_facts(section_text: str, *, accession: str) -> list[SnapshotFact]:
    """Parse common S-1 summary financial tables without an LLM.

    The parser is intentionally narrow: it only emits facts from rows with
    explicit period headers such as `2025 / 2024` or S-1 annual-plus-quarterly
    tables. Ambiguous rows are skipped.
    """
    currency = _detect_presentation_currency(section_text)
    if currency is None:
        # A currency marker is present but ambiguous; refuse deterministic
        # emission and let the LLM path handle this table.
        return []
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
                    currency=currency,
                    # Annual columns of an S-1 come from audited statements;
                    # interim / stub columns are unaudited. Stamp truthfully.
                    is_audited=(fiscal_period or "FY").upper() == "FY",
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


def _dedupe_deterministic_facts(facts: list[SnapshotFact]) -> list[SnapshotFact]:
    deduped: dict[tuple[str, int, str, str], SnapshotFact | None] = {}
    for fact in facts:
        key = (fact.metric, fact.fiscal_year, fact.fiscal_period, fact.period_end)
        existing = deduped.get(key)
        if existing is None and key in deduped:
            continue
        if existing is not None and existing.value_cents != fact.value_cents:
            deduped[key] = None
            continue
        deduped[key] = fact
    return [fact for fact in deduped.values() if fact is not None]
