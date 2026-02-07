"""SEC EDGAR Archives file listing and retrieval."""

import asyncio
import re
from typing import Any

from ..config import CACHE_DIR, SEC_ARCHIVES_BASE
from .cache import DiskCache
from .client import get_client
from .submissions import FilingMeta


async def fetch_filing_index(meta: FilingMeta, force: bool = False) -> dict[str, Any]:
    """Fetch the filing index JSON.

    Args:
        meta: Filing metadata
        force: Bypass cache

    Returns:
        Parsed index JSON with file listings
    """
    url = f"{SEC_ARCHIVES_BASE}/{meta.cik}/{meta.accession_nodash}/index.json"

    cache = DiskCache(CACHE_DIR)

    if not force:
        # Archive indexes are effectively immutable, but keep a conservative TTL.
        cached = cache.get(url, max_age_seconds=86400)
        if cached is not None:
            import json
            return json.loads(cached)

    client = await get_client()
    data, headers = await client.fetch_json(url)

    import json
    cache.put(url, json.dumps(data).encode(), headers)

    return data


async def fetch_file(
    meta: FilingMeta,
    filename: str,
    force: bool = False,
) -> bytes:
    """Fetch a single file from the filing archive.

    Args:
        meta: Filing metadata
        filename: Name of file to fetch
        force: Bypass cache

    Returns:
        File content as bytes
    """
    url = f"{SEC_ARCHIVES_BASE}/{meta.cik}/{meta.accession_nodash}/{filename}"

    cache = DiskCache(CACHE_DIR)

    if not force:
        cached = cache.get(url)
        if cached is not None:
            return cached

    client = await get_client()
    content, headers = await client.fetch(url)

    cache.put(url, content, headers)

    return content


def identify_html_files(index: dict[str, Any], primary_doc: str) -> list[str]:
    """Identify HTML files to process from filing index.

    Follows SEC "Related Official Document" rules for inline XBRL:
    - Primary document is always included
    - Related HTML files (like exhibits) may also be included

    Args:
        index: Filing index JSON
        primary_doc: Primary document filename from metadata

    Returns:
        List of HTML filenames to process, primary first
    """
    additional_files: list[str] = []

    directory = index.get("directory", {})
    items = directory.get("item", [])

    # Patterns for HTML-like files
    html_pattern = re.compile(r"\.(htm|html)$", re.IGNORECASE)

    for item in items:
        name = item.get("name", "")

        # Always include primary document (added explicitly below)
        if name == primary_doc:
            continue

        # Check for HTML files that look like filing documents
        if html_pattern.search(name):
            # Skip formatting/exhibit files that aren't the main document
            # These patterns indicate supplementary files
            skip_patterns = [
                r"^index\.html?$",  # SEC folder index page (not a filing document)
                r".*-index\.html?$",  # Accession index page
                r"^index-headers\.html?$",  # Accession header index
                r"^R\d+\.htm",  # XBRL rendering files
                r"^ex\d+",  # Exhibits (unless primary)
                r"FilingSummary\.html?$",
                r"Financial_Report\.xlsx",
            ]

            should_skip = any(
                re.match(pattern, name, re.IGNORECASE)
                for pattern in skip_patterns
            )

            if not should_skip:
                additional_files.append(name)

    # Ensure primary is present even if not in index
    files = [primary_doc]
    # Keep output deterministic even if SEC changes item ordering.
    files.extend(sorted(set(additional_files), key=lambda s: s.lower()))
    return files


async def fetch_filing_html(
    meta: FilingMeta,
    force: bool = False,
) -> list[tuple[str, bytes]]:
    """Fetch all relevant HTML files for a filing.

    Args:
        meta: Filing metadata
        force: Bypass cache

    Returns:
        List of (filename, content) tuples, primary document first
    """
    index = await fetch_filing_index(meta, force=force)
    html_files = identify_html_files(index, meta.primary_document)

    results: list[tuple[str, bytes]] = []

    # Fetch in parallel; SEC rate limiter still governs request pacing.
    tasks = [asyncio.create_task(fetch_file(meta, filename, force=force)) for filename in html_files]

    for filename, task in zip(html_files, tasks, strict=False):
        try:
            content = await task
        except Exception as e:
            # Log warning but continue - some files may be missing
            import warnings
            warnings.warn(f"Failed to fetch {filename}: {e}")
            continue
        results.append((filename, content))

    return results
