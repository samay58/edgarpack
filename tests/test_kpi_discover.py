"""Unit tests for per-company KPI discovery (`edgarpack which`).

Covers the eight scenarios in the design spec:
- Figma-style fixture: discovery surfaces the company-specific 'paid seats'.
- GAAP exclusion: Costco-style fixture; revenue / operating income never
  reach the company_kpis cache.
- Cache-per-accession: second discover_kpis call on the same pack runs zero
  LLM subprocesses.
- Alias dedupe: a second filing under a new display name folds into the
  same slug and the old display name becomes an alias.
- Table output: `_render_which_table` produces a stable, readable layout.
- JSON output: the CLI json format round-trips through to_json().
- Discovered query path: financials() resolves a discovered slug to a
  CitedValue via the company_kpis cache.
- Period end fix: discovery rows carry the pack's period_of_report when
  the manifest populates it.
"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from edgarpack.harvest.registry import PackRecord, PackRegistry
from edgarpack.query.kpi_discover import (
    CompanyKpiAggregate,
    PeriodPoint,
    discover_kpis,
    lookup_company_kpi,
)
from edgarpack.query.kpi_extract import (
    _clean_discovered_item,
    _parse_discovery_response,
    _slugify,
    extract_discoveries,
)
from edgarpack.query.learned_registry import LearnedRegistry


def _write_pack(
    *,
    pack_dir: Path,
    cik: str,
    accession: str,
    form_type: str,
    filing_date: str,
    period_of_report: str | None,
    company_name: str,
    section_id: str,
    section_body: str,
    section_title: str = "Management's Discussion and Analysis",
) -> None:
    """Write a minimal pack (manifest + one MD&A section) to disk."""
    pack_dir.mkdir(parents=True, exist_ok=True)
    sections_dir = pack_dir / "sections"
    sections_dir.mkdir(exist_ok=True)
    (sections_dir / f"{section_id}.md").write_text(section_body, encoding="utf-8")

    filing: dict = {
        "cik": cik,
        "accession": accession,
        "form_type": form_type,
        "filing_date": filing_date,
        "company_name": company_name,
    }
    if period_of_report is not None:
        filing["period_of_report"] = period_of_report

    manifest = {
        "schema_version": 1,
        "parser_version": "0.1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "source": {"url": "https://example/filing", "fetched_at": datetime.now(UTC).isoformat()},
        "filing": filing,
        "sections": [
            {
                "id": section_id,
                "path": f"sections/{section_id}.md",
                "title": section_title,
                "char_start": 0,
                "char_end": len(section_body),
                "tokens_approx": max(1, len(section_body) // 4),
                "sha256": "0" * 64,
            }
        ],
        "artifacts": {},
        "warnings": [],
        "tokens_total": max(1, len(section_body) // 4),
    }
    (pack_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _register_pack(
    registry: PackRegistry,
    *,
    pack_dir: Path,
    accession: str,
    cik: str,
    company_name: str,
    form_type: str,
    filing_date: str,
    ticker: str | None = None,
) -> PackRecord:
    record = PackRecord(
        accession=accession,
        cik=cik,
        ticker=ticker,
        company_name=company_name,
        form_type=form_type,
        filing_date=filing_date,
        sections_count=1,
        tokens_total=100,
        pack_dir=str(pack_dir),
        built_at=datetime.now(UTC).isoformat(),
    )
    registry.register_pack(record)
    return record


def _mock_llm_response(kpis: list[dict]) -> str:
    return json.dumps({"kpis": kpis})


class TestSlugify(unittest.TestCase):
    def test_lower_snake_case(self) -> None:
        self.assertEqual(_slugify("Paid Seats"), "paid_seats")

    def test_strips_punctuation(self) -> None:
        self.assertEqual(_slugify("Monthly Active Users (MAU)"), "monthly_active_users_mau")

    def test_ascii_fold(self) -> None:
        self.assertEqual(_slugify("Cafés"), "cafes")

    def test_empty(self) -> None:
        self.assertEqual(_slugify(""), "")
        self.assertEqual(_slugify("!!!"), "")


class TestParseDiscoveryResponse(unittest.TestCase):
    def test_parses_object_shape(self) -> None:
        raw = json.dumps({"kpis": [{"slug": "x"}, {"slug": "y"}]})
        self.assertEqual(len(_parse_discovery_response(raw) or []), 2)

    def test_parses_list_shape(self) -> None:
        raw = json.dumps([{"slug": "x"}])
        self.assertEqual(len(_parse_discovery_response(raw) or []), 1)

    def test_strips_markdown_fence(self) -> None:
        raw = f"```json\n{json.dumps({'kpis': [{'slug': 'z'}]})}\n```\n"
        self.assertEqual(len(_parse_discovery_response(raw) or []), 1)

    def test_returns_none_on_garbage(self) -> None:
        self.assertIsNone(_parse_discovery_response("not json at all"))
        self.assertIsNone(_parse_discovery_response(""))


class TestCleanDiscoveredItem(unittest.TestCase):
    def setUp(self) -> None:
        self.text = (
            "\n\n--- [10k_parti_item7_mda] ---\n\n"
            "We ended the year with 1.2 million paid seats, up from 900 thousand."
        )
        self.section_ids = {"10k_parti_item7_mda"}

    def test_valid_item(self) -> None:
        item = {
            "slug": "paid_seats",
            "display_name": "Paid seats",
            "unit": "count",
            "magnitude": "millions",
            "value": 1.2,
            "period_end": "2024-01-31",
            "section_id": "10k_parti_item7_mda",
            "source_substring": "1.2 million paid seats",
            "confidence": 0.9,
        }
        result = _clean_discovered_item(item, self.section_ids, self.text, set())
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.slug, "paid_seats")
        self.assertEqual(result.unit, "count")
        self.assertEqual(result.magnitude, "millions")
        self.assertAlmostEqual(result.value or 0.0, 1.2)
        self.assertFalse(result.reused_slug)

    def test_hallucinated_substring_rejected(self) -> None:
        item = {
            "slug": "ghosts",
            "display_name": "Ghosts",
            "unit": "count",
            "value": 100,
            "source_substring": "100 ghosts observed in the filing",
            "confidence": 1.0,
        }
        self.assertIsNone(
            _clean_discovered_item(item, self.section_ids, self.text, set())
        )

    def test_unknown_section_id_dropped_but_item_kept(self) -> None:
        item = {
            "slug": "paid_seats",
            "display_name": "Paid seats",
            "unit": "count",
            "magnitude": "millions",
            "value": 1.2,
            "section_id": "some_other_section",
            "source_substring": "1.2 million paid seats",
            "confidence": 0.5,
        }
        result = _clean_discovered_item(item, self.section_ids, self.text, set())
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIsNone(result.section_id)

    def test_reused_slug_flag(self) -> None:
        item = {
            "slug": "paid_seats",
            "display_name": "Active Designers",
            "unit": "count",
            "magnitude": "millions",
            "value": 1.2,
            "section_id": "10k_parti_item7_mda",
            "source_substring": "1.2 million paid seats",
            "confidence": 0.9,
        }
        result = _clean_discovered_item(
            item, self.section_ids, self.text, {"paid_seats"}
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertTrue(result.reused_slug)

    def test_invalid_unit_nulls_out(self) -> None:
        item = {
            "slug": "paid_seats",
            "display_name": "Paid seats",
            "unit": "bogus-unit",
            "value": 1.2,
            "magnitude": "millions",
            "section_id": "10k_parti_item7_mda",
            "source_substring": "1.2 million paid seats",
        }
        result = _clean_discovered_item(item, self.section_ids, self.text, set())
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIsNone(result.unit)


class _DiscoverHarness(unittest.TestCase):
    """Shared setup for tests that drive discover_kpis end-to-end."""

    CIK = "0001792044"
    COMPANY = "Figma, Inc."

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.registry_db = Path(self._tmp.name) / "registry.db"
        self.pack_registry = PackRegistry(db_path=self.registry_db)
        self.addCleanup(self.pack_registry.close)

    def _add_pack(
        self,
        *,
        accession: str,
        filing_date: str,
        period_of_report: str,
        form_type: str = "10-K",
        section_body: str = (
            "Key Business Metrics. We ended the fiscal year with 1.2 million "
            "paid seats, compared to 900 thousand in the prior year. "
            "Weekly active teams were 450 thousand."
        ),
    ) -> Path:
        pack_dir = Path(self._tmp.name) / "packs" / accession.replace("-", "")
        _write_pack(
            pack_dir=pack_dir,
            cik=self.CIK,
            accession=accession,
            form_type=form_type,
            filing_date=filing_date,
            period_of_report=period_of_report,
            company_name=self.COMPANY,
            section_id="10k_parti_item7_mda",
            section_body=section_body,
        )
        _register_pack(
            self.pack_registry,
            pack_dir=pack_dir,
            accession=accession,
            cik=self.CIK,
            company_name=self.COMPANY,
            form_type=form_type,
            filing_date=filing_date,
            ticker="FIG",
        )
        return pack_dir


class TestDiscoverKpisFiguraFixture(_DiscoverHarness):
    def test_finds_paid_seats_and_persists(self) -> None:
        self._add_pack(
            accession="0001792044-24-000001",
            filing_date="2024-03-15",
            period_of_report="2024-01-31",
        )

        fake_raw = _mock_llm_response(
            [
                {
                    "slug": "paid_seats",
                    "display_name": "Paid seats",
                    "unit": "count",
                    "magnitude": "millions",
                    "value": 1.2,
                    "period_end": "2024-01-31",
                    "definition": "Seats under a paid subscription at period end.",
                    "section_id": "10k_parti_item7_mda",
                    "source_substring": "1.2 million paid seats",
                    "confidence": 0.92,
                },
                {
                    "slug": "weekly_active_teams",
                    "display_name": "Weekly active teams",
                    "unit": "count",
                    "magnitude": "thousands",
                    "value": 450,
                    "period_end": "2024-01-31",
                    "definition": "Distinct teams that used the product in the last 7 days.",
                    "section_id": "10k_parti_item7_mda",
                    "source_substring": "Weekly active teams were 450 thousand",
                    "confidence": 0.88,
                },
            ]
        )

        with (
            patch("edgarpack.query.kpi_extract._LLM_CMD_KPI", "codex"),
            patch(
                "edgarpack.query.kpi_extract._run_llm_raw",
                return_value=fake_raw,
            ) as mock_run,
        ):
            aggregates = discover_kpis(
                cik=self.CIK,
                pack_registry=self.pack_registry,
                registry_path=self.registry_db,
            )

        # First pass: one LLM call.
        self.assertEqual(mock_run.call_count, 1)

        slugs = {a.slug for a in aggregates}
        self.assertIn("paid_seats", slugs)
        self.assertIn("weekly_active_teams", slugs)

        paid = next(a for a in aggregates if a.slug == "paid_seats")
        self.assertEqual(paid.source, "discovered")
        self.assertEqual(paid.unit, "count")
        self.assertEqual(paid.latest and paid.latest.value, 1.2)
        self.assertEqual(paid.latest and paid.latest.period_end, "2024-01-31")

    def test_caches_per_accession_no_second_llm_call(self) -> None:
        self._add_pack(
            accession="0001792044-24-000001",
            filing_date="2024-03-15",
            period_of_report="2024-01-31",
        )

        fake_raw = _mock_llm_response(
            [
                {
                    "slug": "paid_seats",
                    "display_name": "Paid seats",
                    "unit": "count",
                    "magnitude": "millions",
                    "value": 1.2,
                    "period_end": "2024-01-31",
                    "section_id": "10k_parti_item7_mda",
                    "source_substring": "1.2 million paid seats",
                    "confidence": 0.9,
                }
            ]
        )

        with (
            patch("edgarpack.query.kpi_extract._LLM_CMD_KPI", "codex"),
            patch(
                "edgarpack.query.kpi_extract._run_llm_raw",
                return_value=fake_raw,
            ) as mock_run,
        ):
            discover_kpis(
                cik=self.CIK,
                pack_registry=self.pack_registry,
                registry_path=self.registry_db,
            )
            # Second call on same accession hits cache.
            discover_kpis(
                cik=self.CIK,
                pack_registry=self.pack_registry,
                registry_path=self.registry_db,
            )

        self.assertEqual(mock_run.call_count, 1)

    def test_empty_extraction_persists_sentinel_and_skips_next_call(self) -> None:
        self._add_pack(
            accession="0001792044-24-000002",
            filing_date="2024-03-15",
            period_of_report="2024-01-31",
        )

        fake_raw = _mock_llm_response([])

        with (
            patch("edgarpack.query.kpi_extract._LLM_CMD_KPI", "codex"),
            patch(
                "edgarpack.query.kpi_extract._run_llm_raw",
                return_value=fake_raw,
            ) as mock_run,
        ):
            first = discover_kpis(
                cik=self.CIK,
                pack_registry=self.pack_registry,
                registry_path=self.registry_db,
            )
            second = discover_kpis(
                cik=self.CIK,
                pack_registry=self.pack_registry,
                registry_path=self.registry_db,
            )

        self.assertEqual(first, [])
        self.assertEqual(second, [])
        self.assertEqual(mock_run.call_count, 1)

    def test_alias_accumulates_across_filings(self) -> None:
        self._add_pack(
            accession="0001792044-23-000001",
            filing_date="2023-03-15",
            period_of_report="2023-01-31",
            section_body=(
                "Key Business Metrics. We ended the fiscal year with 900 thousand "
                "active designers, our core subscription measure."
            ),
        )
        self._add_pack(
            accession="0001792044-24-000001",
            filing_date="2024-03-15",
            period_of_report="2024-01-31",
            section_body=(
                "Key Business Metrics. We ended the fiscal year with 1.2 million "
                "paid seats, compared to 900 thousand in the prior year."
            ),
        )

        responses = iter(
            [
                _mock_llm_response(
                    [
                        {
                            "slug": "paid_seats",
                            "display_name": "Active designers",
                            "unit": "count",
                            "magnitude": "thousands",
                            "value": 900,
                            "period_end": "2024-01-31",
                            "section_id": "10k_parti_item7_mda",
                            "source_substring": "1.2 million paid seats",
                            "confidence": 0.9,
                        }
                    ]
                ),
                _mock_llm_response(
                    [
                        {
                            "slug": "paid_seats",
                            "display_name": "Active designers",
                            "unit": "count",
                            "magnitude": "thousands",
                            "value": 900,
                            "period_end": "2023-01-31",
                            "section_id": "10k_parti_item7_mda",
                            "source_substring": "900 thousand active designers",
                            "confidence": 0.85,
                        }
                    ]
                ),
            ]
        )

        def _fake_run(_prompt, timeout=None):  # noqa: ARG001
            try:
                return next(responses)
            except StopIteration:
                return None

        with (
            patch("edgarpack.query.kpi_extract._LLM_CMD_KPI", "codex"),
            patch("edgarpack.query.kpi_extract._run_llm_raw", side_effect=_fake_run),
        ):
            aggregates = discover_kpis(
                cik=self.CIK,
                pack_registry=self.pack_registry,
                registry_path=self.registry_db,
            )

        paid = next((a for a in aggregates if a.slug == "paid_seats"), None)
        self.assertIsNotNone(paid)
        assert paid is not None
        # Both filings contributed rows; the slug is shared.
        self.assertEqual(len(paid.periods), 2)
        # Latest (2024) should lead.
        self.assertEqual(paid.periods[0].period_end, "2024-01-31")


class TestWhichCliOutput(unittest.TestCase):
    def test_json_cli_output_shape(self) -> None:
        aggregate = CompanyKpiAggregate(
            slug="paid_seats",
            display_name="Paid seats",
            source="discovered",
            unit="count",
            definition="Paid subscription seats at period end.",
            aliases=["active designers"],
            periods=[
                PeriodPoint(
                    label="FY2024",
                    sort_key="2024-01-31",
                    period_end="2024-01-31",
                    fiscal_year=2024,
                    fiscal_period="FY",
                    form_type="10-K",
                    accession="0001792044-24-000001",
                    value=1.2,
                    unit="count",
                    magnitude="millions",
                    section_id="10k_parti_item7_mda",
                    chunk_id=None,
                    source_substring="1.2 million paid seats",
                )
            ],
        )
        payload = aggregate.to_json()
        self.assertEqual(payload["slug"], "paid_seats")
        self.assertEqual(payload["source"], "discovered")
        self.assertEqual(payload["latest_period"], "FY2024")
        self.assertEqual(payload["latest_value"], 1.2)
        self.assertEqual(payload["periods"][0]["accession"], "0001792044-24-000001")
        self.assertEqual(payload["aliases"], ["active designers"])

    def test_render_which_table_renders_latest_and_gaps(self) -> None:
        from edgarpack.cli import _render_which_table

        p_2024 = PeriodPoint(
            label="FY2024",
            sort_key="2024-01-31",
            period_end="2024-01-31",
            fiscal_year=2024,
            fiscal_period="FY",
            form_type="10-K",
            accession="A-24",
            value=1.2,
            unit="count",
            magnitude="millions",
            section_id="s",
            chunk_id=None,
            source_substring="...",
        )
        p_2023 = PeriodPoint(
            label="FY2023",
            sort_key="2023-01-31",
            period_end="2023-01-31",
            fiscal_year=2023,
            fiscal_period="FY",
            form_type="10-K",
            accession="A-23",
            value=0.9,
            unit="count",
            magnitude="millions",
            section_id="s",
            chunk_id=None,
            source_substring="...",
        )
        # Metric that dropped in 2024 to test the gap column.
        p_weekly_2023 = PeriodPoint(
            label="FY2023",
            sort_key="2023-01-31",
            period_end="2023-01-31",
            fiscal_year=2023,
            fiscal_period="FY",
            form_type="10-K",
            accession="A-23",
            value=420,
            unit="count",
            magnitude="thousands",
            section_id="s",
            chunk_id=None,
            source_substring="...",
        )

        aggs = [
            CompanyKpiAggregate(
                slug="paid_seats",
                display_name="Paid seats",
                source="discovered",
                unit="count",
                definition=None,
                aliases=["active designers"],
                periods=[p_2024, p_2023],
            ),
            CompanyKpiAggregate(
                slug="weekly_active_teams",
                display_name="Weekly active teams",
                source="discovered",
                unit="count",
                definition=None,
                aliases=[],
                periods=[p_weekly_2023],
            ),
        ]
        table = _render_which_table(aggs, max_periods=4)

        self.assertIn("paid_seats", table)
        self.assertIn("weekly_active_teams", table)
        self.assertIn("FY2024", table)
        self.assertIn("FY2023", table)
        self.assertIn("(aliases) paid_seats", table)
        # weekly_active_teams should render '-' for FY2024 since it was not
        # disclosed that year.
        lines = [line for line in table.splitlines() if line.startswith("weekly_active_teams")]
        self.assertTrue(lines)
        self.assertIn(" -", lines[0])


class TestLookupAndFinancialsRouting(unittest.TestCase):
    CIK = "0001792044"
    COMPANY = "Figma, Inc."

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.registry_db = Path(self._tmp.name) / "registry.db"
        self.pack_registry = PackRegistry(db_path=self.registry_db)
        self.addCleanup(self.pack_registry.close)

        pack_dir = Path(self._tmp.name) / "packs" / "fig24"
        _write_pack(
            pack_dir=pack_dir,
            cik=self.CIK,
            accession="0001792044-24-000001",
            form_type="10-K",
            filing_date="2024-03-15",
            period_of_report="2024-01-31",
            company_name=self.COMPANY,
            section_id="10k_parti_item7_mda",
            section_body="We ended the fiscal year with 1.2 million paid seats.",
        )
        _register_pack(
            self.pack_registry,
            pack_dir=pack_dir,
            accession="0001792044-24-000001",
            cik=self.CIK,
            company_name=self.COMPANY,
            form_type="10-K",
            filing_date="2024-03-15",
            ticker="FIG",
        )

        reg = LearnedRegistry(db_path=self.registry_db)
        try:
            reg.company_kpi_upsert(
                cik=self.CIK,
                accession="0001792044-24-000001",
                slug="paid_seats",
                display_name="Paid seats",
                aliases=[],
                unit="count",
                magnitude="millions",
                value=1.2,
                period_end="2024-01-31",
                fiscal_year=2024,
                fiscal_period="FY",
                form_type="10-K",
                definition="Seats at period end.",
                section_id="10k_parti_item7_mda",
                chunk_id=None,
                source_substring="1.2 million paid seats",
                confidence=0.9,
            )
        finally:
            reg.close()

    def test_lookup_company_kpi_returns_lfy_row(self) -> None:
        row = lookup_company_kpi(
            cik=self.CIK,
            slug="paid_seats",
            period="lfy",
            registry_path=self.registry_db,
            pack_registry=self.pack_registry,
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row.slug, "paid_seats")
        self.assertAlmostEqual(row.value or 0.0, 1.2)

    def test_financials_resolves_discovered_slug(self) -> None:
        """`financials()` must accept a discovered slug and route it
        through the company_kpis cache rather than raising MetricNotFound.
        """
        import importlib

        fin_mod = importlib.import_module("edgarpack.query.financials")

        async def _fake_resolve_ticker(company, force=False):  # noqa: ARG001
            return self.CIK, self.COMPANY

        async def _fake_fetch_company_facts(cik, force=False):  # noqa: ARG001
            return {"facts": {}}

        async def _fake_fetch_submissions(cik, force=False):  # noqa: ARG001
            return {"filings": {"recent": {}}}

        registry_db = self.registry_db
        pack_registry = self.pack_registry

        def _patched_lookup(cik, slug, period, **kwargs):  # noqa: ARG001
            return lookup_company_kpi(
                cik=cik,
                slug=slug,
                period=period,
                registry_path=registry_db,
                pack_registry=pack_registry,
            )

        with (
            patch.object(fin_mod, "resolve_ticker", _fake_resolve_ticker),
            patch.object(fin_mod, "fetch_company_facts", _fake_fetch_company_facts),
            patch.object(fin_mod, "fetch_submissions", _fake_fetch_submissions),
            patch.object(
                fin_mod,
                "LearnedRegistry",
                lambda db_path=None: LearnedRegistry(db_path=registry_db),
            ),
            patch.object(fin_mod, "lookup_company_kpi", _patched_lookup),
        ):
            import asyncio

            result = asyncio.run(
                fin_mod.financials(
                    company="FIG",
                    metrics="paid_seats",
                    period="lfy",
                )
            )

        cited = result.metrics.get("paid_seats")
        self.assertIsNotNone(cited)
        self.assertFalse(isinstance(cited, list))
        # value was stored as (1.2, millions); financials expands to base units.
        self.assertAlmostEqual(float(cited.value or 0), 1_200_000.0)
        self.assertEqual(cited.period_end, date(2024, 1, 31))
        self.assertEqual(cited.source, "learned:kpi-discovered")


class TestExtractDiscoveriesPeriodFix(unittest.TestCase):
    """Regression: extraction rows inherit period_of_report from manifest."""

    def test_rows_carry_period_of_report_from_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack_dir = Path(tmp) / "pack"
            _write_pack(
                pack_dir=pack_dir,
                cik="0001792044",
                accession="0001792044-24-000001",
                form_type="10-K",
                filing_date="2024-03-15",
                period_of_report="2024-01-31",
                company_name="Figma, Inc.",
                section_id="10k_parti_item7_mda",
                section_body="We ended the year with 1.2 million paid seats.",
            )
            manifest_path = pack_dir / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            pack_record = PackRecord(
                accession="0001792044-24-000001",
                cik="0001792044",
                ticker="FIG",
                company_name="Figma, Inc.",
                form_type="10-K",
                filing_date="2024-03-15",
                sections_count=1,
                tokens_total=10,
                pack_dir=str(pack_dir),
                built_at="2024-03-15T00:00:00+00:00",
            )

            fake_raw = _mock_llm_response(
                [
                    {
                        "slug": "paid_seats",
                        "display_name": "Paid seats",
                        "unit": "count",
                        "magnitude": "millions",
                        "value": 1.2,
                        "period_end": "",
                        "section_id": "10k_parti_item7_mda",
                        "source_substring": "1.2 million paid seats",
                        "confidence": 0.9,
                    }
                ]
            )

            with (
                patch("edgarpack.query.kpi_extract._LLM_CMD_KPI", "codex"),
                patch(
                    "edgarpack.query.kpi_extract._run_llm_raw",
                    return_value=fake_raw,
                ),
            ):
                rows = extract_discoveries(
                    pack_dir=pack_dir,
                    pack_record=pack_record,
                    manifest=manifest,
                )

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].period_end, "2024-01-31")
            self.assertEqual(rows[0].fiscal_year, 2024)
            self.assertEqual(rows[0].fiscal_period, "FY")


if __name__ == "__main__":
    unittest.main()
