"""Tests for Chinese number/unit tagging and conversion."""

from edgarpack.china.translate.numbers import (
    NumberTag,
    convert_number,
    restore_numbers,
    tag_numbers,
)


class TestConvertNumber:
    def test_wan_to_million(self):
        result = convert_number("1234.56", "万", "元")
        assert "12.35 million" in result
        assert result.startswith("RMB")

    def test_yi_to_hundred_million(self):
        result = convert_number("5.23", "亿", "元")
        assert "523.00 million" in result

    def test_wanyi_to_trillion(self):
        result = convert_number("1.5", "万亿", "元")
        assert "1.50 trillion" in result

    def test_negative_number(self):
        result = convert_number("100", "万", "元", negative=True)
        assert "-" in result

    def test_bare_number_no_unit(self):
        result = convert_number("42", "", "")
        assert result == "42"

    def test_percentage(self):
        result = convert_number("15.3", "", "%")
        assert "15.30%" in result

    def test_percentage_points(self):
        result = convert_number("2.5", "", "百分点")
        assert "percentage points" in result

    def test_shares(self):
        result = convert_number("5000", "万", "股")
        assert "50.00 million" in result
        assert "shares" in result

    def test_usd_currency(self):
        result = convert_number("100", "万", "美元")
        assert "USD" in result

    def test_large_billion(self):
        result = convert_number("50", "亿", "元")
        assert "5.00 billion" in result

    def test_commas_in_digits(self):
        result = convert_number("1,234.56", "万", "元")
        assert "12.35 million" in result


class TestTagNumbers:
    def test_simple_wan(self):
        text = "收入为1234.56万元"
        tagged, tags = tag_numbers(text)
        assert len(tags) == 1
        assert "<<NUM_001>>" in tagged
        assert tags[0].unit == "万"
        assert tags[0].currency == "元"

    def test_multiple_numbers(self):
        text = "收入为100万元，利润为50亿元"
        tagged, tags = tag_numbers(text)
        assert len(tags) == 2
        assert "<<NUM_001>>" in tagged
        assert "<<NUM_002>>" in tagged

    def test_bare_number_not_tagged(self):
        text = "共有100名员工"
        tagged, tags = tag_numbers(text)
        assert len(tags) == 0
        assert tagged == text

    def test_preserves_surrounding_text(self):
        text = "本期营业收入为500万元，同比增长20%。"
        tagged, tags = tag_numbers(text)
        assert "本期营业收入为" in tagged
        assert "，同比增长" in tagged

    def test_negative_number(self):
        text = "亏损-100万元"
        tagged, tags = tag_numbers(text)
        assert len(tags) == 1
        assert tags[0].value < 0

    def test_wanyi(self):
        text = "市场规模达到1.5万亿元"
        tagged, tags = tag_numbers(text)
        assert len(tags) == 1
        assert tags[0].unit == "万亿"
        assert tags[0].value == 1_500_000_000_000

    def test_br_between_digits_and_unit(self):
        text = "营业收入为12,291.95<br>万元"
        tagged, tags = tag_numbers(text)
        assert len(tags) == 1
        assert "<<NUM_001>>" in tagged


class TestRestoreNumbers:
    def test_restore_single(self):
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
        result = restore_numbers("Revenue was <<NUM_001>>.", tags)
        assert result == "Revenue was RMB 1.00 million."

    def test_restore_multiple(self):
        tags = [
            NumberTag(
                placeholder="<<NUM_001>>",
                original="100万元",
                value=1_000_000,
                unit="万",
                currency="元",
                converted="RMB 1.00 million",
            ),
            NumberTag(
                placeholder="<<NUM_002>>",
                original="50亿元",
                value=5_000_000_000,
                unit="亿",
                currency="元",
                converted="RMB 5.00 billion",
            ),
        ]
        result = restore_numbers("A: <<NUM_001>>, B: <<NUM_002>>", tags)
        assert "RMB 1.00 million" in result
        assert "RMB 5.00 billion" in result

    def test_no_tags_passthrough(self):
        assert restore_numbers("Hello world", []) == "Hello world"


class TestRoundTrip:
    def test_tag_then_restore(self):
        text = "公司实现营业收入1,234.56万元，净利润200亿元。"
        tagged, tags = tag_numbers(text)
        restored = restore_numbers(tagged, tags)
        assert "12.35 million" in restored
        assert "20.00 billion" in restored
