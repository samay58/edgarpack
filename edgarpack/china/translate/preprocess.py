"""Paragraph preprocessing for SSE translation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

_CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")
_PAGE_MARKER_RE = re.compile(r"^\d+-\d+-\d+$")
_BOUNDARY_REPLACEMENT_RE = r"(^|[\s|]|<br>)"
_BOUNDARY_LOOKAHEAD_RE = r"(?=$|[\s|]|<br>)"
_INLINE_PAGE_MARKER_RE = re.compile(
    _BOUNDARY_REPLACEMENT_RE + r"(\d+-\d+-\d+)" + _BOUNDARY_LOOKAHEAD_RE
)
_COMPANY_LINE_RE = re.compile(r"^[\u4e00-\u9fffA-Za-z0-9（）()·]{2,40}股份有限公司$")
_PROSPECTUS_LINE_RE = re.compile(r"^招股说明书(?:（申报稿）|\(申报稿\))?$")
_COMBINED_HEADER_RE = re.compile(
    r"^[\u4e00-\u9fffA-Za-z0-9（）()·]{2,40}股份有限公司\s+招股说明书(?:（申报稿）|\(申报稿\))?$"
)
_INLINE_HEADER_FRAGMENT_RE = re.compile(
    _BOUNDARY_REPLACEMENT_RE
    + r"(?:[\u4e00-\u9fffA-Za-z0-9（）()·]{2,40}股份有限公司\s+招股说明书(?:（申报稿）|\(申报稿\))?"
    + r"|[\u4e00-\u9fffA-Za-z0-9（）()·]{2,40}股份有限公司"
    + r"|招股说明书(?:（申报稿）|\(申报稿\))?)"
    + _BOUNDARY_LOOKAHEAD_RE
)
_INLINE_OCR_MARKER_RE = re.compile(
    _BOUNDARY_REPLACEMENT_RE + r"(~~[A-Za-z0-9><|/=+._-]{1,12}~~)" + _BOUNDARY_LOOKAHEAD_RE
)
_ASCII_NOISE_SPAN_RE = re.compile(
    r"(?<!\w)(?:[A-Za-z0-9=+~`'\"/\\_:;,.!@#$%^&*()\-\[\]{}<>?]+"
    r"(?:\s+[A-Za-z0-9=+~`'\"/\\_:;,.!@#$%^&*()\-\[\]{}<>?]+){1,})(?!\w)"
)


@dataclass(frozen=True)
class ParagraphDecision:
    original: str
    cleaned: str
    action: Literal["drop", "passthrough", "translate"]


def preprocess_paragraphs(paragraphs: list[str]) -> list[ParagraphDecision]:
    """Clean SSE paragraphs before cache lookup and translation."""
    return [_preprocess_one(paragraph) for paragraph in paragraphs]


def _preprocess_one(paragraph: str) -> ParagraphDecision:
    cleaned = paragraph.strip()
    if not cleaned:
        return ParagraphDecision(original=paragraph, cleaned="", action="drop")

    if _PAGE_MARKER_RE.fullmatch(cleaned) or _is_header_footer(cleaned):
        return ParagraphDecision(original=paragraph, cleaned="", action="drop")

    cleaned = _strip_inline_page_artifacts(cleaned)
    if _looks_like_markdown_table(cleaned):
        return ParagraphDecision(original=paragraph, cleaned=cleaned, action="translate")

    if _CHINESE_RE.search(cleaned):
        cleaned = _strip_ocr_noise_spans(cleaned)
    elif _looks_like_pure_ocr_noise(cleaned):
        return ParagraphDecision(original=paragraph, cleaned="", action="drop")

    cleaned = cleaned.strip()
    if not cleaned:
        return ParagraphDecision(original=paragraph, cleaned="", action="drop")

    if _PAGE_MARKER_RE.fullmatch(cleaned) or _is_header_footer(cleaned):
        return ParagraphDecision(original=paragraph, cleaned="", action="drop")

    if not _CHINESE_RE.search(cleaned) and len(cleaned) < 20:
        return ParagraphDecision(original=paragraph, cleaned=cleaned, action="passthrough")

    if not _CHINESE_RE.search(cleaned) and _looks_like_pure_ocr_noise(cleaned):
        return ParagraphDecision(original=paragraph, cleaned="", action="drop")

    return ParagraphDecision(original=paragraph, cleaned=cleaned, action="translate")


def _is_header_footer(text: str) -> bool:
    return bool(
        _COMPANY_LINE_RE.fullmatch(text)
        or _PROSPECTUS_LINE_RE.fullmatch(text)
        or _COMBINED_HEADER_RE.fullmatch(text)
    )


def _looks_like_markdown_table(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    table_rows = [line for line in lines if line.startswith("|") and line.endswith("|")]
    return len(table_rows) >= 2


def _strip_ocr_noise_spans(text: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        span = match.group(0)
        return " " if _looks_like_ascii_ocr_span(span) else span

    cleaned = _ASCII_NOISE_SPAN_RE.sub(_replace, text)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([，。！？；：])", r"\1", cleaned)
    return cleaned.strip()


def _strip_inline_page_artifacts(text: str) -> str:
    cleaned = _INLINE_HEADER_FRAGMENT_RE.sub(lambda match: match.group(1), text)
    cleaned = _INLINE_PAGE_MARKER_RE.sub(lambda match: match.group(1), cleaned)
    cleaned = _INLINE_OCR_MARKER_RE.sub(lambda match: match.group(1), cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned.strip()


def _looks_like_ascii_ocr_span(text: str) -> bool:
    tokens = text.split()
    if len(tokens) < 2:
        return False

    chars = [char for char in text if not char.isspace()]
    if len(chars) < 8:
        return False

    upper = sum(char.isupper() for char in chars)
    lower = sum(char.islower() for char in chars)
    symbols = sum(not char.isalnum() for char in chars)

    has_weird_symbol = any(char in "=+~@#$%^&*<>" for char in chars)
    upperish_tokens = sum(bool(re.search(r"[A-Z]{3,}", token)) for token in tokens)
    if not has_weird_symbol and upperish_tokens < 2:
        return False

    return (upper + symbols) / len(chars) >= 0.55 and upper >= lower


def _looks_like_pure_ocr_noise(text: str) -> bool:
    if _CHINESE_RE.search(text):
        return False

    chars = [char for char in text if not char.isspace()]
    if len(chars) < 8:
        return False

    upper = sum(char.isupper() for char in chars)
    lower = sum(char.islower() for char in chars)
    symbols = sum(not char.isalpha() for char in chars)

    noisy_ratio = (upper + symbols) / len(chars)
    return noisy_ratio >= 0.6 and lower / len(chars) <= 0.2
