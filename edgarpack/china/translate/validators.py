"""Post-translation quality validators.

All heuristic-based (free, no API calls). Run on 100% of translated output.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .numbers import NumberTag, tag_numbers

VALIDATOR_VERSION = "v5"
_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$", re.MULTILINE)
_HAN_RE = re.compile(r"[\u4e00-\u9fff]")
_ASCII_WORD_RE = re.compile(r"[A-Za-z]{2,}")
_PINYIN_ARTIFACT_RE = re.compile(r"\b[a-z]+(?:_[a-z]+)+\b")
_CHINESE_DATE_RE = re.compile(
    r"^(?P<year>\d{4})\s*年\s*(?P<month>\d{1,2})\s*月(?:\s*(?P<day>\d{1,2})\s*日)?$"
)
_ENGLISH_MONTH_YEAR_RE = re.compile(
    r"\b(?P<month>Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
    r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|"
    r"Nov(?:ember)?|Dec(?:ember)?)\.?\s+(?P<year>\d{4})\b",
    re.IGNORECASE,
)
_ENGLISH_MONTH_DAY_YEAR_RE = re.compile(
    r"\b(?P<month>Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
    r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|"
    r"Nov(?:ember)?|Dec(?:ember)?)\.?\s+(?P<day>\d{1,2}),\s+(?P<year>\d{4})\b",
    re.IGNORECASE,
)
_SPLIT_TABLE_DATE_RE = re.compile(
    r"(?P<prefix>\d{4}\s*年)\s*(?P<month_tens>\d)\s*\|\s*"
    r"(?P<month_ones>\d)\s*月\s*(?P<day>\d{1,2})\s*日"
)
_PERCENT_LITERAL_RE = re.compile(r"\d+(?:\.\d+)?%")
_DATE_OR_NUMBER_RE = re.compile(
    r"\d+\s*(?:[:：]\s*\d+(?:\.\d+)?)"
    r"|\d{4}\s*年\s*\d{1,2}\s*月(?:\s*\d{1,2}\s*日)?"
    r"|[-+]?\d[\d,./:%-]*"
)
_LATIN_PUNCT_ONLY_RE = re.compile(r"^[\s\-–—,:;()/%.*<>|]+$")
_ENGLISH_MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


@dataclass
class ValidationIssue:
    validator: str
    message: str
    severity: str = "error"
    paragraph_index: int | None = None


@dataclass
class ValidationReport:
    passed: bool
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(issue.severity == "error" for issue in self.issues)

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [issue for issue in self.issues if issue.severity == "warning"]


class NumberPreservationValidator:
    """Every tagged number in source must appear (converted) in target."""

    def validate(
        self,
        text_en: str,
        number_tags: list[NumberTag],
        paragraph_index: int | None = None,
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for tag in number_tags:
            # Check that the converted representation appears in the output
            if tag.converted not in text_en:
                # Also check if the placeholder leaked through unconverted
                if tag.placeholder in text_en:
                    issues.append(
                        ValidationIssue(
                            validator="number_preservation",
                            message=f"Placeholder {tag.placeholder} not restored in output",
                            severity="error",
                            paragraph_index=paragraph_index,
                        )
                    )
                else:
                    issues.append(
                        ValidationIssue(
                            validator="number_preservation",
                            message=f"Number {tag.original} not found in translation",
                            severity="error",
                            paragraph_index=paragraph_index,
                        )
                    )
        return issues


class LiteralTokenPreservationValidator:
    """Arabic numerals, dates, percentages, and identifiers must survive translation."""

    def validate(
        self,
        text_zh: str,
        text_en: str,
        excluded_tokens: set[str] | None = None,
        paragraph_index: int | None = None,
    ) -> list[ValidationIssue]:
        excluded = excluded_tokens or set()
        normalized_text_zh = _normalize_split_table_dates(text_zh)
        normalized_text_en = _normalize_split_table_dates(text_en)
        source_tokens = {
            _normalize_literal_token(token)
            for token in _DATE_OR_NUMBER_RE.findall(normalized_text_zh)
            if _is_significant_literal_token(token)
        }
        source_tokens.update(_extract_percent_tokens(normalized_text_zh))
        source_tokens.update(_expand_hyphenated_numeric_tokens(source_tokens))
        target_tokens = {
            _normalize_literal_token(token)
            for token in _DATE_OR_NUMBER_RE.findall(normalized_text_en)
            if _is_significant_literal_token(token)
        }
        target_tokens.update(_extract_english_month_year_tokens(normalized_text_en))
        target_tokens.update(_extract_english_month_day_year_tokens(normalized_text_en))
        target_tokens.update(_extract_percent_tokens(normalized_text_en))
        target_tokens.update(_expand_hyphenated_numeric_tokens(target_tokens))
        target_tokens.update(_expand_bare_year_tokens(target_tokens))
        missing = sorted(
            token for token in source_tokens if token not in target_tokens and token not in excluded
        )
        return [
            ValidationIssue(
                validator="literal_preservation",
                message=f"Literal token {token} missing from translation",
                severity="error",
                paragraph_index=paragraph_index,
            )
            for token in missing
        ]


def _expand_hyphenated_numeric_tokens(tokens: set[str]) -> set[str]:
    expanded: set[str] = set()
    for token in tokens:
        if not re.fullmatch(r"\d{4,}-\d+", token):
            continue
        left, right = token.split("-", 1)
        expanded.add(left)
        expanded.add(right)
    return expanded


class ResidualHanValidator:
    """English output should not leak Chinese text outside approved passthrough content."""

    def validate(
        self,
        text_en: str,
        paragraph_index: int | None = None,
    ) -> list[ValidationIssue]:
        if not _HAN_RE.search(text_en):
            return []
        return [
            ValidationIssue(
                validator="residual_han",
                message="Chinese characters remain in English output",
                severity="error",
                paragraph_index=paragraph_index,
            )
        ]


class RomanizedArtifactValidator:
    """Reject pinyin-like underscore artifacts in English output."""

    def validate(
        self,
        text_en: str,
        paragraph_index: int | None = None,
    ) -> list[ValidationIssue]:
        if not _PINYIN_ARTIFACT_RE.search(text_en):
            return []
        return [
            ValidationIssue(
                validator="romanized_artifact",
                message="Pinyin-like underscore artifact found in English output",
                severity="error",
                paragraph_index=paragraph_index,
            )
        ]


class MarkdownTableStructureValidator:
    """Markdown tables must preserve row shape and literal numeric cells."""

    def validate(
        self,
        text_zh: str,
        text_en: str,
        paragraph_index: int | None = None,
    ) -> list[ValidationIssue]:
        zh_rows = [row.strip() for row in text_zh.splitlines() if _TABLE_ROW_RE.match(row)]
        en_rows = [row.strip() for row in text_en.splitlines() if _TABLE_ROW_RE.match(row)]
        if not zh_rows:
            return []

        issues: list[ValidationIssue] = []
        if len(zh_rows) != len(en_rows):
            issues.append(
                ValidationIssue(
                    validator="table_structure",
                    message="Markdown table row count changed during translation",
                    severity="error",
                    paragraph_index=paragraph_index,
                )
            )
            return issues

        for zh_row, en_row in zip(zh_rows, en_rows, strict=False):
            zh_cells = zh_row.split("|")[1:-1]
            en_cells = en_row.split("|")[1:-1]
            if len(zh_cells) != len(en_cells):
                issues.append(
                    ValidationIssue(
                        validator="table_structure",
                        message="Markdown table column count changed during translation",
                        severity="error",
                        paragraph_index=paragraph_index,
                    )
                )
                return issues

            for zh_cell, en_cell in zip(zh_cells, en_cells, strict=False):
                zh_stripped = zh_cell.strip()
                en_stripped = en_cell.strip()
                if _looks_like_separator(zh_stripped):
                    continue
                if _is_literal_cell(zh_stripped):
                    if zh_stripped != en_stripped:
                        issues.append(
                            ValidationIssue(
                                validator="table_structure",
                                message=f"Literal table cell changed: {zh_stripped}",
                                severity="error",
                                paragraph_index=paragraph_index,
                            )
                        )
                elif zh_stripped and not en_stripped:
                    issues.append(
                        ValidationIssue(
                            validator="table_structure",
                            message="Non-empty table cell became empty in translation",
                            severity="error",
                            paragraph_index=paragraph_index,
                        )
                    )

        return issues


class GlossaryConsistencyValidator:
    """Same Chinese term maps to same English term throughout the document."""

    def __init__(self) -> None:
        self._term_map: dict[str, str] = {}

    def validate(
        self,
        text_zh: str,
        text_en: str,
        glossary_terms: dict[str, str],
        paragraph_index: int | None = None,
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for zh_term, expected_en in glossary_terms.items():
            if zh_term in text_zh:
                if zh_term in self._term_map:
                    prev_en = self._term_map[zh_term]
                    if prev_en != expected_en:
                        continue  # overlay may differ from base
                else:
                    self._term_map[zh_term] = expected_en

                # Check the English term appears in the output
                if expected_en.lower() not in text_en.lower():
                    issues.append(
                        ValidationIssue(
                            validator="glossary_consistency",
                            message=(
                                f"'{zh_term}' should translate to '{expected_en}' but not found"
                            ),
                            severity="warning",
                            paragraph_index=paragraph_index,
                        )
                    )
        return issues

    def reset(self) -> None:
        self._term_map.clear()


class CompletionValidator:
    """No source paragraphs silently dropped. Character ratio within expected range."""

    MIN_RATIO = 0.3
    MAX_RATIO = 5.0

    def validate(
        self,
        text_zh: str,
        text_en: str,
        paragraph_index: int | None = None,
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        len_zh = len(text_zh.strip())
        len_en = len(text_en.strip())

        if len_zh == 0:
            return issues

        if len_en == 0:
            issues.append(
                ValidationIssue(
                    validator="completion",
                    message="Translation is empty for non-empty source",
                    severity="error",
                    paragraph_index=paragraph_index,
                )
            )
            return issues

        ratio = len_en / len_zh
        if ratio < self.MIN_RATIO:
            issues.append(
                ValidationIssue(
                    validator="completion",
                    message=(
                        f"Translation suspiciously short (ratio {ratio:.2f}, min {self.MIN_RATIO})"
                    ),
                    severity="error",
                    paragraph_index=paragraph_index,
                )
            )
        elif ratio > self.MAX_RATIO:
            issues.append(
                ValidationIssue(
                    validator="completion",
                    message=(
                        f"Translation suspiciously long (ratio {ratio:.2f}, max {self.MAX_RATIO})"
                    ),
                    severity="warning",
                    paragraph_index=paragraph_index,
                )
            )

        return issues


def validate_translation(
    text_zh: str,
    text_en: str,
    number_tags: list[NumberTag] | None = None,
    glossary_terms: dict[str, str] | None = None,
    glossary_validator: GlossaryConsistencyValidator | None = None,
    allow_han: bool = False,
    paragraph_index: int | None = None,
) -> ValidationReport:
    """Run all validators on a single translated paragraph."""
    issues: list[ValidationIssue] = []
    excluded_literal_tokens: set[str] = set()
    effective_number_tags = number_tags
    if effective_number_tags is None:
        _, effective_number_tags = tag_numbers(text_zh)

    # Number preservation
    if effective_number_tags:
        issues.extend(
            NumberPreservationValidator().validate(text_en, effective_number_tags, paragraph_index)
        )
        excluded_literal_tokens = {
            _normalize_literal_token(token)
            for tag in effective_number_tags
            for token in _DATE_OR_NUMBER_RE.findall(tag.original)
            if _is_significant_literal_token(token)
        }
    issues.extend(
        LiteralTokenPreservationValidator().validate(
            text_zh,
            text_en,
            excluded_tokens=excluded_literal_tokens,
            paragraph_index=paragraph_index,
        )
    )
    issues.extend(MarkdownTableStructureValidator().validate(text_zh, text_en, paragraph_index))
    issues.extend(RomanizedArtifactValidator().validate(text_en, paragraph_index))
    if not allow_han:
        issues.extend(ResidualHanValidator().validate(text_en, paragraph_index))

    # Glossary consistency
    if glossary_terms and glossary_validator:
        issues.extend(
            glossary_validator.validate(text_zh, text_en, glossary_terms, paragraph_index)
        )

    # Completion check
    issues.extend(CompletionValidator().validate(text_zh, text_en, paragraph_index))

    return ValidationReport(
        passed=not any(issue.severity == "error" for issue in issues),
        issues=issues,
    )


def _looks_like_separator(value: str) -> bool:
    return bool(re.fullmatch(r":?-{3,}:?", value))


def _is_literal_cell(value: str) -> bool:
    if not value:
        return True
    if _looks_like_separator(value):
        return True
    if _HAN_RE.search(value) or _ASCII_WORD_RE.search(value):
        return False
    if _LATIN_PUNCT_ONLY_RE.fullmatch(value):
        return True
    if any(ch.isdigit() for ch in value):
        return True
    if value in {"-", "--", "***", "N/A"}:
        return True
    return False


def _is_significant_literal_token(token: str) -> bool:
    if not any(ch.isdigit() for ch in token):
        return False
    digits_only = "".join(ch for ch in token if ch.isdigit())
    if len(digits_only) >= 4:
        return True
    return any(ch in token for ch in ",./:%-")


def _normalize_split_table_dates(text: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        month = int(match.group("month_tens") + match.group("month_ones"))
        day = int(match.group("day"))
        if month < 1 or month > 12 or day < 1 or day > 31:
            return match.group(0)
        return f"{match.group('prefix')}{month}月{day}日"

    return _SPLIT_TABLE_DATE_RE.sub(_replace, text)


def _expand_bare_year_tokens(tokens: set[str]) -> set[str]:
    expanded: set[str] = set()
    for token in tokens:
        if re.fullmatch(r"\d{4}-\d{2}(?:-\d{2})?", token):
            expanded.add(token[:4])
            continue
        fiscal_year_match = re.fullmatch(r"FY\s+(\d{4})", token)
        if fiscal_year_match is not None:
            expanded.add(fiscal_year_match.group(1))
    return expanded


def _normalize_literal_token(token: str) -> str:
    stripped = token.replace("：", ":")
    stripped = re.sub(r"\s*:\s*", ":", stripped)
    stripped = stripped.replace("×", "x")
    stripped = stripped.replace(",", "")
    stripped = stripped.strip(".,;:)]}>-")
    stripped = stripped.strip()
    match = _CHINESE_DATE_RE.fullmatch(stripped)
    if match is None:
        return stripped
    day = match.group("day")
    if day is None:
        return f"{match.group('year')}-{int(match.group('month')):02d}"
    return f"{match.group('year')}-{int(match.group('month')):02d}-{int(day):02d}"


def _extract_english_month_year_tokens(text: str) -> set[str]:
    tokens: set[str] = set()
    for match in _ENGLISH_MONTH_YEAR_RE.finditer(text):
        month_key = match.group("month").rstrip(".").lower()
        month = _ENGLISH_MONTHS.get(month_key)
        if month is None:
            continue
        tokens.add(f"{match.group('year')}-{month:02d}")
    return tokens


def _extract_percent_tokens(text: str) -> set[str]:
    return {
        _normalize_literal_token(match.group(0)) for match in _PERCENT_LITERAL_RE.finditer(text)
    }


def _extract_english_month_day_year_tokens(text: str) -> set[str]:
    tokens: set[str] = set()
    for match in _ENGLISH_MONTH_DAY_YEAR_RE.finditer(text):
        month_key = match.group("month").rstrip(".").lower()
        month = _ENGLISH_MONTHS.get(month_key)
        if month is None:
            continue
        tokens.add(f"{match.group('year')}-{month:02d}-{int(match.group('day')):02d}")
    return tokens
