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


def test_sse_migration_is_idempotent():
    registry = _make_registry()
    # _ensure_schema() already ran once in __init__; run the migration list
    # again directly to confirm it tolerates a second application.
    conn = registry._get_conn()
    registry._run_migrations(conn)
    registry._run_migrations(conn)

    row = conn.execute("PRAGMA table_info(packs)").fetchall()
    columns = {r["name"] for r in row}
    assert "market" in columns
    assert "stock_code" in columns

    registry.close()


def test_register_sse_pack_round_trips():
    registry = _make_registry()
    registry.register(
        accession="SSE:688696:2026-03-20",
        cik="SSE:688696",
        ticker="688696",
        company_name="Chengdu XGIMI Technology Co., Ltd.",
        form_type="ANNUAL-REPORT",
        filing_date="2026-03-20",
        sections_count=12,
        tokens_total=45000,
        pack_dir="/tmp/packs/688696/2026-annual",
        market="SSE",
        stock_code="688696",
    )

    record = registry.lookup("SSE:688696:2026-03-20")
    assert record is not None
    assert record.market == "SSE"
    assert record.stock_code == "688696"

    assert registry.has_sse_filing("688696", "2026-03-20")
    assert not registry.has_sse_filing("688696", "2025-03-20")
    assert not registry.has_sse_filing("000001", "2026-03-20")

    registry.close()


def test_sec_rows_leave_market_and_stock_code_null():
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
        pack_dir="/tmp/packs/0001045810",
    )

    record = registry.lookup("0001045810-25-000042")
    assert record is not None
    assert record.market is None
    assert record.stock_code is None

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
