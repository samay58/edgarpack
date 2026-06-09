"""SEC submissions API for discovering filings.

SEC splits high-volume filers' submission histories across multiple JSON
files. `CIK<cik>.json` holds the most recent window (typically the last
~1,000 filings) under `filings.recent`, and references older paginated
files in `filings.files[]`. For heavy filers like META, the recent window
can cap out in weeks, so accessions older than that are only reachable by
fetching the referenced pagination files.

This module transparently paginates across both when an accession or form
match is not present in `recent`. See `_iter_submission_pages`.
"""

import json
import logging
from collections.abc import AsyncIterator
from datetime import date
from typing import Any

from pydantic import BaseModel

from ..config import CACHE_DIR, SEC_DATA_BASE
from .cache import DiskCache
from .client import get_client

logger = logging.getLogger(__name__)

# Older submission pagination files are immutable (they only contain filings
# from a past date range). Cache them aggressively.
_OLDER_PAGE_TTL_SECONDS = 30 * 24 * 3600  # 30 days


class FilingMeta(BaseModel):
    """Metadata for a single SEC filing."""

    cik: str
    accession: str  # formatted: 0000320193-24-000123
    form_type: str
    filing_date: date
    primary_document: str
    company_name: str
    # SEC submissions API returns a distinct reportDate (the fiscal period
    # this filing covers). Optional so older FilingMeta instances constructed
    # without it still validate.
    period_of_report: date | None = None

    @property
    def accession_nodash(self) -> str:
        """Accession number without dashes (for URL construction)."""
        return self.accession.replace("-", "")


REGISTRATION_FORMS: tuple[str, ...] = (
    "S-1",
    "S-1/A",
    "F-1",
    "F-1/A",
    "424B1",
    "424B2",
    "424B3",
    "424B4",
    "424B5",
    "FWP",
)

REGISTRATION_SENTINEL: str = "__REGISTRATION__"
"""Form-counts dict key signaling the full registration-class family budget.

Shared by UniverseConfig.form_counts (producer) and the harvest planner
(consumer, which expands the sentinel via _list_registration_filings).
"""


def normalize_form_type(form_type: str) -> str:
    """Normalize form type for matching SEC submissions."""
    if not form_type:
        return ""
    form = form_type.strip().upper().replace(" ", "")
    amended = form.endswith("/A")
    if amended:
        form = form[:-2]
    if form in {"10K", "10-K"}:
        base = "10-K"
    elif form in {"10Q", "10-Q"}:
        base = "10-Q"
    elif form in {"8K", "8-K"}:
        base = "8-K"
    elif form in {"S1", "S-1"}:
        base = "S-1"
    elif form in {"F1", "F-1"}:
        base = "F-1"
    elif form == "FWP":
        base = "FWP"
    elif form.startswith("424B") and len(form) == 5 and form[-1].isdigit():
        base = form
    else:
        base = form
    return f"{base}/A" if amended else base


def is_registration_form(form_type: str) -> bool:
    """Return True when the form belongs to the S-1 / pre-IPO family.

    The family covers S-1, S-1/A, F-1, F-1/A, 424B1-5, and FWP. Used as a
    single guard across kpi_discover, periods, and diff/timeline so that
    registration-class filings do not get pulled into 10-K/10-Q logic.
    """
    if not form_type:
        return False
    normalized = normalize_form_type(form_type)
    return normalized in REGISTRATION_FORMS


def normalize_cik(cik: str) -> str:
    """Normalize CIK to 10-digit zero-padded format."""
    return cik.lstrip("0").zfill(10)


def _parse_report_date(report_dates: list[str], idx: int) -> date | None:
    """Safely parse a SEC reportDate string at a given index.

    Returns None if the index is out of range, the entry is empty, or the
    value is not a valid ISO date. The SEC submissions feed usually fills
    reportDate for 10-K/10-Q but may be blank for amendments or exhibits.
    """
    if idx < 0 or idx >= len(report_dates):
        return None
    raw = (report_dates[idx] or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


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
            try:
                parsed = json.loads(cached)
                if not isinstance(parsed, dict):
                    raise ValueError("cached submissions payload was not an object")
            except (json.JSONDecodeError, ValueError):
                # Corrupt cache entries refetch instead of erroring forever.
                cache.clear(url)
            else:
                return parsed

    client = await get_client()
    data, headers = await client.fetch_json(url)

    # Cache the response
    cache.put(url, json.dumps(data).encode(), headers)

    return data


async def _fetch_submissions_page(name: str, force: bool = False) -> dict[str, Any]:
    """Fetch an older submissions pagination file from SEC.

    These files are referenced in `data['filings']['files'][]` on the main
    submissions.json response. They cover closed historical date ranges and
    are therefore immutable. We cache them with a long TTL to avoid
    re-fetching on every historical lookup.

    Returns the flat columnar structure (accessionNumber, form, filingDate,
    etc. at the top level; not nested under a `filings.recent` key).
    """
    url = f"{SEC_DATA_BASE}/submissions/{name}"
    cache = DiskCache(CACHE_DIR)

    if not force:
        cached = cache.get(url, max_age_seconds=_OLDER_PAGE_TTL_SECONDS)
        if cached is not None:
            try:
                parsed = json.loads(cached)
                if not isinstance(parsed, dict):
                    raise ValueError("cached submissions page was not an object")
            except (json.JSONDecodeError, ValueError):
                cache.clear(url)
            else:
                return parsed

    client = await get_client()
    data, headers = await client.fetch_json(url)

    cache.put(url, json.dumps(data).encode(), headers)

    return data


async def _iter_submission_pages(
    data: dict[str, Any],
    force: bool = False,
) -> AsyncIterator[dict[str, Any]]:
    """Yield columnar filing pages for a filer, newest-first.

    First yields `data['filings']['recent']`. Then, if the filer has older
    paginated files, fetches and yields each older page in the order SEC
    lists them (which is newest-historical-range first). Older pages return
    the columnar keys at the top level.

    If fetching an older page fails (network error, 404), a warning is
    logged and iteration continues with remaining pages. Callers that need
    a guaranteed hit should treat "iterator exhausted without match" as the
    not-found signal, not assume every page was reachable.

    Yielded dicts always have the same columnar shape:
        {
            "form": [...],
            "accessionNumber": [...],
            "filingDate": [...],
            "reportDate": [...],
            "primaryDocument": [...],
            ...
        }
    """
    recent = data.get("filings", {}).get("recent", {}) or {}
    yield recent

    older_files = data.get("filings", {}).get("files", []) or []
    for entry in older_files:
        name = entry.get("name")
        if not name:
            continue
        try:
            page = await _fetch_submissions_page(name, force=force)
        # Log and continue on any fetch fault.
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to fetch older submissions page %s: %s. "
                "Older filings in that range will not be discoverable.",
                name,
                exc,
            )
            continue
        yield page


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
    report_dates = filings.get("reportDate", [])
    docs = filings.get("primaryDocument", [])

    # Find matching filings
    target_form = normalize_form_type(form_type)
    for i, form in enumerate(forms):
        if normalize_form_type(form) == target_form:
            return FilingMeta(
                cik=cik,
                accession=accessions[i],
                form_type=form,
                filing_date=date.fromisoformat(dates[i]),
                primary_document=docs[i],
                company_name=company_name,
                period_of_report=_parse_report_date(report_dates, i),
            )

    raise ValueError(f"No {form_type} filing found for CIK {cik}")


async def get_filing_by_accession(
    cik: str,
    accession: str,
    force: bool = False,
) -> FilingMeta:
    """Get filing metadata by accession number.

    Searches the filer's recent window first, then paginates through older
    submission files if needed. This lets callers reach filings that have
    aged out of the recent window, which is common for high-volume filers
    like META whose recent-window boundary is measured in weeks.

    Args:
        cik: CIK number
        accession: Accession number (with or without dashes)
        force: Bypass cache (applies to both the main submissions file and
            any older pagination files consulted)

    Returns:
        FilingMeta for the specified filing

    Raises:
        ValueError: If filing not found across recent + all older pages.
    """
    data = await fetch_submissions(cik, force=force)

    cik = normalize_cik(cik)
    company_name = data.get("name", f"CIK {cik}")

    # Normalize accession format
    accession = accession.replace("-", "")
    if len(accession) == 18:
        # Convert to standard format: XXXXXXXXXX-XX-XXXXXX
        accession = f"{accession[:10]}-{accession[10:12]}-{accession[12:]}"

    async for page in _iter_submission_pages(data, force=force):
        forms = page.get("form", [])
        accessions = page.get("accessionNumber", [])
        dates = page.get("filingDate", [])
        report_dates = page.get("reportDate", [])
        docs = page.get("primaryDocument", [])

        for i, acc in enumerate(accessions):
            if acc == accession:
                return FilingMeta(
                    cik=cik,
                    accession=acc,
                    form_type=forms[i],
                    filing_date=date.fromisoformat(dates[i]),
                    primary_document=docs[i],
                    company_name=company_name,
                    period_of_report=_parse_report_date(report_dates, i),
                )

    raise ValueError(f"Filing {accession} not found for CIK {cik}")


async def list_filings(
    cik: str,
    form_type: str | None = None,
    limit: int = 10,
    force: bool = False,
) -> list[FilingMeta]:
    """List filings for a company, newest first.

    Starts with the recent window, then paginates through older submission
    files if the limit has not yet been reached. For high-volume filers,
    this is how a form filter like `10-K` still surfaces deep history even
    when the recent window is saturated with Form 4 / 144 / 8-K noise.

    Args:
        cik: CIK number
        form_type: Optional form type filter (e.g. "10-K", "10-Q").
        limit: Maximum number of filings to return.
        force: Bypass cache (applies to both the main submissions file and
            any older pagination files consulted).

    Returns:
        List of FilingMeta objects, newest first, up to `limit` entries.
    """
    data = await fetch_submissions(cik, force=force)

    cik = normalize_cik(cik)
    company_name = data.get("name", f"CIK {cik}")

    results: list[FilingMeta] = []
    target_form = normalize_form_type(form_type) if form_type else None

    async for page in _iter_submission_pages(data, force=force):
        forms = page.get("form", [])
        accessions = page.get("accessionNumber", [])
        dates = page.get("filingDate", [])
        report_dates = page.get("reportDate", [])
        docs = page.get("primaryDocument", [])

        for i, form in enumerate(forms):
            if target_form is None or normalize_form_type(form) == target_form:
                results.append(
                    FilingMeta(
                        cik=cik,
                        accession=accessions[i],
                        form_type=form,
                        filing_date=date.fromisoformat(dates[i]),
                        primary_document=docs[i],
                        company_name=company_name,
                        period_of_report=_parse_report_date(report_dates, i),
                    )
                )
                if len(results) >= limit:
                    return results

    return results
