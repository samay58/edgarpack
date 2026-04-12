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
    _read_section_text,
    _resolve_filing_for_period,
    _select_sections,
    _trim_to_budget,
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


class TestSelectSections(unittest.TestCase):
    def test_matches_mda_section(self) -> None:
        sections = [
            {"id": "10k_parti_item1_business", "path": "sections/item1.md",
             "title": "Business", "char_start": 0, "char_end": 100},
            {"id": "10k_parti_item7_managements_discussion_and_analysis",
             "path": "sections/item7.md", "title": "MD&A",
             "char_start": 100, "char_end": 5000},
            {"id": "10k_parti_item8_financial_statements",
             "path": "sections/item8.md", "title": "Financials",
             "char_start": 5000, "char_end": 10000},
        ]
        selected = _select_sections(sections)
        ids = {s["id"] for s in selected}
        self.assertIn("10k_parti_item7_managements_discussion_and_analysis", ids)
        self.assertNotIn("10k_parti_item1_business", ids)

    def test_matches_key_metrics_section_by_slug(self) -> None:
        sections = [
            {"id": "10k_key_metrics_nontraditional",
             "path": "sections/key.md", "title": "Key Metrics",
             "char_start": 0, "char_end": 500},
            {"id": "10k_operating_data_north_america",
             "path": "sections/ops.md", "title": "Operating Data",
             "char_start": 500, "char_end": 1000},
        ]
        selected = _select_sections(sections)
        self.assertEqual(len(selected), 2)

    def test_matches_10q_mda(self) -> None:
        sections = [
            {"id": "10q_parti_item1_financial_statements",
             "path": "sections/q1.md", "title": "Financials",
             "char_start": 0, "char_end": 100},
            {"id": "10q_parti_item2_managements_discussion",
             "path": "sections/q2.md", "title": "MD&A",
             "char_start": 100, "char_end": 2000},
        ]
        selected = _select_sections(sections)
        ids = {s["id"] for s in selected}
        self.assertIn("10q_parti_item2_managements_discussion", ids)

    def test_returns_empty_when_no_matches(self) -> None:
        sections = [
            {"id": "10k_parti_item1_business", "path": "sections/item1.md",
             "title": "Business", "char_start": 0, "char_end": 100},
        ]
        self.assertEqual(_select_sections(sections), [])

    def test_empty_section_list_returns_empty(self) -> None:
        self.assertEqual(_select_sections([]), [])

    def test_preserves_manifest_order(self) -> None:
        """Sections in the output must appear in the same order as the input,
        regardless of which pattern matched which entry."""
        sections = [
            {"id": "10k_parti_item7_mda", "path": "p1",
             "title": "MD&A", "char_start": 0, "char_end": 100},
            {"id": "10k_parti_item1_business", "path": "p2",
             "title": "Business", "char_start": 100, "char_end": 200},  # filtered out
            {"id": "10k_segment_data", "path": "p3",
             "title": "Segments", "char_start": 200, "char_end": 300},
            {"id": "10k_key_metric_nontraditional", "path": "p4",
             "title": "Key Metrics", "char_start": 300, "char_end": 400},
        ]
        selected = _select_sections(sections)
        ids = [s["id"] for s in selected]
        self.assertEqual(
            ids,
            ["10k_parti_item7_mda", "10k_segment_data",
             "10k_key_metric_nontraditional"],
        )


class TestReadSectionText(unittest.TestCase):
    def test_concatenates_section_files_in_order(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            pack_dir = Path(td)
            sections_dir = pack_dir / "sections"
            sections_dir.mkdir()
            (sections_dir / "a.md").write_text("Alpha content", encoding="utf-8")
            (sections_dir / "b.md").write_text("Beta content", encoding="utf-8")
            sections = [
                {"id": "sec_a", "path": "sections/a.md", "title": "A",
                 "char_start": 0, "char_end": 100},
                {"id": "sec_b", "path": "sections/b.md", "title": "B",
                 "char_start": 100, "char_end": 200},
            ]
            text = _read_section_text(pack_dir, sections)
            self.assertIn("Alpha content", text)
            self.assertIn("Beta content", text)
            self.assertIn("sec_a", text)  # separator marker includes the id
            self.assertIn("sec_b", text)

    def test_skips_missing_files_with_warning(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            pack_dir = Path(td)
            (pack_dir / "sections").mkdir()
            sections = [
                {"id": "missing_sec", "path": "sections/missing.md", "title": "Gone",
                 "char_start": 0, "char_end": 100},
            ]
            text = _read_section_text(pack_dir, sections)
            self.assertEqual(text, "")

    def test_skips_undecodable_bytes_with_warning(self) -> None:
        """A section file with non-UTF-8 bytes must be skipped, not raise."""
        with tempfile.TemporaryDirectory() as td:
            pack_dir = Path(td)
            sections_dir = pack_dir / "sections"
            sections_dir.mkdir()
            (sections_dir / "bad.md").write_bytes(b"\xff\xfe\xff bad")
            (sections_dir / "good.md").write_text("Good content", encoding="utf-8")
            sections = [
                {"id": "bad_sec", "path": "sections/bad.md", "title": "Bad",
                 "char_start": 0, "char_end": 100},
                {"id": "good_sec", "path": "sections/good.md", "title": "Good",
                 "char_start": 100, "char_end": 200},
            ]
            # Must not raise; should return only the good section's content.
            text = _read_section_text(pack_dir, sections)
            self.assertIn("Good content", text)
            self.assertNotIn("bad", text)  # the bad file's content is skipped
            # The good section's id should be in the separator
            self.assertIn("good_sec", text)


class TestTrimToBudget(unittest.TestCase):
    def test_passthrough_when_under_budget(self) -> None:
        text = "short text"
        self.assertEqual(_trim_to_budget(text, max_chars=100), text)

    def test_truncates_when_over_budget(self) -> None:
        text = "x" * 200
        trimmed = _trim_to_budget(text, max_chars=100)
        self.assertLessEqual(len(trimmed), 150)
        self.assertIn("truncated", trimmed)

    def test_default_budget_is_reasonable(self) -> None:
        # Default should allow up to ~60K chars (~15K tokens at 4 chars/token)
        text = "x" * 50_000
        trimmed = _trim_to_budget(text)
        self.assertEqual(trimmed, text)  # unmodified


import json as _json
from unittest.mock import patch

from edgarpack.query.kpi_extract import (
    _build_extraction_prompt,
    _extract_via_llm,
    _llm_backend_available_kpi,
)


class TestBuildExtractionPrompt(unittest.TestCase):
    def test_prompt_contains_metric_phrases(self) -> None:
        kpi = KpiDef(
            phrases=("annual recurring revenue", "ARR"),
            unit_hint="USD",
        )
        prompt = _build_extraction_prompt(
            metric="arr", kpi_def=kpi,
            company="CrowdStrike", form_type="10-K",
            filing_date="2024-03-07",
            text="MD&A says ARR was $3.44B at year end.",
        )
        self.assertIn("annual recurring revenue", prompt)
        self.assertIn("ARR", prompt)
        self.assertIn("CrowdStrike", prompt)
        self.assertIn("10-K", prompt)
        self.assertIn("2024-03-07", prompt)
        self.assertIn("MD&A says ARR was $3.44B at year end.", prompt)

    def test_prompt_requests_strict_json(self) -> None:
        kpi = KpiDef(phrases=("ARR",), unit_hint="USD")
        prompt = _build_extraction_prompt(
            metric="arr", kpi_def=kpi,
            company="X", form_type="10-K", filing_date="2024-01-01",
            text="text",
        )
        self.assertIn("JSON", prompt)
        self.assertIn("confidence", prompt)
        self.assertIn("excerpt", prompt)

    def test_prompt_includes_unit_hint(self) -> None:
        kpi = KpiDef(phrases=("NRR",), unit_hint="percent")
        prompt = _build_extraction_prompt(
            metric="nrr", kpi_def=kpi,
            company="X", form_type="10-K", filing_date="2024-01-01",
            text="text",
        )
        self.assertIn("percent", prompt)

    def test_prompt_with_real_catalog_entry(self) -> None:
        """Prompt builds correctly from a real KPI_CATALOG entry."""
        kpi = KPI_CATALOG["arr"]
        prompt = _build_extraction_prompt(
            metric="arr", kpi_def=kpi,
            company="CrowdStrike", form_type="10-K",
            filing_date="2024-03-07",
            text="Our ARR was $3.44 billion at year end.",
        )
        # All canonical phrases from the catalog appear in the prompt
        for phrase in kpi.phrases:
            self.assertIn(phrase, prompt)
        self.assertIn("USD", prompt)
        self.assertIn("CrowdStrike", prompt)
        # Prompt stays under LLM context budget (prompt + 60K text budget)
        self.assertLess(len(prompt), 80_000)


class TestExtractViaLlm(unittest.TestCase):
    def test_returns_none_without_backend(self) -> None:
        with patch("edgarpack.query.kpi_extract._LLM_CMD_KPI", None):
            result = _extract_via_llm("dummy prompt")
            self.assertIsNone(result)

    def test_parses_valid_response(self) -> None:
        fake = _json.dumps({
            "value": 3440000000,
            "unit": "USD",
            "excerpt": "Annual recurring revenue of $3.44 billion",
            "section_id": "10k_parti_item7_mda",
            "confidence": "high",
        })

        class _Fake:
            stdout = fake
            stderr = ""
            returncode = 0

        with patch("edgarpack.query.kpi_extract._LLM_CMD_KPI", "codex"), \
             patch("edgarpack.query.kpi_extract.subprocess.run", return_value=_Fake):
            result = _extract_via_llm("prompt")
            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result["confidence"], "high")
            self.assertEqual(result["value"], 3440000000)
            self.assertEqual(result["unit"], "USD")

    def test_returns_none_on_malformed_json(self) -> None:
        class _Fake:
            stdout = "not json at all"
            stderr = ""
            returncode = 0

        with patch("edgarpack.query.kpi_extract._LLM_CMD_KPI", "codex"), \
             patch("edgarpack.query.kpi_extract.subprocess.run", return_value=_Fake):
            self.assertIsNone(_extract_via_llm("prompt"))

    def test_returns_none_on_nonzero_exit(self) -> None:
        class _Fake:
            stdout = ""
            stderr = "error"
            returncode = 1

        with patch("edgarpack.query.kpi_extract._LLM_CMD_KPI", "codex"), \
             patch("edgarpack.query.kpi_extract.subprocess.run", return_value=_Fake):
            self.assertIsNone(_extract_via_llm("prompt"))

    def test_returns_none_on_timeout(self) -> None:
        import subprocess as _sp

        with patch("edgarpack.query.kpi_extract._LLM_CMD_KPI", "codex"), \
             patch("edgarpack.query.kpi_extract.subprocess.run",
                   side_effect=_sp.TimeoutExpired(cmd="codex", timeout=45)):
            self.assertIsNone(_extract_via_llm("prompt"))

    def test_parses_dict_object_field_types(self) -> None:
        """Reject responses missing required keys or with wrong types."""
        bad_responses = [
            {"confidence": "high"},  # missing value/unit/excerpt/section_id
            {"value": None, "unit": "USD", "excerpt": "x", "section_id": "y",
             "confidence": "high"},  # value is None but confidence is high
            {"value": "not a number", "unit": "USD", "excerpt": "x",
             "section_id": "y", "confidence": "high"},
        ]
        for resp in bad_responses:
            class _Fake:
                stdout = _json.dumps(resp)
                stderr = ""
                returncode = 0
            with patch("edgarpack.query.kpi_extract._LLM_CMD_KPI", "codex"), \
                 patch("edgarpack.query.kpi_extract.subprocess.run", return_value=_Fake):
                self.assertIsNone(_extract_via_llm("prompt"))

    def test_passes_through_not_found_confidence(self) -> None:
        fake = _json.dumps({
            "value": None, "unit": None, "excerpt": "",
            "section_id": "", "confidence": "not_found",
        })

        class _Fake:
            stdout = fake
            stderr = ""
            returncode = 0

        with patch("edgarpack.query.kpi_extract._LLM_CMD_KPI", "codex"), \
             patch("edgarpack.query.kpi_extract.subprocess.run", return_value=_Fake):
            result = _extract_via_llm("prompt")
            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result["confidence"], "not_found")

    def test_parses_json_wrapped_in_markdown_fences(self) -> None:
        """If the LLM wraps its response in ```json ... ```, the salvage
        regex should extract and parse the inner object."""
        wrapped = (
            "```json\n"
            '{"value": 3440000000, "unit": "USD", '
            '"excerpt": "Annual recurring revenue of $3.44 billion", '
            '"section_id": "10k_parti_item7_mda", "confidence": "high"}\n'
            "```"
        )

        class _Fake:
            stdout = wrapped
            stderr = ""
            returncode = 0

        with patch("edgarpack.query.kpi_extract._LLM_CMD_KPI", "codex"), \
             patch("edgarpack.query.kpi_extract.subprocess.run",
                   return_value=_Fake):
            result = _extract_via_llm("prompt")
            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result["value"], 3440000000)
            self.assertEqual(result["confidence"], "high")

    def test_rejects_bool_value(self) -> None:
        """bool is a subclass of int in Python; must not pass numeric validation."""
        import json as _j
        fake = _j.dumps({
            "value": True,
            "unit": "USD",
            "excerpt": "Revenue",
            "section_id": "10k_parti_item7_mda",
            "confidence": "high",
        })

        class _Fake:
            stdout = fake
            stderr = ""
            returncode = 0

        with patch("edgarpack.query.kpi_extract._LLM_CMD_KPI", "codex"), \
             patch("edgarpack.query.kpi_extract.subprocess.run",
                   return_value=_Fake):
            self.assertIsNone(_extract_via_llm("prompt"))

    def test_rejects_empty_section_id(self) -> None:
        """section_id must be a non-empty string."""
        import json as _j
        fake = _j.dumps({
            "value": 3440000000,
            "unit": "USD",
            "excerpt": "Annual recurring revenue of $3.44 billion",
            "section_id": "",
            "confidence": "high",
        })

        class _Fake:
            stdout = fake
            stderr = ""
            returncode = 0

        with patch("edgarpack.query.kpi_extract._LLM_CMD_KPI", "codex"), \
             patch("edgarpack.query.kpi_extract.subprocess.run",
                   return_value=_Fake):
            self.assertIsNone(_extract_via_llm("prompt"))

    def test_rejects_nan_value(self) -> None:
        import json as _j
        fake = _j.dumps({
            "value": float("nan"),
            "unit": "USD",
            "excerpt": "Revenue of NaN",
            "section_id": "10k_parti_item7_mda",
            "confidence": "high",
        })

        class _Fake:
            stdout = fake
            stderr = ""
            returncode = 0

        with patch("edgarpack.query.kpi_extract._LLM_CMD_KPI", "codex"), \
             patch("edgarpack.query.kpi_extract.subprocess.run",
                   return_value=_Fake):
            self.assertIsNone(_extract_via_llm("prompt"))

    def test_rejects_negative_value(self) -> None:
        import json as _j
        fake = _j.dumps({
            "value": -3440000000,
            "unit": "USD",
            "excerpt": "ARR was minus something",
            "section_id": "10k_parti_item7_mda",
            "confidence": "high",
        })

        class _Fake:
            stdout = fake
            stderr = ""
            returncode = 0

        with patch("edgarpack.query.kpi_extract._LLM_CMD_KPI", "codex"), \
             patch("edgarpack.query.kpi_extract.subprocess.run",
                   return_value=_Fake):
            self.assertIsNone(_extract_via_llm("prompt"))

    def test_rejects_unit_not_in_enum(self) -> None:
        import json as _j
        fake = _j.dumps({
            "value": 3440000000,
            "unit": "dollars",  # not in _VALID_LLM_UNITS
            "excerpt": "ARR of $3.44 billion",
            "section_id": "10k_parti_item7_mda",
            "confidence": "high",
        })

        class _Fake:
            stdout = fake
            stderr = ""
            returncode = 0

        with patch("edgarpack.query.kpi_extract._LLM_CMD_KPI", "codex"), \
             patch("edgarpack.query.kpi_extract.subprocess.run",
                   return_value=_Fake):
            self.assertIsNone(_extract_via_llm("prompt"))


from edgarpack.query.kpi_extract import _verify_excerpt_in_text


class TestVerifyExcerptInText(unittest.TestCase):
    def test_exact_substring_passes(self) -> None:
        text = "CrowdStrike reported Annual Recurring Revenue of $3.44 billion at year end."
        excerpt = "Annual Recurring Revenue of $3.44 billion"
        self.assertTrue(_verify_excerpt_in_text(excerpt, text))

    def test_whitespace_normalized(self) -> None:
        text = "ARR of  $3.44  billion  \n at year end."
        excerpt = "ARR of $3.44 billion"
        self.assertTrue(_verify_excerpt_in_text(excerpt, text))

    def test_hallucinated_excerpt_fails(self) -> None:
        text = "CrowdStrike reported $3.44 billion at year end."
        excerpt = "ARR was $3.44 billion, a 30 percent increase year over year"
        self.assertFalse(_verify_excerpt_in_text(excerpt, text))

    def test_empty_excerpt_fails(self) -> None:
        self.assertFalse(_verify_excerpt_in_text("", "some text"))

    def test_empty_text_fails(self) -> None:
        self.assertFalse(_verify_excerpt_in_text("something", ""))

    def test_case_insensitive_match(self) -> None:
        text = "Annual Recurring Revenue was $3.44 billion."
        excerpt = "annual recurring revenue was $3.44 billion"
        self.assertTrue(_verify_excerpt_in_text(excerpt, text))

    def test_value_in_excerpt_passes_when_value_present(self) -> None:
        text = "CrowdStrike reported Annual Recurring Revenue of $3.44 billion at year end."
        excerpt = "Annual Recurring Revenue of $3.44 billion"
        self.assertTrue(_verify_excerpt_in_text(excerpt, text, expected_value="$3.44 billion"))

    def test_value_in_excerpt_fails_when_value_absent(self) -> None:
        """The excerpt is real, but the value the LLM attributed to it came
        from elsewhere in the source. Must be rejected."""
        text = "Revenue was $3.44 billion. Separately, deferred revenue grew to $1.2 billion."
        excerpt = "Revenue was $3.44 billion"
        self.assertFalse(
            _verify_excerpt_in_text(excerpt, text, expected_value="$1.2 billion")
        )

    def test_value_in_excerpt_normalized_whitespace(self) -> None:
        text = "ARR of $3.44 billion."
        excerpt = "ARR of $3.44 billion"
        self.assertTrue(
            _verify_excerpt_in_text(excerpt, text, expected_value="$3.44  billion")
        )

    def test_handles_zero_width_characters(self) -> None:
        """Zero-width spaces in the source must not cause false negatives."""
        text = "Our ARR was $3.44\u200Bbillion at year end."
        excerpt = "ARR was $3.44 billion"
        self.assertTrue(_verify_excerpt_in_text(excerpt, text))

    def test_word_order_mismatch_fails(self) -> None:
        """Same words in a different order is not a substring match."""
        text = "revenue was $3.44 billion"
        excerpt = "$3.44 billion revenue"
        self.assertFalse(_verify_excerpt_in_text(excerpt, text))

    def test_multi_line_excerpt_matches_across_newlines(self) -> None:
        text = "Our key metric this year:\n  ARR of $3.44 billion"
        excerpt = "ARR of $3.44 billion"
        self.assertTrue(_verify_excerpt_in_text(excerpt, text))

    def test_casefold_handles_sharp_s(self) -> None:
        """German ß casefolds to 'ss'. Lowercase alone would miss this."""
        text = "Straße revenue was $100 million"
        excerpt = "STRASSE REVENUE WAS $100 MILLION"
        self.assertTrue(_verify_excerpt_in_text(excerpt, text))


from datetime import date

from edgarpack.query.kpi_extract import _build_cited_from_extraction


class TestBuildCitedFromExtraction(unittest.TestCase):
    def test_builds_cited_value_with_expected_fields(self) -> None:
        kpi = KpiDef(
            phrases=("annual recurring revenue", "ARR"),
            unit_hint="USD",
        )
        response = {
            "value": 3_440_000_000,
            "unit": "USD",
            "excerpt": "Annual recurring revenue of $3.44 billion at fiscal year end",
            "section_id": "10k_parti_item7_managements_discussion",
            "confidence": "high",
        }
        pack_record = PackRecord(
            accession="0001535527-24-000123",
            cik="0001535527",
            ticker="CRWD",
            company_name="CrowdStrike Holdings, Inc.",
            form_type="10-K",
            filing_date="2024-03-07",
            sections_count=10,
            tokens_total=300_000,
            pack_dir="/tmp/packs/0001535527/0001535527-24-000123",
            built_at=datetime.now(UTC).isoformat(),
            manifest_hash=None,
            warnings_json=None,
        )
        pack_manifest = {
            "filing": {
                "cik": "0001535527",
                "accession": "0001535527-24-000123",
                "form_type": "10-K",
                "filing_date": "2024-03-07",
                "company_name": "CrowdStrike Holdings, Inc.",
            },
            "sections": [],
        }

        cited = _build_cited_from_extraction(
            response=response,
            metric="arr",
            kpi_def=kpi,
            pack_record=pack_record,
            pack_manifest=pack_manifest,
            primary_document="crwd-20240131.htm",
        )

        self.assertEqual(cited.value, 3_440_000_000)
        self.assertEqual(cited.unit, "USD")
        self.assertEqual(cited.metric, "arr")
        self.assertEqual(cited.concept, "annual recurring revenue")
        self.assertEqual(cited.accession, "0001535527-24-000123")
        self.assertEqual(cited.cik, "0001535527")
        self.assertEqual(cited.company, "CrowdStrike Holdings, Inc.")
        self.assertEqual(cited.form_type, "10-K")
        self.assertEqual(cited.filed, date(2024, 3, 7))
        self.assertEqual(cited.taxonomy, "kpi-prose")
        self.assertEqual(cited.primary_document, "crwd-20240131.htm")
        self.assertEqual(cited.fact_id, "")
        self.assertIn("$3.44 billion", cited.excerpt_text)

    def test_source_is_learned_kpi_llm(self) -> None:
        """Layer B extractions must be tagged source='learned:kpi-llm'
        so they don't get silently persisted as 'hardcoded' rows."""
        kpi = KpiDef(phrases=("ARR",), unit_hint="USD")
        response = {"value": 1000, "unit": "USD",
                    "excerpt": "ARR of $1,000", "section_id": "s",
                    "confidence": "high"}
        pack_record = PackRecord(
            accession="A-1", cik="C-1", ticker="X", company_name="X",
            form_type="10-K", filing_date="2024-03-07",
            sections_count=0, tokens_total=0, pack_dir="/tmp",
            built_at="2024-03-08T00:00:00+00:00",
        )
        manifest = {"filing": {"filing_date": "2024-03-07"}}
        cited = _build_cited_from_extraction(
            response=response, metric="arr", kpi_def=kpi,
            pack_record=pack_record, pack_manifest=manifest,
            primary_document="doc.htm",
        )
        self.assertEqual(cited.source, "learned:kpi-llm")

    def test_period_end_is_sentinel_not_filing_date(self) -> None:
        """period_end should be date.min (unknown) rather than the filing
        date, which is semantically different from the fiscal period end."""
        kpi = KpiDef(phrases=("ARR",), unit_hint="USD")
        response = {"value": 1000, "unit": "USD",
                    "excerpt": "ARR of $1,000", "section_id": "s",
                    "confidence": "high"}
        pack_record = PackRecord(
            accession="A-1", cik="C-1", ticker="X", company_name="X",
            form_type="10-K", filing_date="2024-03-07",
            sections_count=0, tokens_total=0, pack_dir="/tmp",
            built_at="2024-03-08T00:00:00+00:00",
        )
        manifest = {"filing": {"filing_date": "2024-03-07"}}
        cited = _build_cited_from_extraction(
            response=response, metric="arr", kpi_def=kpi,
            pack_record=pack_record, pack_manifest=manifest,
            primary_document="doc.htm",
        )
        self.assertEqual(cited.period_end, date.min)
        # filed should still be the parsed filing date
        self.assertEqual(cited.filed, date(2024, 3, 7))

    def test_document_url_uses_excerpt(self) -> None:
        kpi = KpiDef(phrases=("ARR",), unit_hint="USD")
        response = {
            "value": 1000, "unit": "USD",
            "excerpt": "Annual recurring revenue of $1,000",
            "section_id": "sec", "confidence": "high",
        }
        pack_record = PackRecord(
            accession="0001535527-24-000123", cik="0001535527",
            ticker="CRWD", company_name="CRWD",
            form_type="10-K", filing_date="2024-03-07",
            sections_count=0, tokens_total=0,
            pack_dir="/tmp/p", built_at="2024-03-08T00:00:00+00:00",
        )
        manifest = {"filing": {
            "cik": "0001535527",
            "accession": "0001535527-24-000123",
            "form_type": "10-K",
            "filing_date": "2024-03-07",
            "company_name": "CRWD",
        }}
        cited = _build_cited_from_extraction(
            response=response, metric="arr", kpi_def=kpi,
            pack_record=pack_record, pack_manifest=manifest,
            primary_document="doc.htm",
        )
        url = cited.document_url
        self.assertIsNotNone(url)
        assert url is not None
        # Should use the excerpt-based text fragment
        self.assertIn("#:~:text=", url)
        self.assertIn("Annual", url)


from edgarpack.query.kpi_extract import _verify_against_prior_filing


class TestVerifyAgainstPriorFiling(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.registry_db = Path(self._tmp.name) / "registry.db"
        self.registry = PackRegistry(db_path=self.registry_db)

    def _register(self, accession: str, filing_date: str) -> None:
        pack_dir = Path(self._tmp.name) / "packs" / "A" / accession
        _write_manifest(pack_dir, sections=[])
        self.registry.register_pack(PackRecord(
            accession=accession,
            cik="0001535527",
            ticker="CRWD",
            company_name="CRWD",
            form_type="10-K",
            filing_date=filing_date,
            sections_count=0,
            tokens_total=0,
            pack_dir=str(pack_dir),
            built_at=datetime.now(UTC).isoformat(),
        ))

    def test_returns_false_when_no_prior_filing(self) -> None:
        # Only one filing registered
        self._register("ACC-A", "2024-03-07")
        verified, method = _verify_against_prior_filing(
            current_value=3.44e9,
            metric="arr",
            cik="0001535527",
            current_accession="ACC-A",
            current_form_type="10-K",
            registry=self.registry,
            registry_path=self.registry_db,
        )
        self.assertFalse(verified)
        self.assertEqual(method, "no_prior_filing")

    def test_returns_true_when_within_order_of_magnitude(self) -> None:
        """If the prior filing's extraction returns a value within 4x,
        verify passes. Simulate by seeding the learned_concepts registry
        with a prior entry so try_extract_kpi hits the cache."""
        from edgarpack.query.learned_registry import LearnedRegistry

        self._register("ACC-23", "2023-03-01")
        self._register("ACC-24", "2024-03-07")

        # Seed a prior-filing learned row so recursive try_extract_kpi is a
        # cache hit instead of a live LLM call.
        reg = LearnedRegistry(db_path=self.registry_db)
        reg.upsert(
            cik="0001535527", metric="arr",
            concept="annual recurring revenue", taxonomy="kpi-prose",
            source="kpi-llm", verified=True,
            verif_method="order_of_magnitude",
            value_sample=2.56e9,  # prior year
            accession="ACC-23",
        )
        reg.close()

        verified, method = _verify_against_prior_filing(
            current_value=3.44e9,  # 1.34x prior year -> within [0.25, 4.0]
            metric="arr",
            cik="0001535527",
            current_accession="ACC-24",
            current_form_type="10-K",
            registry=self.registry,
            registry_path=self.registry_db,
        )
        self.assertTrue(verified)
        self.assertEqual(method, "prior_filing_crosscheck")

    def test_verify_against_prior_via_live_extraction_does_not_poison_cache(self) -> None:
        """When _verify_against_prior_filing triggers a live recursive
        extraction (cache miss), the prior extraction must NOT be cached
        with verified=False — it's a verification helper, not a user-facing
        extraction."""
        from unittest.mock import patch as _patch
        from edgarpack.query.learned_registry import LearnedRegistry

        # Register two 10-Ks (current + prior), no cache seeded
        self._register("ACC-23", "2023-03-01")
        self._register("ACC-24", "2024-03-07")

        # Build synthetic packs for both so the recursive extraction
        # can actually read manifest/sections.
        for acc in ("ACC-23", "ACC-24"):
            pack_dir = Path(self._tmp.name) / "packs" / "A" / acc
            sections_dir = pack_dir / "sections"
            sections_dir.mkdir(parents=True, exist_ok=True)
            (sections_dir / "mda.md").write_text(
                "Annual recurring revenue of $2.56 billion.",
                encoding="utf-8",
            )
            filing_date = "2023-03-01" if acc == "ACC-23" else "2024-03-07"
            manifest = {
                "schema_version": 1,
                "parser_version": "0.1.0",
                "generated_at": datetime.now(UTC).isoformat(),
                "source": {"url": "x", "fetched_at": datetime.now(UTC).isoformat()},
                "filing": {
                    "cik": "0001535527",
                    "accession": acc,
                    "form_type": "10-K",
                    "filing_date": filing_date,
                    "company_name": "CRWD",
                    "primary_document": "crwd.htm",
                },
                "sections": [
                    {"id": "10k_parti_item7_mda", "path": "sections/mda.md",
                     "title": "MD&A", "char_start": 0, "char_end": 100,
                     "tokens_approx": 20, "sha256": "abc"},
                ],
                "artifacts": {},
                "warnings": [],
                "tokens_total": 20,
            }
            (pack_dir / "manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )

        # Mock LLM to return a consistent value for the prior filing
        fake_response = _json.dumps({
            "value": 2_560_000_000,
            "unit": "USD",
            "excerpt": "Annual recurring revenue of $2.56 billion",
            "section_id": "10k_parti_item7_mda",
            "confidence": "high",
        })

        class _Fake:
            stdout = fake_response
            stderr = ""
            returncode = 0

        with _patch("edgarpack.query.kpi_extract._LLM_CMD_KPI", "codex"), \
             _patch("edgarpack.query.kpi_extract.subprocess.run",
                    return_value=_Fake):
            verified, method = _verify_against_prior_filing(
                current_value=3.44e9,  # within 4x of 2.56e9
                metric="arr",
                cik="0001535527",
                current_accession="ACC-24",
                current_form_type="10-K",
                registry=self.registry,
                registry_path=self.registry_db,
            )

        self.assertTrue(verified)
        self.assertEqual(method, "prior_filing_crosscheck")

        # Prior filing should NOT be in learned_concepts (no poison cache)
        reg = LearnedRegistry(db_path=self.registry_db)
        prior_row = reg.lookup("0001535527", "arr", accession="ACC-23")
        reg.close()
        self.assertIsNone(
            prior_row,
            "Prior filing was persisted to learned_concepts with verified=False; "
            "the _no_persist=True flag should prevent this.",
        )


class TestTryExtractKpi(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.registry_db = Path(self._tmp.name) / "registry.db"
        self.pack_registry = PackRegistry(db_path=self.registry_db)
        self.pack_dir = Path(self._tmp.name) / "packs" / "0001535527" / "0001535527-24-000123"

    def _build_pack(self) -> None:
        _write_manifest(
            self.pack_dir,
            sections=[
                {"id": "10k_parti_item7_mda", "path": "sections/mda.md",
                 "title": "MD&A", "char_start": 0, "char_end": 1000,
                 "tokens_approx": 100, "sha256": "abc"}
            ],
        )
        (self.pack_dir / "sections").mkdir(exist_ok=True)
        (self.pack_dir / "sections" / "mda.md").write_text(
            "Annual recurring revenue of $3.44 billion at fiscal year end.",
            encoding="utf-8",
        )
        self.pack_registry.register_pack(PackRecord(
            accession="0001535527-24-000123",
            cik="0001535527",
            ticker="CRWD",
            company_name="CrowdStrike Holdings, Inc.",
            form_type="10-K",
            filing_date="2024-03-07",
            sections_count=1,
            tokens_total=100,
            pack_dir=str(self.pack_dir),
            built_at=datetime.now(UTC).isoformat(),
        ))

    def test_returns_none_for_metric_not_in_catalog(self) -> None:
        from edgarpack.query.kpi_extract import try_extract_kpi
        result = try_extract_kpi(
            metric="not_a_kpi",
            cik="0001535527",
            company="CRWD",
            period="lfy",
            registry_path=self.registry_db,
            pack_registry=self.pack_registry,
        )
        self.assertIsNone(result)

    def test_returns_none_when_no_pack(self) -> None:
        """No pack registered -> None (caller renders diagnostic)."""
        from edgarpack.query.kpi_extract import try_extract_kpi
        result = try_extract_kpi(
            metric="arr",
            cik="9999999",
            company="Nobody",
            period="lfy",
            registry_path=self.registry_db,
            pack_registry=self.pack_registry,
        )
        self.assertIsNone(result)

    def test_successful_extraction_returns_cited_value(self) -> None:
        from unittest.mock import patch as _patch
        from edgarpack.query.kpi_extract import try_extract_kpi
        self._build_pack()

        fake_response = _json.dumps({
            "value": 3_440_000_000,
            "unit": "USD",
            "excerpt": "Annual recurring revenue of $3.44 billion",
            "section_id": "10k_parti_item7_mda",
            "confidence": "high",
        })

        class _Fake:
            stdout = fake_response
            stderr = ""
            returncode = 0

        with _patch("edgarpack.query.kpi_extract._LLM_CMD_KPI", "codex"), \
             _patch("edgarpack.query.kpi_extract.subprocess.run", return_value=_Fake):
            cited = try_extract_kpi(
                metric="arr",
                cik="0001535527",
                company="CrowdStrike Holdings, Inc.",
                period="lfy",
                registry_path=self.registry_db,
                pack_registry=self.pack_registry,
            )

        self.assertIsNotNone(cited)
        assert cited is not None
        self.assertEqual(cited.value, 3_440_000_000)
        self.assertEqual(cited.source, "learned:kpi-llm")
        self.assertEqual(cited.metric, "arr")
        self.assertEqual(cited.accession, "0001535527-24-000123")

        # Row persisted to learned_concepts
        from edgarpack.query.learned_registry import LearnedRegistry
        reg = LearnedRegistry(db_path=self.registry_db)
        row = reg.lookup("0001535527", "arr",
                          accession="0001535527-24-000123")
        self.assertIsNotNone(row)
        reg.close()

    def test_second_call_hits_cache(self) -> None:
        """Second call with the same args should not touch the LLM at all."""
        from unittest.mock import patch as _patch
        from edgarpack.query.kpi_extract import try_extract_kpi
        self._build_pack()

        # Seed the registry with the expected result
        from edgarpack.query.learned_registry import LearnedRegistry
        reg = LearnedRegistry(db_path=self.registry_db)
        reg.upsert(
            cik="0001535527", metric="arr",
            concept="annual recurring revenue",
            taxonomy="kpi-prose", source="kpi-llm", verified=True,
            verif_method="prior_filing_crosscheck", value_sample=3.44e9,
            accession="0001535527-24-000123",
        )
        reg.close()

        # Patch subprocess to blow up if called; cache hit means no call
        with _patch("edgarpack.query.kpi_extract.subprocess.run",
                    side_effect=AssertionError("should not be called")):
            cited = try_extract_kpi(
                metric="arr",
                cik="0001535527",
                company="CrowdStrike Holdings, Inc.",
                period="lfy",
                registry_path=self.registry_db,
                pack_registry=self.pack_registry,
            )

        self.assertIsNotNone(cited)
        assert cited is not None
        self.assertEqual(cited.source, "learned:kpi-cached")

    def test_llm_returns_not_found_returns_none_without_cache(self) -> None:
        from unittest.mock import patch as _patch
        from edgarpack.query.kpi_extract import try_extract_kpi
        self._build_pack()

        fake_response = _json.dumps({
            "value": None, "unit": None, "excerpt": "",
            "section_id": "", "confidence": "not_found",
        })

        class _Fake:
            stdout = fake_response
            stderr = ""
            returncode = 0

        with _patch("edgarpack.query.kpi_extract._LLM_CMD_KPI", "codex"), \
             _patch("edgarpack.query.kpi_extract.subprocess.run", return_value=_Fake):
            cited = try_extract_kpi(
                metric="arr",
                cik="0001535527",
                company="CrowdStrike Holdings, Inc.",
                period="lfy",
                registry_path=self.registry_db,
                pack_registry=self.pack_registry,
            )

        self.assertIsNone(cited)
        from edgarpack.query.learned_registry import LearnedRegistry
        reg = LearnedRegistry(db_path=self.registry_db)
        row = reg.lookup("0001535527", "arr", accession="0001535527-24-000123")
        self.assertIsNone(row)
        reg.close()

    def test_hallucinated_excerpt_is_rejected(self) -> None:
        from unittest.mock import patch as _patch
        from edgarpack.query.kpi_extract import try_extract_kpi
        self._build_pack()

        fake_response = _json.dumps({
            "value": 99_999_999_999,  # nonsense number
            "unit": "USD",
            "excerpt": "This sentence is not in the source text at all",
            "section_id": "10k_parti_item7_mda",
            "confidence": "high",
        })

        class _Fake:
            stdout = fake_response
            stderr = ""
            returncode = 0

        with _patch("edgarpack.query.kpi_extract._LLM_CMD_KPI", "codex"), \
             _patch("edgarpack.query.kpi_extract.subprocess.run", return_value=_Fake):
            cited = try_extract_kpi(
                metric="arr",
                cik="0001535527",
                company="CrowdStrike Holdings, Inc.",
                period="lfy",
                registry_path=self.registry_db,
                pack_registry=self.pack_registry,
            )

        self.assertIsNone(cited)

    def test_cache_hit_survives_malformed_filing_date(self) -> None:
        """A PackRecord with a malformed filing_date should not crash the
        cache path; it should degrade to sentinel values."""
        self._build_pack()

        # Manually tamper with the pack_record by re-registering with a bad date
        # (the registry won't let us do this directly, so we use raw SQL)
        import sqlite3
        conn = sqlite3.connect(str(self.registry_db))
        conn.execute(
            "UPDATE packs SET filing_date = ? WHERE accession = ?",
            ("pending", "0001535527-24-000123"),
        )
        conn.commit()
        conn.close()

        from edgarpack.query.learned_registry import LearnedRegistry
        reg = LearnedRegistry(db_path=self.registry_db)
        reg.upsert(
            cik="0001535527", metric="arr",
            concept="annual recurring revenue",
            taxonomy="kpi-prose", source="kpi-llm", verified=True,
            verif_method="prior_filing_crosscheck", value_sample=3.44e9,
            accession="0001535527-24-000123",
        )
        reg.close()

        from edgarpack.query.kpi_extract import try_extract_kpi

        # Fresh registry reference to pick up the tampered row
        fresh_pack_reg = PackRegistry(db_path=self.registry_db)
        try:
            cited = try_extract_kpi(
                metric="arr",
                cik="0001535527",
                company="CrowdStrike Holdings, Inc.",
                period="lfy",
                registry_path=self.registry_db,
                pack_registry=fresh_pack_reg,
            )
        finally:
            fresh_pack_reg.close()

        # Must not crash. Should return the cached value with sentinel dates.
        self.assertIsNotNone(cited)
        assert cited is not None
        self.assertEqual(cited.source, "learned:kpi-cached")
        self.assertEqual(cited.fiscal_year, 0)
        # filed should be the sentinel date.min

    def test_cache_hit_returns_none_on_corrupt_manifest(self) -> None:
        """A cache hit with a corrupt manifest.json must return None, not
        propagate a JSONDecodeError or leave hit_count inflated."""
        self._build_pack()

        # Corrupt the manifest
        (self.pack_dir / "manifest.json").write_text(
            "{not valid json at all",
            encoding="utf-8",
        )

        from edgarpack.query.kpi_extract import try_extract_kpi
        from edgarpack.query.learned_registry import LearnedRegistry
        reg = LearnedRegistry(db_path=self.registry_db)
        reg.upsert(
            cik="0001535527", metric="arr",
            concept="annual recurring revenue",
            taxonomy="kpi-prose", source="kpi-llm", verified=True,
            verif_method="prior_filing_crosscheck", value_sample=3.44e9,
            accession="0001535527-24-000123",
        )
        reg.close()

        cited = try_extract_kpi(
            metric="arr",
            cik="0001535527",
            company="CrowdStrike Holdings, Inc.",
            period="lfy",
            registry_path=self.registry_db,
            pack_registry=self.pack_registry,
        )

        # Must return None (graceful failure), not crash
        self.assertIsNone(cited)

        # Hit count should NOT have been bumped (Fix 3)
        reg = LearnedRegistry(db_path=self.registry_db)
        row = reg.lookup("0001535527", "arr",
                          accession="0001535527-24-000123")
        reg.close()
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row.hit_count, 0)

    def test_no_persist_flag_skips_upsert(self) -> None:
        """When _no_persist=True, successful extraction should NOT write
        to learned_concepts. Used by the recursive prior-filing verification
        to avoid polluting the cache with verified=False rows."""
        from unittest.mock import patch as _patch
        from edgarpack.query.kpi_extract import try_extract_kpi
        from edgarpack.query.learned_registry import LearnedRegistry
        self._build_pack()

        fake_response = _json.dumps({
            "value": 3_440_000_000,
            "unit": "USD",
            "excerpt": "Annual recurring revenue of $3.44 billion",
            "section_id": "10k_parti_item7_mda",
            "confidence": "high",
        })

        class _Fake:
            stdout = fake_response
            stderr = ""
            returncode = 0

        with _patch("edgarpack.query.kpi_extract._LLM_CMD_KPI", "codex"), \
             _patch("edgarpack.query.kpi_extract.subprocess.run", return_value=_Fake):
            cited = try_extract_kpi(
                metric="arr",
                cik="0001535527",
                company="CrowdStrike Holdings, Inc.",
                period="lfy",
                registry_path=self.registry_db,
                pack_registry=self.pack_registry,
                _no_persist=True,
            )

        # Extraction succeeded...
        self.assertIsNotNone(cited)
        # ...but nothing was written to learned_concepts
        reg = LearnedRegistry(db_path=self.registry_db)
        row = reg.lookup("0001535527", "arr",
                          accession="0001535527-24-000123")
        reg.close()
        self.assertIsNone(row)


if __name__ == "__main__":
    unittest.main()
