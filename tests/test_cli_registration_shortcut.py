"""Short registration commands hide the build/query plumbing."""

from __future__ import annotations

import importlib
import json
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from edgarpack import cli
from edgarpack.query.models import CitedValue, QueryResult


def _result(period: str = "lfy") -> QueryResult:
    return QueryResult(
        company="Bending Spoons S.p.A.",
        cik="0002004711",
        period=period,
        metrics={
            "revenue": CitedValue(
                value=1_306_404_000,
                unit="USD",
                metric="revenue",
                concept="Revenue",
                period_end=date(2025, 12, 31),
                fiscal_year=2025,
                fiscal_period="FY",
                form_type="F-1",
                filed=date(2026, 6, 8),
                accession="0001104659-26-071170",
                cik="0002004711",
                company="Bending Spoons S.p.A.",
                source="s1_snapshot",
            )
        },
    )


def test_f1_shortcut_builds_missing_pack_then_queries(tmp_path, monkeypatch, capsys):
    financials_module = importlib.import_module("edgarpack.query.financials")
    resolved_company = SimpleNamespace(ticker="BEND", cik="0002004711", private=False)
    build_result = SimpleNamespace(
        output_dir=tmp_path / "0002004711" / "0001104659-26-071170",
        filing_meta={
            "accession": "0001104659-26-071170",
            "form_type": "F-1",
            "company_name": "Bending Spoons S.p.A.",
        },
        warnings=[],
    )
    build_pack = AsyncMock(return_value=build_result)
    financials = AsyncMock(return_value=_result())

    monkeypatch.setattr(cli, "_cik_from_company_args", AsyncMock(return_value=(0, "0002004711")))
    monkeypatch.setattr(cli, "_resolve_cli_company", AsyncMock(return_value=resolved_company))
    register_pack = Mock()
    monkeypatch.setattr(cli, "_register_pack_result", register_pack)
    monkeypatch.setattr("edgarpack.pack.build.build_pack", build_pack)
    monkeypatch.setattr(financials_module, "financials", financials)

    rc = cli.main(["f1", "0002004711", "revenue", "--packs", str(tmp_path)])

    captured = capsys.readouterr()
    assert rc == 0
    assert "Revenue:" in captured.out
    assert "Reproduce: edgarpack f1 0002004711 revenue --packs" in captured.out
    assert str(tmp_path) in captured.out
    assert "Building latest F-1 pack" in captured.err
    build_pack.assert_awaited_once()
    kwargs = build_pack.await_args.kwargs
    assert kwargs["form_type"] == "F-1"
    assert kwargs["out_dir"] == tmp_path
    assert kwargs["with_chunks"] is True
    register_pack.assert_called_once_with(build_result, ticker="BEND")
    financials.assert_awaited_once()
    assert financials.await_args.kwargs["pack_root"] == tmp_path


def test_f1_shortcut_reuses_existing_pack(tmp_path, monkeypatch, capsys):
    financials_module = importlib.import_module("edgarpack.query.financials")
    pack_dir = tmp_path / "0002004711" / "0001104659-26-071170"
    pack_dir.mkdir(parents=True)
    (pack_dir / "manifest.json").write_text(
        json.dumps(
            {
                "filing": {
                    "cik": "0002004711",
                    "accession": "0001104659-26-071170",
                    "form_type": "F-1",
                    "filing_date": "2026-06-08",
                    "company_name": "Bending Spoons S.p.A.",
                }
            }
        ),
        encoding="utf-8",
    )
    build_pack = AsyncMock()
    financials = AsyncMock(return_value=_result())

    monkeypatch.setattr(cli, "_cik_from_company_args", AsyncMock(return_value=(0, "0002004711")))
    monkeypatch.setattr(cli, "_resolve_cli_company", AsyncMock())
    monkeypatch.setattr("edgarpack.pack.build.build_pack", build_pack)
    monkeypatch.setattr(financials_module, "financials", financials)

    rc = cli.main(["f1", "0002004711", "revenue", "--packs", str(tmp_path)])

    captured = capsys.readouterr()
    assert rc == 0
    assert "Revenue:" in captured.out
    assert "Reproduce: edgarpack f1 0002004711 revenue --packs" in captured.out
    assert str(tmp_path) in captured.out
    assert "Building latest F-1 pack" not in captured.err
    build_pack.assert_not_awaited()
    financials.assert_awaited_once()
