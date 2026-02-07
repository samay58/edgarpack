"""Core pack builder orchestrating the full pipeline."""

import json
import shutil
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from ..config import SEC_ARCHIVES_BASE
from ..parse.html_clean import clean_html
from ..parse.ixbrl_strip import strip_ixbrl
from ..parse.md_render import render_markdown
from ..parse.semantic_html import reduce_to_semantic
from ..parse.sectionize import Section, sectionize
from ..parse.tokenize import count_tokens, has_tiktoken
from ..sec.archives import fetch_filing_html
from ..sec.submissions import FilingMeta, get_filing_by_accession, get_latest_filing
from ..sec.xbrl import fetch_xbrl_facts
from .chunks import generate_chunks, write_chunks_ndjson
from .llms_txt import generate_llms_txt, write_llms_txt
from .manifest import compute_sha256, create_manifest, write_manifest


class PackResult(BaseModel):
    """Result of building a pack."""

    model_config = {"arbitrary_types_allowed": True}

    output_dir: Path
    filing_meta: dict[str, Any]
    sections_count: int
    tokens_total: int
    warnings: list[str]
    artifacts: list[str]


async def build_pack(
    cik: str,
    accession: str | None = None,
    form_type: str | None = None,
    out_dir: Path = Path("."),
    with_chunks: bool = False,
    with_xbrl: bool = False,
    force: bool = False,
) -> PackResult:
    """Build a complete filing pack.

    Args:
        cik: CIK number
        accession: Specific accession number (optional)
        form_type: Form type for latest filing lookup
        out_dir: Output directory
        with_chunks: Generate chunks.ndjson
        with_xbrl: Generate xbrl.json
        force: Bypass cache

    Returns:
        PackResult with build info
    """
    warnings: list[str] = []
    artifacts: list[str] = []

    # Step 1: Resolve filing metadata
    if accession:
        meta = await get_filing_by_accession(cik, accession, force=force)
    elif form_type:
        meta = await get_latest_filing(cik, form_type, force=force)
    else:
        raise ValueError("Either accession or form_type must be provided")

    # Step 2: Create output directory structure
    pack_dir = out_dir / meta.cik / meta.accession
    legacy_pack_dir = out_dir / meta.cik / meta.accession_nodash
    sections_dir = pack_dir / "sections"

    # Check if already exists
    if pack_dir.exists() and not force:
        manifest_path = pack_dir / "manifest.json"
        if manifest_path.exists():
            # Already built, return existing result
            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
            return PackResult(
                output_dir=pack_dir,
                filing_meta=manifest_data.get("filing", {}),
                sections_count=len(manifest_data.get("sections", [])),
                tokens_total=manifest_data.get("tokens_total", 0),
                warnings=["Pack already exists, use --force to rebuild"],
                artifacts=list(manifest_data.get("artifacts", {}).keys()),
            )

    # Backward-compatible read: older versions used accession_nodash as directory name.
    if legacy_pack_dir.exists() and not pack_dir.exists() and not force:
        legacy_manifest = legacy_pack_dir / "manifest.json"
        if legacy_manifest.exists():
            manifest_data = json.loads(legacy_manifest.read_text(encoding="utf-8"))
            return PackResult(
                output_dir=legacy_pack_dir,
                filing_meta=manifest_data.get("filing", {}),
                sections_count=len(manifest_data.get("sections", [])),
                tokens_total=manifest_data.get("tokens_total", 0),
                warnings=["Pack already exists (legacy layout), use --force to rebuild"],
                artifacts=list(manifest_data.get("artifacts", {}).keys()),
            )

    if pack_dir.exists() and force:
        shutil.rmtree(pack_dir)

    pack_dir.mkdir(parents=True, exist_ok=True)
    sections_dir.mkdir(exist_ok=True)

    # Step 3: Fetch HTML files
    html_files = await fetch_filing_html(meta, force=force)

    if not html_files:
        raise ValueError(f"No HTML files found for filing {meta.accession}")

    # Step 4: Process HTML to markdown
    # Concatenate all HTML files (primary first)
    combined_parts: list[str] = []
    for filename, content in html_files:
        try:
            decoded = content.decode("utf-8")
        except UnicodeDecodeError:
            decoded = content.decode("latin-1")
        combined_parts.append(decoded)
    combined_html = "\n".join(combined_parts)

    # Pipeline: strip iXBRL -> clean HTML -> render markdown
    html_stripped = strip_ixbrl(combined_html)
    html_cleaned = clean_html(html_stripped)
    base_url = f"{SEC_ARCHIVES_BASE}/{meta.cik}/{meta.accession_nodash}/"
    html_semantic = reduce_to_semantic(html_cleaned, base_url=base_url)
    markdown = render_markdown(html_semantic)

    # Step 5: Sectionize
    sections = sectionize(markdown, meta.form_type)

    # Collect section warnings
    for section in sections:
        warnings.extend(section.warnings)

    # Step 6: Write full filing markdown
    full_md_path = pack_dir / "filing.full.md"
    full_md_path.write_text(markdown, encoding="utf-8")
    artifacts.append("filing.full.md")

    # Step 7: Write section files
    for section in sections:
        section_path = sections_dir / f"{section.id}.md"
        section_path.write_text(section.content, encoding="utf-8")
        artifacts.append(f"sections/{section.id}.md")

    # Step 8: Optional - generate chunks
    if with_chunks:
        try:
            chunks = generate_chunks(sections)
            write_chunks_ndjson(chunks, pack_dir)
            artifacts.append("optional/chunks.ndjson")
        except Exception as e:
            warnings.append(f"Failed to generate chunks: {e}")

    # Step 9: Optional - fetch XBRL
    if with_xbrl:
        try:
            xbrl_data = await fetch_xbrl_facts(cik, meta.accession, force=force)
            if xbrl_data:
                optional_dir = pack_dir / "optional"
                optional_dir.mkdir(exist_ok=True)
                xbrl_path = optional_dir / "xbrl.json"
                xbrl_path.write_text(
                    json.dumps(xbrl_data, indent=2, sort_keys=True),
                    encoding="utf-8",
                )
                artifacts.append("optional/xbrl.json")
            else:
                warnings.append("No XBRL data available for this filing")
        except Exception as e:
            warnings.append(f"Failed to fetch XBRL data: {e}")

    # Step 10: Calculate total tokens
    tokens_total = count_tokens(markdown)
    if not has_tiktoken():
        warnings.append("Token counts are approximate (tiktoken not installed)")

    # Step 11: Write llms.txt (needed before hashing artifacts)
    llms_content = generate_llms_txt(
        meta,
        sections,
        has_chunks=with_chunks and "optional/chunks.ndjson" in artifacts,
        has_xbrl=with_xbrl and "optional/xbrl.json" in artifacts,
    )
    write_llms_txt(llms_content, pack_dir)
    artifacts.append("llms.txt")

    # Step 12: Compute hashes for all artifacts (excluding manifest.json itself)
    artifact_hashes: dict[str, str] = {}
    for artifact in sorted(set(artifacts)):
        artifact_path = pack_dir / artifact
        if artifact_path.exists() and artifact != "manifest.json":
            artifact_hashes[artifact] = compute_sha256(artifact_path.read_bytes())

    # Step 13: Write manifest (deterministic)
    source_url = f"{SEC_ARCHIVES_BASE}/{meta.cik}/{meta.accession_nodash}/{meta.primary_document}"
    manifest = create_manifest(
        filing_meta=meta,
        sections=sections,
        artifacts=artifact_hashes,
        warnings=warnings,
        tokens_total=tokens_total,
        source_url=source_url,
    )
    write_manifest(manifest, pack_dir)
    artifacts.append("manifest.json")

    return PackResult(
        output_dir=pack_dir,
        filing_meta={
            "cik": meta.cik,
            "accession": meta.accession,
            "form_type": meta.form_type,
            "filing_date": meta.filing_date.isoformat(),
            "company_name": meta.company_name,
        },
        sections_count=len(sections),
        tokens_total=tokens_total,
        warnings=warnings,
        artifacts=artifacts,
    )


async def build_company_llms(
    cik: str,
    out_dir: Path,
) -> Path:
    """Generate company-level llms.txt listing all processed filings.

    Args:
        cik: CIK number
        out_dir: Output directory containing filing packs

    Returns:
        Path to generated llms.txt
    """
    from ..sec.submissions import fetch_submissions, normalize_cik
    from .llms_txt import generate_company_llms_txt, scan_filings_for_company_llms

    cik = normalize_cik(cik)
    cik_dir = out_dir / cik

    if not cik_dir.exists():
        raise ValueError(f"No filings found for CIK {cik} in {out_dir}")

    # Get company name from submissions
    submissions = await fetch_submissions(cik)
    company_name = submissions.get("name", f"CIK {cik}")

    # Scan for existing filings
    filings = scan_filings_for_company_llms(cik_dir)

    if not filings:
        raise ValueError(f"No processed filings found in {cik_dir}")

    # Generate llms.txt
    content = generate_company_llms_txt(company_name, cik, filings)

    llms_path = cik_dir / "llms.txt"
    llms_path.write_text(content, encoding="utf-8")

    return llms_path
