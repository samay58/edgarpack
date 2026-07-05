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


def test_toc_dot_leaders_are_not_sections():
    """A dot-leader TOC must not steal the clean slug from the real heading."""
    md = """# 招股说明书

目录

第一节 概览 ...................... 1
第二节 本次发行概况 ...................... 5
第三节 发行人基本情况 ...................... 10
第四节 核心技术 ...................... 15
第五节 业务与技术 ...................... 20
第六节 行业概况 ...................... 25
第七节 公司治理 ...................... 30
第八节 财务会计信息 ...................... 35
第九节 募集资金运用 ...................... 40
第十节 风险因素 ...................... 45

## 第一节 概览

公司概览内容。

## 第二节 本次发行概况

发行概况内容。

## 第三节 发行人基本情况

发行人信息。

## 第四节 核心技术

核心技术描述。

## 第五节 业务与技术

业务技术描述。

## 第六节 行业概况

行业概况描述。

## 第七节 公司治理

公司治理描述。

## 第八节 财务会计信息

财务信息描述。

## 第九节 募集资金运用

募集资金描述。

## 第十节 风险因素

风险因素说明。
"""
    sections = find_sections_cn(md)
    ids = [s.id for s in sections]
    expected = [
        "ipo_s01_overview",
        "ipo_s02_offering_summary",
        "ipo_s03_issuer_info",
        "ipo_s04_core_technology",
        "ipo_s05_business_technology",
        "ipo_s06_industry_overview",
        "ipo_s07_corporate_governance",
        "ipo_s08_financial_info",
        "ipo_s09_use_of_proceeds",
        "ipo_s10_risk_factors",
    ]
    for slug in expected:
        assert ids.count(slug) == 1, f"{slug}: expected exactly 1, got {ids.count(slug)}"
    assert not any(i.endswith("_1") for i in ids)


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


def test_bold_wrapped_headings_sectionize():
    """Body headings fully wrapped in bold markers (no # prefix) must still
    be recognized, so a template that bolds every heading (CMB) does not fall
    back to a single unknown_01 blob."""
    md = """# 年度报告

**第一章 公司简介和主要财务指标**

主要财务指标内容。

**第二章 管理层讨论与分析**

管理层讨论。
"""
    sections = find_sections_cn(md, document_type="ANNUAL-REPORT")
    ids = [s.id for s in sections]
    assert "unknown_01" not in ids
    assert "annual_s02_company_profile_key_financials" in ids
    assert "annual_s03_mda" in ids


def test_bold_wrapped_toc_dot_leader_is_not_a_section():
    """The TOC guard applies to the bold-stripped title: a bold-wrapped TOC
    entry with dot leaders must not steal the real heading's slug."""
    md = """# 招股说明书

**第一节 概览 ...................... 1**

## 第一节 概览

公司概览内容。
"""
    sections = find_sections_cn(md)
    ids = [s.id for s in sections]
    assert ids.count("ipo_s01_overview") == 1
    assert not any(i.endswith("_1") for i in ids)
