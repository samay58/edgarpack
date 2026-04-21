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
