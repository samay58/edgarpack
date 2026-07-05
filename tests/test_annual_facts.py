"""Regression tests for SSE annual-report fact extraction (edgarpack/sse/annual_facts.py).

Each test below pins one closed failure mode from the Phase 0 spike that
reproduced BYD FY2025 revenue extracted as 80.00 (an ESG coverage ratio)
under a clean citation.
"""

from __future__ import annotations

from datetime import date

import pytest

from edgarpack.parse.sectionize import Section
from edgarpack.sse.annual_facts import write_annual_facts

FILING_DATE = date(2025, 4, 22)


def _section(section_id: str, content: str) -> Section:
    return Section(
        id=section_id,
        title=section_id,
        content=content,
        char_start=0,
        char_end=len(content),
        warnings=[],
    )


def _write(tmp_path, sections):
    return write_annual_facts(
        tmp_path,
        sections,
        stock_code="688696",
        company_name="Test Co",
        filing_date=FILING_DATE,
        source_url="https://static.cninfo.com.cn/finalpage/test.PDF",
    )


def test_corner_cell_header_alignment(tmp_path):
    """SZSE-style headers with a blank leading cell must not shift column indices."""
    content = """## 第二节 公司简介和主要财务指标

单位：元

||2025年|2024年|增减|2023年|
|---|---:|---:|---:|---:|
|营业收入|1030000000|1000000000|3.00|900000000|
"""
    sections = [_section("annual_s02_company_profile_key_financials", content)]

    facts_path = _write(tmp_path, sections)
    assert facts_path is not None

    import json

    facts = json.loads(facts_path.read_text())
    points = facts["facts"]["cas"]["Revenue"]["units"]["CNY"]
    by_year = {p["fy"]: p["val"] for p in points}

    assert by_year[2025] == 1_030_000_000.0
    assert by_year[2024] == 1_000_000_000.0
    assert by_year[2023] == 900_000_000.0


def test_year_state_leak_quarterly_table_produces_no_annual_points(tmp_path):
    """A quarterly table with no year header must not inherit the prior table's years."""
    content = """## 第二节 公司简介和主要财务指标

单位：元

|主要会计数据|2024年|2023年|增减(%)|2022年|
|---|---:|---:|---:|---:|
|营业收入|1000|900|11.11|800|

|分季度主要财务指标|第一季度|第二季度|第三季度|第四季度|
|---|---:|---:|---:|---:|
|营业收入|300|250|260|190|
"""
    sections = [_section("annual_s02_company_profile_key_financials", content)]

    facts_path = _write(tmp_path, sections)
    assert facts_path is not None

    import json

    facts = json.loads(facts_path.read_text())
    points = facts["facts"]["cas"]["Revenue"]["units"]["CNY"]

    assert len(points) == 3
    values = {p["val"] for p in points}
    assert 300.0 not in values
    assert 250.0 not in values
    assert 260.0 not in values
    assert 190.0 not in values


def test_key_table_only_excludes_non_key_sections(tmp_path):
    """A revenue-labeled row outside the 第二节 key-financials section must be ignored."""
    key_content = """## 第二节 公司简介和主要财务指标

单位：元

|主要会计数据|2024年|增减(%)|
|---|---:|---:|
|营业收入|1000|11.11|
"""
    mda_content = """## 第三节 管理层讨论与分析

|营业收入占比|2024年|
|---|---:|
|营业收入|80.00|
"""
    sections = [
        _section("annual_s02_company_profile_key_financials", key_content),
        _section("annual_s03_mda", mda_content),
    ]

    facts_path = _write(tmp_path, sections)
    assert facts_path is not None

    import json

    facts = json.loads(facts_path.read_text())
    points = facts["facts"]["cas"]["Revenue"]["units"]["CNY"]

    assert len(points) == 1
    assert points[0]["val"] == 1000.0
    assert points[0]["val"] != 80.00


def test_one_point_per_concept_year(tmp_path):
    """At most one point per (concept, fiscal_year); equal-priority ties drop, fail closed."""
    # Each table restates its own 单位 marker: after the unit-scale-boundary
    # fix, a marker no longer leaks across a previous table's rows, so a
    # shared declaration from an earlier table cannot supply this one.
    content = """## 第二节 公司简介和主要财务指标

单位：元

|主要财务指标|2024年|
|---|---:|
|营业收入|1000|

单位：元

|主要财务指标|2024年|
|---|---:|
|营业收入|2000|

单位：元

|主要会计数据|2024年|
|---|---:|
|归属于上市公司股东的净利润|500|

单位：元

|主要财务指标|2024年|
|---|---:|
|归属于上市公司股东的净利润|999|
"""
    sections = [_section("annual_s02_company_profile_key_financials", content)]

    with pytest.warns(UserWarning, match="Revenue"):
        facts_path = _write(tmp_path, sections)

    assert facts_path is not None

    import json

    facts = json.loads(facts_path.read_text())
    cas = facts["facts"]["cas"]

    # Equal-priority conflict (both "other" tables): dropped entirely, fail closed.
    assert "Revenue" not in cas

    # Key-table candidate wins over a conflicting lower-priority candidate.
    net_income_points = cas["ProfitLoss"]["units"]["CNY"]
    assert len(net_income_points) == 1
    assert net_income_points[0]["val"] == 500.0


def test_yoy_cross_check_validates_only_latest_pair(tmp_path):
    """The stated 增减 percent describes only the newest adjacent year pair.

    On a year|year|year|增减 layout, the older (second-newest, third-newest)
    pair must not be validated against a percent that was never computed
    from it. All three years survive.
    """
    content = """## 第二节 公司简介和主要财务指标

单位：元

|主要会计数据|2024年|2023年|2022年|本期比上年增减(%)|
|---|---:|---:|---:|---:|
|营业收入|1000|900|700|11.11|
"""
    sections = [_section("annual_s02_company_profile_key_financials", content)]

    facts_path = _write(tmp_path, sections)
    assert facts_path is not None

    import json

    facts = json.loads(facts_path.read_text())
    revenue_by_year = {p["fy"]: p["val"] for p in facts["facts"]["cas"]["Revenue"]["units"]["CNY"]}

    assert revenue_by_year[2024] == 1000.0
    assert revenue_by_year[2023] == 900.0
    assert revenue_by_year[2022] == 700.0


def test_yoy_cross_check_drops_corrupted_pair(tmp_path):
    """A value implying an implausible YoY swing against the stated 增减 column is dropped."""
    content = """## 第二节 公司简介和主要财务指标

单位：元

|主要会计数据|2024年|2023年|增减(%)|2022年|
|---|---:|---:|---:|---:|
|营业收入|1034600000|1000000000|3.46|900000000|
|归属于上市公司股东的净利润|100000000|10000000|3.46|9000000|
"""
    sections = [_section("annual_s02_company_profile_key_financials", content)]

    with pytest.warns(UserWarning, match="YoY"):
        facts_path = _write(tmp_path, sections)

    assert facts_path is not None

    import json

    facts = json.loads(facts_path.read_text())
    cas = facts["facts"]["cas"]

    revenue_by_year = {p["fy"]: p["val"] for p in cas["Revenue"]["units"]["CNY"]}
    assert revenue_by_year[2024] == 1_034_600_000.0
    assert revenue_by_year[2023] == 1_000_000_000.0
    assert revenue_by_year[2022] == 900_000_000.0

    net_income_by_year = {p["fy"]: p["val"] for p in cas["ProfitLoss"]["units"]["CNY"]}
    assert 2024 not in net_income_by_year
    assert 2023 not in net_income_by_year
    assert net_income_by_year[2022] == 9_000_000.0


def test_backticked_years_and_values_extract_normally(tmp_path):
    """pymupdf4llm mono-font rendering can wrap digits in backtick code spans."""
    content = """## 第二节 公司简介和主要财务指标

单位：元

|主要会计数据|`2024`年|`2023`年|增减(%)|`2022`年|
|---|---:|---:|---:|---:|
|营业收入|`1000000`|`900000`|11.11|`800000`|
"""
    sections = [_section("annual_s02_company_profile_key_financials", content)]

    facts_path = _write(tmp_path, sections)
    assert facts_path is not None

    import json

    facts = json.loads(facts_path.read_text())
    points = facts["facts"]["cas"]["Revenue"]["units"]["CNY"]
    by_year = {p["fy"]: p["val"] for p in points}

    assert by_year[2024] == 1_000_000.0
    assert by_year[2023] == 900_000.0
    assert by_year[2022] == 800_000.0


def test_unit_scale_wan_yuan_scales_correctly(tmp_path):
    """A 万元 (x1e4) unit marker must scale values up to yuan."""
    content = """## 第二节 公司简介和主要财务指标

单位：万元

|主要会计数据|2024年|2023年|增减(%)|2022年|
|---|---:|---:|---:|---:|
|营业收入|100|90|11.11|80|
"""
    sections = [_section("annual_s02_company_profile_key_financials", content)]

    facts_path = _write(tmp_path, sections)
    assert facts_path is not None

    import json

    facts = json.loads(facts_path.read_text())
    points = facts["facts"]["cas"]["Revenue"]["units"]["CNY"]
    by_year = {p["fy"]: p["val"] for p in points}

    assert by_year[2024] == 1_000_000.0
    assert by_year[2023] == 900_000.0
    assert by_year[2022] == 800_000.0


def test_unit_scale_missing_marker_fails_closed(tmp_path):
    """A table with no recognizable 单位 marker must yield no facts, not a guessed unit."""
    content = """## 第二节 公司简介和主要财务指标

|主要会计数据|2024年|2023年|增减(%)|2022年|
|---|---:|---:|---:|---:|
|营业收入|1000|900|11.11|800|
"""
    sections = [_section("annual_s02_company_profile_key_financials", content)]

    with pytest.warns(UserWarning, match="单位"):
        facts_path = _write(tmp_path, sections)

    assert facts_path is None


def test_unit_scale_does_not_cross_previous_table_boundary(tmp_path):
    """A 单位 marker scoping an earlier small table must not leak into the key table."""
    content = """## 第二节 公司简介和主要财务指标

单位：万元

|小表|2024年|
|---|---:|
|其他数据|100|

|主要会计数据|2024年|2023年|增减(%)|2022年|
|---|---:|---:|---:|---:|
|营业收入|1000|900|11.11|800|
"""
    sections = [_section("annual_s02_company_profile_key_financials", content)]

    with pytest.warns(UserWarning, match="单位"):
        facts_path = _write(tmp_path, sections)

    assert facts_path is None


def test_in_table_unit_row_between_title_and_year_header_extracts(tmp_path):
    """SSE-template tables carry the 单位 marker as a row INSIDE the table,
    directly above the year-header row, not as prose before the table."""
    content = """## 第二节 公司简介和主要财务指标

|单位：元<br>币种：人民币|||||
|主要会计数据|2024年|2023年|
|---|---:|---:|
|营业收入|1000|900|
"""
    sections = [_section("annual_s02_company_profile_key_financials", content)]

    facts_path = _write(tmp_path, sections)
    assert facts_path is not None

    import json

    facts = json.loads(facts_path.read_text())
    points = facts["facts"]["cas"]["Revenue"]["units"]["CNY"]
    by_year = {p["fy"]: p["val"] for p in points}

    assert by_year[2024] == 1000.0
    assert by_year[2023] == 900.0


def test_identical_duplicate_year_columns_with_same_value_extract_once(tmp_path):
    """Two identical-year columns (调整后/调整前) with the SAME value are one
    fact written twice, not a conflict."""
    content = """## 第二节 公司简介和主要财务指标

单位：元

|主要会计数据|2024年调整后|2024年调整前|2023年|
|---|---:|---:|---:|
|营业收入|1000|1000|900|
"""
    sections = [_section("annual_s02_company_profile_key_financials", content)]

    facts_path = _write(tmp_path, sections)
    assert facts_path is not None

    import json

    facts = json.loads(facts_path.read_text())
    points = facts["facts"]["cas"]["Revenue"]["units"]["CNY"]
    by_year = {p["fy"]: p["val"] for p in points}

    assert len(points) == 2
    assert by_year[2024] == 1000.0
    assert by_year[2023] == 900.0


def test_identical_duplicate_year_columns_with_differing_values_fail_closed(tmp_path):
    """Two identical-year columns with DIFFERENT values are a genuine
    conflict and still drop, fail closed."""
    content = """## 第二节 公司简介和主要财务指标

单位：元

|主要会计数据|2024年调整后|2024年调整前|2023年|
|---|---:|---:|---:|
|营业收入|1000|1200|900|
"""
    sections = [_section("annual_s02_company_profile_key_financials", content)]

    with pytest.warns(UserWarning, match="Revenue"):
        facts_path = _write(tmp_path, sections)

    assert facts_path is not None

    import json

    facts = json.loads(facts_path.read_text())
    points = facts["facts"]["cas"]["Revenue"]["units"]["CNY"]
    by_year = {p["fy"]: p["val"] for p in points}

    # The conflicting FY2024 pair (1000 vs 1200) drops entirely; the
    # unambiguous FY2023 value still extracts.
    assert 2024 not in by_year
    assert by_year[2023] == 900.0


def test_row_level_unit_suffix_yuan_extracts_at_scale_one(tmp_path):
    """A （元） suffix on the row label itself satisfies the unit gate, no
    table-level 单位 line needed (SZSE/ChiNext-template tables)."""
    content = """## 第二节 公司简介和主要财务指标

|主要会计数据|2024年|2023年|
|---|---:|---:|
|营业收入（元）|1000|900|
"""
    sections = [_section("annual_s02_company_profile_key_financials", content)]

    facts_path = _write(tmp_path, sections)
    assert facts_path is not None

    import json

    facts = json.loads(facts_path.read_text())
    points = facts["facts"]["cas"]["Revenue"]["units"]["CNY"]
    by_year = {p["fy"]: p["val"] for p in points}

    assert by_year[2024] == 1000.0
    assert by_year[2023] == 900.0


def test_row_level_unit_suffix_thousand_yuan_scales(tmp_path):
    """A half-width (千元) row-label suffix (Midea-style) scales x1e3."""
    content = """## 第二节 公司简介和主要财务指标

|主要会计数据|2024年|2023年|
|---|---:|---:|
|营业收入(千元)|1000|900|
"""
    sections = [_section("annual_s02_company_profile_key_financials", content)]

    facts_path = _write(tmp_path, sections)
    assert facts_path is not None

    import json

    facts = json.loads(facts_path.read_text())
    points = facts["facts"]["cas"]["Revenue"]["units"]["CNY"]
    by_year = {p["fy"]: p["val"] for p in points}

    assert by_year[2024] == 1_000_000.0
    assert by_year[2023] == 900_000.0


def test_cmb_split_chapters_key_table_is_scanned(tmp_path):
    """CMB splits the CSRC template's usual compound title into two chapters
    (第一章 公司简介, 第二章 会计数据和财务指标摘要). Both must sectionize to
    the annual_s02 key-financials id so this scan finds the second chapter's
    key financial table instead of missing it under a pinyin-slug fallback."""
    from edgarpack.sse.sectionize_cn import find_sections_cn

    md = """# 2025年年度报告

**第一章 公司简介**

公司概况内容，没有财务数据。

**第二章 会计数据和财务指标摘要**

单位：元

|主要会计数据|2024年|2023年|
|---|---:|---:|
|营业收入|1000|900|

**第三章 管理层讨论与分析**

管理层讨论。
"""
    sections = find_sections_cn(md, document_type="ANNUAL-REPORT")

    facts_path = _write(tmp_path, sections)
    assert facts_path is not None

    import json

    facts = json.loads(facts_path.read_text())
    points = facts["facts"]["cas"]["Revenue"]["units"]["CNY"]
    by_year = {p["fy"]: p["val"] for p in points}

    assert by_year[2024] == 1000.0
    assert by_year[2023] == 900.0


def test_smic_separator_between_marker_and_header_scales_correctly(tmp_path):
    """SMIC's key table has an extra separator between the 单位 marker row and
    the real year-header row (title / marker / separator / year header); the
    upward unit-scale scan must skip that separator instead of breaking on it,
    and still scale 千元 values correctly."""
    content = """## 第二节 公司简介和主要财务指标

||||单位：千元|币种：人民币|
|---|---|---|---|---|
|主要会计数据|2025年|2024年|本期比上年同期增减(%)|2023年|
|营业收入|67323192|57795570|16.5|45250425|
"""
    sections = [_section("annual_s02_company_profile_key_financials", content)]

    facts_path = _write(tmp_path, sections)
    assert facts_path is not None

    import json

    facts = json.loads(facts_path.read_text())
    points = facts["facts"]["cas"]["Revenue"]["units"]["CNY"]
    by_year = {p["fy"]: p["val"] for p in points}

    assert by_year[2025] == 67_323_192_000.0
    assert by_year[2024] == 57_795_570_000.0
    assert by_year[2023] == 45_250_425_000.0


def test_unit_scale_still_stops_at_genuine_previous_table_boundary(tmp_path):
    """The separator skip-ahead for SMIC's layout must not resurrect the
    already-fixed leak across a genuinely earlier, unrelated table: a
    separator whose adjacent row is a real header (not this table's own unit
    marker) still marks a boundary."""
    content = """## 第二节 公司简介和主要财务指标

单位：万元

|小表|2024年|
|---|---:|
|其他数据|100|

|主要会计数据|2024年|2023年|增减(%)|2022年|
|---|---:|---:|---:|---:|
|营业收入|1000|900|11.11|800|
"""
    sections = [_section("annual_s02_company_profile_key_financials", content)]

    with pytest.warns(UserWarning, match="单位"):
        facts_path = _write(tmp_path, sections)

    assert facts_path is None


def test_row_level_unit_suffix_overrides_table_level_marker(tmp_path):
    """A row-level unit suffix conflicting with the table's 单位 line wins for
    that row: it is the more specific disclosure."""
    content = """## 第二节 公司简介和主要财务指标

单位：万元

|主要会计数据|2024年|
|---|---:|
|营业收入（元）|1000|
"""
    sections = [_section("annual_s02_company_profile_key_financials", content)]

    facts_path = _write(tmp_path, sections)
    assert facts_path is not None

    import json

    facts = json.loads(facts_path.read_text())
    points = facts["facts"]["cas"]["Revenue"]["units"]["CNY"]
    by_year = {p["fy"]: p["val"] for p in points}

    # Row-level （元） wins over the table-level 万元 marker: stays 1000,
    # not scaled up x1e4.
    assert by_year[2024] == 1000.0


def test_longi_adjusted_revenue_row_excluded_headline_extracts(tmp_path):
    """LONGi's key table carries both the headline 营业收入 row and an
    adjusted 扣除...后的营业收入 variant. The 扣除 row must not compete with
    the headline for the same fiscal year (the substring match on 营业收入
    would otherwise manufacture a conflict and fail revenue closed)."""
    content = """## 第二节 公司简介和主要财务指标

单位：元

|主要会计数据|2024年|2023年|
|---|---:|---:|
|营业收入|70347049950.42|82582273118.72|
|扣除与主营业务无关的业务收入和不具备商业实质的收入后的营业收入|69156038920.71|81211823906.59|
"""
    sections = [_section("annual_s02_company_profile_key_financials", content)]

    facts_path = _write(tmp_path, sections)
    assert facts_path is not None

    import json

    facts = json.loads(facts_path.read_text())
    points = facts["facts"]["cas"]["Revenue"]["units"]["CNY"]
    by_year = {p["fy"]: p["val"] for p in points}

    assert by_year[2024] == 70_347_049_950.42
    assert by_year[2023] == 82_582_273_118.72


def test_eastmoney_total_revenue_label_extracts(tmp_path):
    """Brokerage/financial filers (East Money) title the headline revenue row
    营业总收入 instead of 营业收入; the contiguous-substring match on
    营业收入 alone cannot see it (总 breaks the substring), so it must be
    accepted as an additional revenue label."""
    content = """## 第二节 公司简介和主要财务指标

|主要会计数据|2024年|2023年|
|---|---:|---:|
|营业总收入（元）|16067741039.51|11604343090.16|
"""
    sections = [_section("annual_s02_company_profile_key_financials", content)]

    facts_path = _write(tmp_path, sections)
    assert facts_path is not None

    import json

    facts = json.loads(facts_path.read_text())
    points = facts["facts"]["cas"]["Revenue"]["units"]["CNY"]
    by_year = {p["fy"]: p["val"] for p in points}

    assert by_year[2024] == 16_067_741_039.51
    assert by_year[2023] == 11_604_343_090.16


def test_eastmoney_both_revenue_labels_differing_still_fails_closed(tmp_path):
    """When a table carries BOTH 营业收入 and 营业总收入 with differing
    values, the existing conflict machinery must still drop both: accepting
    营业总收入 as an additional label is not a preference rule between them."""
    content = """## 第二节 公司简介和主要财务指标

单位：元

|主要会计数据|2024年|
|---|---:|
|营业收入|1000|
|营业总收入|1200|
|归属于上市公司股东的净利润|500|
"""
    sections = [_section("annual_s02_company_profile_key_financials", content)]

    with pytest.warns(UserWarning, match="Revenue"):
        facts_path = _write(tmp_path, sections)

    assert facts_path is not None

    import json

    facts = json.loads(facts_path.read_text())
    cas = facts["facts"]["cas"]

    assert "Revenue" not in cas
