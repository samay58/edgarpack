"""New disclosure detection: find paragraphs with no close match in prior filings."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from ..diff.text_diff import _jaccard, _split_paragraphs


class NewDisclosure(BaseModel):
    """A newly disclosed paragraph not found in prior filings."""

    section_id: str
    section_title: str
    paragraph_text: str
    max_prior_similarity: float
    filing_date: str
    accession: str


def detect_new_disclosures(
    current_pack_dir: Path,
    prior_pack_dirs: list[Path],
    similarity_threshold: float = 0.3,
) -> list[NewDisclosure]:
    """Compare latest filing against all priors to find genuinely new content.

    A paragraph is "new" if its maximum Jaccard similarity to any paragraph
    in any prior filing of the same section is below the threshold.

    Args:
        current_pack_dir: Path to the latest filing pack
        prior_pack_dirs: Paths to all prior filing packs (same company/form)
        similarity_threshold: Below this = new disclosure (default 0.3)

    Returns:
        List of NewDisclosure objects sorted by section
    """
    current_manifest_path = current_pack_dir / "manifest.json"
    if not current_manifest_path.exists():
        return []

    current_manifest = json.loads(current_manifest_path.read_text(encoding="utf-8"))
    filing = current_manifest.get("filing", {})

    # Build corpus of all prior paragraphs per section
    prior_paras: dict[str, list[str]] = {}
    for prior_dir in prior_pack_dirs:
        prior_manifest_path = prior_dir / "manifest.json"
        if not prior_manifest_path.exists():
            continue
        prior_manifest = json.loads(prior_manifest_path.read_text(encoding="utf-8"))
        for section in prior_manifest.get("sections", []):
            sid = section["id"]
            section_path = prior_dir / section["path"]
            if not section_path.exists():
                continue
            text = section_path.read_text(encoding="utf-8")
            paras = _split_paragraphs(text)
            if sid not in prior_paras:
                prior_paras[sid] = []
            prior_paras[sid].extend(paras)

    disclosures: list[NewDisclosure] = []

    for section in current_manifest.get("sections", []):
        sid = section["id"]
        section_path = current_pack_dir / section["path"]
        if not section_path.exists():
            continue

        text = section_path.read_text(encoding="utf-8")
        current_paras = _split_paragraphs(text)
        prior_section_paras = prior_paras.get(sid, [])

        if not prior_section_paras:
            # Entire section is new
            for para in current_paras:
                if len(para.split()) >= 10:  # Skip very short paragraphs
                    disclosures.append(
                        NewDisclosure(
                            section_id=sid,
                            section_title=section.get("title", sid),
                            paragraph_text=para,
                            max_prior_similarity=0.0,
                            filing_date=filing.get("filing_date", ""),
                            accession=filing.get("accession", ""),
                        )
                    )
            continue

        for para in current_paras:
            if len(para.split()) < 10:
                continue

            max_sim = max(_jaccard(para, pp) for pp in prior_section_paras)

            if max_sim < similarity_threshold:
                disclosures.append(
                    NewDisclosure(
                        section_id=sid,
                        section_title=section.get("title", sid),
                        paragraph_text=para,
                        max_prior_similarity=max_sim,
                        filing_date=filing.get("filing_date", ""),
                        accession=filing.get("accession", ""),
                    )
                )

    return disclosures
