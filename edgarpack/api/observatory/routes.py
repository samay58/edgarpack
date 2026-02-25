"""FastAPI routes for the Filing Observatory."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...diff.section_diff import diff_filings
from ...diff.timeline import build_timeline
from ...harvest.registry import PackRegistry
from ...index.inverted import SearchIndex
from ...index.search import search_corpus

# Default paths
_DEFAULT_PACKS_DIR = Path("./packs")


def _get_registry() -> PackRegistry:
    return PackRegistry()


def _get_search_index() -> SearchIndex:
    return SearchIndex()


def _make_router() -> Any:
    from fastapi import APIRouter, HTTPException, Query

    router = APIRouter(prefix="/observatory", tags=["observatory"])

    @router.get("/companies")
    def list_companies() -> list[dict]:
        """Company grid with filing counts and metadata."""
        registry = _get_registry()
        try:
            return registry.list_companies()
        finally:
            registry.close()

    @router.get("/companies/{ticker}")
    def get_company(ticker: str) -> dict:
        """Company detail with filing list and section map."""
        registry = _get_registry()
        try:
            packs = registry.list_packs(ticker=ticker)
            if not packs:
                raise HTTPException(status_code=404, detail=f"No filings found for {ticker}")

            company_name = packs[0].company_name if packs else ticker
            filings = [
                {
                    "accession": p.accession,
                    "form_type": p.form_type,
                    "filing_date": p.filing_date,
                    "sections_count": p.sections_count,
                    "tokens_total": p.tokens_total,
                }
                for p in packs
            ]
            return {
                "ticker": ticker.upper(),
                "company_name": company_name,
                "cik": packs[0].cik if packs else None,
                "filing_count": len(packs),
                "filings": filings,
            }
        finally:
            registry.close()

    @router.get("/companies/{ticker}/diff")
    def get_diff(
        ticker: str,
        form_type: str = Query(default="10-K", description="Form type to diff"),
    ) -> dict:
        """Diff the two most recent filings of a given form type."""
        registry = _get_registry()
        try:
            packs = registry.list_packs(ticker=ticker, form_type=form_type)
            if len(packs) < 2:
                raise HTTPException(
                    status_code=400,
                    detail=f"Need at least 2 {form_type} filings to diff, found {len(packs)}",
                )

            after_dir = Path(packs[0].pack_dir)
            before_dir = Path(packs[1].pack_dir)

            if not after_dir.exists() or not before_dir.exists():
                raise HTTPException(status_code=404, detail="Pack directory not found on disk")

            result = diff_filings(before_dir, after_dir)
            return result.model_dump()
        finally:
            registry.close()

    @router.get("/companies/{ticker}/timeline/{section_id}")
    def get_timeline(
        ticker: str,
        section_id: str,
        form_type: str = Query(default="10-K"),
    ) -> list[dict]:
        """Section evolution across all available filings."""
        registry = _get_registry()
        try:
            packs = registry.list_packs(ticker=ticker, form_type=form_type)
            if not packs:
                raise HTTPException(status_code=404, detail=f"No {form_type} filings for {ticker}")

            # Sort by filing date ascending for timeline
            packs.sort(key=lambda p: p.filing_date)
            pack_dirs = [Path(p.pack_dir) for p in packs if Path(p.pack_dir).exists()]

            entries = build_timeline(pack_dirs, section_id)
            return [e.model_dump() for e in entries]
        finally:
            registry.close()

    @router.get("/search")
    def search(
        q: str = Query(description="Search query"),
        topic: str | None = Query(default=None),
        ticker: str | None = Query(default=None),
        form_type: str | None = Query(default=None),
        limit: int = Query(default=20, le=100),
    ) -> dict:
        """Cross-corpus full-text search with topic facets."""
        index = _get_search_index()
        try:
            result = search_corpus(
                query=q,
                index=index,
                topic=topic,
                ticker=ticker,
                form_type=form_type,
                limit=limit,
            )
            return result.model_dump()
        finally:
            index.close()

    @router.get("/stats")
    def get_stats() -> dict:
        """Registry and index statistics."""
        registry = _get_registry()
        index = _get_search_index()
        try:
            reg_stats = registry.get_stats()
            index_count = index.count()
            topic_stats = index.get_topic_stats()
            return {
                "registry": reg_stats,
                "index": {
                    "total_chunks": index_count,
                    "topics": topic_stats,
                },
            }
        finally:
            registry.close()
            index.close()

    @router.get("/topics")
    def list_topics() -> dict:
        """Topic catalog and stats."""
        from ...index.catalog import TOPIC_CATALOG

        index = _get_search_index()
        try:
            stats = index.get_topic_stats()
            categories = []
            for cat in TOPIC_CATALOG:
                topics = []
                for t in cat.topics:
                    topics.append({"tag": t, "count": stats.get(t, 0)})
                categories.append(
                    {
                        "name": cat.name,
                        "description": cat.description,
                        "topics": topics,
                    }
                )
            return {"categories": categories}
        finally:
            index.close()

    return router


router = _make_router()
