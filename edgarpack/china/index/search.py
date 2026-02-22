"""Lightweight evidence retrieval for MVP."""

from __future__ import annotations

import re
from collections.abc import Iterable

from ..models import EvidenceChunk

_TOKEN_RE = re.compile(r"[a-zA-Z0-9]+")
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "by",
    "for",
    "from",
    "in",
    "is",
    "of",
    "on",
    "or",
    "that",
    "the",
    "to",
    "with",
    "what",
}


def tokenize(text: str) -> list[str]:
    """Tokenize search text into lowercase terms."""
    tokens = [m.group(0).lower() for m in _TOKEN_RE.finditer(text)]
    return [token for token in tokens if len(token) >= 3 and token not in _STOPWORDS]


def score_chunk(query: str, chunk: EvidenceChunk) -> float:
    """Simple lexical score for deterministic MVP retrieval."""
    terms = tokenize(query)
    if not terms:
        return 0.0
    haystack = f"{chunk.text_zh}\n{chunk.text_en}".lower()
    return float(sum(1 for t in terms if t in haystack))


def rank_chunks(
    query: str, chunks: Iterable[EvidenceChunk], limit: int = 10
) -> list[tuple[EvidenceChunk, float]]:
    """Rank chunks by lexical overlap score."""
    scored = [(chunk, score_chunk(query, chunk)) for chunk in chunks]
    scored = [item for item in scored if item[1] > 0.0]
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[:limit]
