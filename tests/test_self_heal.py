"""Tests for self-heal internals (fuzzy match, verifier, orchestrator)."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from edgarpack.query.concepts import MetricMeta
from edgarpack.query.learned_registry import LearnedRegistry
from edgarpack.query.models import CitedValue
from edgarpack.query.self_heal import (
    METRIC_HINTS,
    _company_concepts,
    _fuzzy_match,
    _llm_backend_available,
    _llm_propose,
    try_learn,
    verify_order_of_magnitude,
)

# Small synthetic companyfacts fragment for fuzzy-match tests
_FAKE_FACTS = {
    "us-gaap": {
        "Revenues": {
            "units": {
                "USD": [
                    {
                        "val": 130_000_000_000,
                        "start": "2024-01-01",
                        "end": "2024-12-31",
                        "fy": 2024,
                        "fp": "FY",
                        "form": "10-K",
                        "accn": "0001045810-25-000001",
                        "filed": "2025-02-20",
                    }
                ]
            },
        },
        "NetCashProvidedByUsedInOperatingActivities": {
            "units": {
                "USD": [
                    {
                        "val": 28_000_000_000,
                        "start": "2024-01-01",
                        "end": "2024-12-31",
                        "fy": 2024,
                        "fp": "FY",
                        "form": "10-K",
                        "accn": "0001045810-25-000001",
                        "filed": "2025-02-20",
                    }
                ]
            },
        },
        "PaymentsToAcquirePropertyPlantAndEquipment": {
            "units": {
                "USD": [
                    {
                        "val": 1_100_000_000,
                        "start": "2024-01-01",
                        "end": "2024-12-31",
                        "fy": 2024,
                        "fp": "FY",
                        "form": "10-K",
                        "accn": "0001045810-25-000001",
                        "filed": "2025-02-20",
                    }
                ]
            },
        },
        "EarningsPerShareDiluted": {
            "units": {
                "USD/shares": [
                    {
                        "val": 2.97,
                        "start": "2024-01-01",
                        "end": "2024-12-31",
                        "fy": 2024,
                        "fp": "FY",
                        "form": "10-K",
                        "accn": "0001045810-25-000001",
                        "filed": "2025-02-20",
                    }
                ]
            },
        },
    },
    "dei": {
        # Non-financial, should be ignored
        "EntityCommonStockSharesOutstanding": {
            "units": {"shares": [{"val": 24_600_000_000, "fy": 2024, "fp": "FY"}]},
        },
    },
}

_BAD_REVENUE_FACTS = {
    "us-gaap": {
        "ContractWithCustomerLiabilityRevenueRecognized": {
            "units": {
                "USD": [
                    {
                        "val": 3_500_000_000,
                        "fy": 2026,
                        "fp": "Q1",
                        "form": "10-Q",
                        "start": "2026-01-01",
                        "end": "2026-03-31",
                        "accn": "0001652044-26-000020",
                        "filed": "2026-04-25",
                    }
                ]
            }
        }
    }
}

_BAD_GROSS_PROFIT_FACTS = {
    "us-gaap": {
        "ContractWithCustomerAssetGross": {
            "units": {
                "USD": [
                    {
                        "val": 185_000_000,
                        "fy": 2025,
                        "fp": "FY",
                        "form": "10-K",
                        "end": "2025-12-31",
                        "accn": "0001783879-26-000029",
                        "filed": "2026-02-20",
                    }
                ]
            }
        },
        "AvailableForSaleDebtSecuritiesAccumulatedGrossUnrealizedGainBeforeTax": {
            "units": {
                "USD": [
                    {
                        "val": 641_000_000,
                        "fy": 2025,
                        "fp": "FY",
                        "form": "10-K",
                        "end": "2025-12-31",
                        "accn": "0001326801-26-000001",
                        "filed": "2026-02-04",
                    }
                ]
            }
        },
    }
}


class TestCompanyConcepts(unittest.TestCase):
    def test_lists_us_gaap_and_ifrs_concepts(self) -> None:
        concepts = _company_concepts(_FAKE_FACTS)
        self.assertIn(("Revenues", "us-gaap"), concepts)
        self.assertIn(("NetCashProvidedByUsedInOperatingActivities", "us-gaap"), concepts)

    def test_skips_dei_and_other_taxonomies(self) -> None:
        concepts = _company_concepts(_FAKE_FACTS)
        for _name, taxonomy in concepts:
            self.assertIn(taxonomy, ("us-gaap", "ifrs-full"))

    def test_skips_concepts_with_no_non_none_values(self) -> None:
        facts = {
            "us-gaap": {
                "AllNone": {"units": {"USD": [{"val": None}]}},
                "OK": {"units": {"USD": [{"val": 100}]}},
            }
        }
        concepts = _company_concepts(facts)
        names = {c[0] for c in concepts}
        self.assertIn("OK", names)
        self.assertNotIn("AllNone", names)


class TestFuzzyMatch(unittest.TestCase):
    def test_matches_operating_cash_flow_on_hint(self) -> None:
        candidates = _company_concepts(_FAKE_FACTS)
        hit = _fuzzy_match(
            metric="operating_cash_flow",
            candidates=candidates,
            facts=_FAKE_FACTS,
        )
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit[0], "NetCashProvidedByUsedInOperatingActivities")
        self.assertEqual(hit[1], "us-gaap")

    def test_matches_capex_via_hint_tokens(self) -> None:
        candidates = _company_concepts(_FAKE_FACTS)
        hit = _fuzzy_match(
            metric="capex",
            candidates=candidates,
            facts=_FAKE_FACTS,
        )
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit[0], "PaymentsToAcquirePropertyPlantAndEquipment")

    def test_returns_none_below_threshold(self) -> None:
        candidates = _company_concepts(_FAKE_FACTS)
        hit = _fuzzy_match(
            metric="xyz_nonsense_unrelated",
            candidates=candidates,
            facts=_FAKE_FACTS,
        )
        self.assertIsNone(hit)

    def test_metric_hints_dict_is_non_empty(self) -> None:
        # Sanity check: we want at least the core metrics hinted
        for m in ("revenue", "operating_cash_flow", "capex", "free_cash_flow"):
            self.assertIn(m, METRIC_HINTS)

    def test_revenue_rejects_contract_liability_revenue_recognized(self) -> None:
        candidates = _company_concepts(_BAD_REVENUE_FACTS)
        hit = _fuzzy_match(
            metric="revenue",
            candidates=candidates,
            facts=_BAD_REVENUE_FACTS,
        )
        self.assertIsNone(hit)

    def test_gross_profit_rejects_balance_sheet_gross_concepts(self) -> None:
        candidates = _company_concepts(_BAD_GROSS_PROFIT_FACTS)
        hit = _fuzzy_match(
            metric="gross_profit",
            candidates=candidates,
            facts=_BAD_GROSS_PROFIT_FACTS,
        )
        self.assertIsNone(hit)


class TestLlmPropose(unittest.TestCase):
    def test_llm_backend_available_returns_bool(self) -> None:
        # Don't assert which backend; only that the function returns bool cleanly.
        self.assertIsInstance(_llm_backend_available(), bool)

    def test_llm_propose_returns_none_without_backend(self) -> None:
        with patch("edgarpack.query.self_heal._LLM_CMD", None):
            out = _llm_propose(
                metric="revenue",
                company="Test Co",
                candidates=[("Revenues", "us-gaap")],
            )
            self.assertIsNone(out)

    def test_llm_propose_parses_valid_response(self) -> None:
        fake_stdout = json.dumps({"concept": "Revenues", "taxonomy": "us-gaap"})

        class _FakeCompleted:
            def __init__(self, stdout: str) -> None:
                self.stdout = stdout
                self.stderr = ""
                self.returncode = 0

        with (
            patch("edgarpack.query.self_heal._LLM_CMD", "codex"),
            patch(
                "edgarpack.query.self_heal.subprocess.run", return_value=_FakeCompleted(fake_stdout)
            ),
        ):
            out = _llm_propose(
                metric="revenue",
                company="Test Co",
                candidates=[("Revenues", "us-gaap"), ("SalesRevenueNet", "us-gaap")],
            )
            self.assertEqual(out, ("Revenues", "us-gaap"))

    def test_llm_propose_rejects_hallucinated_concept(self) -> None:
        fake_stdout = json.dumps({"concept": "MadeUpConcept", "taxonomy": "us-gaap"})

        class _FakeCompleted:
            stdout = fake_stdout
            stderr = ""
            returncode = 0

        with (
            patch("edgarpack.query.self_heal._LLM_CMD", "codex"),
            patch("edgarpack.query.self_heal.subprocess.run", return_value=_FakeCompleted),
        ):
            out = _llm_propose(
                metric="revenue",
                company="Test Co",
                candidates=[("Revenues", "us-gaap")],
            )
            self.assertIsNone(out)

    def test_llm_propose_returns_none_on_null_response(self) -> None:
        class _FakeCompleted:
            stdout = "null"
            stderr = ""
            returncode = 0

        with (
            patch("edgarpack.query.self_heal._LLM_CMD", "codex"),
            patch("edgarpack.query.self_heal.subprocess.run", return_value=_FakeCompleted),
        ):
            out = _llm_propose(
                metric="revenue",
                company="Test Co",
                candidates=[("Revenues", "us-gaap")],
            )
            self.assertIsNone(out)

    def test_llm_propose_returns_none_on_malformed_json(self) -> None:
        class _FakeCompleted:
            stdout = "this is not json at all"
            stderr = ""
            returncode = 0

        with (
            patch("edgarpack.query.self_heal._LLM_CMD", "codex"),
            patch("edgarpack.query.self_heal.subprocess.run", return_value=_FakeCompleted),
        ):
            out = _llm_propose(
                metric="revenue",
                company="Test Co",
                candidates=[("Revenues", "us-gaap")],
            )
            self.assertIsNone(out)


class TestVerifyOrderOfMagnitude(unittest.TestCase):
    def test_exact_match_passes(self) -> None:
        self.assertTrue(verify_order_of_magnitude(100.0, 100.0))

    def test_within_2x_passes(self) -> None:
        self.assertTrue(verify_order_of_magnitude(150.0, 100.0))
        self.assertTrue(verify_order_of_magnitude(70.0, 100.0))

    def test_within_4x_passes(self) -> None:
        self.assertTrue(verify_order_of_magnitude(399.0, 100.0))
        self.assertTrue(verify_order_of_magnitude(26.0, 100.0))

    def test_beyond_4x_fails(self) -> None:
        self.assertFalse(verify_order_of_magnitude(500.0, 100.0))
        self.assertFalse(verify_order_of_magnitude(20.0, 100.0))

    def test_zero_prior_year_fails(self) -> None:
        self.assertFalse(verify_order_of_magnitude(100.0, 0.0))

    def test_none_prior_year_fails(self) -> None:
        self.assertFalse(verify_order_of_magnitude(100.0, None))

    def test_handles_negative_values(self) -> None:
        # Operating losses: -100 and -150 should pass
        self.assertTrue(verify_order_of_magnitude(-150.0, -100.0))
        # Sign flip is suspicious but within 4x magnitude is still accepted
        self.assertTrue(verify_order_of_magnitude(100.0, -150.0))


def _prior_year_cited(value: float = 100_000_000_000.0) -> CitedValue:
    return CitedValue(
        value=value,
        unit="USD",
        metric="revenue",
        concept="Revenues",
        period_end=date(2023, 1, 31),
        fiscal_year=2023,
        fiscal_period="FY",
        form_type="10-K",
        filed=date(2023, 2, 1),
        accession="0001045810-23-000001",
        cik="0001045810",
        company="NVIDIA CORP",
    )


class TestTryLearn(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db_path = Path(self._tmp.name) / "registry.db"

    def test_registry_hit_short_circuits(self) -> None:
        reg = LearnedRegistry(db_path=self.db_path)
        reg.upsert(
            cik="0001045810",
            metric="revenue",
            concept="Revenues",
            taxonomy="us-gaap",
            source="fuzzy",
            verified=True,
            verif_method="order_of_magnitude",
            value_sample=130e9,
        )
        reg.close()

        meta = MetricMeta(concepts=(), duration=True)
        result = try_learn(
            metric="revenue",
            meta=meta,
            facts=_FAKE_FACTS,
            cik="0001045810",
            company="NVIDIA CORP",
            prior_year_cited=_prior_year_cited(),
            doc_map={},
            registry_path=self.db_path,
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.concept, "Revenues")
        self.assertEqual(result.source, "learned:cached")

        # Hit count incremented
        reg = LearnedRegistry(db_path=self.db_path)
        row = reg.lookup("0001045810", "revenue")
        assert row is not None
        self.assertEqual(row.hit_count, 1)

    def test_fuzzy_path_persists_and_returns_learned_fuzzy(self) -> None:
        meta = MetricMeta(concepts=(), duration=True)
        result = try_learn(
            metric="operating_cash_flow",
            meta=meta,
            facts=_FAKE_FACTS,
            cik="0001045810",
            company="NVIDIA CORP",
            prior_year_cited=_prior_year_cited(value=25e9),
            doc_map={},
            registry_path=self.db_path,
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.concept, "NetCashProvidedByUsedInOperatingActivities")
        self.assertEqual(result.source, "learned:fuzzy")
        self.assertEqual(result.value, 28_000_000_000)

        # Row persisted
        reg = LearnedRegistry(db_path=self.db_path)
        row = reg.lookup("0001045810", "operating_cash_flow")
        assert row is not None
        self.assertTrue(row.verified)
        self.assertEqual(row.source, "fuzzy")

    def test_returns_none_when_no_fuzzy_or_llm_match(self) -> None:
        meta = MetricMeta(concepts=(), duration=True)
        with patch("edgarpack.query.self_heal._LLM_CMD", None):
            result = try_learn(
                metric="totally_unknown_xyz",
                meta=meta,
                facts=_FAKE_FACTS,
                cik="0001045810",
                company="NVIDIA CORP",
                prior_year_cited=_prior_year_cited(),
                doc_map={},
                registry_path=self.db_path,
            )
        self.assertIsNone(result)

    def test_unverified_persists_but_is_not_returned(self) -> None:
        # Force verification to fail by giving a prior-year value that's 28x off
        meta = MetricMeta(concepts=(), duration=True)
        result = try_learn(
            metric="operating_cash_flow",
            meta=meta,
            facts=_FAKE_FACTS,
            cik="0001045810",
            company="NVIDIA CORP",
            prior_year_cited=_prior_year_cited(value=1.0),
            doc_map={},
            registry_path=self.db_path,
        )
        self.assertIsNone(result)

        reg = LearnedRegistry(db_path=self.db_path)
        row = reg.lookup("0001045810", "operating_cash_flow")
        assert row is not None
        self.assertFalse(row.verified)

    def test_no_prior_year_verifies_from_concepts_own_annual_history(self) -> None:
        """The production resolve path never passes prior_year_cited; try_learn
        must derive the ground truth from the proposed concept's own annual
        history instead of always failing verification."""
        facts = {
            "us-gaap": {
                "NetCashProvidedByUsedInOperatingActivities": {
                    "units": {
                        "USD": [
                            {
                                "val": 28_000_000_000,
                                "start": "2024-01-01",
                                "end": "2024-12-31",
                                "fy": 2024,
                                "fp": "FY",
                                "form": "10-K",
                                "accn": "0001045810-25-000001",
                                "filed": "2025-02-20",
                            },
                            {
                                "val": 25_000_000_000,
                                "start": "2023-01-01",
                                "end": "2023-12-31",
                                "fy": 2023,
                                "fp": "FY",
                                "form": "10-K",
                                "accn": "0001045810-24-000001",
                                "filed": "2024-02-20",
                            },
                        ]
                    },
                },
            }
        }
        meta = MetricMeta(concepts=(), duration=True)
        result = try_learn(
            metric="operating_cash_flow",
            meta=meta,
            facts=facts,
            cik="0001045810",
            company="NVIDIA CORP",
            doc_map={},
            registry_path=self.db_path,
        )
        self.assertIsNotNone(result)
        assert result is not None and not isinstance(result, list)
        self.assertEqual(result.source, "learned:fuzzy")
        self.assertEqual(result.value, 28_000_000_000)

        reg = LearnedRegistry(db_path=self.db_path)
        row = reg.lookup("0001045810", "operating_cash_flow")
        assert row is not None
        self.assertTrue(row.verified)
        self.assertEqual(row.verif_method, "order_of_magnitude")

    def test_no_prior_year_and_single_annual_stays_unverified(self) -> None:
        """One annual entry leaves nothing to verify against: the row persists
        with verified=0 and the value is withheld."""
        meta = MetricMeta(concepts=(), duration=True)
        result = try_learn(
            metric="operating_cash_flow",
            meta=meta,
            facts=_FAKE_FACTS,
            cik="0001045810",
            company="NVIDIA CORP",
            doc_map={},
            registry_path=self.db_path,
        )
        self.assertIsNone(result)

        reg = LearnedRegistry(db_path=self.db_path)
        row = reg.lookup("0001045810", "operating_cash_flow")
        assert row is not None
        self.assertFalse(row.verified)

    def test_unverified_cached_row_falls_through_to_rediscovery(self) -> None:
        """An unverified cached row used to return None forever, even after the
        company filed enough history to verify. It must retry discovery and
        promote the row when verification now passes."""
        from edgarpack.query.models import Diagnostic

        reg = LearnedRegistry(db_path=self.db_path)
        reg.upsert(
            cik="0001045810",
            metric="operating_cash_flow",
            concept="NetCashProvidedByUsedInOperatingActivities",
            taxonomy="us-gaap",
            source="fuzzy",
            verified=False,
            verif_method=None,
            value_sample=28e9,
        )
        reg.close()

        facts = {
            "us-gaap": {
                "NetCashProvidedByUsedInOperatingActivities": {
                    "units": {
                        "USD": [
                            {
                                "val": 28_000_000_000,
                                "start": "2024-01-01",
                                "end": "2024-12-31",
                                "fy": 2024,
                                "fp": "FY",
                                "form": "10-K",
                                "accn": "0001045810-25-000001",
                                "filed": "2025-02-20",
                            },
                            {
                                "val": 25_000_000_000,
                                "start": "2023-01-01",
                                "end": "2023-12-31",
                                "fy": 2023,
                                "fp": "FY",
                                "form": "10-K",
                                "accn": "0001045810-24-000001",
                                "filed": "2024-02-20",
                            },
                        ]
                    },
                },
            }
        }
        meta = MetricMeta(concepts=(), duration=True)
        diagnostics: list[Diagnostic] = []
        result = try_learn(
            metric="operating_cash_flow",
            meta=meta,
            facts=facts,
            cik="0001045810",
            company="NVIDIA CORP",
            doc_map={},
            registry_path=self.db_path,
            diagnostics=diagnostics,
        )
        self.assertIsNotNone(result)
        assert result is not None and not isinstance(result, list)
        self.assertEqual(result.source, "learned:fuzzy")
        self.assertEqual(result.value, 28_000_000_000)
        # The retry is announced, not silent.
        self.assertTrue(
            any(
                d.kind == "learned_mapping_unverified" and "retrying discovery" in d.message
                for d in diagnostics
            )
        )

        reg = LearnedRegistry(db_path=self.db_path)
        row = reg.lookup("0001045810", "operating_cash_flow")
        assert row is not None
        self.assertTrue(row.verified)

    def test_verified_cached_revenue_mapping_must_pass_shape_guard(self) -> None:
        reg = LearnedRegistry(db_path=self.db_path)
        reg.upsert(
            cik="0001652044",
            metric="revenue",
            concept="ContractWithCustomerLiabilityRevenueRecognized",
            taxonomy="us-gaap",
            source="fuzzy",
            verified=True,
            verif_method="manual",
            value_sample=3_500_000_000,
        )
        reg.close()

        meta = MetricMeta(concepts=(), duration=True)
        result = try_learn(
            metric="revenue",
            meta=meta,
            facts=_BAD_REVENUE_FACTS,
            cik="0001652044",
            company="Alphabet Inc.",
            prior_year_cited=_prior_year_cited(value=400_000_000_000),
            doc_map={},
            registry_path=self.db_path,
            period="mrq",
        )

        self.assertIsNone(result)

    def test_verified_cached_gross_profit_mapping_must_pass_shape_guard(self) -> None:
        reg = LearnedRegistry(db_path=self.db_path)
        reg.upsert(
            cik="0001783879",
            metric="gross_profit",
            concept="ContractWithCustomerAssetGross",
            taxonomy="us-gaap",
            source="fuzzy",
            verified=True,
            verif_method="manual",
            value_sample=185_000_000,
        )
        reg.close()

        meta = MetricMeta(concepts=(), duration=True)
        result = try_learn(
            metric="gross_profit",
            meta=meta,
            facts=_BAD_GROSS_PROFIT_FACTS,
            cik="0001783879",
            company="Robinhood Markets, Inc.",
            prior_year_cited=_prior_year_cited(value=1_900_000_000),
            doc_map={},
            registry_path=self.db_path,
            period="lfy",
        )

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
