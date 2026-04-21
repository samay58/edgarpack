"""Tests for paragraph-level translation cache."""

import pytest

from edgarpack.china.translate.cache import TranslationCache, _hash_text, _normalize
from edgarpack.china.translate.provider import TranslationResult


@pytest.fixture
def cache(tmp_path):
    db = tmp_path / "test_cache.db"
    c = TranslationCache(db_path=db)
    yield c
    c.close()


class TestNormalize:
    def test_strips_markdown(self):
        assert _normalize("## **Bold** _italic_") == "Bold italic"

    def test_collapses_whitespace(self):
        assert _normalize("hello   \n  world") == "hello world"

    def test_strips_table_pipes(self):
        assert _normalize("| col1 | col2 |") == "col1 col2"


class TestHashStability:
    def test_same_text_same_hash(self):
        a = _hash_text("净利润为100万元")
        b = _hash_text("净利润为100万元")
        assert a == b

    def test_whitespace_normalized(self):
        a = _hash_text("净利润  为100万元")
        b = _hash_text("净利润 为100万元")
        assert a == b

    def test_different_text_different_hash(self):
        a = _hash_text("净利润")
        b = _hash_text("营业收入")
        assert a != b

    def test_namespace_changes_hash(self):
        assert _hash_text("净利润", namespace="v1") != _hash_text("净利润", namespace="v2")


class TestTranslationCache:
    def test_miss_returns_none(self, cache):
        assert cache.get("不存在的文本") is None

    def test_put_then_get(self, cache):
        result = TranslationResult(
            text_zh="净利润为100万元",
            text_en="Net income was RMB 1.00 million",
            provider="test",
        )
        cache.put(result)
        cached = cache.get("净利润为100万元")
        assert cached is not None
        assert cached.text_en == "Net income was RMB 1.00 million"
        assert cached.provider == "test"

    def test_whitespace_variants_hit_same_entry(self, cache):
        result = TranslationResult(
            text_zh="净利润 为100万元",
            text_en="Net income was RMB 1.00 million",
            provider="test",
        )
        cache.put(result)
        # Extra whitespace should still hit
        cached = cache.get("净利润  为100万元")
        assert cached is not None

    def test_overwrite_on_same_key(self, cache):
        r1 = TranslationResult(text_zh="测试", text_en="Test v1", provider="p1")
        r2 = TranslationResult(text_zh="测试", text_en="Test v2", provider="p2")
        cache.put(r1)
        cache.put(r2)
        cached = cache.get("测试")
        assert cached.text_en == "Test v2"

    def test_stats(self, cache):
        assert cache.stats()["entries"] == 0
        cache.put(TranslationResult(text_zh="a", text_en="A", provider="t"))
        cache.put(TranslationResult(text_zh="b", text_en="B", provider="t"))
        assert cache.stats()["entries"] == 2

    def test_namespace_isolated_entries(self, tmp_path):
        db = tmp_path / "test_cache.db"
        cache_v1 = TranslationCache(db_path=db, namespace="v1")
        cache_v2 = TranslationCache(db_path=db, namespace="v2")
        try:
            cache_v1.put(TranslationResult(text_zh="测试", text_en="Test", provider="p"))
            assert cache_v1.get("测试") is not None
            assert cache_v2.get("测试") is None
        finally:
            cache_v1.close()
            cache_v2.close()
