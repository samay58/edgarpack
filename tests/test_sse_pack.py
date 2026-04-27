"""Integration tests for SSE pack builder using synthetic fixtures."""

import json
from datetime import date
from unittest.mock import patch

import pytest


@pytest.fixture
def tmp_packs(tmp_path):
    return tmp_path / "packs"


@pytest.fixture
def synthetic_pdf(tmp_path):
    """Create a minimal synthetic PDF-like fixture.

    Since we can't easily create a real PDF without pymupdf, we mock
    the pdf_to_markdown function instead.
    """
    pdf_path = tmp_path / "test_prospectus.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 synthetic test content")
    return pdf_path


SYNTHETIC_MARKDOWN = """# 招股说明书

杭州宇树科技股份有限公司

## 重要声明

本公司及全体董事、监事、高级管理人员保证本招股说明书的真实性。

## 第一节 概览

宇树科技是一家专注于机器人研发与制造的高科技企业。公司成立于2016年，
总部位于杭州，主要从事四足机器人、人形机器人等产品的研发、生产和销售。

## 第二节 本次发行概况

本次公开发行股票数量为不超过5,000万股，占发行后总股本比例不低于10%。

## 第四节 核心技术

公司掌握了电机驱动、运动控制、感知决策等多项核心技术。

## 第八节 财务会计信息

2023年度，公司实现营业收入约12亿元。

## 第十节 风险因素

1. 技术迭代风险
2. 市场竞争风险
3. 国际贸易风险
"""


SYNTHETIC_ANNUAL_MARKDOWN = """# 成都极米科技股份有限公司2024年年度报告

## 第一节 释义

报告期内，公司主要业务未发生重大变化。

## 第二节 公司简介和主要财务指标

|主要会计数据|2024年|2023年|本期比上年同期增减(%)|2022年|
|---|---:|---:|---:|---:|
|营业收入|3,404,605,307.88|3,556,563,980.75|-4.27|4,222,341,286.99|
|归属于上市公司<br>股东的净利润|120,142,895.56|120,503,477.67|-0.30|501,467,954.28|
|经营活动产生的<br>现金流量净额|230,241,355.89|378,268,875.23|-39.13|-58,960,536.97|

|主要财务指标|2024年|2023年|本期比上年同期增减(%)|2022年|
|---|---:|---:|---:|---:|
|研发投入占营业收入的比例<br>（%）|10.80|10.72|增加0.08个百分点|8.93|

## 第三节 管理层讨论与分析

公司持续投入研发。
"""


@pytest.mark.asyncio
async def test_build_sse_pack_synthetic(tmp_packs, synthetic_pdf):
    """Test SSE pack builder with mocked PDF conversion."""
    from edgarpack.pack.build import build_sse_pack

    with patch("edgarpack.sse.pdf_to_md.pdf_to_markdown", return_value=SYNTHETIC_MARKDOWN):
        result = await build_sse_pack(
            url="https://example.com/test.pdf",
            stock_code="301536",
            company_name="Unitree Robotics",
            filing_date=date(2026, 3, 20),
            out_dir=tmp_packs,
            pdf_path=synthetic_pdf,
            with_chunks=False,
            force=False,
        )

    assert result.output_dir.exists()
    assert result.sections_count >= 6
    assert result.tokens_total > 0

    # Check pack structure
    pack_dir = result.output_dir
    assert (pack_dir / "filing.full.md").exists()
    assert (pack_dir / "manifest.json").exists()
    assert (pack_dir / "llms.txt").exists()
    assert (pack_dir / "sections").is_dir()
    assert (pack_dir / "optional" / "source.pdf").exists()

    # Check manifest content
    manifest = json.loads((pack_dir / "manifest.json").read_text())
    assert manifest["filing"]["stock_code"] == "301536"
    assert manifest["filing"]["exchange"] == "SSE"
    assert manifest["filing"]["form_type"] == "IPO-PROSPECTUS"
    assert manifest["filing"]["company_name"] == "Unitree Robotics"

    # Check sections
    section_files = list((pack_dir / "sections").glob("*.md"))
    section_ids = {f.stem for f in section_files}
    assert "ipo_s01_overview" in section_ids
    assert "ipo_s10_risk_factors" in section_ids

    # Verify llms.txt references
    llms = (pack_dir / "llms.txt").read_text()
    assert "Unitree Robotics" in llms
    assert "Stock Code: 301536" in llms


@pytest.mark.asyncio
async def test_build_sse_annual_report_extracts_facts(tmp_packs, synthetic_pdf):
    """Annual reports should build as annual packs with citation-backed CAS facts."""
    from edgarpack.pack.build import build_sse_pack

    with patch(
        "edgarpack.sse.pdf_to_md.pdf_to_markdown",
        return_value=SYNTHETIC_ANNUAL_MARKDOWN,
    ):
        result = await build_sse_pack(
            url="https://static.cninfo.com.cn/finalpage/2025-04-22/1223192484.PDF",
            stock_code="688696",
            company_name="Chengdu XGIMI Technology Co., Ltd.",
            filing_date=date(2025, 4, 22),
            out_dir=tmp_packs,
            pdf_path=synthetic_pdf,
            with_chunks=False,
            force=False,
        )

    pack_dir = result.output_dir
    manifest = json.loads((pack_dir / "manifest.json").read_text())
    assert result.filing_meta["form_type"] == "ANNUAL-REPORT"
    assert manifest["filing"]["form_type"] == "ANNUAL-REPORT"
    assert "facts.json" in manifest["artifacts"]

    section_ids = {f.stem for f in (pack_dir / "sections").glob("*.md")}
    assert "annual_s02_company_profile_key_financials" in section_ids

    facts = json.loads((pack_dir / "facts.json").read_text())
    revenue = facts["facts"]["cas"]["Revenue"]["units"]["CNY"][0]
    net_income = facts["facts"]["cas"]["ProfitLoss"]["units"]["CNY"][0]
    operating_cash_flow = facts["facts"]["cas"]["NetCashProvidedByUsedInOperatingActivities"][
        "units"
    ]["CNY"][0]
    r_and_d = facts["facts"]["cas"]["ResearchAndDevelopmentIntensity"]["units"]["pure"][0]

    assert revenue["fy"] == 2024
    assert revenue["val"] == 3_404_605_307.88
    assert net_income["val"] == 120_142_895.56
    assert operating_cash_flow["val"] == 230_241_355.89
    assert r_and_d["val"] == pytest.approx(0.108)
    assert revenue["section_id"] == "annual_s02_company_profile_key_financials"
    assert revenue["source_url"].startswith("https://static.cninfo.com.cn/")


@pytest.mark.asyncio
async def test_build_sse_pack_skip_existing(tmp_packs, synthetic_pdf):
    """Test that building again skips if pack already exists."""
    from edgarpack.pack.build import build_sse_pack

    with patch("edgarpack.sse.pdf_to_md.pdf_to_markdown", return_value=SYNTHETIC_MARKDOWN):
        await build_sse_pack(
            url="https://example.com/test.pdf",
            stock_code="301536",
            company_name="Unitree Robotics",
            filing_date=date(2026, 3, 20),
            out_dir=tmp_packs,
            pdf_path=synthetic_pdf,
        )

        # Second build should skip
        result2 = await build_sse_pack(
            url="https://example.com/test.pdf",
            stock_code="301536",
            company_name="Unitree Robotics",
            filing_date=date(2026, 3, 20),
            out_dir=tmp_packs,
            pdf_path=synthetic_pdf,
        )

    assert "already exists" in result2.warnings[0]


def test_cli_build_sse_help():
    """Test that build-sse CLI subcommand is registered."""
    from edgarpack.cli import main

    with pytest.raises(SystemExit) as exc_info:
        main(["build-sse", "--help"])
    assert exc_info.value.code == 0
