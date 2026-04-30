"""Grid renderer + multi-period JSON shape."""

from __future__ import annotations

import json
import unittest
from datetime import date

from edgarpack.query.comps import (
    _period_label,
    expand_comps_periods,
    format_comps_multi_period_table,
    format_financial_perf_table,
    multi_period_to_full_json,
    multi_period_to_lean_json,
)
from edgarpack.query.models import CitedValue, Diagnostic, QueryResult


def _cv(
    *,
    value: float,
    fy: int,
    metric: str = "revenue",
    concept: str = "Revenues",
    unit: str = "USD",
    accession: str | None = None,
) -> CitedValue:
    return CitedValue(
        value=value,
        unit=unit,
        metric=metric,
        concept=concept,
        period_start=date(fy, 1, 1),
        period_end=date(fy, 12, 31),
        fiscal_year=fy,
        fiscal_period="FY",
        form_type="10-K",
        filed=date(fy + 1, 3, 1),
        accession=accession or f"0000000001-{str(fy + 1)[-2:]}-000001",
        cik="0000000001",
        company="Test Corp",
    )


def _result_for(period: str, *, revenue: float, net_income: float) -> QueryResult:
    # Map period label to FY (lfy=2024, lfy-1=2023, lfy-2=2022).
    fy_by_period = {
        "lfy": 2024,
        "lfy-1": 2023,
        "lfy-2": 2022,
    }
    fy = fy_by_period[period]
    return QueryResult(
        company="Test Corp",
        cik="0000000001",
        period=period,
        metrics={
            "revenue": _cv(value=revenue, fy=fy, metric="revenue"),
            "net_income": _cv(
                value=net_income,
                fy=fy,
                metric="net_income",
                concept="NetIncomeLoss",
            ),
        },
    )


class TestPeriodLabel(unittest.TestCase):
    def test_scalar(self) -> None:
        self.assertEqual(_period_label("lfy"), "LFY")
        self.assertEqual(_period_label("ltm"), "LTM")
        self.assertEqual(_period_label("mrq"), "MRQ")

    def test_suffixed(self) -> None:
        self.assertEqual(_period_label("lfy-1"), "LFY-1")
        self.assertEqual(_period_label("ltm-2"), "LTM-2")
        self.assertEqual(_period_label("mrq-3"), "MRQ-3")


class TestFormatFinancialPerfTable(unittest.TestCase):
    def setUp(self) -> None:
        self.periods = ["lfy", "lfy-1", "lfy-2"]
        self.metrics = ["revenue", "net_income"]
        self.results = {
            "lfy": _result_for("lfy", revenue=100e9, net_income=30e9),
            "lfy-1": _result_for("lfy-1", revenue=80e9, net_income=20e9),
            "lfy-2": _result_for("lfy-2", revenue=50e9, net_income=10e9),
        }

    def test_header_has_metric_plus_periods_in_order(self) -> None:
        out = format_financial_perf_table(
            self.results, self.metrics, self.periods, terminal_width=200
        )
        lines = out.splitlines()
        # Header line is the third line (after "Test Corp ..." and blank).
        header = lines[2]
        self.assertIn("Metric", header)
        self.assertIn("LFY", header)
        self.assertIn("LFY-1", header)
        self.assertIn("LFY-2", header)
        # Newest on the LEFT.
        self.assertLess(header.index("LFY"), header.index("LFY-1"))
        self.assertLess(header.index("LFY-1"), header.index("LFY-2"))

    def test_data_rows_contain_formatted_values(self) -> None:
        out = format_financial_perf_table(
            self.results, self.metrics, self.periods, terminal_width=200
        )
        self.assertIn("Revenue", out)
        self.assertIn("Net Income", out)
        # Formatted with $ prefix and B suffix.
        self.assertIn("$100.0B", out)
        self.assertIn("$80.0B", out)
        self.assertIn("$50.0B", out)

    def test_footer_citations_by_default(self) -> None:
        out = format_financial_perf_table(
            self.results, self.metrics, self.periods, terminal_width=200
        )
        # Footer mode still keeps per-cell markers for traceability.
        self.assertIn("[C1]", out)
        self.assertIn("Sources:", out)
        # Should have 3 unique accessions -> 3 citation IDs.
        self.assertIn("[C1]", out)
        self.assertIn("[C2]", out)
        self.assertIn("[C3]", out)

    def test_off_mode_has_no_citations_section(self) -> None:
        out = format_financial_perf_table(
            self.results,
            self.metrics,
            self.periods,
            citations_mode="off",
            terminal_width=200,
        )
        self.assertNotIn("Sources:", out)
        self.assertNotIn("Citations:", out)

    def test_inline_mode_puts_markers_in_cells(self) -> None:
        out = format_financial_perf_table(
            self.results,
            self.metrics,
            self.periods,
            citations_mode="inline",
            terminal_width=200,
        )
        self.assertIn("[C1]", out)
        self.assertIn("Citations:", out)

    def test_stacked_mode_when_table_too_wide(self) -> None:
        """Dynamic stacking: only fall back to stacked layout when the grid
        actually exceeds the terminal width."""
        # 20 cols is far too narrow for a 4-column grid with $100.0B cells.
        out = format_financial_perf_table(
            self.results, self.metrics, self.periods, terminal_width=20
        )
        self.assertIn("Revenue\n  LFY:", out)

    def test_table_mode_when_grid_fits(self) -> None:
        """Even a 60-col terminal should render as a table for 2 metrics x 3 periods."""
        out = format_financial_perf_table(
            self.results, self.metrics, self.periods, terminal_width=60
        )
        # Single header line with dashes underneath
        self.assertIn("Metric", out)
        self.assertRegex(out, r"-{3,}\s+-{3,}")
        # Not stacked: "Revenue" followed by cells, not "  LFY:"
        self.assertNotIn("Revenue\n  LFY:", out)

    def test_na_cell_when_metric_missing(self) -> None:
        results = dict(self.results)
        results["lfy-2"].metrics["revenue"] = None
        out = format_financial_perf_table(results, self.metrics, self.periods, terminal_width=200)
        self.assertIn("N/A", out)

    def test_footer_sources_group_repeated_filing_ids(self) -> None:
        periods = ["lfy"]
        results = {
            "lfy": QueryResult(
                company="Test Corp",
                cik="0000000001",
                period="lfy",
                metrics={
                    "revenue": _cv(
                        value=100e9,
                        fy=2024,
                        metric="revenue",
                        concept="Revenues",
                        accession="0000000001-25-000001",
                    ),
                    "net_income": _cv(
                        value=30e9,
                        fy=2024,
                        metric="net_income",
                        concept="NetIncomeLoss",
                        accession="0000000001-25-000001",
                    ),
                },
            )
        }

        out = format_financial_perf_table(
            results,
            ["revenue", "net_income"],
            periods,
            citations_mode="footer",
            terminal_width=200,
        )

        source_lines = [
            line for line in out.splitlines() if "0000000001-25-000001" in line
        ]
        self.assertEqual(len(source_lines), 1)
        self.assertIn("[C1, C2]", source_lines[0])


class TestCompsMultiPeriod(unittest.TestCase):
    def test_expand_comps_periods_supports_csv_and_annual_series(self) -> None:
        self.assertEqual(expand_comps_periods("lfy,lfy-1,lfy-2"), ["lfy", "lfy-1", "lfy-2"])
        self.assertEqual(expand_comps_periods("annual:3"), ["lfy", "lfy-1", "lfy-2"])

    def test_company_metric_rows_with_period_columns(self) -> None:
        periods = ["lfy", "lfy-1"]
        results_by_period = {
            "lfy": {
                "NVDA": QueryResult(
                    company="NVIDIA CORP",
                    cik="0001045810",
                    period="lfy",
                    metrics={"revenue": _cv(value=60_922_000_000, fy=2025)},
                ),
                "AMD": QueryResult(
                    company="ADVANCED MICRO DEVICES INC",
                    cik="0000002488",
                    period="lfy",
                    metrics={"revenue": _cv(value=22_680_000_000, fy=2024)},
                ),
            },
            "lfy-1": {
                "NVDA": QueryResult(
                    company="NVIDIA CORP",
                    cik="0001045810",
                    period="lfy-1",
                    metrics={"revenue": _cv(value=26_974_000_000, fy=2024)},
                ),
                "AMD": QueryResult(
                    company="ADVANCED MICRO DEVICES INC",
                    cik="0000002488",
                    period="lfy-1",
                    metrics={"revenue": _cv(value=16_434_000_000, fy=2023)},
                ),
            },
        }

        out = format_comps_multi_period_table(
            results_by_period,
            ["revenue"],
            periods,
            companies=["NVDA", "AMD"],
            citations_mode="footer",
            terminal_width=200,
        )

        header = out.splitlines()[0]
        self.assertIn("Company", header)
        self.assertIn("Metric", header)
        self.assertIn("LFY", header)
        self.assertIn("LFY-1", header)
        self.assertIn("NVIDIA CORP", out)
        self.assertIn("ADVANCED MICRO DEVICES INC", out)
        self.assertIn("Revenue", out)
        self.assertIn("$60.9B", out)
        self.assertIn("$27.0B", out)


class TestMultiPeriodLeanJson(unittest.TestCase):
    def test_lean_shape(self) -> None:
        periods = ["lfy", "lfy-1"]
        metrics = ["revenue", "net_income"]
        results = {
            "lfy": _result_for("lfy", revenue=100e9, net_income=30e9),
            "lfy-1": _result_for("lfy-1", revenue=80e9, net_income=20e9),
        }
        payload = json.loads(multi_period_to_lean_json(results, metrics, periods))

        self.assertEqual(payload["company"], "Test Corp")
        self.assertEqual(payload["cik"], "0000000001")
        self.assertEqual(payload["periods"], periods)
        self.assertIn("permalink", payload)
        self.assertIn("filings", payload)

        # metrics.<name> is a dict keyed by period.
        self.assertIn("revenue", payload["metrics"])
        self.assertIn("net_income", payload["metrics"])
        for metric in metrics:
            self.assertEqual(set(payload["metrics"][metric].keys()), set(periods))
            # Period order preserved (insertion order on the dict).
            self.assertEqual(list(payload["metrics"][metric].keys()), periods)

        # Citation registry has one entry per unique filing.
        self.assertGreaterEqual(len(payload["citations"]), 2)

    def test_full_shape_similar(self) -> None:
        periods = ["lfy"]
        metrics = ["revenue"]
        results = {"lfy": _result_for("lfy", revenue=100e9, net_income=30e9)}
        payload = json.loads(multi_period_to_full_json(results, metrics, periods))
        self.assertEqual(payload["periods"], ["lfy"])
        self.assertIn("revenue", payload["metrics"])
        self.assertIn("lfy", payload["metrics"]["revenue"])

    def test_diagnostics_preserved_by_period(self) -> None:
        periods = ["lfy", "lfy-1"]
        metrics = ["revenue"]
        results = {
            "lfy": _result_for("lfy", revenue=100e9, net_income=30e9),
            "lfy-1": _result_for("lfy-1", revenue=80e9, net_income=20e9),
        }
        results["lfy-1"].diagnostics = [
            Diagnostic(
                metric="revenue",
                kind="layer_b_unresolved",
                message="example diagnostic",
            )
        ]
        payload = json.loads(multi_period_to_lean_json(results, metrics, periods))
        self.assertIn("diagnostics_by_period", payload)
        self.assertIn("lfy-1", payload["diagnostics_by_period"])
        self.assertEqual(
            payload["diagnostics_by_period"]["lfy-1"][0]["message"],
            "example diagnostic",
        )


if __name__ == "__main__":
    unittest.main()
