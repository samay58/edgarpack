"""Provider-agnostic translation adapter interfaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class TranslationResult:
    text_zh: str
    text_en: str
    provider: str


class Translator(Protocol):
    """Minimal provider adapter contract."""

    def translate(self, text_zh: str) -> TranslationResult:
        """Translate Chinese text to English while preserving source text."""


class IdentityTranslator:
    """Deterministic translator used for local development and tests."""

    provider = "identity"

    def translate(self, text_zh: str) -> TranslationResult:
        return TranslationResult(text_zh=text_zh, text_en=text_zh, provider=self.provider)


class PrefixTranslator:
    """Simple adapter placeholder demonstrating provider swappability."""

    def __init__(self, provider_name: str = "mock-provider") -> None:
        self.provider_name = provider_name

    def translate(self, text_zh: str) -> TranslationResult:
        return TranslationResult(
            text_zh=text_zh,
            text_en=f"[EN:{self.provider_name}] {text_zh}",
            provider=self.provider_name,
        )
