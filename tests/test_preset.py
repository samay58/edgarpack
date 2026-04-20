"""Preset expansion for --preset perf + --metrics union semantics."""

from __future__ import annotations

import unittest

from edgarpack.query.presets import PRESETS, expand_metrics


class TestExpandMetrics(unittest.TestCase):
    def test_no_args_returns_none(self) -> None:
        self.assertIsNone(expand_metrics(None, None))
        self.assertIsNone(expand_metrics("", None))
        self.assertIsNone(expand_metrics("   ", ""))

    def test_metrics_only(self) -> None:
        self.assertEqual(
            expand_metrics("revenue,net_income", None),
            ["revenue", "net_income"],
        )

    def test_preset_only(self) -> None:
        result = expand_metrics(None, "perf")
        self.assertEqual(result, list(PRESETS["perf"]))

    def test_preset_plus_metrics_union(self) -> None:
        result = expand_metrics("fcf_to_net_income,eps_growth_yoy", "perf")
        # Preset entries come first
        for i, metric in enumerate(PRESETS["perf"]):
            self.assertEqual(result[i], metric)
        # Appended explicit metrics come after
        self.assertIn("fcf_to_net_income", result)
        self.assertIn("eps_growth_yoy", result)
        # No duplicates
        self.assertEqual(len(result), len(set(result)))

    def test_duplicate_metric_deduped(self) -> None:
        # revenue is in preset perf; passing it again via --metrics should dedupe.
        result = expand_metrics("revenue,gross_margin,revenue", "perf")
        self.assertEqual(result.count("revenue"), 1)
        self.assertEqual(result.count("gross_margin"), 1)

    def test_unknown_preset_raises(self) -> None:
        with self.assertRaises(ValueError):
            expand_metrics(None, "bogus")

    def test_whitespace_in_csv_trimmed(self) -> None:
        result = expand_metrics(" revenue , net_income ", None)
        self.assertEqual(result, ["revenue", "net_income"])


class TestPresetPerfContents(unittest.TestCase):
    def test_perf_preset_has_nine_metrics(self) -> None:
        self.assertEqual(len(PRESETS["perf"]), 9)

    def test_perf_preset_starts_with_revenue(self) -> None:
        self.assertEqual(PRESETS["perf"][0], "revenue")

    def test_perf_preset_contains_cagr(self) -> None:
        self.assertIn("revenue_cagr_3y", PRESETS["perf"])

    def test_perf_preset_contains_margins(self) -> None:
        for m in ("gross_margin", "operating_margin", "net_margin", "fcf_margin"):
            self.assertIn(m, PRESETS["perf"])

    def test_perf_preset_contains_intensity(self) -> None:
        self.assertIn("r_and_d_intensity", PRESETS["perf"])
        self.assertIn("sga_intensity", PRESETS["perf"])


if __name__ == "__main__":
    unittest.main()
