"""CLI-surface tests for self-heal: badges, strict, MetricNotFound."""

from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from edgarpack.cli import _render_query_table, main
from edgarpack.query.models import CitedValue, DerivedValue, QueryResult


def _cited(
    metric: str,
    concept: str,
    value: float,
    source: str = "hardcoded",
    warnings: list[str] | None = None,
) -> CitedValue:
    return CitedValue(
        value=value,
        unit="USD",
        metric=metric,
        concept=concept,
        period_end=date(2025, 1, 1),
        fiscal_year=2025,
        fiscal_period="FY",
        form_type="10-K",
        filed=date(2025, 2, 1),
        accession="0001045810-25-000001",
        cik="0001045810",
        company="NVIDIA CORP",
        source=source,
        warnings=warnings or [],
    )


def _args(**overrides) -> SimpleNamespace:
    defaults = dict(
        citations="inline",
        show_links="primary",
        audit=False,
        output_format="table",
        strict=False,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class TestRenderQueryTable(unittest.TestCase):
    def test_hardcoded_values_have_no_badge(self) -> None:
        qr = QueryResult(
            company="NVIDIA CORP",
            cik="0001045810",
            period="lfy",
            metrics={"revenue": _cited("revenue", "Revenues", 130e9)},
        )
        out = _render_query_table(qr, _args())
        self.assertIn("Revenue", out)
        self.assertNotIn("learned", out.lower())

    def test_learned_fuzzy_value_renders_badge(self) -> None:
        cv = _cited("revenue", "Revenues", 130e9, source="learned:fuzzy")
        qr = QueryResult(
            company="NVIDIA CORP",
            cik="0001045810",
            period="lfy",
            metrics={"revenue": cv},
        )
        out = _render_query_table(qr, _args())
        self.assertIn("learned:fuzzy", out)

    def test_learned_unverified_shows_warning_mark(self) -> None:
        cv = _cited(
            "revenue",
            "Revenues",
            130e9,
            source="learned:llm",
            warnings=["Unverified learned mapping (llm)."],
        )
        qr = QueryResult(
            company="NVIDIA CORP",
            cik="0001045810",
            period="lfy",
            metrics={"revenue": cv},
        )
        out = _render_query_table(qr, _args())
        self.assertIn("learned:llm", out)
        # Unverified -> warning mark (⚠)
        self.assertIn("⚠", out)

    def test_strict_mode_rejects_learned_values(self) -> None:
        cv = _cited("revenue", "Revenues", 130e9, source="learned:llm")
        qr = QueryResult(
            company="NVIDIA CORP",
            cik="0001045810",
            period="lfy",
            metrics={"revenue": cv},
        )
        out = _render_query_table(qr, _args(strict=True))
        self.assertIn("N/A", out)
        self.assertIn("strict", out.lower())

    def test_strict_mode_does_not_affect_hardcoded(self) -> None:
        cv = _cited("revenue", "Revenues", 130e9)
        qr = QueryResult(
            company="NVIDIA CORP",
            cik="0001045810",
            period="lfy",
            metrics={"revenue": cv},
        )
        out = _render_query_table(qr, _args(strict=True))
        self.assertNotIn("N/A", out)

    def test_footer_sources_group_repeated_filing_ids(self) -> None:
        qr = QueryResult(
            company="NVIDIA CORP",
            cik="0001045810",
            period="annual:1",
            metrics={
                "revenue": _cited("revenue", "Revenues", 130e9),
                "net_income": _cited("net_income", "NetIncomeLoss", 30e9),
            },
        )

        out = _render_query_table(qr, _args(citations="footer", show_links="none"))

        source_lines = [line for line in out.splitlines() if "0001045810-25-000001" in line]
        self.assertEqual(len(source_lines), 1)
        self.assertIn("[C1, C2]", source_lines[0])


class TestCliMetricNotFound(unittest.TestCase):
    def test_unknown_metric_prints_suggestions_and_exits_nonzero(self) -> None:
        stderr = io.StringIO()
        with (
            patch(
                "edgarpack.query.financials.resolve_ticker",
                new=AsyncMock(return_value=("0001045810", "NVIDIA CORP")),
            ),
            patch(
                "edgarpack.query.financials.fetch_company_facts",
                new=AsyncMock(return_value={"facts": {}}),
            ),
            patch("edgarpack.query.financials._build_doc_map", new=AsyncMock(return_value={})),
            redirect_stderr(stderr),
        ):
            rc = main(["query", "NVDA", "xyzzy", "--period", "lfy"])
        self.assertEqual(rc, 2)  # 2 = usage-ish error
        err = stderr.getvalue()
        self.assertIn("Unknown metric", err)


class TestLearnedSubcommand(unittest.TestCase):
    def test_list_empty(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "registry.db"
            with patch("edgarpack.query.learned_registry.DEFAULT_REGISTRY_PATH", db):
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    rc = main(["learned", "list"])
                self.assertEqual(rc, 0)
                self.assertIn("no learned mappings", stdout.getvalue().lower())

    def test_list_after_upsert(self) -> None:
        from edgarpack.query.learned_registry import LearnedRegistry

        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "registry.db"
            reg = LearnedRegistry(db_path=db)
            reg.upsert(
                cik="0001045810",
                metric="revenue",
                concept="Revenues",
                taxonomy="us-gaap",
                source="fuzzy",
                verified=True,
            )
            reg.close()
            with patch("edgarpack.query.learned_registry.DEFAULT_REGISTRY_PATH", db):
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    rc = main(["learned", "list"])
                self.assertEqual(rc, 0)
                out = stdout.getvalue()
                self.assertIn("0001045810", out)
                self.assertIn("revenue", out)
                self.assertIn("Revenues", out)

    def test_verify_promotes_unverified_row(self) -> None:
        from edgarpack.query.learned_registry import LearnedRegistry

        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "registry.db"
            reg = LearnedRegistry(db_path=db)
            reg.upsert(
                cik="A",
                metric="rev",
                concept="X",
                taxonomy="us-gaap",
                source="llm",
                verified=False,
            )
            reg.close()
            with patch("edgarpack.query.learned_registry.DEFAULT_REGISTRY_PATH", db):
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    rc = main(["learned", "verify", "A", "rev"])
                self.assertEqual(rc, 0)
            reg = LearnedRegistry(db_path=db)
            row = reg.lookup("A", "rev")
            assert row is not None
            self.assertTrue(row.verified)

    def test_clear_refuses_without_all_or_filter(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "registry.db"
            with patch("edgarpack.query.learned_registry.DEFAULT_REGISTRY_PATH", db):
                stderr = io.StringIO()
                with redirect_stderr(stderr):
                    rc = main(["learned", "clear"])
                self.assertNotEqual(rc, 0)
                self.assertIn("refusing", stderr.getvalue().lower())


class TestDiagnosticsFooter(unittest.TestCase):
    def test_diagnostics_rendered_as_footer(self) -> None:
        from edgarpack.query.models import Diagnostic

        qr = QueryResult(
            company="CRWD",
            cik="0001535527",
            period="lfy",
            metrics={"arr": None},
            diagnostics=[
                Diagnostic(
                    metric="arr",
                    kind="layer_b_unresolved",
                    message="Layer B could not resolve 'arr': no pack.",
                )
            ],
        )
        out = _render_query_table(qr, _args())
        self.assertIn("Diagnostics:", out)
        self.assertIn("arr:", out)
        self.assertIn("Layer B could not resolve", out)

    def test_no_diagnostics_no_footer(self) -> None:
        qr = QueryResult(
            company="CRWD",
            cik="0001535527",
            period="lfy",
            metrics={"revenue": _cited("revenue", "Revenues", 5e9)},
        )
        out = _render_query_table(qr, _args())
        self.assertNotIn("Diagnostics:", out)


class TestStrictHelperParity(unittest.TestCase):
    """Covers edgarpack-x1y: --strict must mean the same thing across query,
    comps, and compare. The canonical gate is query.strict.apply_strict."""

    def test_apply_strict_drops_learned_scalar(self) -> None:
        from edgarpack.query.strict import apply_strict

        qr = QueryResult(
            company="NVIDIA CORP",
            cik="0001045810",
            period="lfy",
            metrics={
                "revenue": _cited("revenue", "Revenues", 130e9, source="learned:llm"),
                "net_income": _cited("net_income", "NetIncomeLoss", 30e9),
            },
        )
        rejected = apply_strict(qr)
        self.assertEqual(rejected, ["revenue"])
        self.assertIsNone(qr.metrics["revenue"])
        self.assertIsNotNone(qr.metrics["net_income"])

    def test_apply_strict_filters_learned_out_of_list(self) -> None:
        from edgarpack.query.strict import apply_strict

        hardcoded = _cited("revenue", "Revenues", 60e9)
        learned = _cited("revenue", "Revenues", 55e9, source="learned:fuzzy")
        qr = QueryResult(
            company="NVIDIA CORP",
            cik="0001045810",
            period="annual:2",
            metrics={"revenue": [hardcoded, learned]},
        )
        rejected = apply_strict(qr)
        # List still has a hardcoded entry, so the metric itself is not
        # fully rejected; but the learned entry is gone.
        self.assertEqual(rejected, [])
        kept = qr.metrics["revenue"]
        self.assertIsInstance(kept, list)
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].source, "hardcoded")

    def test_apply_strict_rejects_derived_with_learned_component(self) -> None:
        """A DerivedValue inherits source='hardcoded' by default, so the gate
        must recurse into components; one learned input poisons the result."""
        from edgarpack.query.strict import apply_strict, is_strict_allowed

        revenue = _cited("revenue", "Revenues", 130e9, source="learned:fuzzy")
        gross_profit = _cited("gross_profit", "GrossProfit", 90e9)
        margin = DerivedValue(
            value=0.69,
            unit="pure",
            metric="gross_margin",
            concept="gross_profit / revenue",
            period_end=date(2025, 1, 1),
            fiscal_year=2025,
            fiscal_period="FY",
            form_type="10-K",
            filed=date(2025, 2, 1),
            accession="0001045810-25-000001",
            cik="0001045810",
            company="NVIDIA CORP",
            derived=True,
            components={"gross_profit": gross_profit, "revenue": revenue},
        )
        self.assertFalse(is_strict_allowed(margin))
        qr = QueryResult(
            company="NVIDIA CORP",
            cik="0001045810",
            period="lfy",
            metrics={"gross_margin": margin},
        )
        rejected = apply_strict(qr)
        self.assertEqual(rejected, ["gross_margin"])
        self.assertIsNone(qr.metrics["gross_margin"])

    def test_apply_strict_recurses_into_nested_derived_components(self) -> None:
        """The learned input may be buried one level down (e.g. ebitda inside
        ebitda_margin); the recursion must reach it."""
        from edgarpack.query.strict import is_strict_allowed

        def _derived(metric: str, components: dict[str, CitedValue]) -> DerivedValue:
            return DerivedValue(
                value=1.0,
                unit="pure",
                metric=metric,
                concept=metric,
                period_end=date(2025, 1, 1),
                fiscal_year=2025,
                fiscal_period="FY",
                form_type="10-K",
                filed=date(2025, 2, 1),
                accession="0001045810-25-000001",
                cik="0001045810",
                company="NVIDIA CORP",
                derived=True,
                components=components,
            )

        learned = _cited("d_and_a", "DepreciationAndAmortization", 5e9, source="learned:llm")
        inner = _derived(
            "ebitda",
            {"operating_income": _cited("operating_income", "OperatingIncomeLoss", 40e9)},
        )
        inner.components["d_and_a"] = learned
        outer = _derived(
            "ebitda_margin",
            {"ebitda": inner, "revenue": _cited("revenue", "Revenues", 130e9)},
        )
        self.assertFalse(is_strict_allowed(outer))

        all_hardcoded = _derived(
            "ebitda_margin",
            {
                "ebitda": _derived(
                    "ebitda",
                    {"operating_income": _cited("operating_income", "OperatingIncomeLoss", 40e9)},
                ),
                "revenue": _cited("revenue", "Revenues", 130e9),
            },
        )
        self.assertTrue(is_strict_allowed(all_hardcoded))

    def test_apply_strict_is_idempotent(self) -> None:
        """Second call returns empty rejections so cmd-level pre-filtering
        does not double-count or misreport."""
        from edgarpack.query.strict import apply_strict

        qr = QueryResult(
            company="NVIDIA CORP",
            cik="0001045810",
            period="lfy",
            metrics={"revenue": _cited("revenue", "Revenues", 130e9, source="learned:llm")},
        )
        first = apply_strict(qr)
        second = apply_strict(qr)
        self.assertEqual(first, ["revenue"])
        self.assertEqual(second, [])


if __name__ == "__main__":
    unittest.main()
