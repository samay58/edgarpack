"""Tests for the search index."""

import tempfile
from pathlib import Path

from edgarpack.index.inverted import IndexedChunk, SearchIndex


def _make_index() -> SearchIndex:
    tmp = tempfile.mktemp(suffix=".db")
    return SearchIndex(db_path=Path(tmp))


def test_index_and_search():
    index = _make_index()
    chunk = IndexedChunk(
        chunk_id="test-001",
        section_id="10k_parti_item1a_risk_factors",
        accession="0001045810-25-000042",
        cik="0001045810",
        ticker="NVDA",
        company_name="NVIDIA CORP",
        form_type="10-K",
        filing_date="2025-02-26",
        text="The company faces significant export control risks related to China.",
        topics=["risk:export_controls", "risk:china_risk"],
    )
    index.index_chunk(chunk)

    hits = index.search("export control")
    assert len(hits) >= 1
    assert hits[0].ticker == "NVDA"
    assert "risk:export_controls" in hits[0].topics

    index.close()


def test_batch_index():
    index = _make_index()
    chunks = [
        IndexedChunk(
            chunk_id=f"chunk-{i}",
            section_id="10k_parti_item1a_risk_factors",
            accession=f"acc-{i:04d}",
            cik="001",
            ticker="NVDA",
            company_name="NVIDIA",
            form_type="10-K",
            filing_date="2025-01-01",
            text=f"Risk factor number {i} discusses cybersecurity threats.",
            topics=["risk:cybersecurity"],
        )
        for i in range(5)
    ]
    count = index.index_chunks_batch(chunks)
    assert count == 5
    assert index.count() == 5

    index.close()


def test_search_with_topic_filter():
    index = _make_index()
    index.index_chunks_batch(
        [
            IndexedChunk(
                chunk_id="c1",
                section_id="s1",
                accession="a1",
                cik="001",
                ticker="NVDA",
                form_type="10-K",
                filing_date="2025-01-01",
                text="Export controls affect our China business.",
                topics=["risk:export_controls", "risk:china_risk"],
            ),
            IndexedChunk(
                chunk_id="c2",
                section_id="s1",
                accession="a2",
                cik="002",
                ticker="AMD",
                form_type="10-K",
                filing_date="2025-01-01",
                text="Supply chain risks in our manufacturing operations.",
                topics=["risk:supply_chain"],
            ),
        ]
    )

    # Search with topic filter
    hits = index.search("export controls", topic="risk:export_controls")
    assert len(hits) >= 1
    assert all("risk:export_controls" in h.topics for h in hits)

    index.close()


def test_search_with_ticker_filter():
    index = _make_index()
    index.index_chunks_batch(
        [
            IndexedChunk(
                chunk_id="c1",
                section_id="s1",
                accession="a1",
                cik="001",
                ticker="NVDA",
                form_type="10-K",
                filing_date="2025-01-01",
                text="Data center revenue growth.",
                topics=[],
            ),
            IndexedChunk(
                chunk_id="c2",
                section_id="s1",
                accession="a2",
                cik="002",
                ticker="AMD",
                form_type="10-K",
                filing_date="2025-01-01",
                text="Data center GPU market.",
                topics=[],
            ),
        ]
    )

    hits = index.search("data center", ticker="NVDA")
    assert len(hits) == 1
    assert hits[0].ticker == "NVDA"

    index.close()


def test_topic_stats():
    index = _make_index()
    index.index_chunks_batch(
        [
            IndexedChunk(
                chunk_id="c1",
                section_id="s1",
                accession="a1",
                cik="001",
                ticker="NVDA",
                form_type="10-K",
                filing_date="2025-01-01",
                text="Export controls.",
                topics=["risk:export_controls"],
            ),
            IndexedChunk(
                chunk_id="c2",
                section_id="s1",
                accession="a2",
                cik="002",
                ticker="AMD",
                form_type="10-K",
                filing_date="2025-01-01",
                text="Export controls too.",
                topics=["risk:export_controls", "risk:china_risk"],
            ),
        ]
    )

    stats = index.get_topic_stats()
    assert stats["risk:export_controls"] == 2
    assert stats["risk:china_risk"] == 1

    index.close()
