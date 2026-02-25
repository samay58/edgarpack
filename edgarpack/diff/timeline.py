"""Chronological section history across filings."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from .models import ChangeType, SectionDelta
from .section_diff import _compute_section_intensity
from .text_diff import diff_paragraphs


class TimelineEntry(BaseModel):
    """A single point in a section's timeline."""

    accession: str
    filing_date: str
    section_found: bool = True
    delta: SectionDelta | None = None
    content_preview: str = ""
    tokens: int = 0


def _load_pack_manifest(pack_dir: Path) -> dict:
    manifest_path = pack_dir / "manifest.json"
    if not manifest_path.exists():
        return {}
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _read_section_text(pack_dir: Path, section_path: str) -> str:
    full_path = pack_dir / section_path
    if not full_path.exists():
        return ""
    return full_path.read_text(encoding="utf-8")


def build_timeline(
    pack_dirs: list[Path],
    section_id: str,
) -> list[TimelineEntry]:
    """Build a chronological timeline of a section across multiple filings.

    Args:
        pack_dirs: List of pack directories, sorted by filing date (ascending)
        section_id: The stable section ID to track

    Returns:
        List of TimelineEntry objects showing evolution
    """
    entries: list[TimelineEntry] = []
    prev_text: str | None = None

    for pack_dir in pack_dirs:
        manifest = _load_pack_manifest(pack_dir)
        if not manifest:
            continue

        filing = manifest.get("filing", {})
        accession = filing.get("accession", "")
        filing_date = filing.get("filing_date", "")

        # Find the target section in this filing
        sections = manifest.get("sections", [])
        target_section = None
        for s in sections:
            if s["id"] == section_id:
                target_section = s
                break

        if target_section is None:
            entries.append(
                TimelineEntry(
                    accession=accession,
                    filing_date=filing_date,
                    section_found=False,
                )
            )
            prev_text = None
            continue

        current_text = _read_section_text(pack_dir, target_section["path"])
        tokens = target_section.get("tokens_approx", 0)
        preview = current_text[:500] + "..." if len(current_text) > 500 else current_text

        delta: SectionDelta | None = None
        if prev_text is not None:
            # Compare with previous version
            para_deltas = diff_paragraphs(prev_text, current_text)
            added = sum(1 for d in para_deltas if d.change_type == ChangeType.ADDED)
            removed = sum(1 for d in para_deltas if d.change_type == ChangeType.REMOVED)
            modified = sum(1 for d in para_deltas if d.change_type == ChangeType.MODIFIED)
            unchanged = sum(1 for d in para_deltas if d.change_type == ChangeType.UNCHANGED)

            if added == 0 and removed == 0 and modified == 0:
                change_type = ChangeType.UNCHANGED
            else:
                change_type = ChangeType.MODIFIED

            delta = SectionDelta(
                section_id=section_id,
                title=target_section.get("title", section_id),
                change_type=change_type,
                paragraphs_added=added,
                paragraphs_removed=removed,
                paragraphs_modified=modified,
                paragraphs_unchanged=unchanged,
                paragraph_deltas=para_deltas,
            )
            delta.change_intensity = _compute_section_intensity(delta)

        entries.append(
            TimelineEntry(
                accession=accession,
                filing_date=filing_date,
                section_found=True,
                delta=delta,
                content_preview=preview,
                tokens=tokens,
            )
        )
        prev_text = current_text

    return entries
