"""Match sections by stable ID and detect changes between filings."""

from __future__ import annotations

import json
from pathlib import Path

from .models import ChangeType, DiffResult, SectionDelta
from .text_diff import diff_paragraphs


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
    changed_words = 0
    for pd in delta.paragraph_deltas:
        words = max(pd.old_word_count, pd.new_word_count)
        total_words += words
        if pd.change_type != ChangeType.UNCHANGED:
            changed_words += words

    if total_words == 0:
        return 0.0
    return changed_words / total_words


def diff_filings(
    before_dir: Path,
    after_dir: Path,
) -> DiffResult:
    """Diff two filing packs by comparing their sections.

    Uses stable section IDs for matching and SHA256 hashes from manifests
    for instant unchanged detection.

    Args:
        before_dir: Path to the earlier filing pack
        after_dir: Path to the later filing pack

    Returns:
        DiffResult with section-level and paragraph-level changes
    """
    before_manifest = _load_manifest(before_dir)
    after_manifest = _load_manifest(after_dir)

    before_filing = before_manifest.get("filing", {})
    after_filing = after_manifest.get("filing", {})

    # Build section lookup maps: id -> {path, sha256, title}
    before_sections = {s["id"]: s for s in before_manifest.get("sections", [])}
    after_sections = {s["id"]: s for s in after_manifest.get("sections", [])}

    all_section_ids = set(before_sections.keys()) | set(after_sections.keys())
    section_deltas: list[SectionDelta] = []
    n_unchanged = 0
    n_modified = 0
    n_added = 0
    n_removed = 0

    for sid in sorted(all_section_ids):
        before_sec = before_sections.get(sid)
        after_sec = after_sections.get(sid)

        if before_sec and not after_sec:
            # Section removed
            n_removed += 1
            old_text = _read_section(before_dir, before_sec["path"])
            para_count = len([p for p in old_text.split("\n\n") if p.strip()])
            section_deltas.append(
                SectionDelta(
                    section_id=sid,
                    title=before_sec.get("title", sid),
                    change_type=ChangeType.REMOVED,
                    paragraphs_removed=para_count,
                    change_intensity=1.0,
                )
            )
            continue

        if not before_sec and after_sec:
            # Section added
            n_added += 1
            new_text = _read_section(after_dir, after_sec["path"])
            para_count = len([p for p in new_text.split("\n\n") if p.strip()])
            section_deltas.append(
                SectionDelta(
                    section_id=sid,
                    title=after_sec.get("title", sid),
                    change_type=ChangeType.ADDED,
                    paragraphs_added=para_count,
                    change_intensity=1.0,
                )
            )
            continue

        # Both exist: check SHA256 for instant unchanged detection
        if before_sec["sha256"] == after_sec["sha256"]:
            n_unchanged += 1
            section_deltas.append(
                SectionDelta(
                    section_id=sid,
                    title=after_sec.get("title", sid),
                    change_type=ChangeType.UNCHANGED,
                    change_intensity=0.0,
                )
            )
            continue

        # Sections differ: do paragraph-level diff
        n_modified += 1
        old_text = _read_section(before_dir, before_sec["path"])
        new_text = _read_section(after_dir, after_sec["path"])

        para_deltas = diff_paragraphs(old_text, new_text)

        added = sum(1 for d in para_deltas if d.change_type == ChangeType.ADDED)
        removed = sum(1 for d in para_deltas if d.change_type == ChangeType.REMOVED)
        modified = sum(1 for d in para_deltas if d.change_type == ChangeType.MODIFIED)
        unchanged = sum(1 for d in para_deltas if d.change_type == ChangeType.UNCHANGED)

        delta = SectionDelta(
            section_id=sid,
            title=after_sec.get("title", sid),
            change_type=ChangeType.MODIFIED,
            paragraphs_added=added,
            paragraphs_removed=removed,
            paragraphs_modified=modified,
            paragraphs_unchanged=unchanged,
            paragraph_deltas=para_deltas,
        )
        delta.change_intensity = _compute_section_intensity(delta)
        section_deltas.append(delta)

    # Compute overall change intensity
    total_sections = len(all_section_ids)
    if total_sections > 0:
        weighted = sum(d.change_intensity for d in section_deltas)
        overall_intensity = weighted / total_sections
    else:
        overall_intensity = 0.0

    return DiffResult(
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
