"""Unit tests for Chinese prospectus sectionizer."""

from edgarpack.sse.sectionize_cn import _cn_num_to_int, _slug_for_title, find_sections_cn


def test_cn_num_basics():
    assert _cn_num_to_int("一") == 1
    assert _cn_num_to_int("五") == 5
    assert _cn_num_to_int("十") == 10
    assert _cn_num_to_int("十二") == 12
    assert _cn_num_to_int("二十") == 20


def test_cn_num_extended_compounds():
    assert _cn_num_to_int("三十") == 30
    assert _cn_num_to_int("三十五") == 35
    assert _cn_num_to_int("九十九") == 99


def test_slug_canonical_sections():
    slug, title = _slug_for_title("概览", 1)
    assert slug == "ipo_s01_overview"
    assert title == "Overview"

    slug, title = _slug_for_title("风险因素", 10)
    assert slug == "ipo_s10_risk_factors"
    assert title == "Risk Factors"

    slug, title = _slug_for_title("核心技术", 4)
    assert slug == "ipo_s04_core_technology"
    assert title == "Core Technology"


def test_slug_declarations():
    slug, title = _slug_for_title("重要声明", None)
    assert slug == "ipo_declarations"
    assert title == "Important Declarations"


def test_slug_annual_report_sections():
    slug, title = _slug_for_title("公司简介和主要财务指标", 2, document_type="ANNUAL-REPORT")
    assert slug == "annual_s02_company_profile_key_financials"
    assert title == "Company Profile and Key Financials"


def test_find_sections_basic():
    md = """# 招股说明书

一些前言内容，这里有超过一百个字符的文本。
一些前言内容，这里有超过一百个字符的文本。
一些前言内容，这里有超过一百个字符的文本。

## 重要声明

本公司声明如下。

## 第一节 概览

公司概览内容。

## 第二节 本次发行概况

发行概况内容。

## 第三节 发行人基本情况

发行人信息。

## 第四节 核心技术

核心技术描述。

## 第十节 风险因素

风险因素说明。
"""
    sections = find_sections_cn(md)

    ids = [s.id for s in sections]
    assert "ipo_declarations" in ids
    assert "ipo_s01_overview" in ids
    assert "ipo_s02_offering_summary" in ids
    assert "ipo_s03_issuer_info" in ids
    assert "ipo_s04_core_technology" in ids
    assert "ipo_s10_risk_factors" in ids


def test_find_sections_no_headings():
    md = "This is just plain text without any Chinese section headings."
    sections = find_sections_cn(md)
    assert len(sections) == 1
    assert sections[0].id == "unknown_01"


def test_find_sections_without_markdown_prefix():
    md = """第一节 概览

公司概览。

第二节 本次发行概况

发行信息。
"""
    sections = find_sections_cn(md)
    ids = [s.id for s in sections]
    assert "ipo_s01_overview" in ids
    assert "ipo_s02_offering_summary" in ids


def test_duplicate_ids_get_suffixed():
    md = """## 第一节 概览

第一部分。

## 第一节 概览

第二部分。
"""
    sections = find_sections_cn(md)
    ids = [s.id for s in sections]
    assert "ipo_s01_overview" in ids
    assert "ipo_s01_overview_1" in ids


def test_find_sections_annual_report():
    md = """# 2024年年度报告

## 第一节 释义

定义内容。

## 第二节 公司简介和主要财务指标

主要财务指标内容。

## 第三节 管理层讨论与分析

管理层讨论。
"""
    sections = find_sections_cn(md, document_type="ANNUAL-REPORT")
    ids = [s.id for s in sections]
    assert "annual_s01_shi_yi" in ids
    assert "annual_s02_company_profile_key_financials" in ids
    assert "annual_s03_mda" in ids


def test_zhang_headings_sectionize():
    md = """# 年度报告

## 第一章 概览

公司概览内容。

## 第二章 本次发行概况

发行概况内容。

## 第三章 核心技术

核心技术描述。
"""
    sections = find_sections_cn(md)
    ids = [s.id for s in sections]
    assert "unknown_01" not in ids
    assert "ipo_s01_overview" in ids
    assert "ipo_s02_offering_summary" in ids
    assert "ipo_s04_core_technology" in ids


def test_bufen_headings_sectionize():
    md = """# 年度报告

## 第一部分 概览

公司概览内容。

## 第二部分 本次发行概况

发行概况内容。
"""
    sections = find_sections_cn(md)
    ids = [s.id for s in sections]
    assert "unknown_01" not in ids
    assert "ipo_s01_overview" in ids
    assert "ipo_s02_offering_summary" in ids


def test_sectionize_dispatch_via_main():
    """Verify that sectionize() dispatches to CN sectionizer for IPO-PROSPECTUS."""
    from edgarpack.parse.sectionize import sectionize

    md = """## 第一节 概览

Content here.

## 第二节 本次发行概况

More content.
"""
    sections = sectionize(md, "IPO-PROSPECTUS")
    ids = [s.id for s in sections]
    assert "ipo_s01_overview" in ids
    assert "ipo_s02_offering_summary" in ids


def test_sectionize_dispatches_annual_report():
    from edgarpack.parse.sectionize import sectionize

    md = """## 第二节 公司简介和主要财务指标

Content here.
"""
    sections = sectionize(md, "ANNUAL-REPORT")
    assert sections[0].id == "annual_s02_company_profile_key_financials"
