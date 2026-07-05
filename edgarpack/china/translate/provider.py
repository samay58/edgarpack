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
