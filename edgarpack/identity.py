"""Identity resolution across SEC and HKEX listings.

The CLI calls `resolve()` with whatever the user typed as the positional
`company` argument, passed once as `ticker=` and once as `company=` to
handle either shape. Ambiguity (two aliases colliding) is caught at
config load time, not query time.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .errors import AmbiguousCompany, UnknownCompany
from .harvest.universe import CompanySpec, load_universe

__all__ = [
    "AmbiguousCompany",
    "IdentityIndex",
    "ResolvedCompany",
    "Source",
    "UnknownCompany",
    "load_identity",
    "resolve",
]

Source = Literal["SEC", "HKEX"]


@dataclass(frozen=True)
class ResolvedCompany:
    ticker: str
    listing: str | None
    source: Source
    cik: str | None
    hk_stock_code: str | None
    aliases: tuple[str, ...]
    private: bool


@dataclass(frozen=True)
class IdentityIndex:
    by_ticker: dict[str, ResolvedCompany]
    by_alias: dict[str, ResolvedCompany]
    all_tickers: tuple[str, ...]


def _source_for(spec: CompanySpec, ticker: str) -> Source:
    if ticker.endswith(".HK"):
        return "HKEX"
    if spec.listing == "HKEX":
        return "HKEX"
    return "SEC"


def _resolved_for(spec: CompanySpec, ticker: str) -> ResolvedCompany:
    return ResolvedCompany(
        ticker=ticker,
        listing=spec.listing,
        source=_source_for(spec, ticker),
        cik=spec.cik,
        hk_stock_code=spec.hk_stock_code,
        aliases=tuple(spec.aliases),
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
        primary = _resolved_for(spec, spec.ticker)
        by_ticker[spec.ticker.upper()] = primary
        for alt in spec.alt_tickers:
            alt_resolved = ResolvedCompany(
                ticker=alt,
                listing="HKEX" if alt.endswith(".HK") else spec.listing,
                source="HKEX" if alt.endswith(".HK") else "SEC",
                cik=spec.cik,
                hk_stock_code=spec.hk_stock_code,
                aliases=tuple(spec.aliases),
                private=spec.private,
            )
            by_ticker[alt.upper()] = alt_resolved

        for alias in spec.aliases:
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
