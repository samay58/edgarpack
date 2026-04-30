"""Tests for deterministic numeric-table translation."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from edgarpack.china.translate.deepinfra import DeepInfraTranslator
from edgarpack.china.translate.glossary import FinancialGlossary
from edgarpack.china.translate.provider import TranslationResult
from edgarpack.china.translate.router import SectionRouter
from edgarpack.china.translate.validators import validate_translation


@pytest.fixture
def router():
    glossary = FinancialGlossary()
    translator = DeepInfraTranslator(glossary=glossary, api_key="test-key")
    return SectionRouter(translator)


@pytest.mark.asyncio
async def test_numeric_heavy_table_uses_deterministic_path_outside_section_8(router):
    paragraph = "\n".join(
        [
            "|项目|**2025/9/30**|**2024/12/31**|",
            "|---|---|---|",
            "|货币资金|179,473.96万元人民币|56,594.28万元人民币|",
            "|应收账款|7,919.92|2,017.50|",
        ]
    )

    with patch.object(router._translator, "translate_batch", new_callable=AsyncMock) as mock_batch:
        results = await router.translate_section("unknown_section", [paragraph])

    assert len(results) == 1
    assert "Cash and Cash Equivalents" in results[0].text_en
    assert "Accounts Receivable" in results[0].text_en
    assert "RMB 1.79 billion" in results[0].text_en
    assert mock_batch.await_count == 0


@pytest.mark.asyncio
async def test_table_translation_preserves_breaks_and_unknown_short_labels(router):
    paragraph = "\n".join(
        [
            "|项目|2016年8月26日|2024|",
            "|---|---|---|",
            "|研发|1.00|2.00|",
            "|期间|**2025** 年**1-9** 月|**2024** 年度|",
            "|截至日|**2025** 年**12** 月**31** 日|**2024** 年**12** 月**31** 日|",
            "|项目|**2025.9.30/**<br>**2025** 年**1-9** 月|**2024.12.31/**<br>**2024** 年度|",
            "|发行价格|【】元|【】万元|",
            "|公告日期|【】年【】月【】日|2024|",
            "|一年内到期的非流<br>动资产|2,181.04|-|",
        ]
    )

    with patch.object(router._translator, "translate_async", new_callable=AsyncMock) as mock_async:
        mapping = {
            "研发": "Research and Development",
            "期间": "Period",
            "截至日": "As of Date",
            "项目": "Item",
            "发行价格": "Offering Price",
            "公告日期": "Announcement Date",
            "一年内到期的非流动资产": "Non-current Assets Due Within One Year",
        }

        async def _fake_translate(text_zh, system_prompt=None):
            return TranslationResult(
                text_zh=text_zh,
                text_en=mapping[text_zh],
                provider="test",
            )

        mock_async.side_effect = _fake_translate
        [result] = await router.translate_section("ipo_s08_financial_info", [paragraph])

    assert "Research and Development" in result.text_en
    assert "<br>" in result.text_en
    assert "2,181.04" in result.text_en
    assert "2016-08-26" in result.text_en
    assert "**2025** **1-9**M" in result.text_en
    assert "FY **2024**" in result.text_en
    assert "**2025**-**12**-**31**" in result.text_en
    assert "**2024**-**12**-**31**" in result.text_en
    assert "**2025.9.30/**<br>**2025** **1-9**M" in result.text_en
    assert "**2024.12.31/**<br>FY **2024**" in result.text_en
    assert "[] yuan" in result.text_en
    assert "[] ten thousand yuan" in result.text_en
    assert "[]-[]-[]" in result.text_en


@pytest.mark.asyncio
async def test_year_only_date_cells_are_normalized(router):
    paragraph = "\n".join(
        [
            "|类别|事件时间|",
            "|---|---|",
            "|高难动作|2024年|",
            "|运动速度|**2025** 年|",
        ]
    )

    with patch.object(router._translator, "translate_async", new_callable=AsyncMock) as mock_async:
        mapping = {
            "类别": "Category",
            "事件时间": "Event Date",
            "高难动作": "High-difficulty Moves",
            "运动速度": "Motion Speed",
        }

        async def _fake_translate(text_zh, system_prompt=None):
            return TranslationResult(
                text_zh=text_zh,
                text_en=mapping[text_zh],
                provider="test",
            )

        mock_async.side_effect = _fake_translate
        [result] = await router.translate_section("ipo_s05_business_technology", [paragraph])

    assert "|High-difficulty Moves|2024|" in result.text_en
    assert "|Motion Speed|**2025**|" in result.text_en


@pytest.mark.asyncio
async def test_age_range_table_labels_preserve_literal_ranges(router):
    paragraph = "\n".join(
        [
            "|年龄结构类别|年龄结构人数|",
            "|---|---|",
            "|30 岁以下（不含30 岁）|212|",
            "|30-40 岁（含30 岁，不含40 岁）|327|",
            "|40-50 岁（含40 岁，不含50 岁）|69|",
            "|50-60 岁（含50 岁，不含60 岁）|2|",
            "|60 岁及以上|0|",
        ]
    )

    with patch.object(router._translator, "translate_async", new_callable=AsyncMock) as mock_async:
        mapping = {
            "年龄结构类别": "Age Structure Category",
            "年龄结构人数": "Age Structure Headcount",
        }

        async def _fake_translate(text_zh, system_prompt=None):
            return TranslationResult(text_zh=text_zh, text_en=mapping[text_zh], provider="test")

        mock_async.side_effect = _fake_translate
        [result] = await router.translate_section("annual_s03_mda", [paragraph])

    assert "30-40 years old (including 30, excluding 40)" in result.text_en
    assert "40-50 years old (including 40, excluding 50)" in result.text_en
    assert "50-60 years old (including 50, excluding 60)" in result.text_en
    assert "Under 30 years old (excluding 30)" in result.text_en
    assert "60 years old and above" in result.text_en
    assert mock_async.await_count == 2


@pytest.mark.asyncio
async def test_multiline_reporting_period_cells_are_normalized(router):
    paragraph = "\n".join(
        [
            "|年份|收入占比|",
            "|---|---|",
            "|2025年<br>1-9月|3.54%|",
        ]
    )

    with patch.object(router._translator, "translate_async", new_callable=AsyncMock) as mock_async:
        mapping = {
            "年份": "Year",
            "收入占比": "Revenue Share",
        }

        async def _fake_translate(text_zh, system_prompt=None):
            return TranslationResult(
                text_zh=text_zh,
                text_en=mapping[text_zh],
                provider="test",
            )

        mock_async.side_effect = _fake_translate
        [result] = await router.translate_section("ipo_s05_business_technology", [paragraph])

    assert "|2025<br>1-9M|3.54%|" in result.text_en


@pytest.mark.asyncio
async def test_spaced_year_month_table_cells_are_zero_padded(router):
    paragraph = "\n".join(
        [
            "|任期起始日期|任期终止日期|",
            "|---|---|",
            "|2016 年8 月|2021 年4 月|",
            "|**2016** 年**8** 月|**2021** 年**4** 月|",
        ]
    )

    with patch.object(router._translator, "translate_async", new_callable=AsyncMock) as mock_async:
        mapping = {
            "任期起始日期": "Term Start Date",
            "任期终止日期": "Term End Date",
        }

        async def _fake_translate(text_zh, system_prompt=None):
            return TranslationResult(text_zh=text_zh, text_en=mapping[text_zh], provider="test")

        mock_async.side_effect = _fake_translate
        [result] = await router.translate_section("annual_s04_corporate_governance", [paragraph])

    assert "|2016-08|2021-04|" in result.text_en
    assert "|**2016**-**08**|**2021**-**04**|" in result.text_en
    assert validate_translation(paragraph, result.text_en).passed


@pytest.mark.asyncio
async def test_multiline_fiscal_year_cells_are_normalized(router):
    paragraph = "\n".join(
        [
            "|年度|占比|",
            "|---|---|",
            "|2024<br>年度|26.44%|",
        ]
    )

    with patch.object(router._translator, "translate_async", new_callable=AsyncMock) as mock_async:
        mapping = {
            "年度": "Year",
            "占比": "Proportion",
        }

        async def _fake_translate(text_zh, system_prompt=None):
            return TranslationResult(
                text_zh=text_zh,
                text_en=mapping[text_zh],
                provider="test",
            )

        mock_async.side_effect = _fake_translate
        [result] = await router.translate_section("ipo_s05_business_technology", [paragraph])

    assert "|FY 2024|26.44%|" in result.text_en


@pytest.mark.asyncio
async def test_xgimi_annual_governance_table_dates_validate(router):
    paragraph = "\n".join(
        [
            "|任职人员姓名|其他单位名称|在其他单位担任的职务|任期起始日期|任期终止日期|",
            "|---|---|---|---|---|",
            "|刘帅|成都极联科技有限公司|监事|2016 年8 月|/|",
            "|尹蕾|XGIMI 株式会社|代表取缔役|2021 年4 月|/|",
        ]
    )

    with patch.object(router._translator, "translate_async", new_callable=AsyncMock) as mock_async:
        mapping = {
            "任职人员姓名": "Name",
            "其他单位名称": "Other Entity",
            "在其他单位担任的职务": "Position Held",
            "任期起始日期": "Term Start Date",
            "任期终止日期": "Term End Date",
            "刘帅": "Liu Shuai",
            "成都极联科技有限公司": "Chengdu Jilian Technology Co., Ltd.",
            "监事": "Supervisor",
            "尹蕾": "Yin Lei",
            "XGIMI株式会社": "XGIMI Corporation",
            "代表取缔役": "Representative Director",
        }

        async def _fake_translate(text_zh, system_prompt=None):
            return TranslationResult(text_zh=text_zh, text_en=mapping[text_zh], provider="test")

        mock_async.side_effect = _fake_translate
        [result] = await router.translate_section("annual_s04_corporate_governance", [paragraph])

    assert "2016-08" in result.text_en
    assert "2021-04" in result.text_en
    report = validate_translation(paragraph, result.text_en)
    assert report.passed, [issue.message for issue in report.issues]


@pytest.mark.asyncio
async def test_markdown_headings_use_structural_label_translation(router):
    paragraph = "## 四、采购情况和主要供应商"

    with patch.object(router._translator, "translate_batch", new_callable=AsyncMock) as mock_batch:
        with patch.object(
            router._translator,
            "translate_async",
            new_callable=AsyncMock,
        ) as mock_async:
            mock_async.return_value = TranslationResult(
                text_zh="四、采购情况和主要供应商",
                text_en="IV. Procurement and Major Suppliers",
                provider="test",
            )
            [result] = await router.translate_section(
                "ipo_s05_business_technology",
                [paragraph],
                strict=True,
            )

    assert result.text_en == "## IV. Procurement and Major Suppliers"
    assert mock_batch.await_count == 0


@pytest.mark.asyncio
async def test_descriptive_table_uses_structural_translation(router):
    paragraph = "\n".join(
        [
            "|项目|内容|",
            "|---|---|",
            "|发行股票类型|人民币普通股（A股）|",
            "|发行日期|【】年【】月【】日|",
        ]
    )

    with patch.object(router._translator, "translate_async", new_callable=AsyncMock) as mock_async:
        mock_async.side_effect = [
            TranslationResult(
                text_zh="发行股票类型",
                text_en="Type of Shares Offered",
                provider="test",
            ),
            TranslationResult(
                text_zh="人民币普通股（A股）",
                text_en="Renminbi Ordinary Shares (A Shares)",
                provider="test",
            ),
            TranslationResult(
                text_zh="发行日期",
                text_en="Offering Date",
                provider="test",
            ),
            TranslationResult(
                text_zh="【】年【】月【】日",
                text_en="[] Year [] Month [] Day",
                provider="test",
            ),
        ]
        results = await router.translate_section("unknown_section", [paragraph])

    assert len(results) == 1
    assert "Type of Shares Offered" in results[0].text_en
    assert "Renminbi Ordinary Shares (A Shares)" in results[0].text_en
    assert mock_async.await_count == 4


@pytest.mark.asyncio
async def test_multiline_parameter_cells_are_translated_line_by_line(router):
    paragraph = "\n".join(
        [
            "|型号|主要参数|",
            "|---|---|",
            "|Z1|自由度：6轴<br>自重：4.5kg<br>最大臂展：740mm|",
        ]
    )

    with patch.object(router._translator, "translate_async", new_callable=AsyncMock) as mock_async:
        mapping = {
            "型号": "Model",
            "主要参数": "Key Parameters",
            "自由度：6轴": "Degrees of Freedom: 6-axis",
            "自重：4.5kg": "Weight: 4.5kg",
            "最大臂展：740mm": "Maximum Reach: 740mm",
        }

        async def _fake_translate(text_zh, system_prompt=None):
            return TranslationResult(
                text_zh=text_zh,
                text_en=mapping[text_zh],
                provider="test",
            )

        mock_async.side_effect = _fake_translate
        [result] = await router.translate_section(
            "ipo_s05_business_technology",
            [paragraph],
            strict=True,
        )

    assert "|Model|Key Parameters|" in result.text_en
    assert "Degrees of Freedom: 6-axis<br>Weight: 4.5kg<br>Maximum Reach: 740mm" in result.text_en


@pytest.mark.asyncio
async def test_percentage_list_cells_preserve_exact_percentages(router):
    paragraph = "\n".join(
        [
            "|股东|持股比例|",
            "|---|---|",
            (
                "|本轮股东|王兴兴：36.1636%；Astrend IV：9.8228%<br>"
                "经纬叁号1.5401%；经纬壹号：5.5674%|"
            ),
        ]
    )

    with patch.object(router._translator, "translate_async", new_callable=AsyncMock) as mock_async:
        mapping = {
            "股东": "Shareholder",
            "持股比例": "Shareholding Ratio",
            "本轮股东": "Current Round Investors",
            "王兴兴": "Wang Xingxing",
            "经纬叁号": "Matrix Partners III",
            "经纬壹号": "Matrix Partners I",
        }

        async def _fake_translate(text_zh, system_prompt=None):
            return TranslationResult(
                text_zh=text_zh,
                text_en=mapping[text_zh],
                provider="test",
            )

        mock_async.side_effect = _fake_translate
        [result] = await router.translate_section("ipo_s03_issuer_info", [paragraph], strict=True)

    assert "Wang Xingxing: 36.1636%" in result.text_en
    assert "Astrend IV: 9.8228%" in result.text_en
    assert "Matrix Partners III: 1.5401%" in result.text_en
    assert "Matrix Partners I: 5.5674%" in result.text_en
    assert "!" not in result.text_en


@pytest.mark.asyncio
async def test_year_prefix_is_restored_when_llm_drops_it(router):
    paragraph = "\n".join(
        [
            "|项目|数值|",
            "|---|---|",
            "|2024年第一次股权转让，|1.00|",
        ]
    )

    with patch.object(router._translator, "translate_async", new_callable=AsyncMock) as mock_async:
        mapping = {
            "项目": "Item",
            "数值": "Value",
            "2024年第一次股权转让，": "First Equity Transfer",
        }

        async def _fake_translate(text_zh, system_prompt=None):
            return TranslationResult(
                text_zh=text_zh,
                text_en=mapping[text_zh],
                provider="test",
            )

        mock_async.side_effect = _fake_translate
        [result] = await router.translate_section("ipo_s03_issuer_info", [paragraph], strict=True)

    assert "2024 First Equity Transfer" in result.text_en


@pytest.mark.asyncio
async def test_inline_period_conversion_does_not_fire_inside_prose_cells(router):
    paragraph = "\n".join(
        [
            "|项目|说明|",
            "|---|---|",
            (
                "|行业定位|公司符合《上海证券交易所科创板企业发行上市申报及推荐暂行规"
                "定（2024年4月修订）》中第五条相关要求。|"
            ),
        ]
    )

    with patch.object(router._translator, "translate_async", new_callable=AsyncMock) as mock_async:
        mapping = {
            "项目": "Item",
            "说明": "Description",
            "行业定位": "Industry Positioning",
            (
                "公司符合《上海证券交易所科创板企业发行上市申报及推荐暂行规定（2024年4月修订）》"
                "中第五条相关要求。"
            ): (
                "The company satisfies the relevant requirements under Article 5 of the "
                "Provisional Regulations (2024-04 revision)."
            ),
        }

        async def _fake_translate(text_zh, system_prompt=None):
            return TranslationResult(
                text_zh=text_zh,
                text_en=mapping[text_zh],
                provider="test",
            )

        mock_async.side_effect = _fake_translate
        [result] = await router.translate_section("ipo_s01_overview", [paragraph], strict=True)

    assert "2024-04 revision" in result.text_en


@pytest.mark.asyncio
async def test_split_date_header_cells_are_repaired_before_translation(router):
    paragraph = "\n".join(
        [
            "|截至2025年1|2月31日，宁波红杉基本情况如下：|2月31日，宁波红杉基本情况如下：|",
            "|---|---|---|",
            "|名称|宁波红杉科盛股权投资合伙企业（有限合伙）||",
        ]
    )

    with patch.object(router._translator, "translate_async", new_callable=AsyncMock) as mock_async:
        mapping = {
            "截至2025年12月31日，宁波红杉基本情况如下：": (
                "As of 2025-12-31, the basic information of Ningbo Sequoia is as follows:"
            ),
            "名称": "Name",
            "宁波红杉科盛股权投资合伙企业（有限合伙）": (
                "Ningbo Sequoia Kesheng Equity Investment Partnership (Limited Partnership)"
            ),
        }

        async def _fake_translate(text_zh, system_prompt=None):
            return TranslationResult(
                text_zh=text_zh,
                text_en=mapping[text_zh],
                provider="test",
            )

        mock_async.side_effect = _fake_translate
        [result] = await router.translate_section("ipo_s03_issuer_info", [paragraph], strict=True)

    assert "As of 2025-12-31" in result.text_en
    assert "20251" not in result.text_en
    assert "February 31" not in result.text_en


@pytest.mark.asyncio
async def test_plain_year_month_date_cells_are_not_treated_as_reporting_periods(router):
    paragraph = "\n".join(
        [
            "|序号|取得时间|",
            "|---|---|",
            "|1|2025年5月|",
            "|2|2025年6月|",
        ]
    )

    with patch.object(router._translator, "translate_async", new_callable=AsyncMock) as mock_async:
        mapping = {
            "序号": "No.",
            "取得时间": "Acquisition Date",
        }

        async def _fake_translate(text_zh, system_prompt=None):
            return TranslationResult(
                text_zh=text_zh,
                text_en=mapping[text_zh],
                provider="test",
            )

        mock_async.side_effect = _fake_translate
        [result] = await router.translate_section("ipo_s03_issuer_info", [paragraph], strict=True)

    assert "2025-05" in result.text_en
    assert "2025-06" in result.text_en
    assert "2025 5M" not in result.text_en
    assert "2025 6M" not in result.text_en


@pytest.mark.asyncio
async def test_flattened_catalog_paragraph_uses_special_route(router):
    paragraph = "型号 产品图片 主要参数 核心特点 AlienGo 站立尺寸：65×31×60cm 产品布局紧凑"

    with patch.object(router._translator, "translate_async", new_callable=AsyncMock) as mock_async:
        mock_async.return_value = TranslationResult(
            text_zh=paragraph,
            text_en="| Model | Key Parameters | Core Features |\n|---|---|---|\n"
            "| AlienGo | Standing Dimensions: 65×31×60cm | Compact layout |",
            provider="test",
        )

        [result] = await router.translate_section("ipo_s05_business_technology", [paragraph])

    assert "| Model | Key Parameters | Core Features |" in result.text_en
    assert mock_async.await_count == 1
    assert mock_async.call_args.kwargs["allow_markdown_artifacts"] is True
