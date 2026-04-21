"""CLI UX tests for the `build -> which -> query` onboarding flow."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from edgarpack import cli
from edgarpack.cli import _render_which_diagnostics
from edgarpack.harvest.registry import PackRecord, PackRegistry
from edgarpack.query.kpi_discover import (
    CompanyKpiAggregate,
    DiscoveryDiagnostics,
    PeriodPoint,
)
from edgarpack.query.layer_zero import MetricNotFound


def _build_args(*, company=None, cik=None, form="10-K", accession=None, tmp_path=None):
    return SimpleNamespace(
        company=company,
        cik=cik,
        accession=accession,
        form=form,
        out=tmp_path or "./packs",
        with_chunks=False,
        with_xbrl=False,
        force=False,
    )


def _which_args(company="FIG", which_format="table", no_cache=False, only="all", max_periods=6):
    return SimpleNamespace(
        company=company,
        which_format=which_format,
        no_cache=no_cache,
        only=only,
        max_periods=max_periods,
    )


def _query_args(company="CRWD", metrics="subscription_customers"):
    return SimpleNamespace(
        company=company,
        metrics=metrics,
        period="lfy",
        preset=None,
        output_format="table",
        force=False,
        strict=False,
        currency="native",
        audit=False,
        show_links="primary",
        citations="inline",
    )


def _resolved_company(ticker="FIG", cik="0001579878", alias="Figma, Inc."):
    return SimpleNamespace(ticker=ticker, cik=cik, aliases=(alias,), private=False, source="SEC")


def _build_result(tmp_path: Path, warnings: list[str] | None = None):
    output_dir = tmp_path / "packs" / "0001579878" / "0001628280-26-009228"
    output_dir.mkdir(parents=True)
    manifest = {
        "filing": {
            "accession": "0001628280-26-009228",
            "cik": "0001579878",
            "company_name": "Figma, Inc.",
            "form_type": "10-K",
            "filing_date": "2026-02-18",
        }
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return SimpleNamespace(
        output_dir=output_dir,
        filing_meta=manifest["filing"],
        sections_count=122,
        tokens_total=144_959,
        warnings=warnings or [],
    )


def test_register_pack_result_writes_registry(tmp_path, monkeypatch):
    registry_path = tmp_path / "registry.db"
    monkeypatch.setattr("edgarpack.harvest.registry.DEFAULT_REGISTRY_PATH", registry_path)

    result = _build_result(tmp_path)
    cli._register_pack_result(result, ticker="FIG")

    reg = PackRegistry(db_path=registry_path)
    try:
        rows = reg.list_packs(cik="0001579878")
    finally:
        reg.close()

    assert len(rows) == 1
    assert rows[0].ticker == "FIG"
    assert rows[0].accession == "0001628280-26-009228"


def test_cmd_build_registers_pack_and_groups_warnings(tmp_path, capsys):
    warnings = [
        "Duplicate section ID detected, suffix added",
        "Duplicate section ID detected, suffix added",
        "Content before first detected section",
    ]
    stub_result = _build_result(tmp_path, warnings=warnings)

    with (
        patch("edgarpack.pack.build.build_pack", new=AsyncMock(return_value=stub_result)),
        patch(
            "edgarpack.cli._resolve_cli_company",
            new=AsyncMock(return_value=_resolved_company()),
        ),
        patch("edgarpack.cli._register_pack_result") as mock_register,
    ):
        rc = cli._cmd_build(_build_args(company="FIG", tmp_path=tmp_path))

    out = capsys.readouterr().out
    assert rc == 0
    mock_register.assert_called_once()
    assert "Registry: ready for `edgarpack which FIG`" in out
    assert "Non-fatal warnings" in out
    assert "Duplicate section IDs: 2 sections were de-duped" in out
    assert "Content before first detected section: 1 boundary issue" in out


def test_cmd_which_no_packs_uses_ticker_first_copy(capsys):
    mock_registry = Mock()
    mock_registry.list_packs.return_value = []
    mock_registry.close.return_value = None

    with (
        patch(
            "edgarpack.cli._resolve_cli_company",
            new=AsyncMock(return_value=_resolved_company()),
        ),
        patch("edgarpack.harvest.registry.PackRegistry", return_value=mock_registry),
    ):
        rc = cli._cmd_which(_which_args(company="FIG"))

    err = capsys.readouterr().err
    assert rc == 1
    assert "`edgarpack build FIG --form 10-K`" in err
    assert "--cik" not in err


def test_cmd_which_shows_progress_and_summary(capsys):
    pack = PackRecord(
        accession="0001628280-26-009228",
        cik="0001579878",
        ticker="FIG",
        company_name="Figma, Inc.",
        form_type="10-K",
        filing_date="2026-02-18",
        sections_count=122,
        tokens_total=144_959,
        pack_dir="packs/0001579878/0001628280-26-009228",
        built_at="2026-02-18T00:00:00+00:00",
    )
    aggregate = CompanyKpiAggregate(
        slug="paid_seats",
        display_name="Paid seats",
        source="discovered",
        unit="count",
        definition=None,
        aliases=[],
        periods=[
            PeriodPoint(
                label="FY2026",
                sort_key="2026-01-31",
                period_end="2026-01-31",
                fiscal_year=2026,
                fiscal_period="FY",
                form_type="10-K",
                accession=pack.accession,
                value=1.2,
                unit="count",
                magnitude="millions",
                section_id="10k_partii_item7_managements_discussion",
                chunk_id=None,
                source_substring="1.2 million paid seats",
            )
        ],
    )

    def _fake_discover(*, diagnostics=None, progress_callback=None, **kwargs):  # noqa: ARG001
        assert diagnostics is not None
        diagnostics.total_registered_packs = 1
        diagnostics.eligible_packs = 1
        diagnostics.discovered_packs = 1
        diagnostics.manifest_missing_packs = 1
        if progress_callback is not None:
            from edgarpack.query.kpi_discover import DiscoveryProgressEvent

            progress_callback(DiscoveryProgressEvent(phase="pack", index=1, total=1, pack=pack))
        return [aggregate]

    mock_registry = Mock()
    mock_registry.list_packs.return_value = [pack]
    mock_registry.close.return_value = None

    with (
        patch(
            "edgarpack.cli._resolve_cli_company",
            new=AsyncMock(return_value=_resolved_company()),
        ),
        patch("edgarpack.harvest.registry.PackRegistry", return_value=mock_registry),
        patch("edgarpack.query.kpi_discover.discover_kpis", side_effect=_fake_discover),
    ):
        rc = cli._cmd_which(_which_args(company="FIG"))

    captured = capsys.readouterr()
    assert rc == 0
    assert "Resolving company FIG -> Figma, Inc. (CIK 0001579878)" in captured.err
    assert "Loading up to 1 registered pack(s)" in captured.err
    assert "Running KPI discovery on filing 1/1 (10-K 2026-02-18)" in captured.err
    assert (
        "Discovery summary: 1 analyzed, 1 skipped "
        "(manifest missing; run `edgarpack build <ticker>`)"
    ) in captured.err
    assert "Rendering KPI table" in captured.err
    assert "paid_seats" in captured.out


def test_cmd_which_empty_state_is_actionable(capsys):
    pack = PackRecord(
        accession="0001628280-26-009228",
        cik="0001579878",
        ticker="FIG",
        company_name="Figma, Inc.",
        form_type="10-K",
        filing_date="2026-02-18",
        sections_count=122,
        tokens_total=144_959,
        pack_dir="packs/0001579878/0001628280-26-009228",
        built_at="2026-02-18T00:00:00+00:00",
    )

    def _fake_discover(*, diagnostics=None, **kwargs):  # noqa: ARG001
        assert diagnostics is not None
        diagnostics.total_registered_packs = 1
        diagnostics.eligible_packs = 1
        diagnostics.llm_failed_packs = 1
        return []

    mock_registry = Mock()
    mock_registry.list_packs.return_value = [pack]
    mock_registry.close.return_value = None

    with (
        patch(
            "edgarpack.cli._resolve_cli_company",
            new=AsyncMock(return_value=_resolved_company()),
        ),
        patch("edgarpack.harvest.registry.PackRegistry", return_value=mock_registry),
        patch("edgarpack.query.kpi_discover.discover_kpis", side_effect=_fake_discover),
    ):
        rc = cli._cmd_which(_which_args(company="FIG"))

    captured = capsys.readouterr()
    assert rc == 0
    assert "No KPIs shown for Figma, Inc. because discovery failed on 1 filing(s)." in captured.out
    assert "`edgarpack which FIG --no-cache`" in captured.out


def test_cmd_query_metric_not_found_adds_actionable_guidance(capsys):
    with patch(
        "edgarpack.query.financials.financials",
        new=AsyncMock(side_effect=MetricNotFound("subscription_customers", ["customer_count"])),
    ):
        rc = cli._cmd_query(_query_args())

    err = capsys.readouterr().err
    assert rc == 2
    assert "Unknown metric" in err
    assert "Tip: `subscription_customers` maps to the catalog metric `customer_count`." in err
    assert "Company-specific KPI slugs come from `edgarpack which CRWD`." in err
    assert "catalog metric like `customer_count`" in err


class TestWhichDiagnosticsSplit(unittest.TestCase):
    def test_missing_manifest_emits_specific_remediation(self) -> None:
        d = DiscoveryDiagnostics(manifest_missing_packs=3)
        out = _render_which_diagnostics(d)
        self.assertIsNotNone(out)
        self.assertIn("manifest missing", out)
        self.assertIn("edgarpack build", out)

    def test_invalid_json_emits_specific_hint(self) -> None:
        d = DiscoveryDiagnostics(manifest_invalid_json_packs=2)
        out = _render_which_diagnostics(d)
        self.assertIsNotNone(out)
        self.assertIn("invalid JSON", out)
        self.assertIn("doctor", out)

    def test_schema_mismatch_emits_specific_hint(self) -> None:
        d = DiscoveryDiagnostics(manifest_schema_mismatch_packs=1)
        out = _render_which_diagnostics(d)
        self.assertIsNotNone(out)
        self.assertIn("schema mismatch", out)

    def test_io_error_emits_specific_hint(self) -> None:
        d = DiscoveryDiagnostics(manifest_io_error_packs=1)
        out = _render_which_diagnostics(d)
        self.assertIsNotNone(out)
        self.assertIn("I/O", out)

    def test_no_manifest_issues_renders_cleanly(self) -> None:
        d = DiscoveryDiagnostics(cached_packs=2, discovered_packs=1)
        out = _render_which_diagnostics(d)
        self.assertIsNotNone(out)
        self.assertIn("cached", out)
        self.assertIn("analyzed", out)
