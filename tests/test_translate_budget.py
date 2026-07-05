from __future__ import annotations

import json
from argparse import Namespace
from types import SimpleNamespace


def test_translate_sse_stops_cleanly_when_budget_exceeded(tmp_path, monkeypatch, capsys):
    from edgarpack import cli
    from edgarpack.china.translate.provider import TranslationResult

    pack_dir = tmp_path / "packs" / "sse" / "688696" / "688696_2025-04-22"
    sections_dir = pack_dir / "sections"
    sections_dir.mkdir(parents=True)
    (pack_dir / "manifest.json").write_text(
        json.dumps({"filing": {"stock_code": "688696"}}),
        encoding="utf-8",
    )
    (sections_dir / "annual_s01_first.md").write_text(
        "第一部分业务描述内容测试。\n",
        encoding="utf-8",
    )
    (sections_dir / "annual_s02_second.md").write_text(
        "第二部分业务描述内容测试。\n",
        encoding="utf-8",
    )

    class FakeTranslator:
        provider = "fake"

        def __init__(self, **_kwargs):
            self.total_tokens_used = 0

        async def close(self):
            pass

    class FakeRouter:
        def __init__(self, translator):
            self._translator = translator

        async def translate_section(self, _section_id, texts, strict=False):
            self._translator.total_tokens_used += 50 * len(texts)
            return [
                TranslationResult(text_zh=text, text_en=f"EN: {text}", provider="fake")
                for text in texts
            ]

    class FakeCache:
        def __init__(self, **_kwargs):
            pass

        def get(self, _text):
            return None

        def put(self, _result):
            pass

        def close(self):
            pass

    def fake_validate(**_kwargs):
        return SimpleNamespace(has_errors=False, issues=[])

    monkeypatch.setattr(
        "edgarpack.china.translate.deepinfra.DeepInfraTranslator",
        FakeTranslator,
    )
    monkeypatch.setattr("edgarpack.china.translate.router.SectionRouter", FakeRouter)
    monkeypatch.setattr("edgarpack.china.translate.cache.TranslationCache", FakeCache)
    monkeypatch.setattr(
        "edgarpack.china.translate.glossary.FinancialGlossary.with_company_overlay",
        lambda *_args, **_kwargs: SimpleNamespace(terms={}, version="fixture"),
    )
    monkeypatch.setattr(
        "edgarpack.china.translate.validators.validate_translation",
        fake_validate,
    )

    rc = cli._cmd_translate_sse(
        Namespace(
            pack=pack_dir,
            model="fixture-model",
            force=True,
            budget_tokens=50,
        ),
    )

    captured = capsys.readouterr()

    # The first section fully completes before the budget trips, so it is
    # not clobbered; the second section is never attempted this run.
    assert rc == 1
    assert (sections_dir / "annual_s01_first.en.md").exists()
    assert not (sections_dir / "annual_s02_second.en.md").exists()
    assert not (pack_dir / "filing.full.en.md").exists()
    assert "Budget exhausted" in captured.out

    manifest = json.loads((pack_dir / "manifest.json").read_text(encoding="utf-8"))
    translation = manifest["translation"]
    assert translation["failed_sections"] == ["annual_s02_second"]
    assert translation["full_filing_written"] is False

    # A --force-free resume must not report "already translated" while a
    # section remains pending; the same failed_sections bookkeeping failed
    # sections already use for resume is what drives this.
    rc_resume = cli._cmd_translate_sse(
        Namespace(pack=pack_dir, model="fixture-model", force=False, budget_tokens=0),
    )
    resumed = capsys.readouterr()
    assert "Pack already translated" not in resumed.err
    assert rc_resume == 0
    assert (sections_dir / "annual_s02_second.en.md").exists()
    assert (pack_dir / "filing.full.en.md").exists()


def test_budget_tokens_zero_is_unlimited(tmp_path, monkeypatch):
    from edgarpack import cli
    from edgarpack.china.translate.provider import TranslationResult

    pack_dir = tmp_path / "packs" / "sse" / "688696" / "688696_2025-04-22"
    sections_dir = pack_dir / "sections"
    sections_dir.mkdir(parents=True)
    (pack_dir / "manifest.json").write_text(
        json.dumps({"filing": {"stock_code": "688696"}}),
        encoding="utf-8",
    )
    (sections_dir / "annual_s01_first.md").write_text(
        "第一部分业务描述内容测试。\n",
        encoding="utf-8",
    )

    class FakeTranslator:
        provider = "fake"

        def __init__(self, **_kwargs):
            self.total_tokens_used = 10_000_000

        async def close(self):
            pass

    class FakeRouter:
        def __init__(self, translator):
            self._translator = translator

        async def translate_section(self, _section_id, texts, strict=False):
            return [
                TranslationResult(text_zh=text, text_en=f"EN: {text}", provider="fake")
                for text in texts
            ]

    class FakeCache:
        def __init__(self, **_kwargs):
            pass

        def get(self, _text):
            return None

        def put(self, _result):
            pass

        def close(self):
            pass

    def fake_validate(**_kwargs):
        return SimpleNamespace(has_errors=False, issues=[])

    monkeypatch.setattr(
        "edgarpack.china.translate.deepinfra.DeepInfraTranslator",
        FakeTranslator,
    )
    monkeypatch.setattr("edgarpack.china.translate.router.SectionRouter", FakeRouter)
    monkeypatch.setattr("edgarpack.china.translate.cache.TranslationCache", FakeCache)
    monkeypatch.setattr(
        "edgarpack.china.translate.glossary.FinancialGlossary.with_company_overlay",
        lambda *_args, **_kwargs: SimpleNamespace(terms={}, version="fixture"),
    )
    monkeypatch.setattr(
        "edgarpack.china.translate.validators.validate_translation",
        fake_validate,
    )

    # budget_tokens=0 (the argparse default) must mean unlimited, even though
    # the translator already reports a huge running total.
    rc = cli._cmd_translate_sse(
        Namespace(pack=pack_dir, model="fixture-model", force=True, budget_tokens=0),
    )

    assert rc == 0
    assert (sections_dir / "annual_s01_first.en.md").exists()
    assert (pack_dir / "filing.full.en.md").exists()
