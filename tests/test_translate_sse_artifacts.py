from __future__ import annotations

import json
from argparse import Namespace
from types import SimpleNamespace


def test_translate_sse_writes_full_artifact_and_quality_metadata(
    tmp_path,
    monkeypatch,
):
    from edgarpack import cli
    from edgarpack.china.translate.provider import TranslationResult

    pack_dir = tmp_path / "packs" / "sse" / "688696" / "688696_2025-04-22"
    sections_dir = pack_dir / "sections"
    sections_dir.mkdir(parents=True)
    (pack_dir / "manifest.json").write_text(
        json.dumps({"filing": {"stock_code": "688696"}}),
        encoding="utf-8",
    )
    (sections_dir / "annual_s02_company_profile_key_financials.md").write_text(
        "营业收入 123\n\n| 项目 | 2024 |\n| --- | --- |\n| 营业收入 | 123 |\n",
        encoding="utf-8",
    )

    class FakeTranslator:
        provider = "fake"

        def __init__(self, **_kwargs):
            pass

        async def close(self):
            pass

    class FakeRouter:
        def __init__(self, _translator):
            pass

        async def translate_section(self, _section_id, texts, strict=False):
            return [
                TranslationResult(
                    text_zh=text,
                    text_en=text.replace("营业收入", "Revenue").replace("项目", "Item"),
                    provider="fake",
                )
                for text in texts
            ]

    class FakeCache:
        namespace = None

        def __init__(self, **_kwargs):
            type(self).namespace = _kwargs.get("namespace")
            pass

        def get(self, _text):
            return None

        def put(self, _result):
            pass

        def close(self):
            pass

    def fake_validate(**_kwargs):
        return SimpleNamespace(
            has_errors=False,
            issues=[SimpleNamespace(severity="warning", message="fixture warning")],
        )

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
        Namespace(pack=pack_dir, model="fixture-model", force=True),
    )

    assert rc == 0
    assert (pack_dir / "filing.full.en.md").exists()
    assert (sections_dir / "annual_s02_company_profile_key_financials.en.md").exists()
    full_en = (pack_dir / "filing.full.en.md").read_text(encoding="utf-8")
    assert "Revenue 123" in full_en
    manifest = json.loads((pack_dir / "manifest.json").read_text(encoding="utf-8"))
    translation = manifest["translation"]
    assert translation["provider"] == "fake"
    assert translation["model"] == "fixture-model"
    assert translation["failed_sections"] == []
    assert translation["full_filing_written"] is True
    assert translation["validation_warning_count"] > 0
    assert translation["validation_error_count"] == 0
    assert FakeCache.namespace == "sse-translate-v10:fake:prompt-v5/router-v15/validator-v5"


def test_translate_sse_missing_deepinfra_key_is_actionable(
    tmp_path,
    monkeypatch,
    capsys,
):
    from edgarpack import cli

    monkeypatch.delenv("EDGARPACK_DEEPINFRA_KEY", raising=False)
    monkeypatch.delenv("DEEPINFRA_API_KEY", raising=False)

    pack_dir = tmp_path / "packs" / "sse" / "688696" / "688696_2025-04-22"
    sections_dir = pack_dir / "sections"
    sections_dir.mkdir(parents=True)
    (pack_dir / "manifest.json").write_text(
        json.dumps({"filing": {"stock_code": "688696"}}),
        encoding="utf-8",
    )
    (sections_dir / "annual_s02_company_profile_key_financials.md").write_text(
        "营业收入 123\n",
        encoding="utf-8",
    )

    rc = cli._cmd_translate_sse(
        Namespace(pack=pack_dir, model="fixture-model", force=True),
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert "EDGARPACK_DEEPINFRA_KEY" in captured.err
    assert "Bearer" not in captured.err


def test_translate_sse_writes_failure_artifact(
    tmp_path,
    monkeypatch,
    capsys,
):
    from edgarpack import cli
    from edgarpack.china.translate.provider import TranslationResult

    pack_dir = tmp_path / "packs" / "sse" / "688696" / "688696_2025-04-22"
    sections_dir = pack_dir / "sections"
    sections_dir.mkdir(parents=True)
    (pack_dir / "manifest.json").write_text(
        json.dumps({"filing": {"stock_code": "688696"}}),
        encoding="utf-8",
    )
    (sections_dir / "annual_s03_mda.md").write_text(
        "公司持续深化技术创新。\n",
        encoding="utf-8",
    )

    class FakeTranslator:
        provider = "fake"

        def __init__(self, **_kwargs):
            pass

        async def close(self):
            pass

    class FakeRouter:
        def __init__(self, _translator):
            pass

        async def translate_section(self, _section_id, texts, strict=False):
            return [
                TranslationResult(
                    text_zh=text,
                    text_en="The Company 持续深化 technological innovation.",
                    provider="fake",
                )
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

    rc = cli._cmd_translate_sse(
        Namespace(pack=pack_dir, model="fixture-model", force=True),
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert "translation.failures.json" in captured.out
    failure_path = pack_dir / "translation.failures.json"
    assert failure_path.exists()
    failures = json.loads(failure_path.read_text(encoding="utf-8"))
    assert failures[0]["section_id"] == "annual_s03_mda"
    assert failures[0]["paragraph_index"] == 0
    assert "公司持续深化" in failures[0]["source"]
    assert "持续深化" in failures[0]["target"]
    assert failures[0]["issues"][0]["validator"] == "residual_han"
    manifest = json.loads((pack_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["translation"]["failure_artifact"] == "translation.failures.json"
