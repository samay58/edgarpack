"""Period resolution for discovered-KPI lookup (lfy-N, mrq-N, annual:N, quarterly:N, ltm)."""

from __future__ import annotations

from pathlib import Path

import pytest

from edgarpack.query.kpi_discover import lookup_company_kpi
from edgarpack.query.learned_registry import LearnedRegistry


@pytest.fixture
def seeded_registry(tmp_path: Path) -> Path:
    db = tmp_path / "learned.db"
    reg = LearnedRegistry(db_path=db)
    cik = "0001564408"
    try:
        # 6 annual rows FY2020-FY2025.
        for yr in (2020, 2021, 2022, 2023, 2024, 2025):
            reg.company_kpi_upsert(
                cik=cik,
                accession=f"000-{yr}-ANN",
                slug="daily_active_users",
                display_name="Daily Active Users",
                aliases=[],
                unit="count",
                magnitude=None,
                value=float((yr - 2019) * 50_000_000),
                period_end=f"{yr}-12-31",
                fiscal_year=yr,
                fiscal_period="FY",
                form_type="10-K",
                definition=None,
                section_id=None,
                chunk_id=None,
                source_substring=None,
                confidence=None,
            )
        # 3 quarterly rows FY2025 Q1-Q3.
        for q in (1, 2, 3):
            reg.company_kpi_upsert(
                cik=cik,
                accession=f"000-2025-Q{q}",
                slug="daily_active_users",
                display_name="Daily Active Users",
                aliases=[],
                unit="count",
                magnitude=None,
                value=float(400_000_000 + q * 10_000_000),
                period_end=f"2025-{3 * q:02d}-31",
                fiscal_year=2025,
                fiscal_period=f"Q{q}",
                form_type="10-Q",
                definition=None,
                section_id=None,
                chunk_id=None,
                source_substring=None,
                confidence=None,
            )
    finally:
        reg.close()
    return db


class TestScalarPeriods:
    def test_lfy_returns_latest_annual(self, seeded_registry: Path) -> None:
        row = lookup_company_kpi(
            cik="0001564408",
            slug="daily_active_users",
            period="lfy",
            registry_path=seeded_registry,
        )
        assert row is not None and not isinstance(row, list)
        assert row.fiscal_year == 2025
        assert row.form_type == "10-K"

    def test_lfy_back_three(self, seeded_registry: Path) -> None:
        row = lookup_company_kpi(
            cik="0001564408",
            slug="daily_active_users",
            period="lfy-3",
            registry_path=seeded_registry,
        )
        assert row is not None and not isinstance(row, list)
        assert row.fiscal_year == 2022

    def test_lfy_out_of_bounds_returns_none(self, seeded_registry: Path) -> None:
        row = lookup_company_kpi(
            cik="0001564408",
            slug="daily_active_users",
            period="lfy-10",
            registry_path=seeded_registry,
        )
        assert row is None

    def test_mrq(self, seeded_registry: Path) -> None:
        row = lookup_company_kpi(
            cik="0001564408",
            slug="daily_active_users",
            period="mrq",
            registry_path=seeded_registry,
        )
        assert row is not None and not isinstance(row, list)
        assert row.fiscal_period == "Q3"

    def test_mrq_back_one(self, seeded_registry: Path) -> None:
        row = lookup_company_kpi(
            cik="0001564408",
            slug="daily_active_users",
            period="mrq-1",
            registry_path=seeded_registry,
        )
        assert row is not None and not isinstance(row, list)
        assert row.fiscal_period == "Q2"

    def test_mrp_returns_newest_of_any_form(self, seeded_registry: Path) -> None:
        row = lookup_company_kpi(
            cik="0001564408",
            slug="daily_active_users",
            period="mrp",
            registry_path=seeded_registry,
        )
        assert row is not None and not isinstance(row, list)


class TestLtmDegrades:
    def test_ltm_returns_same_as_lfy(self, seeded_registry: Path) -> None:
        lfy_row = lookup_company_kpi(
            cik="0001564408",
            slug="daily_active_users",
            period="lfy",
            registry_path=seeded_registry,
        )
        ltm_row = lookup_company_kpi(
            cik="0001564408",
            slug="daily_active_users",
            period="ltm",
            registry_path=seeded_registry,
        )
        assert lfy_row is not None and ltm_row is not None
        assert not isinstance(lfy_row, list) and not isinstance(ltm_row, list)
        assert ltm_row.fiscal_year == lfy_row.fiscal_year

    def test_ltm_back_two_matches_lfy_back_two(self, seeded_registry: Path) -> None:
        lfy_row = lookup_company_kpi(
            cik="0001564408",
            slug="daily_active_users",
            period="lfy-2",
            registry_path=seeded_registry,
        )
        ltm_row = lookup_company_kpi(
            cik="0001564408",
            slug="daily_active_users",
            period="ltm-2",
            registry_path=seeded_registry,
        )
        assert lfy_row is not None and ltm_row is not None
        assert not isinstance(lfy_row, list) and not isinstance(ltm_row, list)
        assert ltm_row.fiscal_year == lfy_row.fiscal_year


class TestSeries:
    def test_annual_six(self, seeded_registry: Path) -> None:
        rows = lookup_company_kpi(
            cik="0001564408",
            slug="daily_active_users",
            period="annual:6",
            registry_path=seeded_registry,
        )
        assert isinstance(rows, list)
        assert len(rows) == 6
        assert [r.fiscal_year for r in rows] == [2025, 2024, 2023, 2022, 2021, 2020]

    def test_annual_partial_coverage(self, seeded_registry: Path) -> None:
        rows = lookup_company_kpi(
            cik="0001564408",
            slug="daily_active_users",
            period="annual:10",
            registry_path=seeded_registry,
        )
        assert isinstance(rows, list)
        assert len(rows) == 6  # Caller handles the partial-coverage diagnostic.

    def test_quarterly_two(self, seeded_registry: Path) -> None:
        rows = lookup_company_kpi(
            cik="0001564408",
            slug="daily_active_users",
            period="quarterly:2",
            registry_path=seeded_registry,
        )
        assert isinstance(rows, list)
        assert [r.fiscal_period for r in rows] == ["Q3", "Q2"]


class TestMisses:
    def test_unknown_slug_returns_none(self, seeded_registry: Path) -> None:
        assert (
            lookup_company_kpi(
                cik="0001564408",
                slug="nonexistent",
                period="lfy",
                registry_path=seeded_registry,
            )
            is None
        )

    def test_unknown_period_falls_back_to_newest(self, seeded_registry: Path) -> None:
        row = lookup_company_kpi(
            cik="0001564408",
            slug="daily_active_users",
            period="weirdo",
            registry_path=seeded_registry,
        )
        assert row is not None and not isinstance(row, list)
