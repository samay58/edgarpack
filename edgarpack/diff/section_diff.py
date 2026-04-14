"""Match sections by stable ID and detect changes between filings."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from ..config import CACHE_DIR
from .models import ChangeType, DiffResult, SectionDelta
from .text_diff import diff_paragraphs

_DIFF_CACHE_DIR = CACHE_DIR.parent / "diff_cache"
_DIFF_CACHE_VERSION = "v5"
_FINANCIAL_SECTION_BASE_DAMPING = 0.4
_FINANCIAL_TABLE_DAMPING = 0.35
_INTEREST_SECTION_WEIGHTS = {
    "prose": 1.0,
    "financial_statement": 0.05,
    "signature": 0.05,
    "exhibit_index": 0.15,
}
_SUPPRESSED_SECTION_TYPES = {"financial_statement", "signature"}
_FORM_PART_PREFIX = re.compile(r"^10[kq]_part[a-z]+_")
_CANONICAL_ITEM_TITLES = {
    "1": "Business",
    "1A": "Risk Factors",
    "1B": "Unresolved Staff Comments",
    "1C": "Cybersecurity",
    "2": "Properties",
    "3": "Legal Proceedings",
    "4": "Mine Safety Disclosures",
    "5": "Market for Registrant's Common Equity",
    "6": "Reserved",
    "7": "Management's Discussion and Analysis",
    "7A": "Quantitative and Qualitative Disclosures About Market Risk",
    "8": "Financial Statements and Supplementary Data",
    "9": "Changes in and Disagreements with Accountants",
    "9A": "Controls and Procedures",
    "9B": "Other Information",
    "9C": "Disclosure Regarding Foreign Jurisdictions that Prevent Inspections",
    "10": "Directors, Executive Officers and Corporate Governance",
    "11": "Executive Compensation",
    "12": "Security Ownership",
    "13": "Certain Relationships and Related Transactions",
    "14": "Principal Accountant Fees and Services",
    "15": "Exhibits and Financial Statement Schedules",
    "16": "Form 10-K Summary",
}
_CROSS_REF_PATTERN = re.compile(
    r"^(?:for|see|refer to|please see|as discussed|of this annual report)\b",
    re.IGNORECASE,
)
_SENTENCE_LIKE_PATTERN = re.compile(r"^(?:our|we|this|that|in|of|as)\b", re.IGNORECASE)


def _load_manifest(pack_dir: Path) -> dict:
    """Load and parse manifest.json from a pack directory."""
    manifest_path = pack_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"No manifest.json in {pack_dir}")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _read_section(pack_dir: Path, section_path: str) -> str:
    """Read a section file from a pack directory."""
    full_path = pack_dir / section_path
    if not full_path.exists():
        return ""
    return full_path.read_text(encoding="utf-8")


def _manifest_fingerprint(manifest: dict) -> str:
    """Stable fingerprint of a manifest payload."""
    manifest_hash = manifest.get("manifest_hash")
    if isinstance(manifest_hash, str) and manifest_hash:
        return manifest_hash
    payload = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _cache_key(before_manifest: dict, after_manifest: dict) -> str:
    combined = (
        f"{_DIFF_CACHE_VERSION}:"
        f"{_manifest_fingerprint(before_manifest)}:{_manifest_fingerprint(after_manifest)}"
    )
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


def _get_cached_diff(key: str) -> DiffResult | None:
    path = _DIFF_CACHE_DIR / f"{key}.json"
    if not path.exists():
        return None
    try:
        return DiffResult.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # Corrupted cache entries should never take down live diff requests.
        path.unlink(missing_ok=True)
        return None


def _cache_diff(key: str, result: DiffResult) -> None:
    _DIFF_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (_DIFF_CACHE_DIR / f"{key}.json").write_text(
        result.model_dump_json(indent=2),
        encoding="utf-8",
    )


def _classify_section(section_id: str) -> str:
    """Classify section type for ranking and noise reduction."""
    sid = section_id.lower()
    if any(
        keyword in sid
        for keyword in (
            "financial_statements",
            "financial_statement",
            "item8",
            "item_8",
            "item8_",
            "item15",
            "item_15",
        )
    ):
        return "financial_statement"
    if "signature" in sid:
        return "signature"
    if "exhibit" in sid and "index" in sid:
        return "exhibit_index"
    return "prose"


def _clean_display_title(raw_title: str) -> str:
    title = re.sub(r"\s+", " ", (raw_title or "").strip())
    for pattern in (
        r"\s+(?:for|see|refer to|please see|as discussed)\s+"
        r"(?:a\s+)?(?:discussion|details?|information|more|further)\b.*$",
        r"\s+for\s+(?:a\s+)?discussion\s+of\b.*$",
        r"\s*of this annual report.*$",
        r"\s*of (?:our|the) (?:\d{4}\s+)?(?:annual|quarterly) report.*$",
    ):
        title = re.sub(pattern, "", title, flags=re.IGNORECASE)
    return title.strip()


def _canonical_title_from_section_id(section_id: str) -> str | None:
    item_match = re.search(r"item_?(?P<item>\d+[a-z]?)(?:_|$)", section_id, re.IGNORECASE)
    if not item_match:
        return None
    return _CANONICAL_ITEM_TITLES.get(item_match.group("item").upper())


def _display_title(section_id: str, raw_title: str) -> str:
    title = _clean_display_title(raw_title)
    canonical = _canonical_title_from_section_id(section_id)
    if not title:
        return canonical or section_id
    if _CROSS_REF_PATTERN.match(title):
        return canonical or title
    words = re.findall(r"[A-Za-z]{2,}", title)
    if canonical and (_SENTENCE_LIKE_PATTERN.match(title) or len(words) > 14 or len(words) < 2):
        return canonical
    return title


def _is_table_heavy_paragraph(text: str) -> bool:
    """Heuristic: table-like or number-dense paragraphs are expected in statements."""
    if not text.strip():
        return False
    if text.count("|") >= 2:
        return True
    tokens = re.findall(r"\S+", text)
    if not tokens:
        return False
    numeric_like = sum(1 for t in tokens if re.fullmatch(r"[\$€£]?\(?\d[\d,.\-%)]*", t))
    return (numeric_like / len(tokens)) >= 0.35


def _delta_text(pd: object) -> str:
    old_text = getattr(pd, "old_text", "") or ""
    new_text = getattr(pd, "new_text", "") or ""
    return f"{old_text}\n{new_text}".strip()


def _section_interest_weight(section_type: str) -> float:
    return _INTEREST_SECTION_WEIGHTS.get(section_type, 1.0)


def _strip_paragraph_deltas(result: DiffResult) -> DiffResult:
    """Return section-level metadata only (lighter payload)."""
    trimmed = result.model_copy(deep=True)
    for delta in trimmed.section_deltas:
        delta.paragraph_deltas = []
    return trimmed


def compute_interest_score(delta: SectionDelta) -> float:
    """Score how interesting a section change is for human review."""
    if delta.change_type == ChangeType.UNCHANGED:
        return 0.0

    score = 0.0
    if delta.paragraph_deltas:
        for pd in delta.paragraph_deltas:
            if pd.is_boilerplate:
                continue

            words = max(pd.old_word_count, pd.new_word_count)
            if words <= 0:
                continue

            if pd.change_type == ChangeType.ADDED:
                score += words * 1.5
            elif pd.change_type == ChangeType.REMOVED:
                score += words * 0.8
            elif pd.change_type == ChangeType.MODIFIED:
                similarity = max(0.0, min(1.0, pd.similarity))
                score += words * (1.0 - similarity)
    else:
        # Added/removed whole-section deltas don't have paragraph details.
        words = delta.paragraphs_added + delta.paragraphs_removed
        if delta.change_type == ChangeType.ADDED:
            score += words * 1.5
        elif delta.change_type == ChangeType.REMOVED:
            score += words * 0.8

    return score * _section_interest_weight(delta.section_type)


def _compute_section_intensity(delta: SectionDelta) -> float:
    """Compute change intensity for a section (0.0 = identical, 1.0 = fully rewritten).

    Weighted by word count so a 3-word boilerplate change counts less than a
    200-word risk factor rewrite. Falls back to paragraph count if word counts
    are unavailable.
    """
    if not delta.paragraph_deltas:
        total = (
            delta.paragraphs_unchanged
            + delta.paragraphs_modified
            + delta.paragraphs_added
            + delta.paragraphs_removed
        )
        if total == 0:
            return 0.0
        changed = delta.paragraphs_modified + delta.paragraphs_added + delta.paragraphs_removed
        return changed / total

    total_words = 0
    changed_words = 0.0
    for pd in delta.paragraph_deltas:
        words = max(pd.old_word_count, pd.new_word_count)
        if words == 0 or pd.is_boilerplate:
            continue
        total_words += words

        paragraph_weight = 1.0
        if delta.section_type == "financial_statement":
            paragraph_weight *= _FINANCIAL_SECTION_BASE_DAMPING
            if _is_table_heavy_paragraph(_delta_text(pd)):
                paragraph_weight *= _FINANCIAL_TABLE_DAMPING

        if pd.change_type in {ChangeType.ADDED, ChangeType.REMOVED}:
            changed_words += words * paragraph_weight
        elif pd.change_type == ChangeType.MODIFIED:
            similarity = max(0.0, min(1.0, pd.similarity))
            changed_words += words * (1.0 - similarity) * paragraph_weight

    if total_words == 0:
        return 0.0
    return changed_words / total_words


def _reduced_section_key(section_id: str) -> str:
    """Strip form+part prefix for fallback matching.

    '10k_partii_item7_managements_discussion' -> 'item7_managements_discussion'
    """
    return _FORM_PART_PREFIX.sub("", section_id)


def diff_filings(
    before_dir: Path,
    after_dir: Path,
    detail: str = "full",
) -> DiffResult:
    """Diff two filing packs by comparing their sections.

    Uses stable section IDs for matching and SHA256 hashes from manifests
    for instant unchanged detection.

    Args:
        before_dir: Path to the earlier filing pack
        after_dir: Path to the later filing pack
        detail: "full" for paragraph deltas, "sections" for section-only payload

    Returns:
        DiffResult with section-level and paragraph-level changes
    """
    if detail not in {"full", "sections"}:
        raise ValueError("detail must be either 'full' or 'sections'")

    before_manifest = _load_manifest(before_dir)
    after_manifest = _load_manifest(after_dir)
    key = _cache_key(before_manifest, after_manifest)
    cached = _get_cached_diff(key)
    if cached is not None:
        return cached if detail == "full" else _strip_paragraph_deltas(cached)

    before_filing = before_manifest.get("filing", {})
    after_filing = after_manifest.get("filing", {})

    # Build section lookup maps: id -> {path, sha256, title}
    before_sections = {s["id"]: s for s in before_manifest.get("sections", [])}
    after_sections = {s["id"]: s for s in after_manifest.get("sections", [])}

    # --- Pass 1: exact ID matching ---
    exact_both = sorted(set(before_sections.keys()) & set(after_sections.keys()))
    exact_matched_before: set[str] = set(exact_both)
    exact_matched_after: set[str] = set(exact_both)
    section_pairs: list[tuple[str, dict | None, dict | None]] = [
        (sid, before_sections[sid], after_sections[sid]) for sid in exact_both
    ]

    # --- Pass 2: fallback matching by item+slug (strip part prefix) ---
    remaining_before = {
        sid: sec for sid, sec in before_sections.items() if sid not in exact_matched_before
    }
    remaining_after = {
        sid: sec for sid, sec in after_sections.items() if sid not in exact_matched_after
    }

    before_by_reduced: dict[str, list[str]] = {}
    for sid in remaining_before:
        key_r = _reduced_section_key(sid)
        before_by_reduced.setdefault(key_r, []).append(sid)

    after_by_reduced: dict[str, list[str]] = {}
    for sid in remaining_after:
        key_r = _reduced_section_key(sid)
        after_by_reduced.setdefault(key_r, []).append(sid)

    fallback_matched_before: set[str] = set()
    fallback_matched_after: set[str] = set()

    for key_r in set(before_by_reduced.keys()) & set(after_by_reduced.keys()):
        before_ids = before_by_reduced[key_r]
        after_ids = after_by_reduced[key_r]
        if len(before_ids) == 1 and len(after_ids) == 1:
            b_sid = before_ids[0]
            a_sid = after_ids[0]
            section_pairs.append((a_sid, before_sections[b_sid], after_sections[a_sid]))
            fallback_matched_before.add(b_sid)
            fallback_matched_after.add(a_sid)

    # --- Pass 3: remaining unmatched are genuinely added/removed ---
    for sid in sorted(remaining_before):
        if sid not in fallback_matched_before:
            section_pairs.append((sid, before_sections[sid], None))

    for sid in sorted(remaining_after):
        if sid not in fallback_matched_after:
            section_pairs.append((sid, None, after_sections[sid]))

    # --- Process all pairs ---
    section_deltas: list[SectionDelta] = []

    for sid, before_sec, after_sec in section_pairs:
        section_type = _classify_section(sid)

        if before_sec and not after_sec:
            old_text = _read_section(before_dir, before_sec["path"])
            para_count = len([p for p in old_text.split("\n\n") if p.strip()])
            words_removed = len(old_text.split())
            delta = SectionDelta(
                section_id=sid,
                title=_display_title(sid, before_sec.get("title", sid)),
                change_type=ChangeType.REMOVED,
                section_type=section_type,
                paragraphs_removed=para_count,
                change_intensity=0.4 if section_type == "financial_statement" else 1.0,
            )
            delta.interest_score = words_removed * 0.8 * _section_interest_weight(section_type)
            section_deltas.append(delta)
            continue

        if not before_sec and after_sec:
            new_text = _read_section(after_dir, after_sec["path"])
            para_count = len([p for p in new_text.split("\n\n") if p.strip()])
            words_added = len(new_text.split())
            delta = SectionDelta(
                section_id=sid,
                title=_display_title(sid, after_sec.get("title", sid)),
                change_type=ChangeType.ADDED,
                section_type=section_type,
                paragraphs_added=para_count,
                change_intensity=0.4 if section_type == "financial_statement" else 1.0,
            )
            delta.interest_score = words_added * 1.5 * _section_interest_weight(section_type)
            section_deltas.append(delta)
            continue

        # Both exist: check SHA256 for instant unchanged detection
        if before_sec["sha256"] == after_sec["sha256"]:
            section_deltas.append(
                SectionDelta(
                    section_id=sid,
                    title=_display_title(sid, after_sec.get("title", sid)),
                    change_type=ChangeType.UNCHANGED,
                    section_type=section_type,
                    change_intensity=0.0,
                )
            )
            continue

        # Sections differ: do paragraph-level diff
        old_text = _read_section(before_dir, before_sec["path"])
        new_text = _read_section(after_dir, after_sec["path"])
        para_deltas = diff_paragraphs(old_text, new_text)

        delta = SectionDelta(
            section_id=sid,
            title=_display_title(sid, after_sec.get("title", sid)),
            change_type=ChangeType.MODIFIED,
            section_type=section_type,
            paragraphs_added=sum(1 for d in para_deltas if d.change_type == ChangeType.ADDED),
            paragraphs_removed=sum(
                1 for d in para_deltas if d.change_type == ChangeType.REMOVED
            ),
            paragraphs_modified=sum(
                1 for d in para_deltas if d.change_type == ChangeType.MODIFIED
            ),
            paragraphs_unchanged=sum(
                1 for d in para_deltas if d.change_type == ChangeType.UNCHANGED
            ),
            paragraph_deltas=para_deltas,
        )
        delta.change_intensity = _compute_section_intensity(delta)
        delta.interest_score = compute_interest_score(delta)
        section_deltas.append(delta)

    # --- Post-processing: suppress noise section types ---
    section_deltas = [
        d for d in section_deltas if d.section_type not in _SUPPRESSED_SECTION_TYPES
    ]

    # --- Post-processing: make boilerplate paragraphs invisible ---
    for delta in section_deltas:
        if delta.paragraph_deltas:
            visible = [pd for pd in delta.paragraph_deltas if not pd.is_boilerplate]
            delta.paragraph_deltas = visible
            delta.paragraphs_added = sum(
                1 for d in visible if d.change_type == ChangeType.ADDED
            )
            delta.paragraphs_removed = sum(
                1 for d in visible if d.change_type == ChangeType.REMOVED
            )
            delta.paragraphs_modified = sum(
                1 for d in visible if d.change_type == ChangeType.MODIFIED
            )
            delta.paragraphs_unchanged = sum(
                1 for d in visible if d.change_type == ChangeType.UNCHANGED
            )

    # Recount section-level stats from non-suppressed deltas
    n_unchanged = sum(1 for d in section_deltas if d.change_type == ChangeType.UNCHANGED)
    n_modified = sum(1 for d in section_deltas if d.change_type == ChangeType.MODIFIED)
    n_added = sum(1 for d in section_deltas if d.change_type == ChangeType.ADDED)
    n_removed = sum(1 for d in section_deltas if d.change_type == ChangeType.REMOVED)

    # Highest-signal deltas first
    section_deltas.sort(key=lambda d: (-d.interest_score, -d.change_intensity, d.section_id))

    # Compute overall change intensity from non-suppressed sections
    total_sections = len(section_deltas)
    if total_sections > 0:
        weighted = sum(d.change_intensity for d in section_deltas)
        overall_intensity = weighted / total_sections
    else:
        overall_intensity = 0.0

    result = DiffResult(
        company=after_filing.get("company_name", before_filing.get("company_name", "")),
        form_type=after_filing.get("form_type", before_filing.get("form_type", "")),
        before_accession=before_filing.get("accession", ""),
        before_date=before_filing.get("filing_date", ""),
        after_accession=after_filing.get("accession", ""),
        after_date=after_filing.get("filing_date", ""),
        sections_unchanged=n_unchanged,
        sections_modified=n_modified,
        sections_added=n_added,
        sections_removed=n_removed,
        overall_change_intensity=overall_intensity,
        section_deltas=section_deltas,
    )
    _cache_diff(key, result)
    return result if detail == "full" else _strip_paragraph_deltas(result)
