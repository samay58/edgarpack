"""Token counting using tiktoken."""

from __future__ import annotations

from typing import Any

try:
    import tiktoken  # type: ignore
except Exception:  # pragma: no cover - environment-dependent
    tiktoken = None  # type: ignore

from ..config import TIKTOKEN_ENCODING

# Lazy-loaded encoder
_encoder: Any | None = None


def get_encoder() -> Any:
    """Get or create the tiktoken encoder."""
    global _encoder
    if tiktoken is None:
        raise RuntimeError(
            "tiktoken is required for exact token counts. "
            "Install the 'tiktoken' package to use cl100k_base."
        )
    if _encoder is None:
        _encoder = tiktoken.get_encoding(TIKTOKEN_ENCODING)
    return _encoder


def has_tiktoken() -> bool:
    """Return True when exact cl100k_base tokenization is available."""
    return tiktoken is not None


def count_tokens(text: str) -> int:
    """Count tokens in text.

    Args:
        text: Text to tokenize

    Returns:
        Token count. Uses tiktoken/cl100k_base when available, otherwise falls back to a
        simple heuristic.
    """
    if tiktoken is None:
        return estimate_tokens(text)
    return len(get_encoder().encode(text))


def estimate_tokens(text: str) -> int:
    """Quick token estimate without full encoding.

    Uses heuristic: ~4 characters per token on average for English.
    Much faster than full tokenization for large texts.

    Args:
        text: Text to estimate

    Returns:
        Estimated token count
    """
    # Rough heuristic: 4 chars per token
    return len(text) // 4


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Truncate text to fit within a token limit.

    Args:
        text: Text to truncate
        max_tokens: Maximum tokens allowed

    Returns:
        Truncated text
    """
    if tiktoken is None:
        # Best-effort heuristic (~4 chars/token).
        return text[: max_tokens * 4]

    encoder = get_encoder()
    tokens = encoder.encode(text)
    if len(tokens) <= max_tokens:
        return text
    return encoder.decode(tokens[:max_tokens])
