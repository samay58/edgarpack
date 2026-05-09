"""Unit tests for S-1 financial snapshot extraction.

Tests cover the pure-data side of the extractor (dataclasses, cache layer,
prompt builder, JSON parser). Network calls to Anthropic are monkeypatched
throughout; a separate live-smoke test exercises the real API path.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from unittest.mock import patch  # noqa: F401 (kept available for future tests)

import pytest

from edgarpack.query.s1_financials import (
    METRIC_SLUGS,
    MODEL_ID,
    PROMPT_SYSTEM,
    SCHEMA_VERSION,
    SnapshotFact,
    SnapshotResult,
    _call_haiku_extract,
    _extract_summary_table_facts,
    build_extraction_prompt,
    extract_or_load_snapshot,
    find_financial_data_section,
    parse_llm_response,
    source_sha256_for_pack,
)


def test_snapshot_fact_required_fields():
    fact = SnapshotFact(
        accession="0001628280-24-041596",
        fiscal_year=2024,
        period_end="2024-12-31",
        metric="revenue",
        value_cents=7828700000,
        currency="USD",
        is_audited=True,
        is_pro_forma=False,
        pro_forma_note=None,
    )
    assert fact.metric == "revenue"
    assert fact.value_cents == 7828700000
    assert fact.currency == "USD"
    assert fact.is_audited is True
    assert fact.is_pro_forma is False
    assert fact.pro_forma_note is None


def test_snapshot_fact_pro_forma_with_assumption():
    fact = SnapshotFact(
        accession="0001628280-26-025762",
        fiscal_year=2025,
        period_end="2025-12-31",
        metric="cash_and_equivalents",
        value_cents=124310000000,
        currency="USD",
        is_audited=False,
        is_pro_forma=True,
        pro_forma_note="assumes IPO price $32.50, midpoint",
    )
    assert fact.is_pro_forma is True
    assert fact.pro_forma_note is not None
    assert "$32.50" in fact.pro_forma_note


def test_metric_slugs_contains_all_v2_metrics():
    assert {
        "revenue",
        "gross_profit",
        "adjusted_gross_profit",
        "operating_income_loss",
        "net_income_loss",
        "operating_cash_flow",
        "capex",
        "adjusted_ebitda",
        "cash_and_equivalents",
        "total_assets",
        "stockholders_equity",
        "shares_outstanding_basic",
        "eps_basic",
    } == METRIC_SLUGS


def test_snapshot_result_serializes_to_json():
    result = SnapshotResult(
        schema_version=SCHEMA_VERSION,
        accession="0001628280-24-041596",
        extracted_at="2026-04-22T18:14:00Z",
        extraction_status="ok",
        source_sha256="abc123",
        model="claude-haiku-4-5-20251001",
        facts=[
            SnapshotFact(
                accession="0001628280-24-041596",
                fiscal_year=2024,
                period_end="2024-12-31",
                metric="revenue",
                value_cents=7828700000,
                currency="USD",
                is_audited=True,
                is_pro_forma=False,
                pro_forma_note=None,
            ),
        ],
    )
    payload = json.loads(result.to_json())
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["accession"] == "0001628280-24-041596"
    assert payload["extraction_status"] == "ok"
    assert len(payload["facts"]) == 1
    assert payload["facts"][0]["metric"] == "revenue"
    assert payload["facts"][0]["value_cents"] == 7828700000


def test_snapshot_result_deserializes_from_json():
    raw = json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "accession": "0001628280-24-041596",
            "extracted_at": "2026-04-22T18:14:00Z",
            "extraction_status": "ok",
            "source_sha256": "abc123",
            "model": "claude-haiku-4-5-20251001",
            "facts": [
                {
                    "accession": "0001628280-24-041596",
                    "fiscal_year": 2024,
                    "period_end": "2024-12-31",
                    "metric": "revenue",
                    "value_cents": 7828700000,
                    "currency": "USD",
                    "is_audited": True,
                    "is_pro_forma": False,
                    "pro_forma_note": None,
                }
            ],
        }
    )
    result = SnapshotResult.from_json(raw)
    assert len(result.facts) == 1
    assert result.facts[0].metric == "revenue"
    assert result.facts[0].value_cents == 7828700000


FIXTURE_DIR = Path(__file__).parent / "fixtures"
CEREBRAS_SFD = FIXTURE_DIR / "cerebras_selected_financial_data.md"


def test_find_financial_data_section_matches_selected_heading():
    md = CEREBRAS_SFD.read_text(encoding="utf-8")
    section = find_financial_data_section(md)
    assert section is not None
    assert "Revenue" in section
    assert "78,287" in section


def test_find_financial_data_section_matches_summary_alternate():
    md = "# Summary Consolidated Financial Data\n\nRevenue ... 100\n\n# Other\n\nFoo"
    section = find_financial_data_section(md)
    assert section is not None
    assert "Revenue" in section
    assert "Foo" not in section  # Stops at next heading


def test_find_financial_data_section_matches_bare_summary_heading_after_toc():
    md = """
Table of Contents

> Summary Consolidated Financial Data ..... 18

    Table of Contents

 Summary Consolidated Financial Data
 The following tables set forth our summary consolidated financial data.

> 2025 / 2024
> Total revenue ... $509,991 / $290,252

## Risk Factors

Investing involves risk.
"""
    section = find_financial_data_section(md)
    assert section is not None
    assert "Total revenue" in section
    assert "Risk Factors" not in section


def test_find_financial_data_section_returns_none_when_absent():
    md = "# Risk Factors\n\nInvesting involves risk.\n\n# Business\n\nWe design systems."
    assert find_financial_data_section(md) is None


def test_find_financial_data_section_truncates_to_50kb_ceiling():
    huge = "# Selected Financial Data\n\n" + ("x" * 100_000)
    section = find_financial_data_section(huge)
    assert section is not None
    assert len(section) <= 50_000 + 200  # tiny slack for heading text itself


def test_build_extraction_prompt_includes_section_text():
    prompt = build_extraction_prompt("# Selected Financial Data\n\nRevenue 100")
    assert "Selected Financial Data" in prompt
    assert "Revenue 100" in prompt


def test_build_extraction_prompt_enumerates_all_metrics():
    prompt = build_extraction_prompt("# stub")
    for slug in (
        "revenue",
        "gross_profit",
        "operating_income_loss",
        "net_income_loss",
        "operating_cash_flow",
        "capex",
        "cash_and_equivalents",
        "total_assets",
        "stockholders_equity",
        "shares_outstanding_basic",
        "eps_basic",
    ):
        assert slug in prompt, f"prompt missing metric: {slug}"


def test_parse_llm_response_accepts_valid_array():
    raw = """[
        {
            "fiscal_year": 2024,
            "period_end": "2024-12-31",
            "metric": "revenue",
            "value_cents": 7828700000,
            "currency": "USD",
            "is_audited": true,
            "is_pro_forma": false,
            "pro_forma_note": null
        }
    ]"""
    facts = parse_llm_response(raw, accession="0001628280-24-041596")
    assert len(facts) == 1
    assert facts[0].metric == "revenue"
    assert facts[0].accession == "0001628280-24-041596"
    assert facts[0].value_cents == 7828700000


def test_parse_llm_response_accepts_json_wrapped_in_code_block():
    raw = """```json
[
    {
        "fiscal_year": 2024,
        "period_end": "2024-12-31",
        "metric": "revenue",
        "value_cents": 7828700000,
        "currency": "USD",
        "is_audited": true,
        "is_pro_forma": false,
        "pro_forma_note": null
    }
]
```"""
    facts = parse_llm_response(raw, accession="x")
    assert len(facts) == 1


def test_parse_llm_response_drops_rows_with_unknown_metric():
    raw = """[
        {"fiscal_year": 2024, "period_end": "2024-12-31", "metric": "bogus",
         "value_cents": 1, "currency": "USD", "is_audited": true,
         "is_pro_forma": false, "pro_forma_note": null},
        {"fiscal_year": 2024, "period_end": "2024-12-31", "metric": "revenue",
         "value_cents": 1, "currency": "USD", "is_audited": true,
         "is_pro_forma": false, "pro_forma_note": null}
    ]"""
    facts = parse_llm_response(raw, accession="x")
    assert len(facts) == 1
    assert facts[0].metric == "revenue"


def test_parse_llm_response_rejects_invalid_json():
    with pytest.raises(ValueError, match="invalid JSON"):
        parse_llm_response("not json at all", accession="x")


def test_parse_llm_response_rejects_non_array_payload():
    with pytest.raises(ValueError, match="expected JSON array"):
        parse_llm_response('{"not": "an array"}', accession="x")


def test_parse_llm_response_drops_rows_missing_required_fields():
    raw = """[
        {"fiscal_year": 2024, "metric": "revenue"}
    ]"""
    facts = parse_llm_response(raw, accession="x")
    assert facts == []


def test_prompt_system_forbids_fabrication():
    assert "not fabricate" in PROMPT_SYSTEM.lower() or "only" in PROMPT_SYSTEM.lower()


_CEREBRAS_2026_SUMMARY_TABLE = """
 Summary Consolidated Financial Data
 The following tables set forth our summary consolidated financial data. The summary
 consolidated statements of operations data for the years ended December 31, 2025
 and 2024 have been derived from our audited consolidated financial statements.

> **Year Ended December 31, / Year Ended December 31, / Year Ended December 31,**
>
> 2025 / 2024
> (in thousands, except per share amounts) / (in thousands, except per share amounts)
> Consolidated Statement of Operations:
> Revenue
> Hardware ... $358,440 / $211,965
> Cloud and other services ... 151,551 / 78,287
> Total revenue ... 509,991 / 290,252
> Gross profit ... 199,071 / 122,738
> Loss from operations ... (145,862) / (101,438)
> Net income (loss) ... $237,827 / $(481,602)
> Net income (loss) per share attributable to common shareholders:    ...........................
> Basic ... $1.64 / $(9.90)
> Other Financial Information:
> Net cash provided by (used in) operating activities ... $(10,050) / $451,978
> Purchases of property and equipment ... $(382,739) / $(23,435)
"""


def test_extract_summary_table_facts_parses_cerebras_2026_statement_table():
    facts = _extract_summary_table_facts(
        _CEREBRAS_2026_SUMMARY_TABLE,
        accession="0001628280-26-025762",
    )
    by_key = {(fact.metric, fact.fiscal_year): fact for fact in facts}

    assert by_key[("revenue", 2025)].value_cents == 50_999_100_000
    assert by_key[("revenue", 2024)].value_cents == 29_025_200_000
    assert by_key[("gross_profit", 2025)].value_cents == 19_907_100_000
    assert by_key[("operating_income_loss", 2025)].value_cents == -14_586_200_000
    assert by_key[("net_income_loss", 2024)].value_cents == -48_160_200_000
    assert by_key[("operating_cash_flow", 2025)].value_cents == -1_005_000_000
    assert by_key[("operating_cash_flow", 2024)].value_cents == 45_197_800_000
    assert by_key[("capex", 2025)].value_cents == 38_273_900_000
    assert by_key[("capex", 2024)].value_cents == 2_343_500_000
    assert by_key[("eps_basic", 2025)].value_cents == 164
    assert by_key[("eps_basic", 2024)].value_cents == -990


_NEUTRON_2026_SUMMARY_TABLE = "\n".join(
    [
        "",
        " Summary Consolidated Financial Data",
        " The following tables set forth our summary consolidated financial data.",
        "",
        (
            "> **Year Ended December 31, / Year Ended December 31, / "
            "Year Ended December 31, / Three Months Ended March 31, / "
            "Three Months Ended March 31,**"
        ),
        "> 2023 / 2024 / 2025 / 2025 / 2026",
        (
            "> (in thousands, except per share amounts) / "
            "(in thousands, except per share amounts) / "
            "(in thousands, except per share amounts) / "
            "(in thousands, except per share amounts) / "
            "(in thousands, except per share amounts)"
        ),
        (
            "> Revenue ................................. Revenue / Revenue / "
            "$ / 521,983 / $ / 686,630 / $ / 886,719 / $ / 129,015 / "
            "$ / 170,150"
        ),
        (
            "> Gross profit ............................ Gross profit / Gross profit / "
            "169,205 / 169,205 / 281,073 / 281,073 / 345,447 / 345,447 / "
            "28,885 / 28,885 / 44,591 / 44,591"
        ),
        (
            "> Operating (loss) income .................. Operating (loss) income / "
            "Operating (loss) income / (24,624) / (24,624) / 46,969 / "
            "46,969 / 70,401 / 70,401 / (31,422) / (31,422) / "
            "(29,032) / (29,032)"
        ),
        (
            "> Net loss ................................. Net loss / Net loss / "
            "$ / (122,358) / $ / (33,913) / $ / (59,309) / "
            "$ / (55,964) / $ / (61,286)"
        ),
        (
            "> Adjusted Gross Profit .................... Adjusted Gross Profit / "
            "Adjusted Gross Profit / $ / 276,300 / $ / 368,600 / "
            "$ / 467,200 / $ / 56,500 / $ / 74,200"
        ),
        (
            "> Adjusted EBITDA .......................... Adjusted EBITDA / "
            "Adjusted EBITDA / $ / 99,754 / $ / 153,400 / $ / 218,100 / "
            "$ / 2,100 / $ / 7,500"
        ),
        (
            "> Net cash provided by operating activities  "
            "Net cash provided by operating activities / "
            "Net cash provided by operating activities / 81,199 / 81,199 / "
            "168,953 / 168,953 / 214,841 / 214,841 / (20,615) / "
            "(20,615) / (22,302) / (22,302)"
        ),
    ]
)


def test_extract_summary_table_facts_parses_neutron_multi_year_and_quarterly_rows():
    facts = _extract_summary_table_facts(
        _NEUTRON_2026_SUMMARY_TABLE,
        accession="0001628280-26-032523",
    )
    by_key = {(fact.metric, fact.fiscal_year, fact.fiscal_period): fact for fact in facts}

    assert by_key[("revenue", 2025, "FY")].value_cents == 88_671_900_000
    assert by_key[("revenue", 2026, "Q1")].period_end == "2026-03-31"
    assert by_key[("revenue", 2026, "Q1")].value_cents == 17_015_000_000
    assert by_key[("gross_profit", 2024, "FY")].value_cents == 28_107_300_000
    assert by_key[("operating_income_loss", 2025, "FY")].value_cents == 7_040_100_000
    assert by_key[("net_income_loss", 2024, "FY")].value_cents == -3_391_300_000
    assert by_key[("adjusted_gross_profit", 2025, "FY")].value_cents == 46_720_000_000
    assert by_key[("adjusted_ebitda", 2025, "FY")].value_cents == 21_810_000_000
    assert by_key[("operating_cash_flow", 2025, "FY")].value_cents == 21_484_100_000
    assert "Adjusted EBITDA" in (by_key[("adjusted_ebitda", 2025, "FY")].source_text or "")


_FERVO_2026_SUMMARY_TABLE = "\n".join(
    [
        "Summary Consolidated Financial and Other Data",
        "> **(In thousands, except share and per share data)**",
        ">",
        "> Year ended December 31, / Year ended December 31, / Year ended December 31,",
        ">",
        "> (In thousands, except share and per share data) ... 2025 / 2024",
        "> Consolidated Statements of Operations",
        "> Revenues ... $138 / $199",
        "> Operating loss ... (48,806) / (41,838)",
        "> Net loss ... $(57,788) / $(41,110)",
        "> Consolidated Statements of Cash Flows",
        "> Net cash used in operating activities ... $(31,757) / $(54,748)",
    ]
)


def test_extract_summary_table_facts_parses_fervo_two_year_summary_rows():
    facts = _extract_summary_table_facts(
        _FERVO_2026_SUMMARY_TABLE,
        accession="0001628280-26-029515",
    )
    by_key = {(fact.metric, fact.fiscal_year, fact.fiscal_period): fact for fact in facts}

    assert by_key[("revenue", 2025, "FY")].value_cents == 13_800_000
    assert by_key[("revenue", 2024, "FY")].value_cents == 19_900_000
    assert by_key[("operating_income_loss", 2025, "FY")].value_cents == -4_880_600_000
    assert by_key[("net_income_loss", 2024, "FY")].value_cents == -4_111_000_000
    assert by_key[("operating_cash_flow", 2025, "FY")].value_cents == -3_175_700_000


_HAWKEYE_2026_MDA_TABLES = "\n".join(
    [
        "Results of Operations",
        "> **(in thousands)**",
        ">",
        (
            "> (in thousands) / (in thousands) / Year ended December 31, 2025 / "
            "Year ended December 31, 2025 / Year ended December 31, 2025 / "
            "Year ended December 31, 2024 / Year ended December 31, 2024 / "
            "Year ended December 31, 2024 / $ Change / $ Change / $ Change / "
            "% Change / % Change / % Change"
        ),
        ">",
        (
            "> Revenue ... Revenue / Revenue / $ / 98,743 / $ / 49,835 / "
            "$ / 48,908 / 98 / 98 / %"
        ),
        (
            "> Revenue from related parties ... Revenue from related parties / "
            "Revenue from related parties / 18,917 / 18,917 / 17,724 / "
            "17,724 / 1,193 / 1,193 / 7 / 7 / %"
        ),
        (
            "> Total Revenue ... Total Revenue / Total Revenue / 117,660 / "
            "117,660 / 67,559 / 67,559 / 50,101 / 50,101 / 74 / 74 / %"
        ),
        "Cash Flows",
        "> **(in thousands)**",
        ">",
        (
            "> (in thousands) / (in thousands) / Year ended December 31, 2025 / "
            "Year ended December 31, 2025 / Year ended December 31, 2025 / "
            "Year ended December 31, 2024 / Year ended December 31, 2024 / "
            "Year ended December 31, 2024"
        ),
        ">",
        (
            "> Net cash (used in) provided by operating activities ... "
            "Net cash (used in) provided by operating activities / "
            "Net cash (used in) provided by operating activities / "
            "$ / (17,339) / $ / 11,966"
        ),
    ]
)


def test_extract_summary_table_facts_parses_hawkeye_mda_comparison_rows():
    facts = _extract_summary_table_facts(
        _HAWKEYE_2026_MDA_TABLES,
        accession="0001628280-26-029373",
    )
    by_key = {(fact.metric, fact.fiscal_year, fact.fiscal_period): fact for fact in facts}

    assert by_key[("revenue", 2025, "FY")].value_cents == 11_766_000_000
    assert by_key[("revenue", 2024, "FY")].value_cents == 6_755_900_000
    assert by_key[("operating_cash_flow", 2025, "FY")].value_cents == -1_733_900_000
    assert by_key[("operating_cash_flow", 2024, "FY")].value_cents == 1_196_600_000


@pytest.mark.asyncio
async def test_extract_or_load_snapshot_supplements_cash_flow_rows_outside_summary(
    tmp_path, monkeypatch
):
    markdown = """
 Summary Consolidated Financial Data
 The following tables set forth our summary consolidated financial data.

> 2025 / 2024
> (in thousands, except per share amounts) / (in thousands, except per share amounts)
> Consolidated Statement of Operations:
> Total revenue ... $509,991 / $290,252
> Net cash provided by (used in) operating activities ... $(10,050) / $451,978

# Consolidated Statements of Cash Flows

> Purchases of property and equipment ... (382,739) / (23,435)
> Purchases of property and equipment included in accounts payable ... 9,453 / $4,286
"""
    pack = _write_pack(
        tmp_path,
        accession="0001628280-26-025762",
        markdown=markdown,
    )

    async def should_not_call_llm(_section):
        raise AssertionError("cash-flow supplement should stay deterministic")

    monkeypatch.setattr("edgarpack.query.s1_financials._call_haiku_extract", should_not_call_llm)

    result = await extract_or_load_snapshot(pack)
    by_key = {(fact.metric, fact.fiscal_year): fact for fact in result.facts}

    assert by_key[("operating_cash_flow", 2025)].value_cents == -1_005_000_000
    assert by_key[("capex", 2025)].value_cents == 38_273_900_000
    assert by_key[("capex", 2024)].value_cents == 2_343_500_000


@pytest.mark.asyncio
async def test_extract_or_load_snapshot_uses_deterministic_summary_table(tmp_path, monkeypatch):
    pack = _write_pack(
        tmp_path,
        accession="0001628280-26-025762",
        markdown=_CEREBRAS_2026_SUMMARY_TABLE,
    )

    async def should_not_call_llm(_section):
        raise AssertionError("deterministic Cerebras table should not require LLM")

    monkeypatch.setattr("edgarpack.query.s1_financials._call_haiku_extract", should_not_call_llm)

    result = await extract_or_load_snapshot(pack)
    by_key = {(fact.metric, fact.fiscal_year): fact for fact in result.facts}

    assert result.extraction_status == "ok"
    assert result.model == "deterministic-summary-table"
    assert by_key[("revenue", 2025)].value_cents == 50_999_100_000
    assert (pack / "s1_financials.json").exists()


@pytest.mark.asyncio
async def test_call_haiku_extract_returns_raw_response_text(monkeypatch):
    fake_text = (
        '[{"fiscal_year": 2024, "period_end": "2024-12-31", "metric": "revenue",'
        ' "value_cents": 7828700000, "currency": "USD", "is_audited": true,'
        ' "is_pro_forma": false, "pro_forma_note": null}]'
    )

    class _FakeBlock:
        type = "text"
        text = fake_text

    class _FakeMessage:
        content = [_FakeBlock()]

    class _FakeMessages:
        async def create(self, **kwargs):  # noqa: ARG002
            return _FakeMessage()

    class _FakeClient:
        messages = _FakeMessages()

    fake_module = types.SimpleNamespace(AsyncAnthropic=lambda: _FakeClient())
    monkeypatch.setitem(sys.modules, "anthropic", fake_module)

    out = await _call_haiku_extract("# stub section")
    assert out == fake_text


@pytest.mark.asyncio
async def test_call_haiku_extract_raises_when_anthropic_import_fails(monkeypatch):
    sys.modules.pop("anthropic", None)

    class _BlockAnthropicFinder:
        def find_spec(self, name, path, target=None):  # noqa: ARG002
            if name == "anthropic":
                raise ImportError("anthropic is not installed in test env")
            return None

    sys.meta_path.insert(0, _BlockAnthropicFinder())
    try:
        with pytest.raises(RuntimeError, match="anthropic"):
            await _call_haiku_extract("# stub")
    finally:
        sys.meta_path.pop(0)


def test_model_id_is_haiku_4_5():
    assert MODEL_ID == "claude-haiku-4-5-20251001"


# ---------------------------------------------------------------------------
# Task 5: source_sha256_for_pack + extract_or_load_snapshot
# ---------------------------------------------------------------------------


def _write_pack(
    root: Path,
    accession: str = "0001628280-24-041596",
    *,
    markdown: str | None = None,
    form_type: str = "S-1",
) -> Path:
    pack = root / accession
    pack.mkdir(parents=True, exist_ok=True)
    (pack / "filing.full.md").write_text(
        markdown if markdown is not None else "# Selected Financial Data\n\nRevenue 78,287",
        encoding="utf-8",
    )
    (pack / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "filing": {
                    "accession": accession,
                    "form_type": form_type,
                    "filing_date": "2024-09-30",
                    "cik": "0002021728",
                    "company_name": "Cerebras Systems Inc",
                },
                "sections": [],
                "parser_version": "test",
            }
        ),
        encoding="utf-8",
    )
    return pack


def test_source_sha256_for_pack_is_stable(tmp_path):
    pack = _write_pack(tmp_path, markdown="hello world")
    digest_a = source_sha256_for_pack(pack)
    digest_b = source_sha256_for_pack(pack)
    assert digest_a == digest_b
    assert len(digest_a) == 64  # sha256 hex


def test_source_sha256_for_pack_changes_on_content_change(tmp_path):
    pack = _write_pack(tmp_path, markdown="A")
    digest_a = source_sha256_for_pack(pack)
    (pack / "filing.full.md").write_text("B", encoding="utf-8")
    digest_b = source_sha256_for_pack(pack)
    assert digest_a != digest_b


@pytest.mark.asyncio
async def test_extract_or_load_snapshot_writes_cache_on_first_call(tmp_path, monkeypatch):
    pack = _write_pack(tmp_path, markdown=CEREBRAS_SFD.read_text(encoding="utf-8"))

    async def fake_haiku(_section):
        return json.dumps(
            [
                {
                    "fiscal_year": 2024,
                    "period_end": "2024-12-31",
                    "metric": "revenue",
                    "value_cents": 7828700000,
                    "currency": "USD",
                    "is_audited": True,
                    "is_pro_forma": False,
                    "pro_forma_note": None,
                }
            ]
        )

    monkeypatch.setattr("edgarpack.query.s1_financials._call_haiku_extract", fake_haiku)

    result = await extract_or_load_snapshot(pack)
    assert result.extraction_status == "ok"
    assert len(result.facts) == 1
    assert result.facts[0].metric == "revenue"
    assert (pack / "s1_financials.json").exists()


@pytest.mark.asyncio
async def test_extract_or_load_snapshot_cache_hit_skips_llm(tmp_path, monkeypatch):
    pack = _write_pack(tmp_path, markdown="# Selected Financial Data\n\nRevenue 1")

    seeded = SnapshotResult(
        schema_version=SCHEMA_VERSION,
        accession="0001628280-24-041596",
        extracted_at="2026-04-22T00:00:00Z",
        extraction_status="ok",
        source_sha256=source_sha256_for_pack(pack),
        model=MODEL_ID,
        facts=[
            SnapshotFact(
                accession="0001628280-24-041596",
                fiscal_year=2024,
                period_end="2024-12-31",
                metric="revenue",
                value_cents=100,
                currency="USD",
                is_audited=True,
                is_pro_forma=False,
                pro_forma_note=None,
            )
        ],
    )
    (pack / "s1_financials.json").write_text(seeded.to_json(), encoding="utf-8")

    called = {"n": 0}

    async def counting_haiku(_section):
        called["n"] += 1
        return "[]"

    monkeypatch.setattr("edgarpack.query.s1_financials._call_haiku_extract", counting_haiku)

    result = await extract_or_load_snapshot(pack)
    assert called["n"] == 0
    assert len(result.facts) == 1
    assert result.facts[0].value_cents == 100


@pytest.mark.asyncio
async def test_extract_or_load_snapshot_invalidates_on_source_change(tmp_path, monkeypatch):
    pack = _write_pack(tmp_path, markdown="# Selected Financial Data\n\nA")
    seeded = SnapshotResult(
        schema_version=SCHEMA_VERSION,
        accession="0001628280-24-041596",
        extracted_at="2026-04-22T00:00:00Z",
        extraction_status="ok",
        source_sha256="stale_hash",
        model=MODEL_ID,
        facts=[],
    )
    (pack / "s1_financials.json").write_text(seeded.to_json(), encoding="utf-8")

    called = {"n": 0}

    async def fresh_haiku(_section):
        called["n"] += 1
        return "[]"

    monkeypatch.setattr("edgarpack.query.s1_financials._call_haiku_extract", fresh_haiku)

    await extract_or_load_snapshot(pack)
    assert called["n"] == 1


@pytest.mark.asyncio
async def test_extract_or_load_snapshot_force_bypasses_cache(tmp_path, monkeypatch):
    pack = _write_pack(tmp_path, markdown="# Selected Financial Data\n\nA")
    seeded = SnapshotResult(
        schema_version=SCHEMA_VERSION,
        accession="0001628280-24-041596",
        extracted_at="2026-04-22T00:00:00Z",
        extraction_status="ok",
        source_sha256=source_sha256_for_pack(pack),
        model=MODEL_ID,
        facts=[],
    )
    (pack / "s1_financials.json").write_text(seeded.to_json(), encoding="utf-8")

    called = {"n": 0}

    async def forced_haiku(_section):
        called["n"] += 1
        return "[]"

    monkeypatch.setattr("edgarpack.query.s1_financials._call_haiku_extract", forced_haiku)

    await extract_or_load_snapshot(pack, force=True)
    assert called["n"] == 1


@pytest.mark.asyncio
async def test_extract_or_load_snapshot_handles_no_section(tmp_path, monkeypatch):
    pack = _write_pack(tmp_path, markdown="# Risk Factors\n\nRisk only, no financial data.")

    called = {"n": 0}

    async def should_not_be_called(_section):
        called["n"] += 1
        return "[]"

    monkeypatch.setattr("edgarpack.query.s1_financials._call_haiku_extract", should_not_be_called)

    result = await extract_or_load_snapshot(pack)
    assert called["n"] == 0
    assert result.extraction_status == "no_financial_data_found"
    assert result.facts == []
    assert (pack / "s1_financials.json").exists()


@pytest.mark.asyncio
async def test_extract_or_load_snapshot_handles_parse_failure(tmp_path, monkeypatch):
    pack = _write_pack(tmp_path, markdown=CEREBRAS_SFD.read_text(encoding="utf-8"))

    async def garbage_haiku(_section):
        return "this is not json"

    monkeypatch.setattr("edgarpack.query.s1_financials._call_haiku_extract", garbage_haiku)

    result = await extract_or_load_snapshot(pack)
    assert result.extraction_status == "llm_parse_failed"
    assert result.facts == []
    assert (pack / "s1_financials.json").exists()


@pytest.mark.asyncio
async def test_extract_or_load_snapshot_handles_missing_api_key(tmp_path, monkeypatch):
    pack = _write_pack(tmp_path, markdown=CEREBRAS_SFD.read_text(encoding="utf-8"))

    async def raising_haiku(_section):
        raise RuntimeError("anthropic package missing")

    monkeypatch.setattr("edgarpack.query.s1_financials._call_haiku_extract", raising_haiku)

    result = await extract_or_load_snapshot(pack)
    assert result.extraction_status == "no_api_key"
    assert result.facts == []
    assert not (pack / "s1_financials.json").exists()
