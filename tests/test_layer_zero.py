"""Tests for Layer 0 alias resolution."""

from __future__ import annotations

import unittest

from edgarpack.query.layer_zero import (
    METRIC_ALIASES,
    MetricNotFound,
    resolve_alias,
    suggest_metrics,
)


class TestResolveAlias(unittest.TestCase):
    def test_canonical_name_passes_through(self) -> None:
        self.assertEqual(resolve_alias("revenue"), "revenue")

    def test_known_alias_resolves(self) -> None:
        self.assertEqual(resolve_alias("fcf"), "free_cash_flow")

    def test_alias_is_case_insensitive(self) -> None:
        self.assertEqual(resolve_alias("FCF"), "free_cash_flow")

    def test_alias_strips_whitespace(self) -> None:
        self.assertEqual(resolve_alias("  fcf  "), "free_cash_flow")

    def test_unknown_name_returns_unchanged(self) -> None:
        # resolve_alias does not raise on unknown; that's the caller's job.
        self.assertEqual(resolve_alias("some_unknown_metric"), "some_unknown_metric")

    def test_common_aliases_present(self) -> None:
        for alias in ("fcf", "opinc", "rev", "ni", "cogs", "gp", "ocf", "eps"):
            self.assertIn(alias, METRIC_ALIASES)


class TestSuggestMetrics(unittest.TestCase):
    def test_suggests_close_match(self) -> None:
        known = {"revenue", "operating_income", "net_income"}
        out = suggest_metrics("revenu", known, n=3)
        self.assertIn("revenue", out)

    def test_returns_empty_on_no_close_match(self) -> None:
        known = {"revenue", "net_income"}
        out = suggest_metrics("xyzzy_nonsense", known, n=3)
        self.assertEqual(out, [])

    def test_respects_limit(self) -> None:
        known = {"revenue", "revenues", "revenu_x"}
        out = suggest_metrics("revenu", known, n=2)
        self.assertLessEqual(len(out), 2)


class TestMetricNotFound(unittest.TestCase):
    def test_carries_name_and_suggestions(self) -> None:
        err = MetricNotFound("revenu", suggestions=["revenue"])
        self.assertEqual(err.metric_name, "revenu")
        self.assertEqual(err.suggestions, ["revenue"])
        self.assertIn("revenu", str(err))
        self.assertIn("revenue", str(err))


if __name__ == "__main__":
    unittest.main()
