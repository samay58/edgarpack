"""Unit tests for S-1 financial snapshot extraction.

Tests cover the pure-data side of the extractor (dataclasses, cache layer,
prompt builder, JSON parser). Network calls to Anthropic are monkeypatched
throughout; a separate live-smoke test exercises the real API path.
"""

from __future__ import annotations

import json
import sys
import types
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch  # noqa: F401 (kept available for future tests)

import pytest

from edgarpack.query.s1_financials import (
    _MAX_OUTPUT_TOKENS,
    METRIC_SLUGS,
    MODEL_ID,
    PROMPT_SYSTEM,
    SCHEMA_VERSION,
    MissingAnthropicKeyError,
    SnapshotFact,
    SnapshotResult,
    _call_haiku_extract,
    _detect_presentation_currency,
    _extract_summary_table_facts,
    _gate_llm_facts,
    _s1_max_output_tokens,
    _s1_model_id,
    _summary_period_from_context,
    build_extraction_prompt,
    extract_or_load_snapshot,
    find_financial_data_section,
    has_registration_pack_for_cik,
    parse_llm_response,
    parse_llm_response_with_salvage,
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
            "pro_forma_note": null,
            "source_text": "Revenue ... $78,287"
        }
    ]"""
    facts = parse_llm_response(raw, accession="0001628280-24-041596")
    assert len(facts) == 1
    assert facts[0].metric == "revenue"
    assert facts[0].accession == "0001628280-24-041596"
    assert facts[0].value_cents == 7828700000
    assert facts[0].source_text == "Revenue ... $78,287"


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
        "pro_forma_note": null,
        "source_text": "Revenue ... $78,287"
    }
]
```"""
    facts = parse_llm_response(raw, accession="x")
    assert len(facts) == 1


def test_parse_llm_response_drops_rows_missing_source_text():
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
    facts = parse_llm_response(raw, accession="x")
    assert facts == []


def test_parse_llm_response_drops_non_december_fy_without_annual_context():
    raw = """[
        {
            "fiscal_year": 2026,
            "period_end": "2026-03-31",
            "fiscal_period": "FY",
            "metric": "revenue",
            "value_cents": 60132100000,
            "currency": "USD",
            "is_audited": false,
            "is_pro_forma": false,
            "pro_forma_note": null,
            "source_text": "Revenue / $ / 601,321"
        }
    ]"""
    facts = parse_llm_response(raw, accession="x")
    assert facts == []


def test_parse_llm_response_drops_non_december_fy_with_as_of_only_context():
    raw = """[
        {
            "fiscal_year": 2026,
            "period_end": "2026-03-31",
            "fiscal_period": "FY",
            "metric": "cash_and_equivalents",
            "value_cents": 60132100000,
            "currency": "USD",
            "is_audited": false,
            "is_pro_forma": false,
            "pro_forma_note": null,
            "source_text": "As of March 31, 2026 / Cash and cash equivalents / $ / 601,321"
        }
    ]"""
    facts = parse_llm_response(raw, accession="x")
    assert facts == []


def test_parse_llm_response_keeps_non_december_fy_with_annual_context():
    raw = """[
        {
            "fiscal_year": 2026,
            "period_end": "2026-03-31",
            "fiscal_period": "FY",
            "metric": "revenue",
            "value_cents": 60132100000,
            "currency": "USD",
            "is_audited": true,
            "is_pro_forma": false,
            "pro_forma_note": null,
            "source_text": "Year ended March 31, 2026 / Revenue / $ / 601,321"
        }
    ]"""
    facts = parse_llm_response(raw, accession="x")
    assert len(facts) == 1


def test_parse_llm_response_drops_shareholder_attributable_net_income():
    raw = """[
        {
            "fiscal_year": 2025,
            "period_end": "2025-12-31",
            "fiscal_period": "FY",
            "metric": "net_income_loss",
            "value_cents": -13700000,
            "currency": "USD",
            "is_audited": true,
            "is_pro_forma": false,
            "pro_forma_note": null,
            "source_text": "Net income attributable to shareholders / $ / (137)"
        },
        {
            "fiscal_year": 2025,
            "period_end": "2025-12-31",
            "fiscal_period": "FY",
            "metric": "net_income_loss",
            "value_cents": -20400000,
            "currency": "USD",
            "is_audited": true,
            "is_pro_forma": false,
            "pro_forma_note": null,
            "source_text": "Net income (loss) / $ / (204)"
        }
    ]"""
    facts = parse_llm_response(raw, accession="x")

    assert len(facts) == 1
    assert facts[0].value_cents == -20400000


def test_parse_llm_response_drops_rows_with_unknown_metric():
    raw = """[
        {"fiscal_year": 2024, "period_end": "2024-12-31", "metric": "bogus",
         "value_cents": 1, "currency": "USD", "is_audited": true,
         "is_pro_forma": false, "pro_forma_note": null, "source_text": "Bogus ... $1"},
        {"fiscal_year": 2024, "period_end": "2024-12-31", "metric": "revenue",
         "value_cents": 1, "currency": "USD", "is_audited": true,
         "is_pro_forma": false, "pro_forma_note": null, "source_text": "Revenue ... $1"}
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


def test_summary_table_parser_fails_closed_on_percent_columns():
    section = """
    Summary Consolidated Financial Data

    > **Year Ended March 31, / Year Ended March 31, / Year Ended March 31,**
    >
    > 2024 / % / 2023 / % / 2022 / %
    > (in millions, except percentages)
    > Revenue ... $3,233 / 100 / % / $2,679 / 100 / % / $2,703 / 100 / %
    > Gross profit ... 3,081 / 95 / % / 2,574 / 96 / % / 2,506 / 93 / %
    """
    assert _extract_summary_table_facts(section, accession="0001193125-23-216983") == []


def test_summary_table_parser_fails_closed_on_interleaved_percent_value_rows():
    section = """
    Summary Financial Data

    > 2023 / 2022 / 2021
    > (in millions, except percentages)
    > Total revenue ........................... 2,679 / 100 / % / 2,703 / 100 / % / 2,027 / 100 / %
    > Gross profit ............................ 2,573 / 96 / % / 2,572 / 95 / % / 1,882 / 93 / %
    """
    assert _extract_summary_table_facts(section, accession="0001193125-23-216983") == []


def test_summary_table_parser_fails_closed_on_trailing_percent_change_rows():
    section = """
    Summary Financial Data

    > 2023 / 2022
    > (in thousands, except percentages)
    > Revenues ... $ / 2,047,889 / $ / 1,345,145 / $ / 702,744 / 52.2 / %
    > Gross profit ... $ / 1,023,299 / $ / 597,700 / $ / 425,599 / 71.2 / %
    > Operating loss ... (133,157 / ) / (621,143 / ) / 487,986 / (78.6 / )%
    """
    assert _extract_summary_table_facts(section, accession="0001493152-24-035216") == []


def test_summary_table_parser_does_not_apply_header_to_distant_rows():
    filler = "\n".join(f"> Narrative line {index}" for index in range(180))
    section = f"""
    Summary Financial Data

    > 2023 / 2022
    > (in thousands)
    {filler}
    > Revenue ... 2,807,909 / 3,396,000
    """
    assert _extract_summary_table_facts(section, accession="0001493152-24-035216") == []


def test_summary_table_parser_does_not_use_prose_year_mentions_as_headers():
    section = """
    Report of Independent Registered Public Accounting Firm

    We have audited the consolidated statements of operations and cash flows for each
    of the years in the two-year period ended September 30, 2023, and the related
    notes for September 30, 2023 and 2022.

    Revenues ................................ $ / 2,807,909 / $ / 3,396,000
    """
    assert _extract_summary_table_facts(section, accession="0001493152-24-035216") == []


def test_summary_table_parser_does_not_use_plan_names_as_year_headers():
    section = """
    Share-based Compensation

    > LTIP 2018 / LTIP 2018 / LTIP 2020 / LTIP 2020
    > Gross profit ............................ 231,105 / 143,117
    > Net loss ................................ (27,524 / ) / (1,473 / )
    """
    assert _extract_summary_table_facts(section, accession="0001193125-21-253415") == []


def test_summary_table_parser_does_not_use_citation_years_as_headers():
    section = """
    Industry Data

    > CustomerGauge, NPS Financial Services/27 Banking NPS Scores 2023, March 26, 2023;
    > Total revenue ........................... 2,811 / 2,276
    """
    assert _extract_summary_table_facts(section, accession="0001628280-25-012824") == []


def test_summary_table_parser_uses_later_table_header_for_later_rows():
    section = """
    Consolidated Balance Sheets

    > September 30, 2023 / September 30, 2022 / September 30, 2022
    > Cash and cash equivalents ............... $ / 130,201 / $ / 364,449

    ## Consolidated Statements of Operations and Comprehensive Loss

    > September 30, 2023 / September 30, 2022 / September 30, 2022
    > Revenues ................................ $ / 2,807,909 / $ / 3,396,000
    """
    facts = _extract_summary_table_facts(section, accession="0001493152-24-035216")
    by_key = {(fact.metric, fact.fiscal_year): fact for fact in facts}

    assert by_key[("revenue", 2023)].value_cents == 280_790_900
    assert by_key[("revenue", 2022)].value_cents == 339_600_000
    assert ("revenue", 2021) not in by_key


def test_summary_table_parser_drops_conflicting_duplicate_facts():
    section = """
    Summary Financial Data

    > 2023 / 2022
    > Revenue ... 100 / 90

    Selected Financial Data

    > 2023 / 2022
    > Revenue ... 101 / 90
    """
    facts = _extract_summary_table_facts(section, accession="0001493152-24-035216")
    by_key = {(fact.metric, fact.fiscal_year): fact for fact in facts}

    assert ("revenue", 2023) not in by_key
    assert by_key[("revenue", 2022)].value_cents == 9_000


def test_summary_table_parser_does_not_label_six_month_rows_as_annual():
    section = """
    Summary Financial Data

    > Six Months Ended March 31, / Six Months Ended March 31,
    > 2024 / 2023
    > Revenue ... 2,047,889 / 1,345,145
    """
    facts = _extract_summary_table_facts(section, accession="0001493152-24-035216")
    by_key = {(fact.metric, fact.fiscal_year, fact.fiscal_period): fact for fact in facts}

    assert by_key[("revenue", 2024, "Q2")].period_end == "2024-03-31"
    assert ("revenue", 2024, "FY") not in by_key


def test_summary_table_parser_merges_split_interim_header_rows():
    section = """
    Summary Financial Data

    > For the Six months Ended / For the Six months Ended
    > March 31 / March 31
    > 2024 / 2023
    > Net cash used in operating activities ... $ / (301,203 / ) / $ / (184,620 / )
    """
    facts = _extract_summary_table_facts(section, accession="0001493152-24-035216")
    by_key = {(fact.metric, fact.fiscal_year, fact.fiscal_period): fact for fact in facts}

    assert by_key[("operating_cash_flow", 2024, "Q2")].period_end == "2024-03-31"
    assert ("operating_cash_flow", 2024, "FY") not in by_key


def test_summary_table_parser_preserves_split_parenthetical_negatives():
    section = """
    Summary Financial Data

    > 2023 / 2022
    > Net cash used in operating activities ... $ / (301,203 / ) / $ / (184,620 / )
    """
    facts = _extract_summary_table_facts(section, accession="0001493152-24-035216")
    by_key = {(fact.metric, fact.fiscal_year): fact for fact in facts}

    assert by_key[("operating_cash_flow", 2023)].value_cents == -30_120_300
    assert by_key[("operating_cash_flow", 2022)].value_cents == -18_462_000


def test_summary_table_parser_fails_closed_on_variance_amount_columns():
    section = """
    Summary Financial Data

    > Six Months Ended March 31, / Six Months Ended March 31, / Six Months Ended March 31
    > 2024 / 2024 / 2023 / 2023 / Variance / Variance
    > (US$) / (US$) / (US$) / (US$) / Amount / Amount
    > Gross profit ............................ $ / 554,875 / $ / 324,551 / $ / 230,324
    """
    assert _extract_summary_table_facts(section, accession="0001493152-24-035216") == []


def test_summary_table_parser_fails_closed_when_row_has_extra_amount_columns():
    section = """
    Summary Financial Data

    > 2021 / 2020
    > (in thousands)
    > Gross profit ............................ 187,179 / 96,004 / 231,105 / 143,117
    > Adjusted EBITDA ......................... 47,299 / 15,975 / 49,762 / 29,869
    """
    assert _extract_summary_table_facts(section, accession="0001193125-21-253415") == []


def test_summary_table_parser_fails_closed_on_annual_plus_unlabeled_interim_values():
    section = "\n".join(
        [
            "Summary Financial Data",
            "",
            "> 2023 / 2022 / 2021",
            "> (in millions)",
            (
                "> Total revenue ........................... $ / 2,679 / $ / 2,703 / "
                "$ / 2,027 / $ / 675 / $ / 692"
            ),
        ]
    )
    assert _extract_summary_table_facts(section, accession="0001193125-23-216983") == []


def test_summary_table_parser_does_not_label_share_count_row_as_eps():
    section = """
    Summary Financial Data

    > 2023 / 2022 / 2021
    > (in millions, except per share amounts)
    > Net income per share:
    > Basic ................................... 1,025,234,000 / 1,025,234,000 / 1,025,234,000
    """
    assert _extract_summary_table_facts(section, accession="0001193125-23-216983") == []


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
        ("> Revenue ... Revenue / Revenue / $ / 98,743 / $ / 49,835 / $ / 48,908 / 98 / 98 / %"),
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


def test_extract_summary_table_facts_skips_hawkeye_mda_percent_comparison_rows():
    facts = _extract_summary_table_facts(
        _HAWKEYE_2026_MDA_TABLES,
        accession="0001628280-26-029373",
    )
    by_key = {(fact.metric, fact.fiscal_year, fact.fiscal_period): fact for fact in facts}

    assert ("revenue", 2025, "FY") not in by_key
    assert ("revenue", 2024, "FY") not in by_key
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

    monkeypatch.setattr("edgarpack.query.registration.llm._call_haiku_extract", should_not_call_llm)

    result = await extract_or_load_snapshot(pack)
    by_key = {(fact.metric, fact.fiscal_year): fact for fact in result.facts}

    assert by_key[("operating_cash_flow", 2025)].value_cents == -1_005_000_000
    assert by_key[("capex", 2025)].value_cents == 38_273_900_000
    assert by_key[("capex", 2024)].value_cents == 2_343_500_000


@pytest.mark.asyncio
async def test_extract_or_load_snapshot_merges_deterministic_and_llm_facts(tmp_path, monkeypatch):
    # Fix 1 (merge-extraction): the deterministic parser reads the Cerebras
    # income-statement slugs but has no label branch for balance-sheet slugs
    # like total_assets. The LLM is invoked ONLY to fill those missing slugs;
    # a deterministic slug wins even when the LLM returns a rival value for it.
    pack = _write_pack(
        tmp_path,
        accession="0001628280-26-025762",
        markdown=_CEREBRAS_2026_SUMMARY_TABLE,
    )

    calls = {"n": 0}

    async def fake_haiku(_section):
        calls["n"] += 1
        return json.dumps(
            [
                {
                    "fiscal_year": 2025,
                    "period_end": "2025-12-31",
                    "metric": "total_assets",
                    "value_cents": 90_000_000_000,
                    "currency": "USD",
                    "is_audited": True,
                    "is_pro_forma": False,
                    "pro_forma_note": None,
                    "source_text": "Total assets ... $900,000",
                },
                {
                    "fiscal_year": 2025,
                    "period_end": "2025-12-31",
                    "metric": "revenue",
                    "value_cents": 111_111_111_111,
                    "currency": "USD",
                    "is_audited": True,
                    "is_pro_forma": False,
                    "pro_forma_note": None,
                    "source_text": "rival revenue the deterministic parser must win over",
                },
            ]
        )

    monkeypatch.setattr("edgarpack.query.registration.llm._call_haiku_extract", fake_haiku)

    result = await extract_or_load_snapshot(pack)
    by_key = {(fact.metric, fact.fiscal_year): fact for fact in result.facts}

    assert result.extraction_status == "ok"
    # The LLM was called exactly once, to fill the slugs the label map misses.
    assert calls["n"] == 1
    # Deterministic income-statement facts win over the LLM's rival revenue.
    assert by_key[("revenue", 2025)].value_cents == 50_999_100_000
    # A balance-sheet slug the deterministic parser cannot see is LLM-filled.
    assert by_key[("total_assets", 2025)].value_cents == 90_000_000_000
    # Provenance records both extractors in the model field.
    assert "deterministic-summary-table" in result.model
    assert _s1_model_id() in result.model
    assert (pack / "s1_financials.json").exists()


@pytest.mark.asyncio
async def test_extract_or_load_snapshot_skips_llm_when_all_slugs_deterministic(
    tmp_path, monkeypatch
):
    # The merge still short-circuits: if the deterministic parser already
    # covers every slug, the LLM is never invoked.
    facts = [
        {
            "accession": "0001628280-26-025762",
            "fiscal_year": 2025,
            "period_end": "2025-12-31",
            "metric": slug,
            "value_cents": 1_000,
            "currency": "USD",
            "is_audited": True,
            "is_pro_forma": False,
            "pro_forma_note": None,
        }
        for slug in METRIC_SLUGS
    ]

    def fake_extract(_section, *, accession):  # noqa: ARG001
        return [SnapshotFact(**row) for row in facts]

    monkeypatch.setattr(
        "edgarpack.query.registration.table_parse._extract_summary_table_facts", fake_extract
    )

    async def should_not_call_llm(_section):
        raise AssertionError("full deterministic coverage must not call the LLM")

    monkeypatch.setattr("edgarpack.query.registration.llm._call_haiku_extract", should_not_call_llm)

    pack = _write_pack(
        tmp_path,
        accession="0001628280-26-025762",
        markdown=_CEREBRAS_2026_SUMMARY_TABLE,
    )
    result = await extract_or_load_snapshot(pack)

    assert result.extraction_status == "ok"
    assert result.model == "deterministic-summary-table"
    assert {fact.metric for fact in result.facts} == set(METRIC_SLUGS)


@pytest.mark.asyncio
async def test_call_haiku_extract_returns_raw_response_text(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
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


def test_has_registration_pack_for_cik_filters_form_and_accession(tmp_path):
    pack = _write_pack(
        tmp_path,
        accession="0001104659-26-071170",
        form_type="F-1",
    )

    assert has_registration_pack_for_cik("0002021728", tmp_path)
    assert has_registration_pack_for_cik("0002021728", tmp_path, form_type="F-1")
    assert has_registration_pack_for_cik(
        "0002021728",
        tmp_path,
        form_type="F-1",
        accession="0001104659-26-071170",
    )
    assert not has_registration_pack_for_cik("0002021728", tmp_path, form_type="S-1")
    assert not has_registration_pack_for_cik(
        "0002021728",
        tmp_path,
        form_type="F-1",
        accession="0000000000-00-000000",
    )
    assert pack.exists()


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
                    "source_text": "Revenue ... $78,287",
                }
            ]
        )

    monkeypatch.setattr("edgarpack.query.registration.llm._call_haiku_extract", fake_haiku)

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

    monkeypatch.setattr("edgarpack.query.registration.llm._call_haiku_extract", counting_haiku)

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

    monkeypatch.setattr("edgarpack.query.registration.llm._call_haiku_extract", fresh_haiku)

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

    monkeypatch.setattr("edgarpack.query.registration.llm._call_haiku_extract", forced_haiku)

    await extract_or_load_snapshot(pack, force=True)
    assert called["n"] == 1


@pytest.mark.asyncio
async def test_extract_or_load_snapshot_handles_no_section(tmp_path, monkeypatch):
    pack = _write_pack(tmp_path, markdown="# Risk Factors\n\nRisk only, no financial data.")

    called = {"n": 0}

    async def should_not_be_called(_section):
        called["n"] += 1
        return "[]"

    monkeypatch.setattr(
        "edgarpack.query.registration.llm._call_haiku_extract", should_not_be_called
    )

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

    monkeypatch.setattr("edgarpack.query.registration.llm._call_haiku_extract", garbage_haiku)

    result = await extract_or_load_snapshot(pack)
    assert result.extraction_status == "llm_parse_failed"
    assert result.facts == []
    assert (pack / "s1_financials.json").exists()


@pytest.mark.asyncio
async def test_extract_or_load_snapshot_handles_missing_api_key(tmp_path, monkeypatch):
    # Fix 2 (error-taxonomy): only a MissingAnthropicKeyError maps to the
    # non-retryable no_api_key status, and no_api_key is never cached so adding
    # the key and re-reading extracts immediately.
    pack = _write_pack(tmp_path, markdown=CEREBRAS_SFD.read_text(encoding="utf-8"))

    async def missing_key_haiku(_section):
        raise MissingAnthropicKeyError("ANTHROPIC_API_KEY is not set")

    monkeypatch.setattr("edgarpack.query.registration.llm._call_haiku_extract", missing_key_haiku)

    result = await extract_or_load_snapshot(pack)
    assert result.extraction_status == "no_api_key"
    assert result.facts == []
    assert not (pack / "s1_financials.json").exists()


@pytest.mark.asyncio
async def test_extract_or_load_snapshot_maps_runtime_api_failure_to_llm_call_failed(
    tmp_path, monkeypatch
):
    # Fix 2 (error-taxonomy): a runtime API failure (429, outage, model
    # retirement) is llm_call_failed, carries the exception text in `detail`,
    # and is cached with a retry_after cooldown -- never mislabeled no_api_key.
    pack = _write_pack(tmp_path, markdown=CEREBRAS_SFD.read_text(encoding="utf-8"))

    async def raising_haiku(_section):
        raise RuntimeError("overloaded: 429")

    monkeypatch.setattr("edgarpack.query.registration.llm._call_haiku_extract", raising_haiku)

    result = await extract_or_load_snapshot(pack)
    assert result.extraction_status == "llm_call_failed"
    assert result.detail is not None and "429" in result.detail
    assert result.retry_after is not None
    assert result.facts == []
    assert (pack / "s1_financials.json").exists()


# ---------------------------------------------------------------------------
# Fix 3: retryable-cache (cooldown + truncated-array salvage)
# ---------------------------------------------------------------------------


def _write_failure_snapshot(pack: Path, *, retry_after: str) -> None:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "accession": pack.name,
        "extracted_at": "2026-04-22T00:00:00Z",
        "extraction_status": "llm_call_failed",
        "source_sha256": source_sha256_for_pack(pack),
        "model": "claude-haiku-4-5-20251001",
        "detail": "overloaded: 429",
        "retry_after": retry_after,
        "facts": [],
    }
    (pack / "s1_financials.json").write_text(json.dumps(payload), encoding="utf-8")


@pytest.mark.asyncio
async def test_extract_or_load_snapshot_serves_cached_failure_within_cooldown(
    tmp_path, monkeypatch
):
    # Fix 3: a retryable failure is served from cache while its cooldown is
    # active, so a rapid re-read does not re-hit the API.
    pack = _write_pack(tmp_path, markdown=CEREBRAS_SFD.read_text(encoding="utf-8"))
    future = (datetime.now(UTC) + timedelta(minutes=20)).isoformat().replace("+00:00", "Z")
    _write_failure_snapshot(pack, retry_after=future)

    async def should_not_call_llm(_section):
        raise AssertionError("cached failure inside cooldown must not re-hit the API")

    monkeypatch.setattr("edgarpack.query.registration.llm._call_haiku_extract", should_not_call_llm)

    result = await extract_or_load_snapshot(pack)
    assert result.extraction_status == "llm_call_failed"
    assert result.facts == []


@pytest.mark.asyncio
async def test_extract_or_load_snapshot_reattempts_cached_failure_after_cooldown(
    tmp_path, monkeypatch
):
    # Fix 3: once the cooldown has elapsed, a read re-attempts extraction
    # instead of serving the stale failure forever.
    pack = _write_pack(tmp_path, markdown="# Selected Financial Data\n\nRevenue 78,287")
    past = (datetime.now(UTC) - timedelta(minutes=1)).isoformat().replace("+00:00", "Z")
    _write_failure_snapshot(pack, retry_after=past)

    calls = {"n": 0}

    async def recovering_haiku(_section):
        calls["n"] += 1
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
                    "source_text": "Revenue ... $78,287",
                }
            ]
        )

    monkeypatch.setattr("edgarpack.query.registration.llm._call_haiku_extract", recovering_haiku)

    result = await extract_or_load_snapshot(pack)
    assert calls["n"] == 1
    assert result.extraction_status == "ok"
    assert any(fact.metric == "revenue" for fact in result.facts)


def test_parse_llm_response_with_salvage_recovers_truncated_array():
    # Fix 3: a response cut off mid-array is trimmed to its last complete
    # object and parsed, marking the snapshot truncated.
    raw = (
        '[{"fiscal_year": 2024, "period_end": "2024-12-31", "metric": "total_assets",'
        ' "value_cents": 100, "currency": "USD", "is_audited": true, "is_pro_forma": false,'
        ' "pro_forma_note": null, "source_text": "Total assets ... $100"},'
        ' {"fiscal_year": 2024, "period_end": "2024-12-31", "metric": "cash_and_equ'
    )
    facts, truncated = parse_llm_response_with_salvage(raw, accession="a")
    assert truncated is True
    assert [f.metric for f in facts] == ["total_assets"]


def test_parse_llm_response_with_salvage_reraises_when_nothing_recoverable():
    # No complete object present: salvage cannot recover anything, so the
    # ValueError propagates and the caller records llm_parse_failed.
    with pytest.raises(ValueError):
        parse_llm_response_with_salvage("[{not valid", accession="a")


@pytest.mark.asyncio
async def test_extract_or_load_snapshot_salvages_truncated_llm_json(tmp_path, monkeypatch):
    # Fix 3 (integration): a truncated LLM array still yields an `ok` snapshot
    # with the truncated marker rather than an llm_parse_failed.
    pack = _write_pack(tmp_path, markdown="# Selected Financial Data\n\nRevenue 78,287")

    async def truncated_haiku(_section):
        return (
            '[{"fiscal_year": 2024, "period_end": "2024-12-31", "metric": "total_assets",'
            ' "value_cents": 90000000000, "currency": "USD", "is_audited": true,'
            ' "is_pro_forma": false, "pro_forma_note": null, "source_text": "Total assets"},'
            ' {"fiscal_year": 2024, "period_end": "2024-12-31", "metric": "cash_and_equ'
        )

    monkeypatch.setattr("edgarpack.query.registration.llm._call_haiku_extract", truncated_haiku)

    result = await extract_or_load_snapshot(pack)
    assert result.extraction_status == "ok"
    assert result.truncated is True
    assert any(fact.metric == "total_assets" for fact in result.facts)
    # truncated-ok-retry: only one of thirteen slugs was salvaged, so the
    # snapshot must carry a cooldown rather than caching the gap forever.
    assert result.retry_after is not None


# ---------------------------------------------------------------------------
# Fix: truncated-ok-retry (a truncated ok snapshot with missing slugs is
# retryable on a cooldown; complete-but-truncated stays permanent)
# ---------------------------------------------------------------------------


def _write_truncated_ok_snapshot(
    pack: Path,
    *,
    retry_after: str | None,
    facts: list[dict],
) -> None:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "accession": pack.name,
        "extracted_at": "2026-04-22T00:00:00Z",
        "extraction_status": "ok",
        "source_sha256": source_sha256_for_pack(pack),
        "model": "deterministic-summary-table",
        "retry_after": retry_after,
        "truncated": True,
        "gate_rejections": [],
        "facts": facts,
    }
    (pack / "s1_financials.json").write_text(json.dumps(payload), encoding="utf-8")


def _bare_fact(metric: str, *, value_cents: int = 1) -> dict:
    return {
        "accession": "a",
        "fiscal_year": 2024,
        "period_end": "2024-12-31",
        "metric": metric,
        "value_cents": value_cents,
        "currency": "USD",
        "is_audited": True,
        "is_pro_forma": False,
        "pro_forma_note": None,
    }


@pytest.mark.asyncio
async def test_extract_or_load_snapshot_serves_truncated_ok_within_cooldown(tmp_path, monkeypatch):
    # A truncated ok snapshot missing slugs is served from cache while its
    # cooldown is active, exactly like a retryable failure status.
    pack = _write_pack(tmp_path, markdown=CEREBRAS_SFD.read_text(encoding="utf-8"))
    future = (datetime.now(UTC) + timedelta(minutes=20)).isoformat().replace("+00:00", "Z")
    _write_truncated_ok_snapshot(
        pack, retry_after=future, facts=[_bare_fact("revenue", value_cents=7828700000)]
    )

    async def should_not_call_llm(_section):
        raise AssertionError("truncated ok inside cooldown must not re-hit the API")

    monkeypatch.setattr("edgarpack.query.registration.llm._call_haiku_extract", should_not_call_llm)

    result = await extract_or_load_snapshot(pack)
    assert result.extraction_status == "ok"
    assert result.truncated is True
    assert [f.metric for f in result.facts] == ["revenue"]


@pytest.mark.asyncio
async def test_extract_or_load_snapshot_fills_missing_slugs_after_truncated_cooldown(
    tmp_path, monkeypatch
):
    # Once the cooldown elapses, a read re-extracts only the missing slugs
    # and merges them in; the previously cached fact is never overwritten.
    pack = _write_pack(tmp_path, markdown=CEREBRAS_SFD.read_text(encoding="utf-8"))
    past = (datetime.now(UTC) - timedelta(minutes=1)).isoformat().replace("+00:00", "Z")
    _write_truncated_ok_snapshot(
        pack, retry_after=past, facts=[_bare_fact("revenue", value_cents=7828700000)]
    )

    calls = {"n": 0}

    async def filling_haiku(_section):
        calls["n"] += 1
        return json.dumps(
            [
                {
                    "fiscal_year": 2024,
                    "period_end": "2024-12-31",
                    "metric": "total_assets",
                    "value_cents": 44768800000,
                    "currency": "USD",
                    "is_audited": True,
                    "is_pro_forma": False,
                    "pro_forma_note": None,
                    "source_text": "Total assets ... $447,688",
                }
            ]
        )

    monkeypatch.setattr("edgarpack.query.registration.llm._call_haiku_extract", filling_haiku)

    result = await extract_or_load_snapshot(pack)
    assert calls["n"] == 1
    metrics = {f.metric for f in result.facts}
    assert "revenue" in metrics and "total_assets" in metrics
    # The retry's own response parsed cleanly (no truncation this time), so
    # the marker clears even though other slugs remain genuinely unfound.
    assert result.truncated is False
    assert result.retry_after is None


@pytest.mark.asyncio
async def test_extract_or_load_snapshot_truncated_ok_without_gaps_stays_permanent(
    tmp_path, monkeypatch
):
    # A truncated snapshot that already covers every metric slug is a
    # complete extraction; it must never re-attempt, cooldown or not.
    pack = _write_pack(tmp_path, markdown=CEREBRAS_SFD.read_text(encoding="utf-8"))
    facts = [_bare_fact(slug) for slug in sorted(METRIC_SLUGS)]
    _write_truncated_ok_snapshot(pack, retry_after=None, facts=facts)

    async def should_not_call_llm(_section):
        raise AssertionError("a complete-but-truncated snapshot must never re-attempt")

    monkeypatch.setattr("edgarpack.query.registration.llm._call_haiku_extract", should_not_call_llm)

    result = await extract_or_load_snapshot(pack)
    assert result.extraction_status == "ok"
    assert result.truncated is True
    assert len(result.facts) == len(METRIC_SLUGS)


# ---------------------------------------------------------------------------
# Fix: empty-ok-retryable (an empty / fully-gated LLM array with no
# deterministic facts is retryable, not a permanent ok with zero facts)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_or_load_snapshot_empty_llm_response_is_retryable_not_ok(
    tmp_path, monkeypatch
):
    pack = _write_pack(tmp_path, markdown="# Selected Financial Data\n\nRevenue 78,287")

    async def empty_haiku(_section):
        return "[]"

    monkeypatch.setattr("edgarpack.query.registration.llm._call_haiku_extract", empty_haiku)

    result = await extract_or_load_snapshot(pack)
    assert result.extraction_status == "no_financial_data_found"
    assert result.facts == []
    assert result.retry_after is not None


@pytest.mark.asyncio
async def test_extract_or_load_snapshot_reattempts_after_empty_llm_response(tmp_path, monkeypatch):
    pack = _write_pack(tmp_path, markdown="# Selected Financial Data\n\nRevenue 78,287")
    past = (datetime.now(UTC) - timedelta(minutes=1)).isoformat().replace("+00:00", "Z")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "accession": pack.name,
        "extracted_at": "2026-04-22T00:00:00Z",
        "extraction_status": "no_financial_data_found",
        "source_sha256": source_sha256_for_pack(pack),
        "model": MODEL_ID,
        "retry_after": past,
        "facts": [],
    }
    (pack / "s1_financials.json").write_text(json.dumps(payload), encoding="utf-8")

    calls = {"n": 0}

    async def recovering_haiku(_section):
        calls["n"] += 1
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
                    "source_text": "Revenue ... $78,287",
                }
            ]
        )

    monkeypatch.setattr("edgarpack.query.registration.llm._call_haiku_extract", recovering_haiku)

    result = await extract_or_load_snapshot(pack)
    assert calls["n"] == 1
    assert result.extraction_status == "ok"
    assert any(fact.metric == "revenue" for fact in result.facts)


# ---------------------------------------------------------------------------
# Fix 4: model-config (env overrides + one transient retry)
# ---------------------------------------------------------------------------


def test_s1_model_id_honors_env_override(monkeypatch):
    monkeypatch.setenv("EDGARPACK_S1_MODEL", "claude-test-model")
    assert _s1_model_id() == "claude-test-model"
    monkeypatch.delenv("EDGARPACK_S1_MODEL", raising=False)
    assert _s1_model_id() == MODEL_ID


def test_s1_max_output_tokens_honors_env_override(monkeypatch):
    monkeypatch.setenv("EDGARPACK_S1_MAX_TOKENS", "1234")
    assert _s1_max_output_tokens() == 1234
    monkeypatch.setenv("EDGARPACK_S1_MAX_TOKENS", "not-a-number")
    assert _s1_max_output_tokens() == _MAX_OUTPUT_TOKENS
    monkeypatch.delenv("EDGARPACK_S1_MAX_TOKENS", raising=False)
    assert _s1_max_output_tokens() == _MAX_OUTPUT_TOKENS


@pytest.mark.asyncio
async def test_call_haiku_extract_retries_once_on_transient_error(monkeypatch):
    # Fix 4: a single transient API failure is retried once (after a short
    # backoff) before the call succeeds.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    attempts = {"n": 0}

    class _FakeBlock:
        type = "text"
        text = "[]"

    class _FakeMessage:
        content = [_FakeBlock()]

    class _FakeMessages:
        async def create(self, **kwargs):  # noqa: ARG002
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise RuntimeError("transient overload")
            return _FakeMessage()

    class _FakeClient:
        messages = _FakeMessages()

    fake_module = types.SimpleNamespace(AsyncAnthropic=lambda: _FakeClient())
    monkeypatch.setitem(sys.modules, "anthropic", fake_module)

    sleeps: list[float] = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr("edgarpack.query.registration.llm.asyncio.sleep", fake_sleep)

    out = await _call_haiku_extract("# stub")
    assert out == "[]"
    assert attempts["n"] == 2
    assert sleeps == [2.0]


# ---------------------------------------------------------------------------
# Fix 5: currency-honesty (presentation detection + ISO-4217 validation)
# ---------------------------------------------------------------------------


def test_detect_presentation_currency_reads_non_usd_marker():
    assert _detect_presentation_currency("Amounts expressed in thousands of RMB.") == "CNY"
    assert _detect_presentation_currency("in millions of EUR") == "EUR"
    assert _detect_presentation_currency("(in thousands, except per share amounts)") == "USD"


def test_detect_presentation_currency_fails_closed_when_ambiguous():
    assert (
        _detect_presentation_currency("expressed in thousands of RMB and in millions of EUR")
        is None
    )


def test_summary_table_parser_stamps_non_usd_presentation_currency():
    section = "\n".join(
        [
            "Summary Consolidated Financial Data",
            "Amounts expressed in thousands of RMB.",
            "",
            "> 2023 / 2022",
            "> Total revenue ... 1,000 / 900",
        ]
    )
    facts = _extract_summary_table_facts(section, accession="0001493152-24-000001")
    by_key = {(fact.metric, fact.fiscal_year): fact for fact in facts}
    assert by_key[("revenue", 2023)].currency == "CNY"
    assert by_key[("revenue", 2023)].value_cents == 100_000_000


def test_summary_table_parser_fails_closed_on_ambiguous_currency():
    section = "\n".join(
        [
            "Summary Consolidated Financial Data",
            "expressed in thousands of RMB and in millions of EUR",
            "",
            "> 2023 / 2022",
            "> Total revenue ... 1,000 / 900",
        ]
    )
    assert _extract_summary_table_facts(section, accession="0001493152-24-000001") == []


def test_parse_llm_response_rejects_invalid_currency_code():
    good_and_bad = json.dumps(
        [
            {
                "fiscal_year": 2024,
                "period_end": "2024-12-31",
                "metric": "revenue",
                "value_cents": 100,
                "currency": "USD",
                "is_audited": True,
                "is_pro_forma": False,
                "pro_forma_note": None,
                "source_text": "Year ended December 31, 2024 Revenue 1",
            },
            {
                "fiscal_year": 2024,
                "period_end": "2024-12-31",
                "metric": "gross_profit",
                "value_cents": 50,
                "currency": "ZZZ",
                "is_audited": True,
                "is_pro_forma": False,
                "pro_forma_note": None,
                "source_text": "Year ended December 31, 2024 Gross profit 1",
            },
        ]
    )
    facts = parse_llm_response(good_and_bad, accession="a")
    assert [f.metric for f in facts] == ["revenue"]


# ---------------------------------------------------------------------------
# Fix 7: real-period-ends (non-December fiscal years, honest interims)
# ---------------------------------------------------------------------------


def test_summary_period_from_context_carries_non_december_fiscal_year_end():
    # The exact bug: "year ended March 31, 2026" must cite -03-31, not -12-31.
    assert _summary_period_from_context(2026, "Year ended March 31, 2026") == ("FY", "2026-03-31")
    # A bare year with no month-day carries an absent period end (empty
    # string in the snapshot row) rather than fabricating a December
    # year-end for non-calendar filers (fix: bare-year-absent-period).
    assert _summary_period_from_context(2026, "2026") == ("FY", "")
    # Interim contexts never classify as FY.
    assert _summary_period_from_context(2026, "three months ended January 31, 2026") == (
        "Q1",
        "2026-01-31",
    )
    # An interim marker with no parseable month-day yields no fabricated period.
    assert _summary_period_from_context(2026, "six months ended") is None


def test_summary_table_parser_carries_march_fiscal_year_end():
    section = "\n".join(
        [
            "Summary Financial Data",
            "> Year ended March 31, / Year ended March 31,",
            "> 2026 / 2025",
            "> Revenue ... 100 / 90",
        ]
    )
    facts = _extract_summary_table_facts(section, accession="0001493152-24-000001")
    by_key = {(fact.metric, fact.fiscal_year): fact for fact in facts}
    assert by_key[("revenue", 2026)].period_end == "2026-03-31"
    assert by_key[("revenue", 2026)].fiscal_period == "FY"
    assert by_key[("revenue", 2025)].period_end == "2025-03-31"


def test_summary_table_parser_bare_year_header_has_absent_period_end():
    # fix: bare-year-absent-period. A header row that is nothing but the
    # bare years (no "Year ended" caption) carries no month-day anywhere,
    # so the resulting FY facts get an absent period end, not a fabricated
    # December 31.
    section = "\n".join(
        [
            "Summary Financial Data",
            "> 2026 / 2025",
            "> Revenue ... 100 / 90",
        ]
    )
    facts = _extract_summary_table_facts(section, accession="0001493152-24-000001")
    by_key = {(fact.metric, fact.fiscal_year): fact for fact in facts}
    assert by_key[("revenue", 2026)].period_end == ""
    assert by_key[("revenue", 2026)].fiscal_period == "FY"
    assert by_key[("revenue", 2025)].period_end == ""


# ---------------------------------------------------------------------------
# Fix 8: full-hash (invalidate on any content change, including past 50KB)
# ---------------------------------------------------------------------------


def test_source_sha256_for_pack_reflects_change_past_50kb():
    # The old scan window was the first 50KB; a change past that must still
    # move the hash so a late parser fix or amendment invalidates the cache.
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        pack = Path(tmp) / "pack"
        pack.mkdir()
        base = "A" * 60_000
        (pack / "filing.full.md").write_text(base, encoding="utf-8")
        digest_before = source_sha256_for_pack(pack)
        (pack / "filing.full.md").write_text(base + "B", encoding="utf-8")
        assert source_sha256_for_pack(pack) != digest_before


# ---------------------------------------------------------------------------
# Fix 10: magnitude-gates (drop implausible LLM rows, never guess)
# ---------------------------------------------------------------------------


def test_gate_llm_facts_drops_gross_profit_exceeding_revenue():
    trusted = [SnapshotFact("a", 2024, "2024-12-31", "revenue", 100, "USD", True, False, None)]
    llm = [SnapshotFact("a", 2024, "2024-12-31", "gross_profit", 200, "USD", True, False, None)]
    kept, rejections = _gate_llm_facts(llm, trusted)
    assert kept == []
    assert any("gross_profit exceeds revenue" in reason for reason in rejections)


def test_gate_llm_facts_drops_cash_exceeding_total_assets():
    trusted = [SnapshotFact("a", 2024, "2024-12-31", "total_assets", 100, "USD", True, False, None)]
    llm = [
        SnapshotFact("a", 2024, "2024-12-31", "cash_and_equivalents", 200, "USD", True, False, None)
    ]
    kept, rejections = _gate_llm_facts(llm, trusted)
    assert kept == []
    assert any("cash exceeds total_assets" in reason for reason in rejections)


def test_gate_llm_facts_drops_negative_revenue():
    llm = [SnapshotFact("a", 2024, "2024-12-31", "revenue", -5, "USD", True, False, None)]
    kept, rejections = _gate_llm_facts(llm, [])
    assert kept == []
    assert any("negative value" in reason for reason in rejections)


def test_gate_llm_facts_drops_implausible_year_over_year_ratio():
    trusted = [SnapshotFact("a", 2023, "2023-12-31", "revenue", 100, "USD", True, False, None)]
    llm = [SnapshotFact("a", 2024, "2024-12-31", "revenue", 100_000, "USD", True, False, None)]
    kept, rejections = _gate_llm_facts(llm, trusted)
    assert kept == []
    assert any("year-over-year" in reason for reason in rejections)


def test_gate_llm_facts_keeps_plausible_rows():
    trusted = [SnapshotFact("a", 2024, "2024-12-31", "revenue", 1000, "USD", True, False, None)]
    llm = [
        SnapshotFact("a", 2024, "2024-12-31", "gross_profit", 600, "USD", True, False, None),
        SnapshotFact("a", 2024, "2024-12-31", "total_assets", 5000, "USD", True, False, None),
    ]
    kept, rejections = _gate_llm_facts(llm, trusted)
    assert {f.metric for f in kept} == {"gross_profit", "total_assets"}
    assert rejections == []


@pytest.mark.asyncio
async def test_extract_or_load_snapshot_records_gate_rejections(tmp_path, monkeypatch):
    # Fix 10 (integration): a magnitude-gated LLM row is dropped and recorded
    # in gate_rejections, never surfaced as a fact.
    pack = _write_pack(
        tmp_path,
        accession="0001628280-26-025762",
        markdown=_CEREBRAS_2026_SUMMARY_TABLE,
    )

    async def bad_haiku(_section):
        # gross_profit for 2025 wildly exceeds the deterministic revenue.
        return json.dumps(
            [
                {
                    "fiscal_year": 2025,
                    "period_end": "2025-12-31",
                    "metric": "total_assets",
                    "value_cents": -1,
                    "currency": "USD",
                    "is_audited": True,
                    "is_pro_forma": False,
                    "pro_forma_note": None,
                    "source_text": "Total assets ... $(1)",
                }
            ]
        )

    monkeypatch.setattr("edgarpack.query.registration.llm._call_haiku_extract", bad_haiku)

    result = await extract_or_load_snapshot(pack)
    assert result.gate_rejections
    assert not any(fact.metric == "total_assets" for fact in result.facts)
