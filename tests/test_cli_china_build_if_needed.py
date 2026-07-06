"""`edgarpack query` auto-builds a missing A-share pack instead of erroring.

Mirrors the f1/s1 build-if-needed shortcut: an SSE/A-share code with no local
pack triggers a CNINFO latest-annual acquire + build, then the normal query
runs against the freshly built pack. HKEX targets and --no-build keep
today's behavior untouched.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from edgarpack import cli
from edgarpack.china import build_if_needed
from edgarpack.china.acquire import CninfoAnnualReportRef
from edgarpack.hk.extract import HKExtractionBlockedError

_SELECTED = CninfoAnnualReportRef(
    stock_code="002594",
    company_name="BYD Company Limited",
    title="2024年年度报告",
    filing_date=date(2025, 4, 22),
    source_url="https://static.cninfo.com.cn/finalpage/2025-04-22/002594.PDF",
)


def _write_sse_pack(
    pack_dir: Path, *, stock_code: str, company_name: str, filing_date: date
) -> None:
    pack_dir.mkdir(parents=True)
    filing_id = pack_dir.name
    (pack_dir / "manifest.json").write_text(
        json.dumps(
            {
                "filing": {
                    "company_name": company_name,
                    "filing_date": filing_date.isoformat(),
                    "form_type": "ANNUAL-REPORT",
                    "stock_code": stock_code,
                    "exchange": "SSE",
                }
            }
        ),
        encoding="utf-8",
    )
    (pack_dir / "facts.json").write_text(
        json.dumps(
            {
                "source": "SSE",
                "exchange": "SSE",
                "stock_code": stock_code,
                "company": company_name,
                "facts": {
                    "cas": {
                        "Revenue": {
                            "label": "Revenue",
                            "units": {
                                "CNY": [
                                    {
                                        "start": "2024-01-01",
                                        "end": "2024-12-31",
                                        "fy": 2024,
                                        "fp": "FY",
                                        "form": "ANNUAL-REPORT",
                                        "accn": filing_id,
                                        "filed": filing_date.isoformat(),
                                        "source_url": _SELECTED.source_url,
                                        "source_document": "optional/source.pdf",
                                        "section_id": "annual_s02_company_profile_key_financials",
                                        "matched_label": "营业收入",
                                        "extraction_method": "regex:annual_table",
                                        "val": 777_000_000.0,
                                    }
                                ]
                            },
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )


async def _fake_build_sse_pack(**kwargs: object) -> SimpleNamespace:
    stock_code = str(kwargs["stock_code"])
    company_name = str(kwargs["company_name"])
    filing_date = kwargs["filing_date"]
    assert isinstance(filing_date, date)
    out_dir = Path(str(kwargs["out_dir"]))
    filing_id = f"{stock_code}_{filing_date.isoformat()}"
    pack_dir = out_dir / "sse" / stock_code / filing_id
    _write_sse_pack(
        pack_dir, stock_code=stock_code, company_name=company_name, filing_date=filing_date
    )
    return SimpleNamespace(
        output_dir=pack_dir,
        filing_meta={
            "company_name": company_name,
            "form_type": "ANNUAL-REPORT",
            "filing_date": filing_date.isoformat(),
        },
        sections_count=1,
        tokens_total=10,
        warnings=[],
    )


def test_cold_query_builds_missing_sse_pack_then_returns_value(tmp_path, monkeypatch, capsys):
    calls: list[dict[str, object]] = []

    async def fake_build_sse_pack(**kwargs: object) -> SimpleNamespace:
        calls.append(kwargs)
        return await _fake_build_sse_pack(**kwargs)

    monkeypatch.setattr(
        build_if_needed, "_find_latest_sse_annual_report", lambda *_a, **_k: _SELECTED
    )
    monkeypatch.setattr("edgarpack.pack.build.build_sse_pack", fake_build_sse_pack)

    rc = cli.main(["query", "002594", "revenue", "--packs", str(tmp_path), "--format", "json"])

    captured = capsys.readouterr()
    assert rc == 0
    assert len(calls) == 1
    assert calls[0]["stock_code"] == "002594"
    assert calls[0]["url"] == _SELECTED.source_url
    assert "No local pack for 002594; fetching the latest annual report from CNINFO" in captured.err
    payload = json.loads(captured.out)
    assert payload["metrics"]["revenue"]["value"] == 777_000_000.0

    built_pack = tmp_path / "sse" / "002594" / "002594_2025-04-22"
    assert built_pack.is_dir()
    assert (built_pack / "facts.json").exists()


def test_warm_query_with_existing_pack_never_calls_build(tmp_path, monkeypatch, capsys):
    pack_dir = tmp_path / "sse" / "002594" / "002594_2025-04-22"
    _write_sse_pack(
        pack_dir,
        stock_code="002594",
        company_name="BYD Company Limited",
        filing_date=date(2025, 4, 22),
    )

    def fail_find(*_a: object, **_k: object) -> CninfoAnnualReportRef:
        raise AssertionError("should not look up a latest annual report for a warm pack")

    async def fail_build(**_k: object) -> SimpleNamespace:
        raise AssertionError("should not build when a pack already exists")

    monkeypatch.setattr(build_if_needed, "_find_latest_sse_annual_report", fail_find)
    monkeypatch.setattr("edgarpack.pack.build.build_sse_pack", fail_build)

    rc = cli.main(["query", "002594", "revenue", "--packs", str(tmp_path), "--format", "json"])

    captured = capsys.readouterr()
    assert rc == 0
    assert "fetching the latest annual report" not in captured.err
    payload = json.loads(captured.out)
    assert payload["metrics"]["revenue"]["value"] == 777_000_000.0


def test_no_build_flag_preserves_current_missing_pack_error(tmp_path, monkeypatch, capsys):
    def fail_find(*_a: object, **_k: object) -> CninfoAnnualReportRef:
        raise AssertionError("--no-build must not attempt discovery/acquire at all")

    async def fail_build(**_k: object) -> SimpleNamespace:
        raise AssertionError("--no-build must not attempt a build")

    monkeypatch.setattr(build_if_needed, "_find_latest_sse_annual_report", fail_find)
    monkeypatch.setattr("edgarpack.pack.build.build_sse_pack", fail_build)

    rc = cli.main(["query", "002594", "revenue", "--packs", str(tmp_path), "--no-build"])

    captured = capsys.readouterr()
    assert rc == 1
    assert (
        "Error: No SSE pack found for 002594. "
        "Run `edgarpack build-sse 002594 --latest-annual --with-chunks` first."
    ) in captured.err
    assert not (tmp_path / "sse").exists()


def test_build_failure_propagates_message_and_leaves_packs_root_untouched(
    tmp_path, monkeypatch, capsys
):
    def fail_find(*_a: object, **_k: object) -> CninfoAnnualReportRef:
        raise LookupError(
            "Latest full annual report found on CNINFO for 002594 is "
            "'2023年年度报告' filed 2024-03-01, more than 18 months before the newest "
            "announcement in this result set (2026-06-01). Rejecting as stale rather "
            "than returning a years-old filing as the latest annual report."
        )

    async def fail_build(**_k: object) -> SimpleNamespace:
        raise AssertionError("a selector failure must not reach the build step")

    monkeypatch.setattr(build_if_needed, "_find_latest_sse_annual_report", fail_find)
    monkeypatch.setattr("edgarpack.pack.build.build_sse_pack", fail_build)

    rc = cli.main(["query", "002594", "revenue", "--packs", str(tmp_path)])

    captured = capsys.readouterr()
    assert rc != 0
    assert "Rejecting as stale" in captured.err
    assert not (tmp_path / "sse").exists()


def test_hkex_target_auto_builds_via_hk_not_sse(tmp_path, monkeypatch, capsys):
    def fail_find(*_a: object, **_k: object) -> CninfoAnnualReportRef:
        raise AssertionError("HKEX targets must not route through SSE auto-build")

    async def fail_build(**_k: object) -> SimpleNamespace:
        raise AssertionError("HKEX targets must not route through SSE auto-build")

    monkeypatch.setattr(build_if_needed, "_find_latest_sse_annual_report", fail_find)
    monkeypatch.setattr("edgarpack.pack.build.build_sse_pack", fail_build)

    calls: dict[str, str] = {}

    def fake_hk_build(code: str, packs_root: object) -> object:
        calls["code"] = code
        raise LookupError("no annual report found (test)")

    monkeypatch.setattr(build_if_needed, "_build_hk_query_pack", fake_hk_build)

    rc = cli.main(["query", "0700.HK", "revenue", "--packs", str(tmp_path)])

    captured = capsys.readouterr()
    assert rc != 0
    # HK auto-build was attempted (and SSE was not).
    assert calls.get("code") == "00700"
    assert "fetching the latest annual report from HKEX news" in captured.err
    assert "no annual report found" in captured.err


def test_hkex_blocked_auto_build_does_not_publish_pack(tmp_path, monkeypatch, capsys):
    def fail_find(*_a: object, **_k: object) -> CninfoAnnualReportRef:
        raise AssertionError("HKEX targets must not route through SSE auto-build")

    async def fail_build(**_k: object) -> SimpleNamespace:
        raise AssertionError("HKEX targets must not route through SSE auto-build")

    def blocked_hk(_code: str, _packs_root: Path) -> Path:
        raise HKExtractionBlockedError("statement text was image-only")

    monkeypatch.setattr(build_if_needed, "_find_latest_sse_annual_report", fail_find)
    monkeypatch.setattr("edgarpack.pack.build.build_sse_pack", fail_build)
    monkeypatch.setattr(build_if_needed, "_build_hk_query_pack", blocked_hk)

    rc = cli.main(["query", "0700.HK", "revenue", "--packs", str(tmp_path)])

    captured = capsys.readouterr()
    assert rc != 0
    assert "statement text was image-only" in captured.err
    assert not (tmp_path / "hk" / "00700" / "00700_2025").exists()


def test_no_build_flag_skips_hk_auto_build(tmp_path, monkeypatch, capsys):
    def fail_hk(*_a: object, **_k: object) -> object:
        raise AssertionError("--no-build must skip HK auto-build")

    monkeypatch.setattr(build_if_needed, "_build_hk_query_pack", fail_hk)

    rc = cli.main(["query", "0700.HK", "revenue", "--no-build", "--packs", str(tmp_path)])

    captured = capsys.readouterr()
    assert rc != 0
    assert "No HKEX pack found for 00700" in captured.err
    assert "fetching" not in captured.err


def test_built_pack_with_no_facts_reports_distinct_message_and_skips_build(
    tmp_path, monkeypatch, capsys
):
    stale_pack = tmp_path / "sse" / "002594" / "002594_2025-04-22"
    stale_pack.mkdir(parents=True)
    (stale_pack / "manifest.json").write_text(
        json.dumps(
            {
                "filing": {
                    "company_name": "BYD Company Limited",
                    "filing_date": "2025-04-22",
                    "form_type": "ANNUAL-REPORT",
                    "stock_code": "002594",
                    "exchange": "SSE",
                }
            }
        ),
        encoding="utf-8",
    )
    # No facts.json: the extractor found no annual-report fact rows.

    def fail_find(*_a: object, **_k: object) -> CninfoAnnualReportRef:
        raise AssertionError("a build that already ran with no facts must not be retried")

    async def fail_build(**_k: object) -> SimpleNamespace:
        raise AssertionError("a build that already ran with no facts must not be retried")

    monkeypatch.setattr(build_if_needed, "_find_latest_sse_annual_report", fail_find)
    monkeypatch.setattr("edgarpack.pack.build.build_sse_pack", fail_build)

    rc = cli.main(["query", "002594", "revenue", "--packs", str(tmp_path)])

    captured = capsys.readouterr()
    assert rc != 0
    assert (
        "Pack for 002594 was built but no facts were extracted; "
        "see the build warnings (rebuild with --force after fixing)."
    ) in captured.err
    assert "No SSE pack found for 002594" not in captured.err
