"""Tests for post-translation quality validators."""

from edgarpack.china.translate.numbers import NumberTag
from edgarpack.china.translate.validators import (
    CompletionValidator,
    GlossaryConsistencyValidator,
    LiteralTokenPreservationValidator,
    MarkdownTableStructureValidator,
    NumberPreservationValidator,
    ResidualHanValidator,
    RomanizedArtifactValidator,
    validate_translation,
)


class TestNumberPreservationValidator:
    def test_all_numbers_present_passes(self):
        tags = [
            NumberTag(
                placeholder="<<NUM_001>>",
                original="100万元",
                value=1_000_000,
                unit="万",
                currency="元",
                converted="RMB 1.00 million",
            )
        ]
        v = NumberPreservationValidator()
        issues = v.validate("Revenue was RMB 1.00 million.", tags)
        assert issues == []

    def test_missing_number_flags(self):
        tags = [
            NumberTag(
                placeholder="<<NUM_001>>",
                original="100万元",
                value=1_000_000,
                unit="万",
                currency="元",
                converted="RMB 1.00 million",
            )
        ]
        v = NumberPreservationValidator()
        issues = v.validate("Revenue was significant.", tags)
        assert len(issues) == 1
        assert "100万元" in issues[0].message

    def test_unreplaced_placeholder_flags(self):
        tags = [
            NumberTag(
                placeholder="<<NUM_001>>",
                original="100万元",
                value=1_000_000,
                unit="万",
                currency="元",
                converted="RMB 1.00 million",
            )
        ]
        v = NumberPreservationValidator()
        issues = v.validate("Revenue was <<NUM_001>>.", tags)
        assert len(issues) == 1
        assert "not restored" in issues[0].message


class TestGlossaryConsistencyValidator:
    def test_consistent_term_passes(self):
        v = GlossaryConsistencyValidator()
        issues = v.validate(
            "公司净利润增长",
            "The company's Net Income increased",
            {"净利润": "Net Income"},
        )
        assert issues == []

    def test_missing_term_flags(self):
        v = GlossaryConsistencyValidator()
        issues = v.validate(
            "公司净利润增长",
            "The company's profit grew",
            {"净利润": "Net Income"},
        )
        assert len(issues) == 1
        assert "Net Income" in issues[0].message

    def test_case_insensitive_match(self):
        v = GlossaryConsistencyValidator()
        issues = v.validate(
            "基本每股收益",
            "basic eps was 1.5",
            {"基本每股收益": "Basic EPS"},
        )
        assert issues == []


class TestCompletionValidator:
    def test_normal_ratio_passes(self):
        v = CompletionValidator()
        zh = "公司实现营业收入五百万元" * 3  # ~39 chars
        en = "The company achieved revenue of five million yuan" * 3  # ~150 chars
        issues = v.validate(zh, en)
        assert issues == []

    def test_empty_translation_flags(self):
        v = CompletionValidator()
        issues = v.validate("有内容的中文文本", "")
        assert len(issues) == 1
        assert "empty" in issues[0].message

    def test_too_short_flags(self):
        v = CompletionValidator()
        issues = v.validate("这是一段很长的中文文本需要翻译成英文" * 10, "Short.")
        assert len(issues) == 1
        assert "short" in issues[0].message
        assert issues[0].severity == "error"

    def test_empty_source_passes(self):
        v = CompletionValidator()
        issues = v.validate("", "")
        assert issues == []


class TestValidateTranslation:
    def test_all_pass(self):
        report = validate_translation(
            text_zh="公司营业收入",
            text_en="Company revenue increased",
        )
        assert report.passed

    def test_empty_translation_fails(self):
        report = validate_translation(
            text_zh="有内容的文本",
            text_en="",
        )
        assert not report.passed
        assert len(report.issues) == 1

    def test_combined_check_with_numbers(self):
        tags = [
            NumberTag(
                placeholder="<<NUM_001>>",
                original="100万元",
                value=1_000_000,
                unit="万",
                currency="元",
                converted="RMB 1.00 million",
            )
        ]
        report = validate_translation(
            text_zh="营业收入为100万元",
            text_en="Revenue was RMB 1.00 million.",
            number_tags=tags,
        )
        assert report.passed

    def test_derived_number_tags_allow_converted_amounts(self):
        report = validate_translation(
            text_zh="2022年至2024年，公司研发费用累计金额14,995.35万元，高于8,000万元",
            text_en=(
                "From 2022 to 2024, cumulative R&D expenses amounted to "
                "RMB 149.95 million, exceeding RMB 80.00 million."
            ),
        )
        assert report.passed

    def test_residual_han_fails_when_not_allowed(self):
        report = validate_translation(
            text_zh="项目",
            text_en="项目",
        )
        assert not report.passed
        assert any(issue.validator == "residual_han" for issue in report.issues)


class TestLiteralTokenPreservationValidator:
    def test_missing_date_token_flags(self):
        issues = LiteralTokenPreservationValidator().validate(
            "截至2025/9/30，营业收入为179,473.96万元",
            "Revenue increased materially.",
        )
        assert any("2025/9/30" in issue.message for issue in issues)

    def test_single_digit_marker_is_ignored(self):
        issues = LiteralTokenPreservationValidator().validate(
            "截至2025年1月，公司第1次增资完成",
            "As of 2025, the capital increase was completed.",
        )
        assert not any("Literal token 1" in issue.message for issue in issues)

    def test_trailing_punctuation_does_not_break_match(self):
        issues = LiteralTokenPreservationValidator().validate(
            "截至2025年6月，公司持股比例为10.94%。",
            "As of June 2025, the shareholding ratio was 10.94%.",
        )
        assert issues == []

    def test_chinese_date_matches_iso_date(self):
        issues = LiteralTokenPreservationValidator().validate(
            "成立日期为2016年8月26日",
            "Date of establishment: 2016-08-26.",
        )
        assert issues == []

    def test_spaced_chinese_date_matches_iso_date(self):
        issues = LiteralTokenPreservationValidator().validate(
            "股权转让协议签署于2024 年 9 月 26 日",
            "The equity transfer agreement was signed on 2024-09-26.",
        )
        assert issues == []

    def test_spaced_chinese_date_matches_english_full_date(self):
        issues = LiteralTokenPreservationValidator().validate(
            "股权转让协议签署于2024 年 9 月 26 日",
            "The equity transfer agreement was signed on September 26, 2024.",
        )
        assert issues == []

    def test_split_table_date_matches_repaired_iso_date(self):
        issues = LiteralTokenPreservationValidator().validate(
            "|截至2025年1|2月31日，宁波红杉基本情况如下：|",
            "|As of 2025-12-31, Ningbo Hongshan's Basic Information:|",
        )
        assert issues == []

    def test_bare_year_is_satisfied_by_year_month_token(self):
        issues = LiteralTokenPreservationValidator().validate(
            "2026年第一次临时股东会于2026年3月召开",
            "The first extraordinary general meeting of shareholders was held in 2026-03.",
        )
        assert issues == []

    def test_chinese_year_month_matches_iso_year_month(self):
        issues = LiteralTokenPreservationValidator().validate(
            "根据（2024年4月修订）规定",
            "According to the revised rules (2024-04).",
        )
        assert issues == []

    def test_fullwidth_ratio_matches_ascii_ratio(self):
        issues = LiteralTokenPreservationValidator().validate(
            "按照1：0.0019的比例折为股本",
            "Converted into share capital at a ratio of 1:0.0019.",
        )
        assert issues == []

    def test_fullwidth_ratio_with_space_matches_ascii_ratio(self):
        issues = LiteralTokenPreservationValidator().validate(
            "按照1： 0.0019的比例折为股本",
            "Converted into share capital at a ratio of 1:0.0019.",
        )
        assert issues == []

    def test_percentages_after_numbered_names_are_not_lost(self):
        issues = LiteralTokenPreservationValidator().validate(
            "经纬壹号：5.5674%；经乾二号：7.1075%",
            "Matrix No. 1: 5.5674%; Jingqian No. 2: 7.1075%",
        )
        assert issues == []

    def test_comma_number_matches_plain_number(self):
        issues = LiteralTokenPreservationValidator().validate(
            "H1先后夺得1,500米跑第一名",
            "H1 won first place in the 1500-meter race.",
        )
        assert issues == []

    def test_hyphenated_numeric_identifier_matches_split_source_tokens(self):
        issues = LiteralTokenPreservationValidator().validate(
            "备案号为浙ICP备17044557号-7",
            "Filing number: Zhejiang ICP No. 17044557-7.",
        )
        assert issues == []


class TestMarkdownTableStructureValidator:
    def test_literal_cells_must_match(self):
        issues = MarkdownTableStructureValidator().validate(
            "|项目|2025/9/30|\n|---|---|\n|货币资金|179,473.96|",
            "|Item|2024/12/31|\n|---|---|\n|Cash and Cash Equivalents|179,473.96|",
        )
        assert any("Literal table cell changed" in issue.message for issue in issues)


class TestResidualHanValidator:
    def test_han_is_rejected(self):
        issues = ResidualHanValidator().validate("项目")
        assert len(issues) == 1


class TestRomanizedArtifactValidator:
    def test_pinyin_like_token_is_rejected(self):
        issues = RomanizedArtifactValidator().validate("zai_yan")
        assert len(issues) == 1
