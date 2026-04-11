"""CLI-surface tests for self-heal: badges, strict, MetricNotFound."""

from __future__ import annotations

import unittest
from datetime import date
from types import SimpleNamespace

from edgarpack.cli import _render_query_table
from edgarpack.query.models import CitedValue, QueryResult


def _cited(metric: str, concept: str, value: float, source: str = "hardcoded",
           warnings: list[str] | None = None) -> CitedValue:
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
            "revenue", "Revenues", 130e9,
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


import io
from contextlib import redirect_stderr
from unittest.mock import AsyncMock, patch

from edgarpack.cli import main


class TestCliMetricNotFound(unittest.TestCase):
    def test_unknown_metric_prints_suggestions_and_exits_nonzero(self) -> None:
        stderr = io.StringIO()
        with patch("edgarpack.query.financials.resolve_ticker",
                   new=AsyncMock(return_value=("0001045810", "NVIDIA CORP"))), \
             patch("edgarpack.query.financials.fetch_company_facts",
                   new=AsyncMock(return_value={"facts": {}})), \
             patch("edgarpack.query.financials._build_doc_map",
                   new=AsyncMock(return_value={})), \
             redirect_stderr(stderr):
            rc = main(["query", "NVDA", "xyzzy", "--period", "lfy"])
        self.assertEqual(rc, 2)  # 2 = usage-ish error
        err = stderr.getvalue()
        self.assertIn("Unknown metric", err)


if __name__ == "__main__":
    unittest.main()
