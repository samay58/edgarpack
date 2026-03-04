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


def _overlap_ratio(a: str, b: str) -> float:
    """Overlap ratio: shared words over the smaller paragraph vocabulary."""
    words_a = set(_normalize(a).split())
    words_b = set(_normalize(b).split())
    if not words_a and not words_b:
        return 1.0
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / min(len(words_a), len(words_b))


def _split_paragraphs(text: str) -> list[str]:
    """Split text into paragraphs on double newlines, filtering empties."""
    parts = re.split(r"\n\n+", text.strip())
    return [p.strip() for p in parts if p.strip()]


_BOILERPLATE_TOKEN_PATTERN = re.compile(
    r"^(?:"
    r"\d{1,4}"
    r"|q[1-4]"
    r"|fy\d{2,4}"
    r"|f\d{2,4}"
    r"|january|february|march|april|may|june|july|august|september|october|november|december"
    r"|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec"
    r"|fiscal|year|quarter|ended|ending|beginning|begin|through|since"
    r"|item|form|report|annual|quarterly|page|pages|note|notes|section|see|refer|discussion"
    r"|st|nd|rd|th"
    r")$",
    re.IGNORECASE,
)


def _tokenize_for_change_detection(text: str) -> set[str]:
    """Tokenize normalized text to alphanumeric words for lightweight heuristics."""
    return set(re.findall(r"[a-z0-9]+", _normalize(text)))


def _is_boilerplate_change(old_text: str, new_text: str, similarity: float) -> bool:
    """Detect mechanical changes unlikely to be substantive (dates/refs/page numbers)."""
    if similarity < 0.80:
        return False

    old_words = _tokenize_for_change_detection(old_text)
    new_words = _tokenize_for_change_detection(new_text)
    diff_words = (old_words - new_words) | (new_words - old_words)
    if not diff_words:
        return False

    return all(_BOILERPLATE_TOKEN_PATTERN.match(word) for word in diff_words)


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

    # Build similarity matrices. match_score allows high-overlap expansions to be matched
    # as modified paragraphs even when strict Jaccard is dragged down by large insertions.
    n_old = len(unmatched_old)
    n_new = len(unmatched_new)
    jaccard: list[list[float]] = [[0.0] * n_new for _ in range(n_old)]
    match_score: list[list[float]] = [[0.0] * n_new for _ in range(n_old)]
    for oi, (_, op) in enumerate(unmatched_old):
        for nj, (_, np_) in enumerate(unmatched_new):
            sim = _jaccard(op, np_)
            overlap = _overlap_ratio(op, np_)
            jaccard[oi][nj] = sim
            # Overlap-based rescue score avoids false added/removed for contained rewrites.
            match_score[oi][nj] = max(sim, overlap * 0.8)

    # Dynamic programming alignment keeps pairings in order and avoids cross-matching
    # distant paragraphs that can happen with pure greedy global matching.
    dp: list[list[float]] = [[0.0] * (n_new + 1) for _ in range(n_old + 1)]
    back: list[list[str]] = [[""] * (n_new + 1) for _ in range(n_old + 1)]
    for oi in range(1, n_old + 1):
        back[oi][0] = "up"
    for nj in range(1, n_new + 1):
        back[0][nj] = "left"

    for oi in range(1, n_old + 1):
        for nj in range(1, n_new + 1):
            best = dp[oi - 1][nj]
            move = "up"
            if dp[oi][nj - 1] > best:
                best = dp[oi][nj - 1]
                move = "left"

            score = match_score[oi - 1][nj - 1]
            if score >= similarity_threshold:
                diagonal = dp[oi - 1][nj - 1] + score
                if diagonal > best:
                    best = diagonal
                    move = "diag"

            dp[oi][nj] = best
            back[oi][nj] = move

    matched_pairs: list[tuple[int, int, float]] = []
    oi = n_old
    nj = n_new
    while oi > 0 or nj > 0:
        move = back[oi][nj]
        if oi > 0 and nj > 0 and move == "diag":
            score = match_score[oi - 1][nj - 1]
            if score >= similarity_threshold:
                matched_pairs.append((oi - 1, nj - 1, jaccard[oi - 1][nj - 1]))
                oi -= 1
                nj -= 1
                continue
        if oi > 0 and (nj == 0 or move == "up"):
            oi -= 1
        else:
            nj -= 1

    for oi, nj, sim in reversed(matched_pairs):
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
                is_boilerplate=_is_boilerplate_change(op, np_, sim),
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
