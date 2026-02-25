"""Paragraph-level diff within changed sections."""

from __future__ import annotations

import hashlib
import re

from .models import ChangeType, ParagraphDelta


def _normalize(text: str) -> str:
    """Normalize text for comparison: collapse whitespace, lowercase."""
    return re.sub(r"\s+", " ", text.strip().lower())


def _fingerprint(text: str) -> str:
    """SHA256 fingerprint of normalized text."""
    return hashlib.sha256(_normalize(text).encode()).hexdigest()


def _jaccard(a: str, b: str) -> float:
    """Word-level Jaccard similarity between two strings."""
    words_a = set(_normalize(a).split())
    words_b = set(_normalize(b).split())
    if not words_a and not words_b:
        return 1.0
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


def _split_paragraphs(text: str) -> list[str]:
    """Split text into paragraphs on double newlines, filtering empties."""
    parts = re.split(r"\n\n+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def diff_paragraphs(
    old_text: str,
    new_text: str,
    similarity_threshold: float = 0.5,
) -> list[ParagraphDelta]:
    """Compute paragraph-level diff between two section texts.

    Strategy:
    1. Split both texts into paragraphs
    2. Fingerprint each paragraph for exact match detection
    3. For unmatched paragraphs, use Jaccard similarity to find modifications
    4. Remaining unmatched are additions/removals

    Args:
        old_text: Previous filing section text
        new_text: Current filing section text
        similarity_threshold: Minimum Jaccard similarity to consider a modification

    Returns:
        List of ParagraphDelta objects describing changes
    """
    old_paras = _split_paragraphs(old_text)
    new_paras = _split_paragraphs(new_text)

    old_fps = [_fingerprint(p) for p in old_paras]
    new_fps = [_fingerprint(p) for p in new_paras]

    # Track which paragraphs have been matched
    old_matched = [False] * len(old_paras)
    new_matched = [False] * len(new_paras)
    deltas: list[ParagraphDelta] = []

    # Pass 1: exact matches by fingerprint
    for i, ofp in enumerate(old_fps):
        for j, nfp in enumerate(new_fps):
            if not new_matched[j] and ofp == nfp:
                old_matched[i] = True
                new_matched[j] = True
                deltas.append(
                    ParagraphDelta(
                        change_type=ChangeType.UNCHANGED,
                        old_text=old_paras[i],
                        new_text=new_paras[j],
                        similarity=1.0,
                        old_word_count=len(old_paras[i].split()),
                        new_word_count=len(new_paras[j].split()),
                    )
                )
                break

    # Pass 2: fuzzy match unmatched paragraphs
    unmatched_old = [(i, old_paras[i]) for i in range(len(old_paras)) if not old_matched[i]]
    unmatched_new = [(j, new_paras[j]) for j in range(len(new_paras)) if not new_matched[j]]

    # Build similarity matrix for unmatched pairs
    pairs: list[tuple[float, int, int]] = []
    for oi, (i, op) in enumerate(unmatched_old):
        for nj, (j, np_) in enumerate(unmatched_new):
            sim = _jaccard(op, np_)
            if sim >= similarity_threshold:
                pairs.append((sim, oi, nj))

    # Greedy match by highest similarity
    pairs.sort(reverse=True)
    old_fuzzy_matched: set[int] = set()
    new_fuzzy_matched: set[int] = set()

    for sim, oi, nj in pairs:
        if oi in old_fuzzy_matched or nj in new_fuzzy_matched:
            continue
        old_fuzzy_matched.add(oi)
        new_fuzzy_matched.add(nj)
        i, op = unmatched_old[oi]
        j, np_ = unmatched_new[nj]
        old_matched[i] = True
        new_matched[j] = True
        deltas.append(
            ParagraphDelta(
                change_type=ChangeType.MODIFIED,
                old_text=op,
                new_text=np_,
                similarity=sim,
                old_word_count=len(op.split()),
                new_word_count=len(np_.split()),
            )
        )

    # Pass 3: remaining unmatched old = removed, unmatched new = added
    for i in range(len(old_paras)):
        if not old_matched[i]:
            deltas.append(
                ParagraphDelta(
                    change_type=ChangeType.REMOVED,
                    old_text=old_paras[i],
                    similarity=0.0,
                    old_word_count=len(old_paras[i].split()),
                )
            )

    for j in range(len(new_paras)):
        if not new_matched[j]:
            deltas.append(
                ParagraphDelta(
                    change_type=ChangeType.ADDED,
                    new_text=new_paras[j],
                    similarity=0.0,
                    new_word_count=len(new_paras[j].split()),
                )
            )

    return deltas
