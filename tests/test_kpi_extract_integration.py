"""End-to-end Layer B integration test with synthetic pack + mocked LLM."""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

from edgarpack.harvest.registry import PackRecord, PackRegistry

_P = "edgarpack.query.financials"


def _build_synthetic_pack(td: Path) -> tuple[PackRegistry, Path]:
    """Build a tmp PackRegistry + one fake CrowdStrike 10-K pack with an
    MD&A section containing ARR prose."""
    registry_db = td / "registry.db"
    packs_dir = td / "packs" / "0001535527" / "0001535527-24-000123"
    sections_dir = packs_dir / "sections"
    sections_dir.mkdir(parents=True)
    (sections_dir / "mda.md").write_text(
        "Our subscription-first business model has driven "
        "Annual Recurring Revenue of $3.44 billion as of the end of fiscal 2024, "
        "an increase of 34 percent year over year.\n",
        encoding="utf-8",
    )
    manifest = {
        "schema_version": 1,
        "parser_version": "0.1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "source": {"url": "https://example", "fetched_at": datetime.now(UTC).isoformat()},
        "filing": {
            "cik": "0001535527",
            "accession": "0001535527-24-000123",
            "form_type": "10-K",
            "filing_date": "2024-03-07",
            "company_name": "CrowdStrike Holdings, Inc.",
            "primary_document": "crwd-20240131.htm",
        },
        "sections": [
            {"id": "10k_parti_item7_mda",
             "title": "MD&A",
             "path": "sections/mda.md",
             "char_start": 0, "char_end": 500,
             "tokens_approx": 80, "sha256": "abc"},
        ],
        "artifacts": {},
        "warnings": [],
        "tokens_total": 80,
    }
    (packs_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    registry = PackRegistry(db_path=registry_db)
    registry.register_pack(PackRecord(
        accession="0001535527-24-000123",
        cik="0001535527",
        ticker="CRWD",
        company_name="CrowdStrike Holdings, Inc.",
        form_type="10-K",
        filing_date="2024-03-07",
        sections_count=1,
        tokens_total=80,
        pack_dir=str(packs_dir),
        built_at=datetime.now(UTC).isoformat(),
    ))
    return registry, registry_db


class TestLayerBEndToEnd(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.td = Path(self._tmp.name)
        self.pack_registry, self.pack_registry_db = _build_synthetic_pack(self.td)
        self.learned_db = self.td / "learned.db"

    async def test_kpi_query_end_to_end(self) -> None:
        from edgarpack.query.financials import financials

        fake_response = json.dumps({
            "value": 3_440_000_000,
            "unit": "USD",
            "excerpt": "Annual Recurring Revenue of $3.44 billion",
            "section_id": "10k_parti_item7_mda",
            "confidence": "high",
        })

        class _FakeCompleted:
            stdout = fake_response
            stderr = ""
            returncode = 0

        with patch(f"{_P}.resolve_ticker",
                   new=AsyncMock(return_value=("0001535527", "CrowdStrike Holdings, Inc."))), \
             patch(f"{_P}.fetch_company_facts",
                   new=AsyncMock(return_value={"facts": {}})), \
             patch(f"{_P}._build_doc_map",
                   new=AsyncMock(return_value={})), \
             patch("edgarpack.query.kpi_extract._LLM_CMD_KPI", "codex"), \
             patch("edgarpack.query.kpi_extract.subprocess.run",
                   return_value=_FakeCompleted), \
             patch("edgarpack.query.kpi_extract.PackRegistry",
                   return_value=self.pack_registry), \
             patch("edgarpack.query.learned_registry.DEFAULT_REGISTRY_PATH",
                   self.learned_db):
            result = await financials("CRWD", metrics="arr", period="lfy")

        arr = result.metrics.get("arr")
        self.assertIsNotNone(arr)
        assert arr is not None
        self.assertEqual(arr.value, 3_440_000_000)
        self.assertEqual(arr.source, "learned:kpi-llm")
        self.assertEqual(arr.accession, "0001535527-24-000123")

    async def test_mixed_query_revenue_and_kpi(self) -> None:
        """A query mixing a hardcoded metric and a Layer B KPI returns both."""
        from edgarpack.query.financials import financials

        # Minimal facts blob so revenue resolves via the hardcoded path
        facts = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": [{
            "val": 3_000_000_000, "fy": 2024, "fp": "FY",
            "start": "2023-02-01", "end": "2024-01-31",
            "form": "10-K", "filed": "2024-03-07",
            "accn": "0001535527-24-000123",
            "frame": "CY2024",
        }]}}}}}

        fake_response = json.dumps({
            "value": 3_440_000_000,
            "unit": "USD",
            "excerpt": "Annual Recurring Revenue of $3.44 billion",
            "section_id": "10k_parti_item7_mda",
            "confidence": "high",
        })

        class _FakeCompleted:
            stdout = fake_response
            stderr = ""
            returncode = 0

        with patch(f"{_P}.resolve_ticker",
                   new=AsyncMock(return_value=("0001535527", "CrowdStrike Holdings, Inc."))), \
             patch(f"{_P}.fetch_company_facts",
                   new=AsyncMock(return_value=facts)), \
             patch(f"{_P}._build_doc_map",
                   new=AsyncMock(return_value={})), \
             patch("edgarpack.query.kpi_extract._LLM_CMD_KPI", "codex"), \
             patch("edgarpack.query.kpi_extract.subprocess.run",
                   return_value=_FakeCompleted), \
             patch("edgarpack.query.kpi_extract.PackRegistry",
                   return_value=self.pack_registry), \
             patch("edgarpack.query.learned_registry.DEFAULT_REGISTRY_PATH",
                   self.learned_db):
            result = await financials("CRWD", metrics="revenue,arr", period="lfy")

        rev = result.metrics.get("revenue")
        arr = result.metrics.get("arr")
        assert rev is not None and arr is not None
        self.assertEqual(rev.source, "hardcoded")
        self.assertEqual(arr.source, "learned:kpi-llm")

    async def test_no_pack_produces_diagnostic(self) -> None:
        """When no pack is registered for the CIK, Layer B returns None and
        a diagnostic is attached to the QueryResult."""
        from edgarpack.query.financials import financials

        with patch(f"{_P}.resolve_ticker",
                   new=AsyncMock(return_value=("9999999", "Unknown Co"))), \
             patch(f"{_P}.fetch_company_facts",
                   new=AsyncMock(return_value={"facts": {}})), \
             patch(f"{_P}._build_doc_map",
                   new=AsyncMock(return_value={})), \
             patch("edgarpack.query.kpi_extract.PackRegistry",
                   return_value=self.pack_registry), \
             patch("edgarpack.query.learned_registry.DEFAULT_REGISTRY_PATH",
                   self.learned_db):
            result = await financials("UNKNOWN", metrics="arr", period="lfy")

        self.assertIsNone(result.metrics["arr"])
        self.assertTrue(
            any(d.metric == "arr" for d in result.diagnostics)
        )


if __name__ == "__main__":
    unittest.main()
