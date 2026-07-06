import json
from pathlib import Path
from types import SimpleNamespace

from edgarpack.china.pack_store import classify_china_pack, discover_china_pack


def _resolved_sse() -> SimpleNamespace:
    return SimpleNamespace(source="SSE", stock_code="002594", ticker="002594", aliases=())


def _resolved_hk() -> SimpleNamespace:
    return SimpleNamespace(
        source="HKEX",
        stock_code="00700",
        hk_stock_code="00700",
        ticker="0700.HK",
        aliases=("Tencent",),
    )


def _write_pack(pack_dir: Path, *, facts: dict[str, object]) -> None:
    pack_dir.mkdir(parents=True)
    (pack_dir / "manifest.json").write_text(json.dumps({"filing": {"filing_date": "2025-04-22"}}))
    (pack_dir / "facts.json").write_text(json.dumps({"facts": facts}))


def test_sse_pack_store_classifies_queryable_missing_and_built_without_facts(tmp_path):
    resolved = _resolved_sse()

    assert classify_china_pack(resolved, tmp_path).kind == "missing"

    empty_pack = tmp_path / "sse" / "002594" / "002594_2025-04-22"
    _write_pack(empty_pack, facts={"cas": {}})
    status = classify_china_pack(resolved, tmp_path)
    assert status.kind == "built_without_facts"
    assert status.pack_dir == empty_pack
    assert discover_china_pack(resolved, tmp_path) is None

    full_pack = tmp_path / "sse" / "002594" / "002594_2026-04-22"
    _write_pack(full_pack, facts={"cas": {"Revenue": {"units": {"CNY": [{"val": 1}]}}}})
    status = classify_china_pack(resolved, tmp_path)
    assert status.kind == "queryable"
    assert status.pack_dir == full_pack
    assert discover_china_pack(resolved, tmp_path) == full_pack


def test_hk_pack_store_classifies_hk_and_hkex_variants(tmp_path):
    resolved = _resolved_hk()

    empty_pack = tmp_path / "hkex" / "00700" / "00700_2024"
    _write_pack(empty_pack, facts={"hkfrs": {}})
    status = classify_china_pack(resolved, tmp_path)
    assert status.kind == "built_without_facts"
    assert status.pack_dir == empty_pack

    full_pack = tmp_path / "hk" / "00700" / "00700_2025"
    _write_pack(full_pack, facts={"hkfrs": {"Revenue": {"units": {"HKD": [{"val": 1}]}}}})
    status = classify_china_pack(resolved, tmp_path)
    assert status.kind == "queryable"
    assert status.pack_dir == full_pack
    assert discover_china_pack(resolved, tmp_path) == full_pack
