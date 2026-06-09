"""End-to-end self-heal integration test with real financials() call.

Uses fully mocked SEC responses and a tmp SQLite registry. No network calls.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from edgarpack.query.layer_zero import resolve_alias

_P = "edgarpack.query.financials"

MOCK_SUBMISSIONS = {
    "cik": 1045810,
    "name": "NVIDIA CORP",
    "filings": {
        "recent": {
            "accessionNumber": ["0001045810-25-000001", "0001045810-24-000001"],
            "primaryDocument": ["nvda-20250126.htm", "nvda-20240128.htm"],
        },
    },
}

# Facts blob where 'Revenues' is the standard concept (hardcoded path finds it)
# and 'CashFlowFromOperationsNovelTag2026' is a synthetic concept name NOT in
# METRIC_MAP for operating_cash_flow, so querying it forces self-heal.
FACTS_WITH_NOVEL_CONCEPT = {
    "facts": {
        "us-gaap": {
            "Revenues": {
                "units": {
                    "USD": [
                        {
                            "val": 130_000_000_000,
                            "fy": 2025,
                            "fp": "FY",
                            "start": "2024-01-29",
                            "end": "2025-01-26",
                            "form": "10-K",
                            "filed": "2025-02-21",
                            "accn": "0001045810-25-000001",
                            "frame": "CY2025",
                        },
                        {
                            "val": 60_000_000_000,
                            "fy": 2024,
                            "fp": "FY",
                            "start": "2023-01-30",
                            "end": "2024-01-28",
                            "form": "10-K",
                            "filed": "2024-02-21",
                            "accn": "0001045810-24-000001",
                            "frame": "CY2024",
                        },
                    ]
                }
            },
            "CashFlowFromOperationsNovelTag2026": {
                "units": {
                    "USD": [
                        {
                            "val": 28_000_000_000,
                            "fy": 2025,
                            "fp": "FY",
                            "start": "2024-01-29",
                            "end": "2025-01-26",
                            "form": "10-K",
                            "filed": "2025-02-21",
                            "accn": "0001045810-25-000001",
                        },
                        {
                            "val": 25_000_000_000,
                            "fy": 2024,
                            "fp": "FY",
                            "start": "2023-01-30",
                            "end": "2024-01-28",
                            "form": "10-K",
                            "filed": "2024-02-21",
                            "accn": "0001045810-24-000001",
                        },
                    ]
                }
            },
        }
    }
}


# Same shape as FACTS_WITH_NOVEL_CONCEPT, but the novel operating-cash-flow
# tag is close enough to the metric's token pool for the fuzzy matcher
# (cash/provided/operating/activities), with two annual years so the
# verifier has a prior-year ground truth to derive.
FACTS_WITH_FUZZY_NOVEL_CONCEPT = {
    "facts": {
        "us-gaap": {
            "Revenues": FACTS_WITH_NOVEL_CONCEPT["facts"]["us-gaap"]["Revenues"],
            "CashProvidedByOperatingActivitiesNovel2026": {
                "units": {
                    "USD": [
                        {
                            "val": 28_000_000_000,
                            "fy": 2025,
                            "fp": "FY",
                            "start": "2024-01-29",
                            "end": "2025-01-26",
                            "form": "10-K",
                            "filed": "2025-02-21",
                            "accn": "0001045810-25-000001",
                        },
                        {
                            "val": 25_000_000_000,
                            "fy": 2024,
                            "fp": "FY",
                            "start": "2023-01-30",
                            "end": "2024-01-28",
                            "form": "10-K",
                            "filed": "2024-02-21",
                            "accn": "0001045810-24-000001",
                        },
                    ]
                }
            },
        }
    }
}


class TestSelfHealIntegration(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db_path = Path(self._tmp.name) / "registry.db"

    async def test_alias_only_query_goes_through_hardcoded(self) -> None:
        from edgarpack.query.financials import financials

        with (
            patch(
                f"{_P}.resolve_ticker", new=AsyncMock(return_value=("0001045810", "NVIDIA CORP"))
            ),
            patch(
                f"{_P}.fetch_company_facts", new=AsyncMock(return_value=FACTS_WITH_NOVEL_CONCEPT)
            ),
            patch(
                f"{_P}._build_doc_map",
                new=AsyncMock(
                    return_value={
                        "0001045810-25-000001": "nvda-20250126.htm",
                        "0001045810-24-000001": "nvda-20240128.htm",
                    }
                ),
            ),
            patch("edgarpack.query.learned_registry.DEFAULT_REGISTRY_PATH", self.db_path),
        ):
            # 'rev' -> 'revenue' via alias. Revenue resolves through METRIC_MAP.
            result = await financials("NVDA", metrics="rev", period="lfy")

        self.assertEqual(resolve_alias("rev"), "revenue")
        self.assertIn("revenue", result.metrics)
        rev = result.metrics["revenue"]
        self.assertIsNotNone(rev)
        # Hardcoded path, no learned badge
        self.assertEqual(rev.source, "hardcoded")

    async def test_hardcoded_still_hardcoded(self) -> None:
        # Querying a canonical name that resolves through METRIC_MAP should
        # not touch self-heal at all.
        from edgarpack.query.financials import financials

        with (
            patch(
                f"{_P}.resolve_ticker", new=AsyncMock(return_value=("0001045810", "NVIDIA CORP"))
            ),
            patch(
                f"{_P}.fetch_company_facts", new=AsyncMock(return_value=FACTS_WITH_NOVEL_CONCEPT)
            ),
            patch(f"{_P}._build_doc_map", new=AsyncMock(return_value={})),
            patch("edgarpack.query.learned_registry.DEFAULT_REGISTRY_PATH", self.db_path),
        ):
            result = await financials("NVDA", metrics="revenue", period="lfy")

        rev = result.metrics["revenue"]
        self.assertIsNotNone(rev)
        self.assertEqual(rev.source, "hardcoded")

    async def test_fuzzy_discovery_verifies_without_explicit_prior_year(self) -> None:
        """Regression for the masking pattern: financials() never passes a
        prior_year_cited into try_learn, so verification used to fail on
        every production self-heal and the value was withheld. The resolve
        path must now verify against the proposed concept's own history."""
        from edgarpack.query.financials import financials
        from edgarpack.query.learned_registry import LearnedRegistry

        with (
            patch(
                f"{_P}.resolve_ticker", new=AsyncMock(return_value=("0001045810", "NVIDIA CORP"))
            ),
            patch(
                f"{_P}.fetch_company_facts",
                new=AsyncMock(return_value=FACTS_WITH_FUZZY_NOVEL_CONCEPT),
            ),
            patch(f"{_P}._build_doc_map", new=AsyncMock(return_value={})),
            patch("edgarpack.query.learned_registry.DEFAULT_REGISTRY_PATH", self.db_path),
        ):
            result = await financials("NVDA", metrics="operating_cash_flow", period="lfy")

        ocf = result.metrics["operating_cash_flow"]
        self.assertIsNotNone(ocf)
        assert ocf is not None and not isinstance(ocf, list)
        self.assertEqual(ocf.source, "learned:fuzzy")
        self.assertEqual(ocf.value, 28_000_000_000)
        self.assertEqual(ocf.concept, "CashProvidedByOperatingActivitiesNovel2026")
        diag_kinds = [d.kind for d in result.diagnostics]
        self.assertNotIn("learned_mapping_unverified", diag_kinds)

        reg = LearnedRegistry(db_path=self.db_path)
        row = reg.lookup("0001045810", "operating_cash_flow")
        assert row is not None
        self.assertTrue(row.verified)
        self.assertEqual(row.verif_method, "order_of_magnitude")

    async def test_registry_hit_returns_learned_cached(self) -> None:
        """Pre-seeded registry row short-circuits self-heal and returns
        source='learned:cached'."""
        from edgarpack.query.learned_registry import LearnedRegistry

        # Pre-seed the registry
        reg = LearnedRegistry(db_path=self.db_path)
        reg.upsert(
            cik="0001045810",
            metric="operating_cash_flow",
            concept="CashFlowFromOperationsNovelTag2026",
            taxonomy="us-gaap",
            source="fuzzy",
            verified=True,
            verif_method="order_of_magnitude",
            value_sample=28_000_000_000.0,
        )
        reg.close()

        # Force METRIC_MAP's operating_cash_flow to a concepts tuple that
        # doesn't match FACTS_WITH_NOVEL_CONCEPT, forcing fallback.
        from edgarpack.query import concepts as _concepts_mod

        patched_meta = _concepts_mod.MetricMeta(
            concepts=("NonexistentOpCfConcept",),
            duration=True,
        )

        from edgarpack.query.financials import financials

        with (
            patch.dict(
                _concepts_mod.METRIC_MAP,
                {"operating_cash_flow": patched_meta},
                clear=False,
            ),
            patch(
                f"{_P}.resolve_ticker", new=AsyncMock(return_value=("0001045810", "NVIDIA CORP"))
            ),
            patch(
                f"{_P}.fetch_company_facts", new=AsyncMock(return_value=FACTS_WITH_NOVEL_CONCEPT)
            ),
            patch(
                f"{_P}._build_doc_map",
                new=AsyncMock(
                    return_value={
                        "0001045810-25-000001": "nvda-20250126.htm",
                    }
                ),
            ),
            patch("edgarpack.query.learned_registry.DEFAULT_REGISTRY_PATH", self.db_path),
        ):
            result = await financials("NVDA", metrics="operating_cash_flow", period="lfy")

        ocf = result.metrics["operating_cash_flow"]
        self.assertIsNotNone(ocf)
        assert ocf is not None
        # Registry hit -> learned:cached
        self.assertEqual(ocf.source, "learned:cached")
        self.assertEqual(ocf.concept, "CashFlowFromOperationsNovelTag2026")


if __name__ == "__main__":
    unittest.main()
