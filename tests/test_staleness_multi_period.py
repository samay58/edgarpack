"""Staleness guard should skip explicit offset periods (lfy-N, ltm-N, mrq-N)."""

from __future__ import annotations

import unittest

from edgarpack.query.financials import _staleness_limit


class TestStalenessOffsetPeriods(unittest.TestCase):
    def test_bare_selectors_use_default(self) -> None:
        self.assertEqual(_staleness_limit("lfy"), 2)
        self.assertEqual(_staleness_limit("ltm"), 2)
        self.assertEqual(_staleness_limit("mrq"), 2)
        self.assertEqual(_staleness_limit("mrp"), 2)

    def test_offset_1_skipped(self) -> None:
        self.assertGreaterEqual(_staleness_limit("lfy-1"), 999)
        self.assertGreaterEqual(_staleness_limit("ltm-1"), 999)
        self.assertGreaterEqual(_staleness_limit("mrq-1"), 999)

    def test_offset_2_skipped(self) -> None:
        self.assertGreaterEqual(_staleness_limit("lfy-2"), 999)
        self.assertGreaterEqual(_staleness_limit("ltm-2"), 999)
        self.assertGreaterEqual(_staleness_limit("mrq-2"), 999)

    def test_offset_5_skipped(self) -> None:
        self.assertGreaterEqual(_staleness_limit("lfy-5"), 999)
        self.assertGreaterEqual(_staleness_limit("ltm-5"), 999)
        self.assertGreaterEqual(_staleness_limit("mrq-5"), 999)

    def test_series_still_skipped(self) -> None:
        self.assertGreaterEqual(_staleness_limit("annual:5"), 999)
        self.assertGreaterEqual(_staleness_limit("quarterly:8"), 999)

    def test_case_insensitive(self) -> None:
        self.assertGreaterEqual(_staleness_limit("LFY-3"), 999)
        self.assertGreaterEqual(_staleness_limit("  ltm-2  "), 999)


if __name__ == "__main__":
    unittest.main()
