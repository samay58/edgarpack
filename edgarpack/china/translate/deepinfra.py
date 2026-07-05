"""DeepInfra/DeepSeek translation provider using OpenAI-compatible REST API."""

from __future__ import annotations

import asyncio
import email.utils
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

from .glossary import FinancialGlossary
from .numbers import restore_numbers, tag_numbers
from .provider import TranslationResult

DEEPINFRA_ENDPOINT = "https://api.deepinfra.com/v1/openai/chat/completions"
DEFAULT_MODEL = "deepseek-ai/DeepSeek-V3"

_BASE_SYSTEM_PROMPT = (
    "You are a professional Chinese-to-English financial translator. "
    "Translate the Chinese text into natural, professional English "
    "suitable for institutional investors.\n\n"
    "Rules:\n"
    "1. Preserve all markdown formatting (headings, tables, lists, bold, italic).\n"
    "2. Preserve only placeholder tokens already present in the input, such as "
    "<<NUM_XXX>> and <<LIT_XXX>>. Never invent new <<...>> tokens or replace raw "
    "numbers, dates, or identifiers with descriptive placeholders.\n"
    "3. Use the glossary below for consistent financial terminology.\n"
    "4. Translate naturally, not literally. "
    "Read like a bilingual Chinese finance professional wrote it.\n"
    "5. Preserve table structure: keep pipe characters | and alignment.\n"
    "6. Keep raw Arabic numerals, dates, and identifiers unchanged unless they are "
    "existing <<NUM_XXX>> placeholders.\n"
    "7. Do not add explanations or commentary. Output only the translated text.\n\n"
    "Glossary:\n{glossary}"
)
PROMPT_VERSION = "v5"
_META_COMMENTARY_PREFIXES = (
    "no translation needed",
    "this appears to be",
    "keep as-is",
    "note:",
    "translator's note:",
)
_CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")
_PLACEHOLDER_RE = re.compile(r"<<[^<>]+>>")
_DUPLICATE_CURRENCY_RE = re.compile(r"\b(RMB|USD|HKD|EUR|JPY)\s+\1\b")
_SOURCE_NOTE_PREFIX_RE = re.compile(r"^\s*注\s*[:：]")
_CHINESE_DATE_LITERAL_RE = re.compile(
    r"^(?P<year>\d{4})\s*年(?:(?P<month>\d{1,2})\s*月(?:(?P<day>\d{1,2})\s*日)?)?$"
)
_LITERAL_TOKEN_RE = re.compile(
    r"\d{4}\s*年度"
    r"|\d{4}\s*年(?:\s*\d{1,2}\s*月(?:\s*\d{1,2}\s*日)?)?"
    r"|\d{4}(?:[/-]\d{1,2}){1,2}"
    r"|\d{1,2}-\d{1,2}"
    r"|\d+(?:,\d{3})+(?:\.\d+)?%?"
    r"|\d+\.\d+%?"
    r"|\d{2,}%?"
)
_SOURCE_ENUMERATED_YEAR_PREFIX_RE = re.compile(
    r"[（(]\s*(?P<index>\d+)\s*[）)]\s*"
    r"(?P<year>\d{4})\s*年(?:\s*(?P<month>\d{1,2})\s*月)?"
)
_TARGET_ENUMERATED_CLAUSE_RE = re.compile(r"\((?P<index>\d+)\)\s*")
_RETRY_PROMPT_SUFFIX = (
    "\n\nCritical reminder:\n"
    "- Never invent new <<...>> placeholders.\n"
    "- If the input does not contain a placeholder, the output must not contain one.\n"
    "- Return only the translated text."
)
_TRUNCATION_RETRY_PROMPT_SUFFIX = (
    "\n\nCritical reminder:\n"
    "- The previous response was cut off before it finished.\n"
    "- Produce the complete translation without leaving it unfinished.\n"
)
_CELL_RETRY_PROMPT_SUFFIX = (
    "\n\nCell translation reminder:\n"
    "- Translate only the text in this short table cell.\n"
    "- Output a concise English label, not a sentence.\n"
    "- Keep all digits, dates, punctuation, and markdown markers exactly unchanged."
)
_MARKDOWN_ARTIFACT_RETRY_PROMPT_SUFFIX = (
    "\n\nCritical reminder:\n"
    "- Do not invent markdown tables, columns, or rows.\n"
    "- Do not invent markdown image syntax or image URLs.\n"
    "- Do not invent pipe-separated table layouts or use | as a visual separator.\n"
    "- If the source contains no pipe-delimited table or image markup, "
    "the output must contain none.\n"
    "- Preserve the source structure faithfully."
)
_ENGLISH_ONLY_RETRY_PROMPT_SUFFIX = (
    "\n\nCritical reminder:\n"
    "- Translate all Chinese text into English.\n"
    "- Do not leave Chinese characters in the output.\n"
    "- Preserve markdown heading markers, numbering, bold, and punctuation.\n"
    "- Output only the English translation."
)
_RESIDUAL_HAN_REPAIR_PROMPT_SUFFIX = (
    "\n\nFinal repair pass:\n"
    "- The prior output still contained Chinese characters.\n"
    "- Translate every remaining Chinese character into English.\n"
    "- Preserve every existing <<NUM_XXX>> and <<LIT_XXX>> placeholder exactly.\n"
    "- Preserve all raw numbers, dates, markdown markers, table pipes, and line breaks.\n"
    "- Output only the repaired English translation."
)
_TRANSIENT_HTTP_EXCEPTIONS = (
    httpx.ConnectError,
    httpx.ReadError,
    httpx.ReadTimeout,
    httpx.RemoteProtocolError,
)
_MAX_API_RETRIES = 3
_RATE_LIMIT_MAX_API_RETRIES = 6


class DeepInfraConfigurationError(RuntimeError):
    """Raised when the DeepInfra translator is missing required configuration."""


class DeepInfraEmptyResponseError(RuntimeError):
    """Raised when a DeepInfra response contains no choices."""


@dataclass(frozen=True)
class _CompletionResult:
    content: str
    finish_reason: str


def _resolve_api_key(api_key: str | None = None) -> str:
    if api_key is not None:
        resolved = api_key.strip()
    else:
        resolved = (
            os.environ.get("EDGARPACK_DEEPINFRA_KEY") or os.environ.get("DEEPINFRA_API_KEY") or ""
        ).strip()

    if not resolved:
        raise DeepInfraConfigurationError(
            "DeepInfra API key missing. Set EDGARPACK_DEEPINFRA_KEY "
            "(preferred) or DEEPINFRA_API_KEY before running translation."
        )
    return resolved


def _retry_delay_seconds(response: httpx.Response | None, attempt: int) -> float:
    if response is not None:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return min(60.0, max(0.0, float(retry_after)))
            except ValueError:
                try:
                    parsed = email.utils.parsedate_to_datetime(retry_after)
                except (TypeError, ValueError):
                    pass
                else:
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=UTC)
                    delay = max(0.0, (parsed - datetime.now(UTC)).total_seconds())
                    return float(min(60.0, delay))
    return float(min(60.0, 2.0 * (2**attempt)))


def _build_system_prompt(glossary: FinancialGlossary, extra: str = "") -> str:
    prompt = _BASE_SYSTEM_PROMPT.format(glossary=glossary.format_for_prompt())
    if extra:
        prompt += f"\n\n{extra}"
    return prompt


class DeepInfraTranslator:
    """Translates Chinese text via DeepSeek V3 on DeepInfra's OpenAI-compatible API."""

    def __init__(
        self,
        glossary: FinancialGlossary,
        model: str = DEFAULT_MODEL,
        api_key: str | None = None,
        max_concurrency: int = 5,
    ) -> None:
        self.glossary = glossary
        self.model = model
        self.api_key = _resolve_api_key(api_key)
        self._semaphore = asyncio.Semaphore(max(1, max_concurrency))
        self._system_prompt = _build_system_prompt(glossary)
        self._client: httpx.AsyncClient | None = None
        self.prompt_tokens_used = 0
        self.completion_tokens_used = 0

    @property
    def provider(self) -> str:
        return f"deepinfra/{self.model}"

    @property
    def total_tokens_used(self) -> int:
        return self.prompt_tokens_used + self.completion_tokens_used

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=300.0)
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def translate(self, text_zh: str) -> TranslationResult:
        """Synchronous single-paragraph translation."""
        return asyncio.run(self._translate_one(text_zh, self._system_prompt))

    async def translate_async(
        self,
        text_zh: str,
        system_prompt: str | None = None,
        allow_markdown_artifacts: bool = False,
    ) -> TranslationResult:
        """Async single-paragraph translation."""
        prompt = system_prompt or self._system_prompt
        return await self._translate_one(
            text_zh,
            prompt,
            allow_markdown_artifacts=allow_markdown_artifacts,
        )

    async def translate_batch(
        self,
        paragraphs: list[str],
        system_prompt: str | None = None,
    ) -> list[TranslationResult]:
        """Translate paragraphs in chunks of 20, with semaphore-limited concurrency."""
        prompt = system_prompt or self._system_prompt
        results: list[TranslationResult] = []
        chunk_size = 20
        for i in range(0, len(paragraphs), chunk_size):
            chunk = paragraphs[i : i + chunk_size]
            tasks = [self._translate_one(p, prompt) for p in chunk]
            results.extend(await asyncio.gather(*tasks))
        return results

    async def _translate_one(
        self,
        text_zh: str,
        system_prompt: str,
        allow_markdown_artifacts: bool = False,
    ) -> TranslationResult:
        """Core translation: tag numbers, call LLM, restore numbers."""
        if not text_zh.strip():
            return TranslationResult(text_zh=text_zh, text_en=text_zh, provider=self.provider)

        tagged_text, number_tags = tag_numbers(text_zh)
        tagged_text, literal_tags = _tag_literal_tokens(tagged_text)
        allowed_placeholders = set(_PLACEHOLDER_RE.findall(tagged_text))

        async with self._semaphore:
            completion = await self._call_api(tagged_text, system_prompt)
            text_en_raw = _clean_translation_output(completion.content, text_zh)
            retry_for_truncation = completion.finish_reason == "length"
            retry_for_placeholders = _has_invented_placeholders(text_en_raw, allowed_placeholders)
            retry_for_markdown = not allow_markdown_artifacts and _has_invented_markdown_artifacts(
                text_zh, text_en_raw
            )
            retry_for_chinese = _contains_chinese(text_en_raw) and _contains_chinese(text_zh)
            if (
                retry_for_truncation
                or retry_for_placeholders
                or retry_for_markdown
                or retry_for_chinese
            ):
                retry_prompt = system_prompt
                if retry_for_truncation:
                    retry_prompt += _TRUNCATION_RETRY_PROMPT_SUFFIX
                if retry_for_placeholders:
                    retry_prompt += _RETRY_PROMPT_SUFFIX
                if retry_for_markdown:
                    retry_prompt += _MARKDOWN_ARTIFACT_RETRY_PROMPT_SUFFIX
                if retry_for_chinese:
                    retry_prompt += _ENGLISH_ONLY_RETRY_PROMPT_SUFFIX
                completion = await self._call_api(tagged_text, retry_prompt)
                text_en_raw = _clean_translation_output(completion.content, text_zh)
                if (
                    completion.finish_reason == "length"
                    or _has_invented_placeholders(text_en_raw, allowed_placeholders)
                    or (
                        not allow_markdown_artifacts
                        and _has_invented_markdown_artifacts(text_zh, text_en_raw)
                    )
                ):
                    text_en_raw = text_zh
                elif _contains_chinese(text_en_raw) and _contains_chinese(text_zh):
                    repair_prompt = system_prompt + _RESIDUAL_HAN_REPAIR_PROMPT_SUFFIX
                    repaired_completion = await self._call_api(tagged_text, repair_prompt)
                    repaired = _clean_translation_output(repaired_completion.content, text_zh)
                    if (
                        repaired_completion.finish_reason == "length"
                        or _has_invented_placeholders(repaired, allowed_placeholders)
                        or (
                            not allow_markdown_artifacts
                            and _has_invented_markdown_artifacts(text_zh, repaired)
                        )
                        or _contains_chinese(repaired)
                    ):
                        text_en_raw = text_zh
                    else:
                        text_en_raw = repaired

        text_en_with_literals = _restore_literal_tokens(text_en_raw, literal_tags)
        text_en = _clean_restored_translation(restore_numbers(text_en_with_literals, number_tags))
        text_en = _restore_enumerated_clause_year_prefixes(text_zh, text_en)

        return TranslationResult(text_zh=text_zh, text_en=text_en, provider=self.provider)

    async def _call_api(self, text: str, system_prompt: str) -> _CompletionResult:
        """Make the actual HTTP call to DeepInfra.

        Raises DeepInfraEmptyResponseError on an empty `choices` list rather than
        echoing the input text back as a translation. A truncated completion
        (finish_reason == "length") is returned as-is; the caller decides whether
        to retry or give up, since retrying belongs to the translation-quality
        ladder, not the transport layer.
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            "temperature": 0.0,
            "max_tokens": 4096,
        }

        client = await self._get_client()
        last_error: Exception | None = None
        max_attempts = _RATE_LIMIT_MAX_API_RETRIES
        for attempt in range(max_attempts):
            try:
                resp = await client.post(DEEPINFRA_ENDPOINT, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                usage = data.get("usage") or {}
                self.prompt_tokens_used += usage.get("prompt_tokens", 0) or 0
                self.completion_tokens_used += usage.get("completion_tokens", 0) or 0
                choices = data.get("choices", [])
                if not choices:
                    raise DeepInfraEmptyResponseError("DeepInfra response contained no choices")
                choice = choices[0]
                content = choice.get("message", {}).get("content", text)
                return _CompletionResult(
                    content=content if isinstance(content, str) else text,
                    finish_reason=choice.get("finish_reason") or "",
                )
            except httpx.HTTPStatusError as exc:
                last_error = exc
                status = exc.response.status_code
                retryable = status in {408, 429, 500, 502, 503, 504}
                if not retryable or attempt == max_attempts - 1:
                    raise
                await asyncio.sleep(_retry_delay_seconds(exc.response, attempt))
                continue
            except _TRANSIENT_HTTP_EXCEPTIONS as exc:
                last_error = exc
                if attempt == _MAX_API_RETRIES - 1:
                    raise
                await asyncio.sleep(0.5 * (2**attempt))

        if last_error is not None:
            raise last_error
        raise DeepInfraEmptyResponseError("DeepInfra request exhausted retries with no response")

    def build_system_prompt(self, extra: str = "") -> str:
        return _build_system_prompt(self.glossary, extra)

    def build_table_cell_prompt(self, strict: bool = False) -> str:
        extra = (
            "You are translating a short markdown table cell. "
            "Return a concise English label only. "
            "Do not emit notes, prose, or alternative phrasings."
        )
        prompt = self.build_system_prompt(extra)
        if strict:
            prompt += _CELL_RETRY_PROMPT_SUFFIX
        return prompt


def _clean_translation_output(text: str, fallback: str) -> str:
    cleaned_lines = []
    source_is_note = bool(_SOURCE_NOTE_PREFIX_RE.match(fallback))
    for line in text.splitlines():
        stripped = line.strip()
        lowered = stripped.lower()
        if stripped and lowered.startswith(_META_COMMENTARY_PREFIXES):
            if lowered.startswith("note:") and source_is_note:
                cleaned_lines.append(line)
                continue
            continue
        cleaned_lines.append(line)

    cleaned = "\n".join(cleaned_lines).strip()
    return cleaned or fallback


def _has_invented_placeholders(text: str, allowed_placeholders: set[str]) -> bool:
    placeholders = set(_PLACEHOLDER_RE.findall(text))
    return any(placeholder not in allowed_placeholders for placeholder in placeholders)


def _contains_chinese(text: str) -> bool:
    return bool(_CHINESE_RE.search(text))


def _has_invented_markdown_artifacts(source: str, translated: str) -> bool:
    if "image_url" in translated.lower():
        return True
    if "![" in translated and "![" not in source:
        return True
    if "|" not in source and translated.count("|") >= 3:
        return True
    if _contains_markdown_table(translated) and not _contains_markdown_table(source):
        return True
    return False


def _contains_markdown_table(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    edge_pipe_rows = [line for line in lines if line.startswith("|") and line.endswith("|")]
    if len(edge_pipe_rows) >= 2:
        return True

    pipe_rows = [line for line in lines if line.count("|") >= 2]
    if len(pipe_rows) < 2:
        return False

    separator_re = re.compile(r"^\s*:?-{2,}:?(?:\s*\|\s*:?-{2,}:?)+\s*$")
    return any(separator_re.fullmatch(line) for line in pipe_rows)


def _clean_restored_translation(text: str) -> str:
    previous = None
    cleaned = text
    while cleaned != previous:
        previous = cleaned
        cleaned = _DUPLICATE_CURRENCY_RE.sub(r"\1", cleaned)
    return cleaned


def _restore_enumerated_clause_year_prefixes(text_zh: str, text_en: str) -> str:
    source_prefixes: dict[str, str] = {}
    for match in _SOURCE_ENUMERATED_YEAR_PREFIX_RE.finditer(text_zh):
        prefix = match.group("year")
        month = match.group("month")
        if month is not None:
            prefix = f"{prefix}-{int(month):02d}"
        source_prefixes.setdefault(match.group("index"), prefix)

    if not source_prefixes:
        return text_en

    target_matches = list(_TARGET_ENUMERATED_CLAUSE_RE.finditer(text_en))
    if not target_matches:
        return text_en

    pieces: list[str] = []
    cursor = 0
    for index, match in enumerate(target_matches):
        clause_start = match.end()
        clause_end = (
            target_matches[index + 1].start() if index + 1 < len(target_matches) else len(text_en)
        )
        clause_prefix = source_prefixes.get(match.group("index"))
        pieces.append(text_en[cursor:clause_start])
        clause_text = text_en[clause_start:clause_end]
        if clause_prefix is None or _clause_contains_year_prefix(clause_text, clause_prefix):
            pieces.append(clause_text)
        else:
            leading_ws_len = len(clause_text) - len(clause_text.lstrip())
            pieces.append(
                clause_text[:leading_ws_len] + clause_prefix + " " + clause_text[leading_ws_len:]
            )
        cursor = clause_end
    pieces.append(text_en[cursor:])
    return "".join(pieces)


def _clause_contains_year_prefix(clause_text: str, prefix: str) -> bool:
    if prefix in clause_text:
        return True
    if re.fullmatch(r"\d{4}", prefix):
        if re.search(rf"\b{prefix}-\d{{2}}(?:-\d{{2}})?\b", clause_text):
            return True
        if re.search(rf"\bFY\s+{prefix}\b", clause_text):
            return True
    return False


def _tag_literal_tokens(text: str) -> tuple[str, list[tuple[str, str]]]:
    tags: list[tuple[str, str]] = []
    parts: list[str] = []
    cursor = 0

    for match in _PLACEHOLDER_RE.finditer(text):
        if match.start() > cursor:
            segment, segment_tags = _tag_literal_segment(
                text[cursor : match.start()],
                len(tags) + 1,
            )
            tags.extend(segment_tags)
            parts.append(segment)
        parts.append(match.group(0))
        cursor = match.end()

    if cursor < len(text):
        segment, segment_tags = _tag_literal_segment(text[cursor:], len(tags) + 1)
        tags.extend(segment_tags)
        parts.append(segment)

    return "".join(parts), tags


def _tag_literal_segment(segment: str, start_index: int) -> tuple[str, list[tuple[str, str]]]:
    tags: list[tuple[str, str]] = []
    seen: dict[str, str] = {}

    def _replace(match: re.Match[str]) -> str:
        token = match.group(0)
        if not _should_tag_literal_token(token):
            return token
        if token in seen:
            return seen[token]
        placeholder = f"<<LIT_{start_index + len(tags):03d}>>"
        tags.append((placeholder, _normalized_literal_restore_text(token)))
        seen[token] = placeholder
        return placeholder

    return _LITERAL_TOKEN_RE.sub(_replace, segment), tags


def _restore_literal_tokens(text: str, tags: list[tuple[str, str]]) -> str:
    restored = text
    for placeholder, replacement in tags:
        restored = restored.replace(placeholder, replacement)
    return restored


def _should_tag_literal_token(token: str) -> bool:
    digits = "".join(ch for ch in token if ch.isdigit())
    if len(digits) < 2:
        return False
    return any(ch in token for ch in "/-.,%") or len(digits) >= 4 or token.endswith("%")


def _normalized_literal_restore_text(token: str) -> str:
    token = re.sub(r"\s+", "", token)
    if token.endswith("年度") and token[:4].isdigit():
        return f"FY {token[:4]}"
    match = _CHINESE_DATE_LITERAL_RE.fullmatch(token)
    if match is None:
        return token
    year = match.group("year")
    month = match.group("month")
    day = match.group("day")
    if month is None:
        return year
    month_int = int(month)
    if day is None:
        return f"{year}-{month_int:02d}"
    return f"{year}-{month_int:02d}-{int(day):02d}"
