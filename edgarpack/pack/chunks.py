"""Generate semantic chunks from sections."""

from bisect import bisect_right
import hashlib
import json
import re
from pathlib import Path

from pydantic import BaseModel

from ..config import DEFAULT_CHUNK_MAX_TOKENS, DEFAULT_CHUNK_MIN_TOKENS
from ..parse.tokenize import count_tokens, has_tiktoken, truncate_to_tokens


class Chunk(BaseModel):
    """A semantic chunk of a section."""

    chunk_id: str
    section_id: str
    chunk_index: int
    text: str
    char_start: int
    char_end: int
    tokens: int


def generate_chunk_id(section_id: str, chunk_index: int, text: str) -> str:
    """Generate deterministic chunk ID.

    Args:
        section_id: Parent section ID
        chunk_index: Index within section
        text: Chunk text (normalized for hashing)

    Returns:
        SHA256-based chunk ID
    """
    # Normalize text for consistent hashing
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    content = f"{section_id}:{chunk_index}:{normalized}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def find_paragraph_boundaries(text: str) -> list[int]:
    """Find paragraph boundaries (double newlines).

    Args:
        text: Text to analyze

    Returns:
        List of character positions where paragraphs end
    """
    boundaries = []
    for match in re.finditer(r"\n\n+", text):
        boundaries.append(match.end())
    return boundaries


def find_sentence_boundaries(text: str) -> list[int]:
    """Find sentence boundaries.

    Args:
        text: Text to analyze

    Returns:
        List of character positions where sentences end
    """
    boundaries = []
    # Match sentence-ending punctuation followed by space or newline
    for match in re.finditer(r"[.!?]\s+", text):
        boundaries.append(match.end())
    return boundaries


def chunk_section(
    section_id: str,
    content: str,
    min_tokens: int = DEFAULT_CHUNK_MIN_TOKENS,
    max_tokens: int = DEFAULT_CHUNK_MAX_TOKENS,
) -> list[Chunk]:
    """Split section content into semantic chunks.

    Strategy:
    1. Prefer paragraph boundaries (double newline)
    2. Fall back to sentence boundaries
    3. Hard split if no good boundary found

    Args:
        section_id: Section identifier
        content: Section content
        min_tokens: Minimum tokens per chunk (target)
        max_tokens: Maximum tokens per chunk

    Returns:
        List of Chunk objects
    """
    chunks: list[Chunk] = []

    if not content:
        return chunks

    min_tokens = max(1, int(min_tokens))
    max_tokens = max(1, int(max_tokens))
    if min_tokens > max_tokens:
        min_tokens = max_tokens

    # If content is small enough, return as single chunk
    total_tokens = count_tokens(content)
    if total_tokens <= max_tokens:
        return [
            Chunk(
                chunk_id=generate_chunk_id(section_id, 0, content),
                section_id=section_id,
                chunk_index=0,
                text=content,
                char_start=0,
                char_end=len(content),
                tokens=total_tokens,
            )
        ]

    # Find all potential boundaries (sorted, unique, and always include EOF).
    all_boundaries = sorted(
        set(find_paragraph_boundaries(content) + find_sentence_boundaries(content) + [len(content)])
    )

    start = 0
    chunk_index = 0
    n = len(content)

    while start < n:
        best_end: int | None = None
        best_tokens: int | None = None
        fallback_end: int | None = None
        fallback_tokens: int | None = None

        if has_tiktoken():
            truncated = truncate_to_tokens(content[start:], max_tokens)
            if not truncated:
                break
            max_end = start + len(truncated)
            idx = bisect_right(all_boundaries, max_end) - 1
            if idx >= 0 and all_boundaries[idx] > start:
                best_end = all_boundaries[idx]
            else:
                best_end = max_end
            text = content[start:best_end]
            if not text:
                break
            best_tokens = count_tokens(text)
        else:
            for end in all_boundaries:
                if end <= start:
                    continue
                candidate = content[start:end]
                candidate_tokens = count_tokens(candidate)
                if candidate_tokens <= max_tokens:
                    if candidate_tokens >= min_tokens:
                        best_end = end
                        best_tokens = candidate_tokens
                    else:
                        fallback_end = end
                        fallback_tokens = candidate_tokens
                    continue
                break

            if best_end is None or best_end <= start:
                if fallback_end is not None and fallback_end > start:
                    best_end = fallback_end
                    best_tokens = fallback_tokens
                else:
                    best_end = min(n, start + max_tokens * 4)
                    best_tokens = count_tokens(content[start:best_end])

        text = content[start:best_end]
        if not text:
            break

        chunks.append(
            Chunk(
                chunk_id=generate_chunk_id(section_id, chunk_index, text),
                section_id=section_id,
                chunk_index=chunk_index,
                text=text,
                char_start=start,
                char_end=best_end,
                tokens=best_tokens if best_tokens is not None else count_tokens(text),
            )
        )
        chunk_index += 1
        start = best_end

    return chunks


def generate_chunks(
    sections: list,  # List of Section objects
    min_tokens: int = DEFAULT_CHUNK_MIN_TOKENS,
    max_tokens: int = DEFAULT_CHUNK_MAX_TOKENS,
) -> list[Chunk]:
    """Generate chunks for all sections.

    Args:
        sections: List of Section objects
        min_tokens: Minimum tokens per chunk
        max_tokens: Maximum tokens per chunk

    Returns:
        List of all Chunk objects
    """
    all_chunks: list[Chunk] = []

    for section in sections:
        section_chunks = chunk_section(
            section.id,
            section.content,
            min_tokens=min_tokens,
            max_tokens=max_tokens,
        )
        all_chunks.extend(section_chunks)

    return all_chunks


def write_chunks_ndjson(chunks: list[Chunk], output_dir: Path) -> Path:
    """Write chunks to ndjson file.

    Args:
        chunks: List of Chunk objects
        output_dir: Directory to write to

    Returns:
        Path to written file
    """
    optional_dir = output_dir / "optional"
    optional_dir.mkdir(exist_ok=True)

    path = optional_dir / "chunks.ndjson"

    with path.open("w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(chunk.model_dump_json() + "\n")

    return path
