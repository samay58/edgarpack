"""Tests for FinancialGlossary loader and prompt formatter."""

import json
import tempfile
from pathlib import Path

from edgarpack.china.translate.glossary import FinancialGlossary


def test_load_default_glossary():
    g = FinancialGlossary()
    assert len(g) > 100
    assert g.version == "1.0.0"


def test_lookup_known_term():
    g = FinancialGlossary()
    assert g.lookup("净利润") == "Net Income"
    assert g.lookup("资产负债表") == "Balance Sheet"
    assert g.lookup("中国证监会") == "CSRC"


def test_lookup_unknown_returns_none():
    g = FinancialGlossary()
    assert g.lookup("不存在的词") is None


def test_overlay_overrides_base():
    g = FinancialGlossary(overlay={"净利润": "Net Profit (Custom)"})
    assert g.lookup("净利润") == "Net Profit (Custom)"


def test_overlay_adds_new_terms():
    g = FinancialGlossary(overlay={"宇树科技": "Unitree Robotics"})
    assert g.lookup("宇树科技") == "Unitree Robotics"
    assert g.lookup("净利润") == "Net Income"


def test_format_for_prompt_has_table_header():
    g = FinancialGlossary()
    prompt = g.format_for_prompt(max_terms=10)
    lines = prompt.splitlines()
    assert lines[0] == "Chinese | English"
    assert lines[1] == "--- | ---"
    assert len(lines) == 12  # header + separator + 10 terms


def test_format_for_prompt_prioritizes_longer_terms():
    g = FinancialGlossary()
    prompt = g.format_for_prompt(max_terms=5)
    lines = prompt.splitlines()[2:]  # skip header
    zh_terms = [line.split(" | ")[0] for line in lines]
    lengths = [len(t) for t in zh_terms]
    assert lengths == sorted(lengths, reverse=True)


def test_custom_glossary_path():
    data = {"version": "test", "terms": {"测试": "Test"}}
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(data, f)
        f.flush()
        g = FinancialGlossary(glossary_path=Path(f.name))
    assert len(g) == 1
    assert g.lookup("测试") == "Test"
    assert g.version == "test"


def test_terms_returns_copy():
    g = FinancialGlossary()
    terms = g.terms
    terms["新词"] = "New Term"
    assert g.lookup("新词") is None
