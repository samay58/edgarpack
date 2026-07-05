"""Shared citation registry behavior for terminal and JSON outputs."""

from __future__ import annotations

from datetime import date

from edgarpack.query.citations import CitationRegistry, calculation_summary
from edgarpack.query.models import CitedValue, DerivedValue, QueryResult


def _cv(
    metric: str,
    concept: str,
    value: float,
    *,
    fact_id: str,
    filed: date | None = date(2025, 2, 1),
) -> CitedValue:
    return CitedValue(
        value=value,
        unit="USD",
        metric=metric,
        concept=concept,
        period_start=date(2024, 1, 1),
        period_end=date(2024, 12, 31),
        fiscal_year=2024,
        fiscal_period="FY",
        form_type="10-K",
        filed=filed,
        accession="0000000001-25-000001",
        cik="0000000001",
        company="Test Corp",
        primary_document="test-20241231.htm",
        fact_id=fact_id,
    )


def _gross_margin() -> DerivedValue:
    gross_profit = _cv("gross_profit", "GrossProfit", 40.0, fact_id="f-gp")
    revenue = _cv("revenue", "Revenues", 100.0, fact_id="f-rev")
    return DerivedValue(
        value=0.4,
        unit="pure",
        metric="gross_margin",
        concept="gross_profit / revenue",
        period_start=date(2024, 1, 1),
        period_end=date(2024, 12, 31),
        fiscal_year=2024,
        fiscal_period="FY",
        form_type="10-K",
        filed=date(2025, 2, 1),
        accession="0000000001-25-000001",
        cik="0000000001",
        company="Test Corp",
        primary_document="test-20241231.htm",
        fact_id="f-gm",
        components={"gross_profit": gross_profit, "revenue": revenue},
    )


def test_registry_dedupes_direct_citations() -> None:
    registry = CitationRegistry()
    revenue = _cv("revenue", "Revenues", 100.0, fact_id="f-rev")

    assert registry.register_citation(revenue) == "C1"
    assert registry.register_citation(revenue) == "C1"
    assert list(registry.citations) == ["C1"]
    assert registry.citations["C1"]["type"] == "citation"


def test_registry_registers_derived_with_component_refs() -> None:
    registry = CitationRegistry()
    gross_margin = _gross_margin()

    assert registry.marker_for("gross_margin", gross_margin) == "[D1]"
    calc = registry.calculations["D1"]

    assert calc["type"] == "derived"
    assert calc["result_citation_id"] == "C3"
    assert calc["component_citation_ids"] == {
        "gross_profit": "C1",
        "revenue": "C2",
    }
    assert "using gross_profit[C1], revenue[C2]" in calculation_summary("D1", calc)


def test_calculation_component_filed_none_serializes_as_null() -> None:
    # Regression for citations-filed-none: a China pack whose manifest has
    # no announcement date leaves component.filed as None. Reproduced via a
    # China gross_margin query, where the derived value itself also carries
    # no accession/filed (no single filing backs a ratio).
    registry = CitationRegistry()
    gross_profit = _cv("gross_profit", "GrossProfit", 40.0, fact_id="f-gp", filed=None)
    revenue = _cv("revenue", "Revenues", 100.0, fact_id="f-rev")
    gross_margin = DerivedValue(
        value=0.4,
        unit="pure",
        metric="gross_margin",
        concept="gross_profit / revenue",
        period_start=date(2024, 1, 1),
        period_end=date(2024, 12, 31),
        fiscal_year=2024,
        fiscal_period="FY",
        form_type="10-K",
        filed=None,
        accession="0000000001-25-000001",
        cik="0000000001",
        company="Test Corp",
        primary_document="test-20241231.htm",
        fact_id="f-gm",
        components={"gross_profit": gross_profit, "revenue": revenue},
    )

    calc_id = registry.register_calculation("gross_margin", gross_margin)
    components_by_role = {c["role"]: c for c in registry.calculations[calc_id]["components"]}

    assert components_by_role["gross_profit"]["filed"] is None
    assert components_by_role["revenue"]["filed"] == "2025-02-01"


def test_query_result_lean_json_uses_registry_records() -> None:
    gross_margin = _gross_margin()
    result = QueryResult(
        company="Test Corp",
        cik="0000000001",
        metrics={"gross_margin": gross_margin},
    )

    lean = result.to_lean_dict()
    metric = lean["metrics"]["gross_margin"]
    calc = lean["calculations"][metric["calculation_id"]]

    assert metric["citation_ids"] == [calc["result_citation_id"]]
    assert metric["component_citation_ids"] == calc["component_citation_ids"]
    assert lean["citations"][calc["component_citation_ids"]["revenue"]]["concept"] == "Revenues"
