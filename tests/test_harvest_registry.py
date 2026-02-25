"""Tests for the pack registry."""

import tempfile
from pathlib import Path

from edgarpack.harvest.registry import PackRegistry


def _make_registry() -> PackRegistry:
    """Create a temp registry for testing."""
    tmp = tempfile.mktemp(suffix=".db")
    return PackRegistry(db_path=Path(tmp))


def test_register_and_lookup():
    registry = _make_registry()
    registry.register(
        accession="0001045810-25-000042",
        cik="0001045810",
        ticker="NVDA",
        company_name="NVIDIA CORP",
        form_type="10-K",
        filing_date="2025-02-26",
        sections_count=22,
        tokens_total=156000,
        pack_dir="/tmp/packs/0001045810/0001045810-25-000042",
    )

    record = registry.lookup("0001045810-25-000042")
    assert record is not None
    assert record.ticker == "NVDA"
    assert record.sections_count == 22
    assert record.tokens_total == 156000

    registry.close()


def test_has_accession():
    registry = _make_registry()
    assert not registry.has_accession("0001045810-25-000042")

    registry.register(
        accession="0001045810-25-000042",
        cik="0001045810",
        ticker="NVDA",
        company_name="NVIDIA CORP",
        form_type="10-K",
        filing_date="2025-02-26",
        sections_count=22,
        tokens_total=156000,
        pack_dir="/tmp/packs/test",
    )

    assert registry.has_accession("0001045810-25-000042")
    assert not registry.has_accession("0001045810-25-999999")

    registry.close()


def test_list_packs_by_ticker():
    registry = _make_registry()

    for i, (ticker, cik) in enumerate([("NVDA", "001"), ("NVDA", "001"), ("AMD", "002")]):
        registry.register(
            accession=f"acc-{i:04d}",
            cik=cik,
            ticker=ticker,
            company_name=f"{ticker} Corp",
            form_type="10-K",
            filing_date=f"2025-0{i + 1}-01",
            sections_count=10,
            tokens_total=50000,
            pack_dir=f"/tmp/packs/{i}",
        )

    nvda_packs = registry.list_packs(ticker="NVDA")
    assert len(nvda_packs) == 2
    assert all(p.ticker == "NVDA" for p in nvda_packs)

    amd_packs = registry.list_packs(ticker="AMD")
    assert len(amd_packs) == 1

    registry.close()


def test_list_companies():
    registry = _make_registry()

    registry.register(
        accession="acc-001",
        cik="001",
        ticker="NVDA",
        company_name="NVIDIA CORP",
        form_type="10-K",
        filing_date="2025-01-01",
        sections_count=22,
        tokens_total=150000,
        pack_dir="/tmp/packs/1",
    )
    registry.register(
        accession="acc-002",
        cik="001",
        ticker="NVDA",
        company_name="NVIDIA CORP",
        form_type="10-Q",
        filing_date="2025-04-01",
        sections_count=15,
        tokens_total=80000,
        pack_dir="/tmp/packs/2",
    )
    registry.register(
        accession="acc-003",
        cik="002",
        ticker="AMD",
        company_name="AMD INC",
        form_type="10-K",
        filing_date="2025-02-01",
        sections_count=20,
        tokens_total=140000,
        pack_dir="/tmp/packs/3",
    )

    companies = registry.list_companies()
    assert len(companies) == 2

    registry.close()


def test_get_stats():
    registry = _make_registry()
    registry.register(
        accession="acc-001",
        cik="001",
        ticker="NVDA",
        company_name="NVIDIA",
        form_type="10-K",
        filing_date="2025-01-01",
        sections_count=20,
        tokens_total=100000,
        pack_dir="/tmp/p",
    )

    stats = registry.get_stats()
    assert stats["total_packs"] == 1
    assert stats["companies"] == 1
    assert stats["total_tokens"] == 100000

    registry.close()
