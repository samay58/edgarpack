from unittest.mock import MagicMock

from edgarpack.hk.extract import HKFact
from edgarpack.hk.llm_extract import (
    cache_key_for,
    extract_metric_via_llm,
    fill_missing_with_llm,
)


def test_cache_key_is_deterministic():
    k1 = cache_key_for("acc-1", "hkex_income_statement", "revenue", "prompt")
    k2 = cache_key_for("acc-1", "hkex_income_statement", "revenue", "prompt")
    assert k1 == k2
    assert len(k1) == 64


def test_cache_key_changes_with_inputs():
    base = cache_key_for("acc-1", "hkex_income_statement", "revenue", "prompt")
    assert cache_key_for("acc-2", "hkex_income_statement", "revenue", "prompt") != base
    assert cache_key_for("acc-1", "hkex_balance_sheet", "revenue", "prompt") != base
    assert cache_key_for("acc-1", "hkex_income_statement", "net_income", "prompt") != base
    assert cache_key_for("acc-1", "hkex_income_statement", "revenue", "prompt v2") != base


def test_extract_metric_via_llm_writes_cache_on_first_call(tmp_path):
    fake_client = MagicMock()
    fake_client.send.return_value = '{"value": 71200000, "label": "Total revenue"}'

    result = extract_metric_via_llm(
        section_text="Revenue: US$ 71.2M",
        section_id="hkex_income_statement",
        metric="revenue",
        accession="test-acc",
        cache_dir=tmp_path,
        client=fake_client,
    )
    assert result == {"value": 71200000, "label": "Total revenue"}
    assert fake_client.send.call_count == 1
    cache_files = list(tmp_path.glob("*.json"))
    assert len(cache_files) == 1


def test_extract_metric_via_llm_hits_cache_on_second_call(tmp_path):
    fake_client = MagicMock()
    fake_client.send.return_value = '{"value": 71200000, "label": "Total revenue"}'

    extract_metric_via_llm("text", "hkex_income_statement", "revenue", "acc", tmp_path, fake_client)
    extract_metric_via_llm("text", "hkex_income_statement", "revenue", "acc", tmp_path, fake_client)
    assert fake_client.send.call_count == 1


def test_extract_metric_via_llm_handles_value_null(tmp_path):
    fake_client = MagicMock()
    fake_client.send.return_value = '{"value": null, "label": null}'

    result = extract_metric_via_llm(
        "text", "hkex_income_statement", "revenue", "acc", tmp_path, fake_client
    )
    assert result == {"value": None, "label": None}


def test_fill_missing_with_llm_does_not_call_for_already_extracted(tmp_path):
    sections_dir = tmp_path / "sections"
    sections_dir.mkdir()
    (sections_dir / "hkex_income_statement.md").write_text("Revenue 71200000")

    existing = [
        HKFact(
            metric="revenue",
            concept="Revenue",
            value=71_200_000,
            unit="USD",
            section_id="hkex_income_statement",
            extraction_method="regex",
            matched_label="Revenue",
        ),
    ]

    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()

    fake_client = MagicMock()
    fake_client.send.return_value = '{"value": 0, "label": "should not be called"}'

    result = fill_missing_with_llm(
        existing, sections_dir, "HKFRS", "acc", cache_dir=cache_dir, client=fake_client
    )
    revenue_facts = [f for f in result if f.metric == "revenue"]
    assert len(revenue_facts) == 1
    assert revenue_facts[0].extraction_method == "regex"


def test_fill_missing_with_llm_adds_fact_when_llm_returns_value(tmp_path):
    sections_dir = tmp_path / "sections"
    sections_dir.mkdir()
    (sections_dir / "hkex_balance_sheet.md").write_text("Total assets US$ 64,000,000")

    existing = []  # nothing extracted yet
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()

    fake_client = MagicMock()
    fake_client.send.return_value = '{"value": 64000000, "label": "Total assets"}'

    result = fill_missing_with_llm(
        existing, sections_dir, "HKFRS", "acc", cache_dir=cache_dir, client=fake_client
    )
    total_assets_facts = [f for f in result if f.metric == "total_assets"]
    assert len(total_assets_facts) >= 1
    assert total_assets_facts[0].extraction_method == "learned:llm"
    assert total_assets_facts[0].value == 64_000_000


def test_fill_missing_with_llm_skips_when_llm_returns_null(tmp_path):
    sections_dir = tmp_path / "sections"
    sections_dir.mkdir()
    (sections_dir / "hkex_balance_sheet.md").write_text("Some unrelated prose")

    existing = []
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()

    fake_client = MagicMock()
    fake_client.send.return_value = '{"value": null, "label": null}'

    result = fill_missing_with_llm(
        existing, sections_dir, "HKFRS", "acc", cache_dir=cache_dir, client=fake_client
    )
    total_assets_facts = [f for f in result if f.metric == "total_assets"]
    assert len(total_assets_facts) == 0
