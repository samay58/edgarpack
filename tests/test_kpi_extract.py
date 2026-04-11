"""Unit tests for Layer B KPI extraction."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from edgarpack.harvest.registry import PackRecord, PackRegistry
from edgarpack.query.kpi_extract import (
    KPI_CATALOG,
    KpiDef,
    _load_pack_manifest,
    _resolve_filing_for_period,
)


class TestKpiCatalog(unittest.TestCase):
    def test_catalog_has_core_saas_kpis(self) -> None:
        for name in ("arr", "nrr", "rpo", "crpo", "billings"):
            self.assertIn(name, KPI_CATALOG)

    def test_catalog_has_core_consumer_kpis(self) -> None:
        for name in ("dau", "mau", "arpu"):
            self.assertIn(name, KPI_CATALOG)

    def test_catalog_has_core_marketplace_kpis(self) -> None:
        for name in ("gmv", "take_rate", "gross_bookings"):
            self.assertIn(name, KPI_CATALOG)

    def test_catalog_has_core_retail_kpis(self) -> None:
        for name in ("same_store_sales", "store_count"):
            self.assertIn(name, KPI_CATALOG)

    def test_catalog_has_core_fintech_kpis(self) -> None:
        for name in ("tpv", "aum"):
            self.assertIn(name, KPI_CATALOG)

    def test_catalog_is_non_empty(self) -> None:
        self.assertGreaterEqual(len(KPI_CATALOG), 25)

    def test_every_kpi_has_non_empty_phrases(self) -> None:
        for name, kpi in KPI_CATALOG.items():
            self.assertGreater(
                len(kpi.phrases), 0,
                f"{name} has no phrases",
            )
            for phrase in kpi.phrases:
                self.assertIsInstance(phrase, str)
                self.assertTrue(phrase.strip(),
                                f"{name} has an empty phrase")

    def test_every_kpi_has_valid_unit_hint(self) -> None:
        valid_units = {"USD", "count", "percent", "days", "pure"}
        for name, kpi in KPI_CATALOG.items():
            self.assertIn(kpi.unit_hint, valid_units,
                          f"{name} has invalid unit_hint={kpi.unit_hint!r}")


class TestKpiDef(unittest.TestCase):
    def test_kpi_def_is_frozen(self) -> None:
        kpi = KpiDef(phrases=("ARR",), unit_hint="USD")
        with self.assertRaises((AttributeError, TypeError)):
            kpi.unit_hint = "percent"  # type: ignore[misc]

    def test_kpi_def_defaults(self) -> None:
        kpi = KpiDef(phrases=("ARR",), unit_hint="USD")
        self.assertEqual(kpi.industry, ())
        self.assertEqual(kpi.description, "")


def _write_manifest(pack_dir: Path, sections: list[dict]) -> None:
    """Write a minimal manifest.json that Layer B's loader can parse."""
    pack_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "parser_version": "0.1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "source": {"url": "https://example/filing", "fetched_at": datetime.now(UTC).isoformat()},
        "filing": {
            "cik": "0001535527",
            "accession": "0001535527-24-000123",
            "form_type": "10-K",
            "filing_date": "2024-03-07",
            "company_name": "CrowdStrike Holdings, Inc.",
        },
        "sections": sections,
        "artifacts": {},
        "warnings": [],
        "tokens_total": 0,
    }
    (pack_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


class TestResolveFilingForPeriod(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.registry_db = Path(self._tmp.name) / "registry.db"
        self.packs_dir = Path(self._tmp.name) / "packs"
        self.packs_dir.mkdir()
        self.registry = PackRegistry(db_path=self.registry_db)

    def _register(self, accession: str, form_type: str, filing_date: str) -> Path:
        pack_dir = self.packs_dir / "0001535527" / accession
        _write_manifest(pack_dir, sections=[])
        self.registry.register_pack(PackRecord(
            accession=accession,
            cik="0001535527",
            ticker="CRWD",
            company_name="CrowdStrike Holdings, Inc.",
            form_type=form_type,
            filing_date=filing_date,
            sections_count=0,
            tokens_total=0,
            pack_dir=str(pack_dir),
            built_at=datetime.now(UTC).isoformat(),
        ))
        return pack_dir

    def test_lfy_returns_most_recent_10k(self) -> None:
        self._register("0001535527-23-000001", "10-K", "2023-03-01")
        self._register("0001535527-24-000123", "10-K", "2024-03-07")
        rec = _resolve_filing_for_period("0001535527", "lfy", self.registry)
        self.assertIsNotNone(rec)
        assert rec is not None
        self.assertEqual(rec.accession, "0001535527-24-000123")

    def test_mrq_returns_most_recent_10q(self) -> None:
        self._register("0001535527-24-000200", "10-Q", "2024-06-05")
        self._register("0001535527-24-000123", "10-K", "2024-03-07")
        rec = _resolve_filing_for_period("0001535527", "mrq", self.registry)
        self.assertIsNotNone(rec)
        assert rec is not None
        self.assertEqual(rec.form_type, "10-Q")

    def test_annual_series_returns_nth_most_recent(self) -> None:
        self._register("0001535527-22-000001", "10-K", "2022-03-01")
        self._register("0001535527-23-000001", "10-K", "2023-03-01")
        self._register("0001535527-24-000123", "10-K", "2024-03-07")
        rec = _resolve_filing_for_period("0001535527", "annual:2", self.registry)
        assert rec is not None
        self.assertEqual(rec.accession, "0001535527-23-000001")

    def test_returns_none_when_no_pack(self) -> None:
        rec = _resolve_filing_for_period("9999999", "lfy", self.registry)
        self.assertIsNone(rec)

    def test_returns_none_for_annual_out_of_range(self) -> None:
        self._register("0001535527-24-000123", "10-K", "2024-03-07")
        rec = _resolve_filing_for_period("0001535527", "annual:5", self.registry)
        self.assertIsNone(rec)

    def test_mrp_picks_most_recent_across_forms(self) -> None:
        self._register("0001535527-24-000123", "10-K", "2024-03-07")
        self._register("0001535527-24-000200", "10-Q", "2024-06-05")  # newer
        rec = _resolve_filing_for_period("0001535527", "mrp", self.registry)
        assert rec is not None
        self.assertEqual(rec.form_type, "10-Q")
        self.assertEqual(rec.filing_date, "2024-06-05")

    def test_ltm_picks_most_recent_across_forms(self) -> None:
        self._register("0001535527-23-000001", "10-K", "2023-03-01")
        self._register("0001535527-24-000123", "10-K", "2024-03-07")  # newer K
        self._register("0001535527-24-000200", "10-Q", "2024-06-05")  # newest Q
        rec = _resolve_filing_for_period("0001535527", "ltm", self.registry)
        assert rec is not None
        self.assertEqual(rec.filing_date, "2024-06-05")

    def test_quarterly_series_returns_nth_most_recent(self) -> None:
        self._register("0001535527-24-000100", "10-Q", "2024-03-05")
        self._register("0001535527-24-000200", "10-Q", "2024-06-05")
        self._register("0001535527-24-000300", "10-Q", "2024-09-05")
        rec = _resolve_filing_for_period("0001535527", "quarterly:2", self.registry)
        assert rec is not None
        self.assertEqual(rec.accession, "0001535527-24-000200")

    def test_unknown_period_returns_none(self) -> None:
        self._register("0001535527-24-000123", "10-K", "2024-03-07")
        self.assertIsNone(_resolve_filing_for_period("0001535527", "gibberish", self.registry))
        self.assertIsNone(_resolve_filing_for_period("0001535527", "annual:abc", self.registry))
        self.assertIsNone(_resolve_filing_for_period("0001535527", "annual:0", self.registry))


class TestLoadPackManifest(unittest.TestCase):
    def test_loads_manifest_json_from_pack_dir(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            pack_dir = Path(td) / "pack"
            _write_manifest(pack_dir, sections=[
                {"id": "10k_parti_item7_mda", "title": "MD&A",
                 "path": "sections/10k_parti_item7_mda.md",
                 "char_start": 0, "char_end": 1000,
                 "tokens_approx": 200, "sha256": "deadbeef"}
            ])
            manifest = _load_pack_manifest(pack_dir)
            self.assertIn("sections", manifest)
            self.assertEqual(len(manifest["sections"]), 1)
            self.assertEqual(manifest["sections"][0]["id"], "10k_parti_item7_mda")

    def test_raises_if_no_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            pack_dir = Path(td) / "nothing"
            pack_dir.mkdir()
            with self.assertRaises(FileNotFoundError):
                _load_pack_manifest(pack_dir)


if __name__ == "__main__":
    unittest.main()
