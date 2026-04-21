"""Tests for DeepInfra translator (mocked, no API calls)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from edgarpack.china.translate.deepinfra import DeepInfraTranslator, _build_system_prompt
from edgarpack.china.translate.glossary import FinancialGlossary
from edgarpack.china.translate.provider import TranslationResult
from edgarpack.china.translate.router import SectionRouter


@pytest.fixture
def glossary():
    return FinancialGlossary()


@pytest.fixture
def translator(glossary):
    return DeepInfraTranslator(glossary=glossary, api_key="test-key")


class TestSystemPrompt:
    def test_includes_glossary_table(self, glossary):
        prompt = _build_system_prompt(glossary)
        assert "Chinese | English" in prompt
        assert "--- | ---" in prompt

    def test_includes_placeholder_instruction(self, glossary):
        prompt = _build_system_prompt(glossary)
        assert "<<NUM_XXX>>" in prompt
        assert "Never invent new <<...>> tokens" in prompt

    def test_extra_appended(self, glossary):
        prompt = _build_system_prompt(glossary, extra="Translate formally.")
        assert "Translate formally." in prompt


class TestDeepInfraTranslator:
    def test_provider_name(self, translator):
        assert translator.provider == "deepinfra/deepseek-ai/DeepSeek-V3"

    @pytest.mark.asyncio
    async def test_empty_text_passthrough(self, translator):
        result = await translator.translate_async("")
        assert result.text_en == ""
        assert result.text_zh == ""

    @pytest.mark.asyncio
    async def test_translate_calls_api(self, translator):
        with patch.object(translator, "_call_api", new_callable=AsyncMock) as mock_api:
            mock_api.return_value = "Revenue was <<NUM_001>>."
            result = await translator.translate_async("营业收入为1000万元")

        assert isinstance(result, TranslationResult)
        assert result.text_zh == "营业收入为1000万元"
        assert "10.00 million" in result.text_en
        mock_api.assert_called_once()

    @pytest.mark.asyncio
    async def test_number_tags_preserved_through_translation(self, translator):
        with patch.object(translator, "_call_api", new_callable=AsyncMock) as mock_api:
            mock_api.return_value = "Net income was <<NUM_001>>, revenue was <<NUM_002>>."
            result = await translator.translate_async("净利润100万元，营业收入500亿元")

        assert "1.00 million" in result.text_en
        assert "50.00 billion" in result.text_en

    @pytest.mark.asyncio
    async def test_literal_tags_preserved_through_translation(self, translator):
        with patch.object(translator, "_call_api", new_callable=AsyncMock) as mock_api:
            mock_api.return_value = "The ratio was <<LIT_001>> as of <<LIT_002>>."
            result = await translator.translate_async("截至2025/9/30，比例为10.94%。")

        assert "2025/9/30" in result.text_en
        assert "10.94%" in result.text_en

    @pytest.mark.asyncio
    async def test_spaced_year_literals_preserved_through_translation(self, translator):
        with patch.object(translator, "_call_api", new_callable=AsyncMock) as mock_api:
            mock_api.return_value = (
                "From <<LIT_001>> to <<LIT_002>>, cumulative R&D expenses were <<NUM_001>>."
            )
            result = await translator.translate_async(
                "2022 年至2024 年，公司研发费用累计金额14,995.35万元"
            )

        assert "2022" in result.text_en
        assert "2024" in result.text_en
        assert "RMB 149.95 million" in result.text_en

    @pytest.mark.asyncio
    async def test_year_only_and_fiscal_year_literals_normalize_cleanly(self, translator):
        with patch.object(translator, "_call_api", new_callable=AsyncMock) as mock_api:
            mock_api.return_value = "As of <<LIT_001>>, FY comparison: <<LIT_002>>."
            result = await translator.translate_async("截至2024 年，比较期间为2023 年度。")

        assert "2024" in result.text_en
        assert "FY 2023" in result.text_en

    @pytest.mark.asyncio
    async def test_spaced_full_date_literal_is_preserved(self, translator):
        with patch.object(translator, "_call_api", new_callable=AsyncMock) as mock_api:
            mock_api.return_value = "Signed on <<LIT_001>>."
            result = await translator.translate_async("协议签署于2024 年 9 月 26 日。")

        assert "2024-09-26" in result.text_en

    @pytest.mark.asyncio
    async def test_enumerated_clause_year_prefixes_are_restored(self, translator):
        source = (
            "（ 1 ） 2025 年 6 月股权增资：新增投资人；"
            "（ 2 ） 2025 年股权激励计划扩容：上海宇翼认购新增股份。"
        )
        with patch.object(translator, "_call_api", new_callable=AsyncMock) as mock_api:
            mock_api.return_value = (
                "(1) Equity capital increase: new investors participated; "
                "(2) Expansion of the equity incentive plan: "
                "Shanghai Yuyi subscribed to new shares."
            )
            result = await translator.translate_async(source)

        assert "(1) 2025-06 Equity capital increase" in result.text_en
        assert "(2) 2025 Expansion of the equity incentive plan" in result.text_en

    @pytest.mark.asyncio
    async def test_batch_translation(self, translator):
        with patch.object(translator, "_call_api", new_callable=AsyncMock) as mock_api:
            mock_api.return_value = "Translated text."
            results = await translator.translate_batch(["段落一", "段落二", "段落三"])

        assert len(results) == 3
        assert all(isinstance(r, TranslationResult) for r in results)
        assert mock_api.call_count == 3

    @pytest.mark.asyncio
    async def test_call_api_retries_transient_read_error(self, translator):
        request = httpx.Request("POST", "https://api.deepinfra.com")
        response = httpx.Response(
            200,
            request=request,
            json={"choices": [{"message": {"content": "Translated text."}}]},
        )
        client = AsyncMock()
        client.post.side_effect = [httpx.ReadError("boom"), response]

        with patch.object(translator, "_get_client", new_callable=AsyncMock) as mock_get_client:
            mock_get_client.return_value = client
            text = await translator._call_api("测试", translator.build_system_prompt())

        assert text == "Translated text."
        assert client.post.await_count == 2

    @pytest.mark.asyncio
    async def test_meta_commentary_is_stripped(self, translator):
        with patch.object(translator, "_call_api", new_callable=AsyncMock) as mock_api:
            mock_api.return_value = (
                "No translation needed. This appears to be a section number or identifier."
            )
            result = await translator.translate_async("1-1-17")

        assert result.text_en == "1-1-17"

    @pytest.mark.asyncio
    async def test_legitimate_note_translation_is_preserved(self, translator):
        with patch.object(translator, "_call_api", new_callable=AsyncMock) as mock_api:
            mock_api.return_value = (
                "Note: The key performance parameters of the company's products vary "
                "across different scenarios and model configurations."
            )
            result = await translator.translate_async(
                "注：公司产品的关键性能参数在不同场景、不同型号参数配置中有所差异。"
            )

        assert result.text_en.startswith("Note:")
        assert "model configurations" in result.text_en

    @pytest.mark.asyncio
    async def test_invented_placeholders_trigger_retry(self, translator):
        with patch.object(translator, "_call_api", new_callable=AsyncMock) as mock_api:
            mock_api.side_effect = [
                "截至<<NUM_YEAR>>，营业收入为<<NUM_001>>。",
                "As of 2025, revenue was <<NUM_001>>.",
            ]
            result = await translator.translate_async("营业收入为100万元")

        assert "RMB 1.00 million" in result.text_en
        assert mock_api.await_count == 2

    @pytest.mark.asyncio
    async def test_residual_chinese_output_triggers_english_retry(self, translator):
        with patch.object(translator, "_call_api", new_callable=AsyncMock) as mock_api:
            mock_api.side_effect = [
                "## **4** 、发行人技术实力与衡量核心竞争力的关键业务数据、指标",
                (
                    "## **4**. Issuer Technical Strength and Key Business Data and "
                    "Metrics for Evaluating Core Competitiveness"
                ),
            ]
            result = await translator.translate_async(
                "## **4** 、发行人技术实力与衡量核心竞争力的关键业务数据、指标"
            )

        assert "Issuer Technical Strength" in result.text_en
        assert mock_api.await_count == 2

    @pytest.mark.asyncio
    async def test_invented_markdown_artifacts_trigger_retry(self, translator):
        source = "型号 AlienGo 主要参数 站立尺寸：65×31×60cm 核心特点 产品布局紧凑"
        with patch.object(translator, "_call_api", new_callable=AsyncMock) as mock_api:
            mock_api.side_effect = [
                "| Model | Product Image |\n|---|---|\n| AlienGo | ![AlienGo](image_url) |",
                (
                    "Model AlienGo. Key parameter: standing dimensions 65×31×60cm. "
                    "Core feature: compact layout."
                ),
            ]
            result = await translator.translate_async(source)

        assert "image_url" not in result.text_en
        assert "|" not in result.text_en
        assert mock_api.await_count == 2

    @pytest.mark.asyncio
    async def test_pipe_separated_pseudo_table_triggers_retry(self, translator):
        source = "型号 AlienGo 主要参数 站立尺寸：65×31×60cm 核心特点 产品布局紧凑"
        with patch.object(translator, "_call_api", new_callable=AsyncMock) as mock_api:
            mock_api.side_effect = [
                "Model | Product Image | Key Parameters | Core Features\n"
                "--- | --- | --- | ---\n"
                "AlienGo | | Standing dimensions 65×31×60cm | Compact layout",
                "Model AlienGo. Standing dimensions 65×31×60cm. Core feature: compact layout.",
            ]
            result = await translator.translate_async(source)

        assert "|" not in result.text_en
        assert mock_api.await_count == 2

    @pytest.mark.asyncio
    async def test_pipe_rich_non_markdown_layout_triggers_retry(self, translator):
        source = "型号 AlienGo 主要参数 站立尺寸：65×31×60cm 核心特点 产品布局紧凑"
        with patch.object(translator, "_call_api", new_callable=AsyncMock) as mock_api:
            mock_api.side_effect = [
                "Model | Product Image | Key Parameters | Core Features | Compact layout",
                "Model AlienGo. Standing dimensions 65×31×60cm. Core feature: compact layout.",
            ]
            result = await translator.translate_async(source)

        assert "|" not in result.text_en
        assert mock_api.await_count == 2

    def test_build_table_cell_prompt(self, translator):
        prompt = translator.build_table_cell_prompt(strict=True)
        assert "short markdown table cell" in prompt
        assert "concise English label" in prompt


class TestSectionRouter:
    @pytest.fixture
    def router(self, translator):
        return SectionRouter(translator)

    def test_strategy_names(self, router):
        assert router.get_strategy_name("ipo_declarations") == "template_cache"
        assert router.get_strategy_name("ipo_s10_risk_factors") == "specialized"
        assert router.get_strategy_name("ipo_s08_financial_info") == "specialized"
        assert router.get_strategy_name("unknown_section") == "standard"

    @pytest.mark.asyncio
    async def test_translate_section_calls_batch(self, router, translator):
        with patch.object(translator, "translate_batch", new_callable=AsyncMock) as mock_batch:
            mock_batch.return_value = [
                TranslationResult(text_zh="a", text_en="A", provider="test"),
                TranslationResult(text_zh="b", text_en="B", provider="test"),
            ]
            results = await router.translate_section("ipo_s10_risk_factors", ["a", "b"])

        assert len(results) == 2
        mock_batch.assert_called_once()
        call_kwargs = mock_batch.call_args
        assert "system_prompt" in call_kwargs.kwargs
        assert "legal precision" in call_kwargs.kwargs["system_prompt"].lower()
