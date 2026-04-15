"""Identity resolution across SEC and HKEX listings.

Single entrypoint for the CLI. `--ticker` and `--company` both flow
through `resolve()`. Ambiguity (two aliases colliding) is caught at
config load time, not query time.

Spec: docs/superpowers/specs/2026-04-14-china-query-performance-design.md
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .harvest.universe import CompanySpec, load_universe

Source = Literal["SEC", "HKEX"]


class UnknownCompany(ValueError):  # noqa: N818
    """Raised when a ticker or alias does not resolve to any company."""


class AmbiguousCompany(ValueError):  # noqa: N818
    """Raised at config load when two companies claim the same alias."""


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
        private=False,
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
                private=False,
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
    """Resolve a CLI --ticker or --company into a canonical ResolvedCompany."""
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
    raise UnknownCompany(
        f"Unknown company {company!r}. Did you mean: {', '.join(suggestions) or 'none'}?"
    )
