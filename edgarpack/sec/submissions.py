"""SEC submissions API for discovering filings."""

from datetime import date
from typing import Any

from pydantic import BaseModel

from ..config import CACHE_DIR, SEC_DATA_BASE
from .cache import DiskCache
from .client import get_client


class FilingMeta(BaseModel):
    """Metadata for a single SEC filing."""

    cik: str
    accession: str  # formatted: 0000320193-24-000123
    form_type: str
    filing_date: date
    primary_document: str
    company_name: str

    @property
    def accession_nodash(self) -> str:
        """Accession number without dashes (for URL construction)."""
        return self.accession.replace("-", "")


def normalize_cik(cik: str) -> str:
    """Normalize CIK to 10-digit zero-padded format."""
    return cik.lstrip("0").zfill(10)


async def fetch_submissions(cik: str, force: bool = False) -> dict[str, Any]:
    """Fetch company submissions JSON from SEC.

    Args:
        cik: CIK number (with or without leading zeros)
        force: Bypass cache

    Returns:
        Parsed submissions JSON
    """
    cik = normalize_cik(cik)
    url = f"{SEC_DATA_BASE}/submissions/CIK{cik}.json"

    cache = DiskCache(CACHE_DIR)

    # Use cached version if available and fresh (1 hour)
    if not force:
        cached = cache.get(url, max_age_seconds=3600)
        if cached is not None:
            import json
            return json.loads(cached)

    client = await get_client()
    data, headers = await client.fetch_json(url)

    # Cache the response
    import json
    cache.put(url, json.dumps(data).encode(), headers)

    return data


async def get_latest_filing(
    cik: str,
    form_type: str,
    force: bool = False,
) -> FilingMeta:
    """Get the latest filing of a specific type.

    Args:
        cik: CIK number
        form_type: Form type (10-K, 10-Q, 8-K)
        force: Bypass cache

    Returns:
        FilingMeta for the latest matching filing

    Raises:
        ValueError: If no matching filing found
    """
    data = await fetch_submissions(cik, force=force)

    cik = normalize_cik(cik)
    company_name = data.get("name", f"CIK {cik}")

    filings = data.get("filings", {}).get("recent", {})

    forms = filings.get("form", [])
    accessions = filings.get("accessionNumber", [])
    dates = filings.get("filingDate", [])
    docs = filings.get("primaryDocument", [])

    # Find matching filings
    for i, form in enumerate(forms):
        if form == form_type:
            return FilingMeta(
                cik=cik,
                accession=accessions[i],
                form_type=form_type,
                filing_date=date.fromisoformat(dates[i]),
                primary_document=docs[i],
                company_name=company_name,
            )

    raise ValueError(f"No {form_type} filing found for CIK {cik}")


async def get_filing_by_accession(
    cik: str,
    accession: str,
    force: bool = False,
) -> FilingMeta:
    """Get filing metadata by accession number.

    Args:
        cik: CIK number
        accession: Accession number (with or without dashes)
        force: Bypass cache

    Returns:
        FilingMeta for the specified filing

    Raises:
        ValueError: If filing not found
    """
    data = await fetch_submissions(cik, force=force)

    cik = normalize_cik(cik)
    company_name = data.get("name", f"CIK {cik}")

    # Normalize accession format
    accession = accession.replace("-", "")
    if len(accession) == 18:
        # Convert to standard format: XXXXXXXXXX-XX-XXXXXX
        accession = f"{accession[:10]}-{accession[10:12]}-{accession[12:]}"

    filings = data.get("filings", {}).get("recent", {})

    forms = filings.get("form", [])
    accessions = filings.get("accessionNumber", [])
    dates = filings.get("filingDate", [])
    docs = filings.get("primaryDocument", [])

    for i, acc in enumerate(accessions):
        if acc == accession:
            return FilingMeta(
                cik=cik,
                accession=acc,
                form_type=forms[i],
                filing_date=date.fromisoformat(dates[i]),
                primary_document=docs[i],
                company_name=company_name,
            )

    raise ValueError(f"Filing {accession} not found for CIK {cik}")


async def list_filings(
    cik: str,
    form_type: str | None = None,
    limit: int = 10,
    force: bool = False,
) -> list[FilingMeta]:
    """List recent filings for a company.

    Args:
        cik: CIK number
        form_type: Optional form type filter
        limit: Maximum number of filings to return
        force: Bypass cache

    Returns:
        List of FilingMeta objects
    """
    data = await fetch_submissions(cik, force=force)

    cik = normalize_cik(cik)
    company_name = data.get("name", f"CIK {cik}")

    filings = data.get("filings", {}).get("recent", {})

    forms = filings.get("form", [])
    accessions = filings.get("accessionNumber", [])
    dates = filings.get("filingDate", [])
    docs = filings.get("primaryDocument", [])

    results: list[FilingMeta] = []
    for i, form in enumerate(forms):
        if form_type is None or form == form_type:
            results.append(FilingMeta(
                cik=cik,
                accession=accessions[i],
                form_type=form,
                filing_date=date.fromisoformat(dates[i]),
                primary_document=docs[i],
                company_name=company_name,
            ))
            if len(results) >= limit:
                break

    return results
