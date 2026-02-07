"""Generate llms.txt files for filings and companies."""

from pathlib import Path
from typing import Any


def generate_llms_txt(
    filing_meta: Any,  # FilingMeta
    sections: list[Any],  # Section
    has_chunks: bool = False,
    has_xbrl: bool = False,
) -> str:
    """Generate filing-level llms.txt content.

    Args:
        filing_meta: Filing metadata
        sections: List of sections
        has_chunks: Whether chunks.ndjson is included
        has_xbrl: Whether xbrl.json is included

    Returns:
        llms.txt content as string
    """
    lines = []

    # Header
    lines.append(
        f"# {filing_meta.company_name} {filing_meta.form_type} "
        f"({filing_meta.filing_date.isoformat()})"
    )
    lines.append("")
    lines.append(f"> CIK: {filing_meta.cik} | Accession: {filing_meta.accession}")
    lines.append("")

    # Filing Pack section
    lines.append("## Filing Pack")
    lines.append("")
    lines.append("- [Full Filing](filing.full.md)")
    lines.append("- [Manifest](manifest.json)")
    lines.append("")

    # Sections
    lines.append("## Sections")
    lines.append("")
    for section in sections:
        section_path = f"sections/{section.id}.md"
        lines.append(f"- [{section.title}]({section_path})")
    lines.append("")

    # Optional artifacts
    if has_chunks or has_xbrl:
        lines.append("## Optional")
        lines.append("")
        if has_chunks:
            lines.append("- [Chunks](optional/chunks.ndjson)")
        if has_xbrl:
            lines.append("- [XBRL Data](optional/xbrl.json)")
        lines.append("")

    return "\n".join(lines)


def generate_company_llms_txt(
    company_name: str,
    cik: str,
    filings: list[dict[str, Any]],
) -> str:
    """Generate company-level llms.txt listing all processed filings.

    Args:
        company_name: Company name
        cik: CIK number
        filings: List of filing info dicts with keys:
            - form_type
            - filing_date (as string)
            - accession

    Returns:
        llms.txt content as string
    """
    lines = []

    # Header
    lines.append(f"# {company_name} SEC Filings")
    lines.append("")
    lines.append(f"> CIK: {cik}")
    lines.append("")

    # Recent Filings
    lines.append("## Recent Filings")
    lines.append("")

    for filing in filings:
        form_type = filing.get("form_type", "Unknown")
        filing_date = filing.get("filing_date", "Unknown")
        accession = filing.get("accession", "")

        lines.append(f"- [{form_type} {filing_date}]({accession}/llms.txt)")

    lines.append("")

    return "\n".join(lines)


def write_llms_txt(content: str, output_dir: Path) -> Path:
    """Write llms.txt to file.

    Args:
        content: llms.txt content
        output_dir: Directory to write to

    Returns:
        Path to written file
    """
    path = output_dir / "llms.txt"
    path.write_text(content, encoding="utf-8")
    return path


def scan_filings_for_company_llms(cik_dir: Path) -> list[dict[str, Any]]:
    """Scan a CIK directory for processed filings.

    Args:
        cik_dir: Directory containing filing subdirectories

    Returns:
        List of filing info dicts sorted by date (newest first)
    """
    filings = []

    for subdir in cik_dir.iterdir():
        if not subdir.is_dir():
            continue

        manifest_path = subdir / "manifest.json"
        if not manifest_path.exists():
            continue

        try:
            import json

            manifest = json.loads(manifest_path.read_text())
            filing_info = manifest.get("filing", {})

            filings.append(
                {
                    "form_type": filing_info.get("form_type", "Unknown"),
                    "filing_date": filing_info.get("filing_date", "Unknown"),
                    "accession": subdir.name,
                }
            )
        except Exception:
            continue

    # Sort by date, newest first
    filings.sort(key=lambda f: f.get("filing_date", ""), reverse=True)

    return filings
