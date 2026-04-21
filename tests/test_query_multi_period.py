"""Multi-period render: formula dedup across periods (Task C3)."""

from __future__ import annotations

import unittest
from datetime import date

from edgarpack.query.comps import (
    _register_calculation,
    format_financial_perf_table,
)
from edgarpack.query.models import CitedValue, DerivedValue, QueryResult


def _ocf(fy: int, accession: str) -> CitedValue:
    return CitedValue(
        value=1000.0,
        unit="USD",
        metric="cashFlowFromOperations",
        concept="CashFlowFromOperations",
        period_start=date(fy, 1, 1),
        period_end=date(fy, 12, 31),
        fiscal_year=fy,
        fiscal_period="FY",
        form_type="10-K",
        filed=date(fy + 1, 2, 1),
        accession=accession,
        cik="0001326801",
        company="Alphabet",
        taxonomy="us-gaap",
        primary_document="goog.htm",
        fact_id=f"f-ocf-{fy}",
    )


def _capex(fy: int, accession: str) -> CitedValue:
    return CitedValue(
        value=300.0,
        unit="USD",
        metric="capitalExpenditure",
        concept="CapitalExpenditure",
        period_start=date(fy, 1, 1),
        period_end=date(fy, 12, 31),
        fiscal_year=fy,
        fiscal_period="FY",
        form_type="10-K",
        filed=date(fy + 1, 2, 1),
        accession=accession,
        cik="0001326801",
        company="Alphabet",
        taxonomy="us-gaap",
        primary_document="goog.htm",
        fact_id=f"f-capex-{fy}",
    )


def _fcf(fy: int, accession: str) -> DerivedValue:
    return DerivedValue(
        value=700.0,
        unit="USD",
        metric="free_cash_flow",
        concept="cashFlowFromOperations - capitalExpenditures",
        period_start=date(fy, 1, 1),
        period_end=date(fy, 12, 31),
        fiscal_year=fy,
        fiscal_period="FY",
        form_type="10-K",
        filed=date(fy + 1, 2, 1),
        accession=accession,
        cik="0001326801",
        company="Alphabet",
        taxonomy="us-gaap",
        primary_document="goog.htm",
        fact_id=f"f-fcf-{fy}",
        components={
            "cashFlowFromOperations": _ocf(fy, accession),
            "capitalExpenditures": _capex(fy, accession),
        },
    )


class TestFormulaDedup(unittest.TestCase):
    def test_formula_appears_once_across_periods(self) -> None:
        citation_ids: dict[str, str] = {}
        citation_records: dict[str, dict[str, object]] = {}
        calc_ids: dict[str, str] = {}
        calc_records: dict[str, dict[str, object]] = {}
        formula_records: dict[tuple[str, str], dict[str, object]] = {}

        for fy, accn in [(2024, "a"), (2023, "b"), (2022, "c"), (2021, "d")]:
            _register_calculation(
                "free_cash_flow",
                _fcf(fy, accn),
                citation_ids,
                citation_records,
                calc_ids,
                calc_records,
                formula_records=formula_records,
            )

        self.assertEqual(len(calc_records), 4, "one calc per period")
        self.assertEqual(len(formula_records), 1, "formula string shared across all periods")
        fk = next(iter(formula_records))
        self.assertEqual(fk[0], "free_cash_flow")
        self.assertEqual(fk[1], "derived")
        bound = formula_records[fk].get("calc_ids")
        self.assertIsInstance(bound, list)
        self.assertEqual(len(bound), 4)

    def test_register_calculation_without_formula_records_arg_still_works(self) -> None:
        """Single-period path (no formula_records kwarg) must remain behavior-compatible."""
        citation_ids: dict[str, str] = {}
        citation_records: dict[str, dict[str, object]] = {}
        calc_ids: dict[str, str] = {}
        calc_records: dict[str, dict[str, object]] = {}

        cid1 = _register_calculation(
            "free_cash_flow",
            _fcf(2024, "a"),
            citation_ids,
            citation_records,
            calc_ids,
            calc_records,
        )
        self.assertEqual(cid1, "D1")
        self.assertEqual(len(calc_records), 1)


class TestFormulaDedupInGridRender(unittest.TestCase):
    """Integration: rendering a multi-period grid with a derived metric prints
    the formula ONCE, not once per period."""

    def _results(self, periods_and_fy: list[tuple[str, int, str]]) -> dict[str, QueryResult]:
        results: dict[str, QueryResult] = {}
        for period, fy, accn in periods_and_fy:
            results[period] = QueryResult(
                company="Alphabet",
                cik="0001326801",
                period=period,
                metrics={"free_cash_flow": _fcf(fy, accn)},
            )
        return results

    def test_footer_mode_dedups_formula(self) -> None:
        periods = ["lfy", "lfy-1", "lfy-2", "lfy-3"]
        results = self._results(
            [
                ("lfy", 2024, "a"),
                ("lfy-1", 2023, "b"),
                ("lfy-2", 2022, "c"),
                ("lfy-3", 2021, "d"),
            ]
        )
        out = format_financial_perf_table(
            results,
            ["free_cash_flow"],
            periods,
            terminal_width=200,
        )
        # Exactly one "free_cash_flow =" line in the Calculations footer.
        self.assertEqual(
            out.count("free_cash_flow ="),
            1,
            f"formula should print once, got:\n{out}",
        )
        # Calc markers for all four periods should still be unique in the grid.
        for cid in ("D1", "D2", "D3", "D4"):
            self.assertIn(f"[{cid}]", out, f"missing per-period calc id {cid}")

    def test_inline_mode_dedups_formula(self) -> None:
        periods = ["lfy", "lfy-1"]
        results = self._results(
            [
                ("lfy", 2024, "a"),
                ("lfy-1", 2023, "b"),
            ]
        )
        out = format_financial_perf_table(
            results,
            ["free_cash_flow"],
            periods,
            citations_mode="inline",
            terminal_width=200,
        )
        self.assertEqual(out.count("free_cash_flow ="), 1)
        # Both per-period markers present in the data row.
        self.assertIn("[D1]", out)
        self.assertIn("[D2]", out)

    def test_audit_mode_emits_per_period_components(self) -> None:
        """Under --audit, the per-period component breakdown still prints, but
        the formula header line itself remains a single entry per metric."""
        periods = ["lfy", "lfy-1"]
        results = self._results(
            [
                ("lfy", 2024, "a"),
                ("lfy-1", 2023, "b"),
            ]
        )
        out = format_financial_perf_table(
            results,
            ["free_cash_flow"],
            periods,
            citations_mode="inline",
            audit=True,
            terminal_width=200,
        )
        self.assertEqual(out.count("free_cash_flow ="), 1)
        # Audit subtable should have a per-period line for each calc id.
        self.assertIn("[D1]", out)
        self.assertIn("[D2]", out)

    def test_non_audit_inline_has_no_component_subtable(self) -> None:
        """Without --audit: one-line formula summary, no per-component dump."""
        periods = ["lfy", "lfy-1"]
        results = self._results(
            [
                ("lfy", 2024, "a"),
                ("lfy-1", 2023, "b"),
            ]
        )
        out = format_financial_perf_table(
            results,
            ["free_cash_flow"],
            periods,
            citations_mode="inline",
            audit=False,
            terminal_width=200,
        )
        # No role-labeled component breakdown lines in non-audit mode.
        self.assertNotIn("cashFlowFromOperations[C", out)
        self.assertNotIn("capitalExpenditures[C", out)


if __name__ == "__main__":
    unittest.main()
