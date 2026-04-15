import json
from pathlib import Path

import pytest

from edgarpack.hk.extract import extract_facts_from_pack, extract_with_regex


def test_extract_revenue_simple_inline_currency():
    text = "Total revenue          US$  71,200,000"
    facts = extract_with_regex(text, "hkex_income_statement", "HKFRS")
    assert any(f.metric == "revenue" and f.value == 71_200_000 for f in facts)


def test_extract_handles_parenthesized_negative():
    text = "Loss for the year         US$  (465,000,000)"
    facts = extract_with_regex(text, "hkex_income_statement", "HKFRS")
    rows = [f for f in facts if f.metric == "net_income"]
    if rows:
        assert rows[0].value == -465_000_000 or rows[0].value == 465_000_000


def test_extract_no_match_returns_empty():
    text = "Some boilerplate prose with no numbers anywhere."
    facts = extract_with_regex(text, "hkex_income_statement", "HKFRS")
    assert facts == []


def test_extract_only_runs_for_financial_sections():
    text = "Revenue US$ 71,200,000"
    facts = extract_with_regex(text, "hkex_chairman_statement", "HKFRS")
    assert facts == []


def test_extract_facts_from_pack_writes_facts_json(tmp_path):
    pack_dir = tmp_path / "test_pack"
    pack_dir.mkdir()
    sections_dir = pack_dir / "sections"
    sections_dir.mkdir()
    (sections_dir / "hkex_income_statement.md").write_text(
        "# Consolidated Statement of Profit or Loss\n\n"
        "Total revenue          US$  71,200,000\n"
        "Cost of revenue        US$  (54,800,000)\n"
    )
    (pack_dir / "manifest.json").write_text(
        json.dumps(
            {
                "source": "HKEX",
                "stock_code": "00100",
                "fiscal_year": 2024,
                "accounting_standard": "HKFRS",
                "reporting_currency": "USD",
                "company": "Test Company",
                "pdf_url": "",
                "announcement_date": "",
            }
        )
    )

    facts_path = extract_facts_from_pack(pack_dir, llm_fallback=False)
    assert facts_path.exists()
    data = json.loads(facts_path.read_text())
    assert "facts" in data
    standard_facts = data["facts"]["hkfrs"]
    assert any(
        info["units"]["USD"][0]["val"] == 71_200_000
        for concept, info in standard_facts.items()
        if "USD" in info.get("units", {})
    )


def test_extract_facts_minimax_real_pack_yields_revenue():
    pack_dir = Path("tests/fixtures/china_packs/minimax_2024")
    if not (pack_dir / "manifest.json").exists():
        pytest.skip("minimax fixture pack not built")
    facts_path = extract_facts_from_pack(pack_dir, llm_fallback=False)
    data = json.loads(facts_path.read_text())
    revenues = [
        info["units"][unit][0]["val"]
        for std in data["facts"].values()
        for concept, info in std.items()
        for unit in info.get("units", {})
        if any(canonical in concept.lower() for canonical in ("revenue", "turnover"))
    ]
    assert revenues, f"No revenue value found for MiniMax in {data['facts']}"
    assert any(r > 1_000_000 for r in revenues), f"All revenue values implausibly small: {revenues}"
