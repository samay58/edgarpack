"""Manifest model and generation."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from ..config import PARSER_VERSION, SCHEMA_VERSION


class SourceInfo(BaseModel):
    """Information about the data source."""

    url: str
    fetched_at: datetime


class FilingInfo(BaseModel):
    """Filing metadata in manifest."""

    cik: str
    accession: str
    form_type: str
    filing_date: str
    company_name: str


class SectionInfo(BaseModel):
    """Section metadata in manifest."""

    id: str
    title: str
    path: str
    char_start: int
    char_end: int
    tokens_approx: int
    sha256: str


class Manifest(BaseModel):
    """Pack manifest with all metadata."""

    schema_version: int = SCHEMA_VERSION
    parser_version: str = PARSER_VERSION
    generated_at: datetime
    source: SourceInfo
    filing: FilingInfo
    sections: list[SectionInfo]
    artifacts: dict[str, str]  # path -> sha256
    warnings: list[str]
    tokens_total: int


def compute_sha256(content: bytes | str) -> str:
    """Compute SHA256 hash of content.

    Args:
        content: Bytes or string to hash

    Returns:
        Hex-encoded SHA256 hash
    """
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def create_manifest(
    filing_meta: Any,  # FilingMeta from submissions
    sections: list[Any],  # Section from sectionize
    artifacts: dict[str, str],  # path -> sha256
    warnings: list[str],
    tokens_total: int,
    source_url: str,
) -> Manifest:
    """Create a manifest for a filing pack.

    Args:
        filing_meta: Filing metadata from SEC
        sections: List of sections with content
        artifacts: Map of artifact paths to SHA256 hashes
        warnings: List of warning messages
        tokens_total: Total token count
        source_url: URL of the filing

    Returns:
        Populated Manifest object
    """
    from ..parse.tokenize import count_tokens

    section_infos = []
    for section in sections:
        section_path = f"sections/{section.id}.md"
        section_hash = compute_sha256(section.content)

        section_infos.append(
            SectionInfo(
                id=section.id,
                title=section.title,
                path=section_path,
                char_start=section.char_start,
                char_end=section.char_end,
                tokens_approx=count_tokens(section.content),
                sha256=section_hash,
            )
        )

    # Determinism: use a stable timestamp derived from the filing date.
    stable_at = datetime(
        filing_meta.filing_date.year,
        filing_meta.filing_date.month,
        filing_meta.filing_date.day,
        tzinfo=UTC,
    )

    return Manifest(
        generated_at=stable_at,
        source=SourceInfo(
            url=source_url,
            fetched_at=stable_at,
        ),
        filing=FilingInfo(
            cik=filing_meta.cik,
            accession=filing_meta.accession,
            form_type=filing_meta.form_type,
            filing_date=filing_meta.filing_date.isoformat(),
            company_name=filing_meta.company_name,
        ),
        sections=section_infos,
        artifacts=artifacts,
        warnings=warnings,
        tokens_total=tokens_total,
    )


def write_manifest(manifest: Manifest, output_dir: Path) -> Path:
    """Write manifest to JSON file.

    Args:
        manifest: Manifest object
        output_dir: Directory to write to

    Returns:
        Path to written manifest file
    """
    manifest_path = output_dir / "manifest.json"
    payload = manifest.model_dump(mode="json")
    manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest_path
