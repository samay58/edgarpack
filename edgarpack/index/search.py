"""High-level cross-corpus search API."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from .inverted import SearchHit, SearchIndex


class SearchResult(BaseModel):
    """Aggregated search result with company grouping."""

    query: str
    total_hits: int
    hits: list[SearchHit]
    companies: list[str]
    topics_found: list[str]


def search_corpus(
    query: str,
    index: SearchIndex | None = None,
    index_path: Path | None = None,
    topic: str | None = None,
    ticker: str | None = None,
    form_type: str | None = None,
    limit: int = 20,
) -> SearchResult:
    """Search across the filing corpus with optional filters.

    Args:
        query: Full-text search query
        index: Existing SearchIndex instance (optional)
        index_path: Path to index database (optional, uses default)
        topic: Filter by topic tag
        ticker: Filter by company ticker
        form_type: Filter by form type (10-K, 10-Q, 8-K)
        limit: Maximum results

    Returns:
        SearchResult with grouped hits
    """
    if index is None:
        index = SearchIndex(index_path)

    hits = index.search(
        query=query,
        topic=topic,
        ticker=ticker,
        form_type=form_type,
        limit=limit,
    )

    companies = sorted(set(h.ticker or h.cik for h in hits))
    topics_found = sorted(set(t for h in hits for t in h.topics))

    return SearchResult(
        query=query,
        total_hits=len(hits),
        hits=hits,
        companies=companies,
        topics_found=topics_found,
    )
