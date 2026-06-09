"""Paragraph-level diff within changed sections."""

from __future__ import annotations

import hashlib
import math
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


_RESCUE_MIN_JACCARD = 0.6
_RESCUE_MIN_DISTINCTIVE = 0.5

_DISTINCTIVE_DF_RATIO = 0.25
_DISTINCTIVE_MIN_PARAS = 8
_DISTINCTIVE_FLOOR = 0.2


def _doc_frequencies(paragraphs: list[str]) -> dict[str, int]:
    """Count, per token, how many paragraphs contain it."""
    df: dict[str, int] = {}
    for paragraph in paragraphs:
        for word in set(_normalize(paragraph).split()):
            df[word] = df.get(word, 0) + 1
    return df


def _distinctive_jaccard(a: str, b: str, df: dict[str, int], total_paras: int) -> float:
    """Jaccard over tokens that are NOT ambient across the section's paragraphs.

    Legal boilerplate ("could adversely affect our business...") appears in most
    risk paragraphs and inflates plain Jaccard between unrelated topics. Tokens
    present in >= _DISTINCTIVE_DF_RATIO of paragraphs are dropped before
    comparing. Small sections fall back to plain Jaccard: DF over a handful of
    paragraphs is noise.
    """
    if total_paras < _DISTINCTIVE_MIN_PARAS:
        return _jaccard(a, b)
    cutoff = max(2, math.ceil(total_paras * _DISTINCTIVE_DF_RATIO))
    words_a = {w for w in set(_normalize(a).split()) if df.get(w, 0) < cutoff}
    words_b = {w for w in set(_normalize(b).split()) if df.get(w, 0) < cutoff}
    if not words_a and not words_b:
        # Pure-ambient paragraphs carry no distinctive signal either way.
        return _jaccard(a, b)
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)


def _split_paragraphs(text: str) -> list[str]:
    """Split text into paragraphs on double newlines, filtering empties."""
    parts = re.split(r"\n\n+", text.strip())
    return [p.strip() for p in parts if p.strip()]


_TOC_LINK_PATTERN = re.compile(
    r"^\[.*?\]\(#[a-zA-Z0-9_-]+\)$",
)


def _is_toc_link(text: str) -> bool:
    """Return True if the paragraph is solely a TOC or anchor link."""
    return bool(_TOC_LINK_PATTERN.match(text.strip()))


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


_CROSS_REF_OPENER = re.compile(
    r"^(?:(?:please\s+)?see\s|refer\s+to\s|as\s+discussed\s+in\s|"
    r"for\s+(?:additional|further)\s+(?:information|discussion|details?))",
    re.IGNORECASE,
)
_CROSS_REF_TARGET = re.compile(r"(?:item\s+\d+|note\s+\d+|part\s+[IVXivx]+)", re.IGNORECASE)


def _is_cross_reference(text: str) -> bool:
    """Return True if text is a short cross-reference sentence."""
    stripped = text.strip()
    if len(stripped.split()) > 100:
        return False
    return bool(_CROSS_REF_OPENER.match(stripped) and _CROSS_REF_TARGET.search(stripped))


def _is_boilerplate_change(old_text: str, new_text: str, similarity: float) -> bool:
    """Detect mechanical changes unlikely to be substantive.

    Two checks:
    1. Strict: 80%+ similarity AND 100% of changed words match boilerplate tokens
    2. Ratio: >60% of changed words match boilerplate tokens (any similarity)
    Also flags cross-reference paragraph pairs regardless of content changes.
    """
    if _is_cross_reference(old_text) and _is_cross_reference(new_text):
        return True

    old_words = _tokenize_for_change_detection(old_text)
    new_words = _tokenize_for_change_detection(new_text)
    diff_words = (old_words - new_words) | (new_words - old_words)
    if not diff_words:
        return False

    boilerplate_count = sum(1 for w in diff_words if _BOILERPLATE_TOKEN_PATTERN.match(w))

    # Strict check: high similarity + all changed words are boilerplate
    if similarity >= 0.80 and boilerplate_count == len(diff_words):
        return True

    # Ratio check: >60% of changed words are boilerplate tokens.
    # Require at least 3 diff words to avoid short-paragraph false positives.
    if len(diff_words) >= 3 and boilerplate_count / len(diff_words) > 0.60:
        return True

    return False


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
    old_paras = [p for p in _split_paragraphs(old_text) if not _is_toc_link(p)]
    new_paras = [p for p in _split_paragraphs(new_text) if not _is_toc_link(p)]

    df = _doc_frequencies(old_paras + new_paras)
    total_paras = len(old_paras) + len(new_paras)

    norm_old_full = _normalize(old_text)
    norm_new_full = _normalize(new_text)

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
    distinctive: list[list[float]] = [[0.0] * n_new for _ in range(n_old)]
    for oi, (_, op) in enumerate(unmatched_old):
        for nj, (_, np_) in enumerate(unmatched_new):
            sim = _jaccard(op, np_)
            overlap = _overlap_ratio(op, np_)
            dist = _distinctive_jaccard(op, np_, df, total_paras)
            jaccard[oi][nj] = sim
            distinctive[oi][nj] = dist
            # Overlap-based rescue score avoids false added/removed for contained
            # rewrites; the distinctive floor keeps boilerplate-tail pairs apart.
            score = max(sim, overlap * 0.8)
            match_score[oi][nj] = score if dist >= _DISTINCTIVE_FLOOR else 0.0

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

    # Pass 3: order-free rescue. The DP is order-preserving, so a paragraph that
    # moved across the section ends up unmatched on both sides. Near-verbatim
    # leftovers pair here as MOVED; greedy best-first keeps it deterministic.
    leftover_old = [i for i in range(len(old_paras)) if not old_matched[i]]
    leftover_new = [j for j in range(len(new_paras)) if not new_matched[j]]
    rescue_candidates: list[tuple[float, int, int]] = []
    for i in leftover_old:
        for j in leftover_new:
            sim = _jaccard(old_paras[i], new_paras[j])
            if sim < _RESCUE_MIN_JACCARD:
                continue
            if _distinctive_jaccard(old_paras[i], new_paras[j], df, total_paras) < (
                _RESCUE_MIN_DISTINCTIVE
            ):
                continue
            rescue_candidates.append((sim, i, j))
    rescue_candidates.sort(key=lambda c: (-c[0], c[1], c[2]))
    for sim, i, j in rescue_candidates:
        if old_matched[i] or new_matched[j]:
            continue
        old_matched[i] = True
        new_matched[j] = True
        deltas.append(
            ParagraphDelta(
                change_type=ChangeType.MOVED,
                old_text=old_paras[i],
                new_text=new_paras[j],
                similarity=sim,
                old_word_count=len(old_paras[i].split()),
                new_word_count=len(new_paras[j].split()),
                is_boilerplate=_is_boilerplate_change(old_paras[i], new_paras[j], sim),
            )
        )

    # Pass 4: remaining unmatched old = removed, unmatched new = added.
    # Before emitting REMOVED/ADDED, check whole-paragraph normalized containment in
    # the opposite full text: verbatim content that still exists in the after filing
    # (re-split or repositioned) is demoted to MOVED at similarity 1.0, contributing
    # zero to interest and intensity by construction.
    for i in range(len(old_paras)):
        if old_matched[i]:
            continue
        if _normalize(old_paras[i]) in norm_new_full:
            deltas.append(
                ParagraphDelta(
                    change_type=ChangeType.MOVED,
                    old_text=old_paras[i],
                    new_text=old_paras[i],
                    similarity=1.0,
                    old_word_count=len(old_paras[i].split()),
                    new_word_count=len(old_paras[i].split()),
                )
            )
            continue
        deltas.append(
            ParagraphDelta(
                change_type=ChangeType.REMOVED,
                old_text=old_paras[i],
                similarity=0.0,
                old_word_count=len(old_paras[i].split()),
            )
        )

    for j in range(len(new_paras)):
        if new_matched[j]:
            continue
        if _normalize(new_paras[j]) in norm_old_full:
            deltas.append(
                ParagraphDelta(
                    change_type=ChangeType.MOVED,
                    old_text=new_paras[j],
                    new_text=new_paras[j],
                    similarity=1.0,
                    old_word_count=len(new_paras[j].split()),
                    new_word_count=len(new_paras[j].split()),
                )
            )
            continue
        deltas.append(
            ParagraphDelta(
                change_type=ChangeType.ADDED,
                new_text=new_paras[j],
                similarity=0.0,
                new_word_count=len(new_paras[j].split()),
            )
        )

    return deltas
