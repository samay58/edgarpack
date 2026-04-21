"""Financial glossary for Chinese-to-English translation."""

from __future__ import annotations

import json
from pathlib import Path

_GLOSSARY_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent / "data" / "glossary_zh_en.json"
)


class FinancialGlossary:
    """Loads zh->en financial terms and formats them for LLM system prompts."""

    def __init__(
        self,
        glossary_path: Path | None = None,
        overlay: dict[str, str] | None = None,
    ) -> None:
        path = glossary_path or _GLOSSARY_PATH
        raw = json.loads(path.read_text(encoding="utf-8"))
        self._terms: dict[str, str] = dict(raw.get("terms", {}))
        self._version: str = raw.get("version", "unknown")
        if overlay:
            self._terms.update(overlay)

    @property
    def version(self) -> str:
        return self._version

    @property
    def terms(self) -> dict[str, str]:
        return dict(self._terms)

    def __len__(self) -> int:
        return len(self._terms)

    def lookup(self, zh_term: str) -> str | None:
        return self._terms.get(zh_term)

    def format_for_prompt(self, max_terms: int = 200) -> str:
        """Render glossary as a compact table for LLM system prompts.

        Selects the first *max_terms* entries (longest zh first so specific
        multi-char terms take priority over short generic ones).
        """
        sorted_terms = sorted(self._terms.items(), key=lambda kv: -len(kv[0]))
        selected = sorted_terms[:max_terms]
        lines = ["Chinese | English", "--- | ---"]
        for zh, en in selected:
            lines.append(f"{zh} | {en}")
        return "\n".join(lines)

    @classmethod
    def with_company_overlay(
        cls,
        stock_code: str,
        packs_dir: Path,
        glossary_path: Path | None = None,
    ) -> FinancialGlossary:
        """Load glossary with per-company overlay if it exists."""
        overlay_path = packs_dir / "sse" / stock_code / "glossary_overlay.json"
        overlay: dict[str, str] | None = None
        if overlay_path.exists():
            overlay = json.loads(overlay_path.read_text(encoding="utf-8"))
        return cls(glossary_path=glossary_path, overlay=overlay)
