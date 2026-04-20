"""Ticker / CIK / company-name resolution via SEC's company_tickers.json."""

from __future__ import annotations

import difflib
import json
import re
from typing import Any

from ..config import CACHE_DIR
from ..errors import AmbiguousCompany, UnknownCompany
from .cache import DiskCache
from .client import get_client
from .submissions import normalize_cik

_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_TICKERS_CACHE_TTL = 86400

# Conservative suffix set stripped from the tail of normalized names so
# "NVIDIA" and "NVIDIA Corp" both normalize to "nvidia".
_SUFFIXES = frozenset(
    {
        "inc",
        "incorporated",
        "corp",
        "corporation",
        "co",
        "company",
        "ltd",
        "limited",
        "llc",
        "lp",
        "plc",
        "sa",
        "ag",
        "nv",
        "holdings",
        "group",
        "trust",
    }
)

# Matches ticker-shaped inputs: short, all uppercase, alphanumeric plus . or -.
_TICKER_SHAPE_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


def _normalize(name: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace, drop tail suffixes."""
    tokens = re.sub(r"[^\w\s]", " ", name).lower().split()
    while tokens and tokens[-1] in _SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def _looks_like_ticker(s: str) -> bool:
    return bool(_TICKER_SHAPE_RE.match(s.strip()))


async def _fetch_raw(force: bool = False) -> dict[str, Any]:
    """Fetch SEC's raw company_tickers.json payload (cached 24h)."""
    cache = DiskCache(CACHE_DIR)

    if not force:
        cached = cache.get(_TICKERS_URL, max_age_seconds=_TICKERS_CACHE_TTL)
        if cached is not None:
            return json.loads(cached)  # type: ignore[no-any-return]

    client = await get_client()
    data, headers = await client.fetch_json(_TICKERS_URL)
    cache.put(_TICKERS_URL, json.dumps(data).encode(), headers)
    return data


def _build_ticker_map(data: dict[str, Any]) -> dict[str, tuple[str, str]]:
    """Build uppercase-ticker -> (zero-padded CIK, title) index."""
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


def _build_name_map(
    data: dict[str, Any],
) -> dict[str, list[tuple[str, str, str]]]:
    """Build normalized-name -> [(cik, ticker, title), ...] index.

    One normalized key can map to multiple rows (share classes, distinct
    issuers sharing a stem). The resolver surfaces these as ambiguity errors.
    """
    result: dict[str, list[tuple[str, str, str]]] = {}
    for entry in data.values():
        if not isinstance(entry, dict):
            continue
        ticker = str(entry.get("ticker", "")).upper()
        cik = normalize_cik(str(entry.get("cik_str", "")))
        title = str(entry.get("title", ""))
        if not (ticker and cik and title):
            continue
        key = _normalize(title)
        if not key:
            continue
        result.setdefault(key, []).append((cik, ticker, title))
    return result


async def resolve_company(query: str, force: bool = False) -> tuple[str, str, str]:
    """Resolve a ticker, CIK, or company name to (cik, ticker, title).

    Args:
        query: Ticker (e.g. "NVDA"), digit CIK ("1045810"), or company
            name ("NVIDIA", "NVIDIA Corp", "apple inc.").
        force: Bypass the 24h ticker-list cache.

    Returns:
        (zero-padded CIK, uppercase ticker, official title). The ticker may
        be empty when the input was a bare CIK that is not in the map.

    Raises:
        UnknownCompany: no match; message includes top fuzzy suggestions.
        AmbiguousCompany: normalized name matches multiple rows.
    """
    q = query.strip()
    if not q:
        raise UnknownCompany("Empty company query")

    raw = await _fetch_raw(force=force)
    ticker_map = _build_ticker_map(raw)
    name_map = _build_name_map(raw)

    # 1. All digits -> CIK passthrough.
    if q.isdigit():
        cik = normalize_cik(q)
        for ticker, (mapped_cik, title) in ticker_map.items():
            if mapped_cik == cik:
                return cik, ticker, title
        return cik, "", f"CIK {cik}"

    # 2. Exact ticker match.
    key_upper = q.upper()
    if key_upper in ticker_map:
        cik, title = ticker_map[key_upper]
        return cik, key_upper, title

    # 3. Exact normalized-name match.
    key_norm = _normalize(q)
    if key_norm and key_norm in name_map:
        matches = name_map[key_norm]
        if len(matches) == 1:
            cik, ticker, title = matches[0]
            return cik, ticker, title
        rendered = ", ".join(f"{ticker} ({title})" for (_cik, ticker, title) in matches)
        raise AmbiguousCompany(
            f"Ambiguous company {q!r}. Matches: {rendered}. Use a ticker to disambiguate."
        )

    # 4. Fuzzy fallback. Ticker-shaped inputs fuzz against tickers; anything
    #    else fuzzes against normalized names. Either way, suggestions are
    #    rendered "Title (TICKER)".
    suggestions: list[str] = []
    if _looks_like_ticker(q):
        for t in difflib.get_close_matches(key_upper, list(ticker_map.keys()), n=3):
            cand_cik, title = ticker_map[t]
            suggestions.append(f"{title} ({t})")
        label = "ticker"
    else:
        needle = key_norm or q.lower()
        for name in difflib.get_close_matches(needle, list(name_map.keys()), n=3):
            _cik, ticker, title = name_map[name][0]
            suggestions.append(f"{title} ({ticker})")
        label = "company"

    hint = ", ".join(suggestions) if suggestions else "none"
    raise UnknownCompany(f"Unknown {label} {q!r}. Did you mean: {hint}?")


async def resolve_ticker(company: str, force: bool = False) -> tuple[str, str]:
    """Backward-compatible wrapper returning (cik, title).

    Prefer ``resolve_company`` for new code. Raises ``UnknownCompany`` or
    ``AmbiguousCompany`` (both subclasses of ``ValueError``).
    """
    cik, _ticker, title = await resolve_company(company, force=force)
    return cik, title
