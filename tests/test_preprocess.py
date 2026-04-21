"""Tests for SSE translation preprocessing."""

from edgarpack.china.translate.preprocess import preprocess_paragraphs


def test_drops_page_marker():
    [decision] = preprocess_paragraphs(["1-1-17"])
    assert decision.action == "drop"


def test_drops_repeated_headers():
    decisions = preprocess_paragraphs(
        ["宇树科技股份有限公司", "招股说明书", "宇树科技股份有限公司 招股说明书"]
    )
    assert all(decision.action == "drop" for decision in decisions)


def test_drops_pure_ocr_garbage():
    [decision] = preprocess_paragraphs(["BROF= ATi+4--- OneSF5 EM: EREM"])
    assert decision.action == "drop"


def test_strips_mixed_ocr_noise_but_keeps_chinese():
    [decision] = preprocess_paragraphs(
        ["本次发行股票拟在科创板上市 RRARATRRWER ORE, BEMRADRAAU RRAK 投资者应充分了解风险。"]
    )
    assert decision.action == "translate"
    assert "RRARATRRWER" not in decision.cleaned
    assert "投资者应充分了解风险" in decision.cleaned


def test_short_non_chinese_passthrough():
    [decision] = preprocess_paragraphs(["AGI"])
    assert decision.action == "passthrough"
    assert decision.cleaned == "AGI"


def test_strips_inline_page_artifacts_from_mixed_paragraph():
    [decision] = preprocess_paragraphs(
        ["宇树科技股份有限公司 招股说明书 型号 B2 ~~D2~~ 最高防护等级： IP68 1-1-95 ~~|~~"]
    )
    assert decision.action == "translate"
    assert "宇树科技股份有限公司" not in decision.cleaned
    assert "招股说明书" not in decision.cleaned
    assert "1-1-95" not in decision.cleaned
    assert "~~D2~~" not in decision.cleaned
    assert "~~|~~" not in decision.cleaned
    assert "型号 B2" in decision.cleaned


def test_strips_inline_page_artifacts_inside_markdown_table_cells():
    [decision] = preprocess_paragraphs(["|型号<br>~~a~~|产品图片<br>~~ee~~|主要参数|<br>1-1-95|"])
    assert decision.action == "translate"
    assert "~~a~~" not in decision.cleaned
    assert "~~ee~~" not in decision.cleaned
    assert "1-1-95" not in decision.cleaned
