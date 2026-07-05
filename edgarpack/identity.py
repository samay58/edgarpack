"""Identity resolution across SEC, HKEX, and mainland China listings.

The CLI calls `resolve()` with whatever the user typed as the positional
`company` argument, passed once as `ticker=` and once as `company=` to
handle either shape. Ambiguity (two aliases colliding) is caught at
config load time, not query time.
"""

from __future__ import annotations

import dataclasses
import difflib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from .errors import AmbiguousCompany, UnknownCompany, VenueNotAvailable
from .harvest.universe import CompanySpec, load_universe

__all__ = [
    "AmbiguousCompany",
    "IdentityIndex",
    "ResolvedCompany",
    "Source",
    "UnknownCompany",
    "VenueNotAvailable",
    "load_identity",
    "looks_like_china_a_share_code",
    "resolve",
    "select_venue",
    "ticker_for_venue",
    "venue_identifier",
]

Source = Literal["SEC", "HKEX", "SSE"]

_A_SHARE_PREFIXES = (
    "000",
    "001",
    "002",
    "003",
    "300",
    "301",
    "600",
    "601",
    "603",
    "605",
    "688",
)


@dataclass(frozen=True)
class ResolvedCompany:
    ticker: str
    listing: str | None
    source: Source
    cik: str | None
    hk_stock_code: str | None
    stock_code: str | None
    aliases: tuple[str, ...]
    private: bool


@dataclass(frozen=True)
class IdentityIndex:
    by_ticker: dict[str, ResolvedCompany]
    by_alias: dict[str, ResolvedCompany]
    all_tickers: tuple[str, ...]


def looks_like_china_a_share_code(value: str) -> bool:
    code = value.strip()
    return code.isdigit() and len(code) == 6 and code.startswith(_A_SHARE_PREFIXES)


def _source_for(spec: CompanySpec, ticker: str) -> Source:
    listing = (spec.listing or "").upper()
    if ticker.upper().endswith(".HK"):
        return "HKEX"
    if listing == "HKEX":
        return "HKEX"
    if listing in {"SSE", "STAR", "STAR MARKET"}:
        return "SSE"
    if ticker.isdigit() and len(ticker) == 6 and spec.stock_code:
        return "SSE"
    return "SEC"


def _resolved_for(spec: CompanySpec, ticker: str) -> ResolvedCompany:
    display_names = [spec.name] if spec.name else []
    display_aliases = tuple(dict.fromkeys([*display_names, *spec.aliases]))
    cik = spec.cik
    if cik:
        # Packs and the harvest registry store zero-padded CIKs; resolve to
        # the same shape so exact-match consumers (doctor, registry) hit.
        cik = cik.lstrip("0").zfill(10)
    return ResolvedCompany(
        ticker=ticker,
        listing=spec.listing,
        source=_source_for(spec, ticker),
        cik=cik,
        hk_stock_code=spec.hk_stock_code,
        # No fallback to hk_stock_code here: stock_code is the SSE identity,
        # hk_stock_code is the HKEX identity. A dual-listed spec (e.g. one
        # SEC + HKEX, no A-share) must NOT have its HKEX code leak into the
        # SSE-specific field just because stock_code was left unset.
        stock_code=spec.stock_code,
        aliases=display_aliases,
        private=spec.private,
    )


def load_identity(path: Path) -> IdentityIndex:
    """Build an in-memory index from a universe.toml file.

    Raises AmbiguousCompany if any alias is claimed by more than one company.
    """
    universe = load_universe(path)
    by_ticker: dict[str, ResolvedCompany] = {}
    by_alias: dict[str, ResolvedCompany] = {}

    for spec in universe.companies:
        primary_key = spec.ticker or spec.name or spec.cik
        if not primary_key:
            continue

        primary = _resolved_for(spec, primary_key)
        # primary_key is always ticker-resolvable, even when spec.ticker is
        # unset. A dual-listed entry with no single privileged ticker (e.g.
        # cik as the neutral anchor, ADR/HK symbols both in alt_tickers)
        # still needs its anchor identifier to resolve as a "ticker" lookup.
        ticker_inserts = [(primary_key, primary)]
        for alt in spec.alt_tickers:
            ticker_inserts.append((alt, _resolved_for(spec, alt)))
        for raw_ticker, resolved in ticker_inserts:
            key = raw_ticker.upper()
            existing = by_ticker.get(key)
            if existing is not None and (existing.cik, existing.stock_code) != (
                resolved.cik,
                resolved.stock_code,
            ):
                raise AmbiguousCompany(
                    f"Ticker {raw_ticker!r} is claimed by two different companies in universe.toml"
                )
            by_ticker[key] = resolved

        aliases = [*(spec.aliases or [])]
        if spec.name:
            aliases.append(spec.name)
        for alias in aliases:
            key = alias.lower().strip()
            if key in by_alias and by_alias[key].ticker != primary.ticker:
                raise AmbiguousCompany(
                    f"Alias {alias!r} is claimed by both "
                    f"{by_alias[key].ticker} and {primary.ticker}"
                )
            by_alias[key] = primary

    return IdentityIndex(
        by_ticker=by_ticker,
        by_alias=by_alias,
        all_tickers=tuple(sorted(by_ticker.keys())),
    )


def resolve(
    index: IdentityIndex,
    ticker: str | None,
    company: str | None,
) -> ResolvedCompany:
    """Resolve a ticker symbol or a company alias into a ResolvedCompany.

    Pass exactly one of ``ticker`` or ``company``. The CLI typically calls
    this twice for the same user input (first as ticker, then as company
    alias) to paper over the ambiguity between short tickers and names.
    """
    if ticker is None and company is None:
        raise ValueError("resolve() requires ticker or company")

    if ticker is not None:
        key = ticker.upper()
        if key in index.by_ticker:
            return index.by_ticker[key]
        suggestions = difflib.get_close_matches(key, index.all_tickers, n=3)
        if not suggestions:
            suggestions = list(index.all_tickers[:3])
        raise UnknownCompany(
            f"Unknown ticker {ticker!r}. Did you mean: {', '.join(suggestions) or 'none'}?"
        )

    assert company is not None
    key = company.lower().strip()
    if key in index.by_alias:
        return index.by_alias[key]
    alias_keys = sorted(index.by_alias.keys())
    suggestions = difflib.get_close_matches(key, alias_keys, n=3)
    if not suggestions:
        suggestions = alias_keys[:3]
    rendered = [f"{a} ({index.by_alias[a].ticker})" for a in suggestions]
    raise UnknownCompany(
        f"Unknown company {company!r}. Did you mean: {', '.join(rendered) or 'none'}?"
    )


_VENUE_NOTE: dict[Source, str] = {
    "SEC": "SEC EDGAR filings",
    "HKEX": "HKEX filings",
    "SSE": "CNINFO annual reports",
}

_VENUE_ABSENCE: dict[Source, str] = {
    "SEC": "does not file with the SEC",
    "HKEX": "does not have an HKEX listing",
    "SSE": "does not file with the SSE",
}


def _venue_key(venue: str) -> Source:
    key = venue.strip().upper()
    if key not in ("SEC", "HKEX", "SSE"):
        raise ValueError(f"Unknown venue {venue!r}. Choose one of: sec, hkex, sse.")
    return cast(Source, key)


def venue_identifier(resolved: ResolvedCompany, venue: str) -> str | None:
    """The identifier `resolved` carries for `venue`, or None if unpopulated."""
    key = _venue_key(venue)
    if key == "SEC":
        return resolved.cik
    if key == "HKEX":
        return resolved.hk_stock_code
    return resolved.stock_code


def _display_name(resolved: ResolvedCompany) -> str:
    if resolved.aliases:
        first = resolved.aliases[0].strip()
        if first:
            return first
    return resolved.ticker


def select_venue(resolved: ResolvedCompany, venue: str) -> ResolvedCompany:
    """Apply an explicit venue override (the CLI's --venue flag).

    Raises VenueNotAvailable, teaching every venue the entry DOES carry an
    identifier for, when the requested one is absent. On success, returns a
    ResolvedCompany carrying only the chosen venue's identity: the other two
    of {cik, hk_stock_code, stock_code} are nulled out so a downstream reader
    cannot accidentally pick up an identifier from a different listing.
    """
    key = _venue_key(venue)
    identifier = venue_identifier(resolved, key)
    if not identifier:
        # List the entry's own default venue first (matching how a user
        # thinks of the company), then the rest in a fixed order.
        try:
            default = _venue_key(resolved.listing) if resolved.listing else None
        except ValueError:
            default = None
        order = list(dict.fromkeys([v for v in (default, "SEC", "HKEX", "SSE") if v]))
        available = [
            f"{v.lower()} ({code}, {_VENUE_NOTE[v]})"
            for v in order
            if (code := venue_identifier(resolved, v))
        ]
        raise VenueNotAvailable(
            f"{_display_name(resolved)} {_VENUE_ABSENCE[key]}. "
            f"Available: {', '.join(available) or 'none'}."
        )
    return dataclasses.replace(
        resolved,
        listing=key,
        source=key,
        cik=identifier if key == "SEC" else None,
        hk_stock_code=identifier if key == "HKEX" else None,
        stock_code=identifier if key == "SSE" else None,
    )


def ticker_for_venue(index: IdentityIndex, resolved: ResolvedCompany, venue: str) -> str | None:
    """Find a ticker key that independently re-resolves to `venue`.

    Callers that only accept a plain company string (financials(), the
    identify command's ADR-symbol display) use this instead of threading a
    ResolvedCompany through, so those functions need no changes: whatever
    string this returns, re-resolving it lands on the requested venue slice
    of the same dual-listed company.
    """
    key = _venue_key(venue)
    if key == "SSE":
        # A bare 6-digit A-share code always re-resolves, independent of
        # universe.toml ticker registration, via the china-a-share-code
        # passthrough in financials(). No need to search for a ticker key,
        # and no ADR-style symbol is more "correct" here than the code.
        return venue_identifier(resolved, key)

    identity_key = (resolved.cik, resolved.hk_stock_code, resolved.stock_code)
    candidates = [
        ticker
        for ticker, candidate in index.by_ticker.items()
        if candidate.source == key
        and (candidate.cik, candidate.hk_stock_code, candidate.stock_code) == identity_key
    ]
    if not candidates:
        # No ticker/alt_ticker independently routes here (e.g. a populated
        # hk_stock_code with no ".HK" alt_ticker on file). Best effort: reuse
        # resolved.ticker if it already sits at this venue, else the bare
        # identifier (unlikely to resolve for HKEX, but nothing better is
        # available).
        if resolved.source == key:
            return resolved.ticker
        return venue_identifier(resolved, key)

    if key == "SEC":
        # Prefer a human ticker symbol over a bare numeric key (a CIK
        # registered as its own ticker_insert) so identify's ADR label
        # reads "BABA", not the CIK repeated.
        alpha = sorted(t for t in candidates if not t.replace(".", "").isdigit())
        if alpha:
            return alpha[0]
    return sorted(candidates)[0]
