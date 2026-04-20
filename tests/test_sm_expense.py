"""sm_expense / sm_intensity return None for SG&A-only filers; value when tagged."""

from __future__ import annotations

import unittest

from edgarpack.query.concepts import METRIC_MAP, resolve_concept
from edgarpack.query.financials import _compute_derived
from edgarpack.query.periods import select_period


def _entry(fy: int, val: float) -> dict:
    return {
        "val": val,
        "start": f"{fy}-01-01",
        "end": f"{fy}-12-31",
        "fy": fy,
        "fp": "FY",
        "form": "10-K",
        "accn": f"0000000001-{str(fy + 1)[-2:]}-000001",
        "filed": f"{fy + 1}-03-01",
    }


def _facts(concepts: dict[str, list[dict]]) -> dict:
    return {"us-gaap": {c: {"units": {"USD": entries}} for c, entries in concepts.items()}}


class TestSmExpense(unittest.TestCase):
    def test_sm_expense_resolves_when_tagged(self) -> None:
        facts = _facts(
            {
                "SellingAndMarketingExpense": [_entry(2024, 200_000_000)],
            }
        )
        meta = METRIC_MAP["sm_expense"]
        resolved = resolve_concept("sm_expense", facts)
        self.assertIsNotNone(resolved)
        concept, taxonomy = resolved
        value = select_period(
            facts,
            concept,
            "sm_expense",
            meta,
            "Test",
            "0000000001",
            "lfy",
            taxonomy=taxonomy,
        )
        self.assertIsNotNone(value)
        self.assertEqual(value.value, 200_000_000)

    def test_sm_expense_returns_none_for_sga_only_filer(self) -> None:
        facts = _facts(
            {
                "SellingGeneralAndAdministrativeExpense": [_entry(2024, 500_000_000)],
            }
        )
        # sm_expense should NOT silently fall back to SG&A.
        resolved = resolve_concept("sm_expense", facts)
        self.assertIsNone(resolved)

    def test_sm_intensity_none_when_sm_missing(self) -> None:
        facts = _facts(
            {
                "Revenues": [_entry(2024, 1_000_000_000)],
                "SellingGeneralAndAdministrativeExpense": [_entry(2024, 100_000_000)],
            }
        )
        meta = METRIC_MAP["sm_intensity"]
        result = _compute_derived(facts, "sm_intensity", meta, "Test", "0000000001", "lfy", None)
        self.assertIsNone(result)

    def test_sm_intensity_computes_when_sm_tagged(self) -> None:
        facts = _facts(
            {
                "Revenues": [_entry(2024, 1_000_000_000)],
                "SellingAndMarketingExpense": [_entry(2024, 200_000_000)],
            }
        )
        meta = METRIC_MAP["sm_intensity"]
        result = _compute_derived(facts, "sm_intensity", meta, "Test", "0000000001", "lfy", None)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.value, 0.2, places=6)


if __name__ == "__main__":
    unittest.main()
