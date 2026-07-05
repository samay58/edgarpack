"""The f1/s1 shortcuts must not blindly rebuild over an existing amendment pack.

Before the registration-family fix, an on-disk F-1/A pack failed the
shortcut's exists-check (which normalized "F-1" and compared for exact
equality), so `edgarpack f1 X` triggered a redundant original-F-1 build on
every invocation even though the newest filing was already packed.
"""

from __future__ import annotations

import importlib
import json
from datetime import date
from unittest.mock import AsyncMock

from edgarpack import cli
from edgarpack.query.models import CitedValue, QueryResult


def _result() -> QueryResult:
    return QueryResult(
        company="Bending Spoons S.p.A.",
        cik="0002004711",
        period="lfy",
        metrics={
            "revenue": CitedValue(
                value=1_306_404_000,
                unit="USD",
                metric="revenue",
                concept="Revenue",
                period_end=date(2025, 12, 31),
                fiscal_year=2025,
                fiscal_period="FY",
                form_type="F-1/A",
                filed=date(2026, 6, 8),
                accession="0001104659-26-071188",
                cik="0002004711",
                company="Bending Spoons S.p.A.",
                source="s1_snapshot",
            )
        },
    )


def test_f1_shortcut_reuses_existing_amendment_pack(tmp_path, monkeypatch, capsys):
    financials_module = importlib.import_module("edgarpack.query.financials")
    pack_dir = tmp_path / "0002004711" / "0001104659-26-071188"
    pack_dir.mkdir(parents=True)
    (pack_dir / "manifest.json").write_text(
        json.dumps(
            {
                "filing": {
                    "cik": "0002004711",
                    "accession": "0001104659-26-071188",
                    "form_type": "F-1/A",
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
    assert "Building latest F-1 pack" not in captured.err
    build_pack.assert_not_awaited()
    financials.assert_awaited_once()
