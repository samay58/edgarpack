"""Unit tests for Layer B KPI extraction."""

from __future__ import annotations

import unittest

from edgarpack.query.kpi_extract import KPI_CATALOG, KpiDef


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


if __name__ == "__main__":
    unittest.main()
