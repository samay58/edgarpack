"""Ticker-to-CIK resolution via SEC's company_tickers.json endpoint."""

from __future__ import annotations

import json
from typing import Any

from ..config import CACHE_DIR
from .cache import DiskCache
from .client import get_client
from .submissions import normalize_cik

# SEC's canonical ticker list
_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

# Cache ticker list for 24 hours
_TICKERS_CACHE_TTL = 86400


async def _fetch_ticker_map(force: bool = False) -> dict[str, tuple[str, str]]:
    """Fetch and build ticker -> (cik, company_name) mapping.

    Returns:
        Dict keyed by uppercase ticker, values are (zero-padded CIK, company name).
    """
    cache = DiskCache(CACHE_DIR)

    if not force:
        cached = cache.get(_TICKERS_URL, max_age_seconds=_TICKERS_CACHE_TTL)
        if cached is not None:
            raw: dict[str, Any] = json.loads(cached)
            return _build_map(raw)

    client = await get_client()
    data, headers = await client.fetch_json(_TICKERS_URL)

    cache.put(_TICKERS_URL, json.dumps(data).encode(), headers)

    return _build_map(data)


def _build_map(data: dict[str, Any]) -> dict[str, tuple[str, str]]:
    """Build ticker lookup from SEC's company_tickers.json format.

    The SEC format is: {"0": {"cik_str": "320193", "ticker": "AAPL", "title": "Apple Inc"}, ...}
    """
    result: dict[str, tuple[str, str]] = {}
    for entry in data.values():
        if not isinstance(entry, dict):
            continue
        ticker = str(entry.get("ticker", "")).upper()
        cik = normalize_cik(str(entry.get("cik_str", "")))
        title = str(entry.get("title", ""))
        if ticker and cik:
            result[ticker] = (cik, title)
    return result


async def resolve_ticker(company: str, force: bool = False) -> tuple[str, str]:
    """Resolve a ticker symbol or CIK to (cik, company_name).

    Accepts either a ticker ("NVDA") or a raw CIK string ("1045810").
    CIK strings are passed through with a best-effort company name lookup.

    Args:
        company: Ticker symbol or CIK number.
        force: Bypass cache.

    Returns:
        (zero-padded CIK, company name)

    Raises:
        ValueError: If ticker not found.
    """
    company = company.strip()

    # If it looks like a CIK (all digits), pass through
    if company.isdigit():
        cik = normalize_cik(company)
        # Try to find company name from ticker map
        ticker_map = await _fetch_ticker_map(force=force)
        for _ticker, (mapped_cik, name) in ticker_map.items():
            if mapped_cik == cik:
                return cik, name
        return cik, f"CIK {cik}"

    # Ticker lookup
    ticker_map = await _fetch_ticker_map(force=force)
    key = company.upper()
    if key not in ticker_map:
        raise ValueError(f"Unknown ticker: {company}")
    return ticker_map[key]
