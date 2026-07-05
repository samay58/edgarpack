"""SSE / China A-share translation pipeline orchestrator.

Owns the end-to-end zh->en translation run for a single pack: the
resume-by-default skip check, per-section paragraph translation with
cache/validation/retry, fail-closed section handling, an optional token
spend budget, and manifest bookkeeping. Extracted out of edgarpack.cli so
the CLI command stays a thin dispatcher (see docs/BACKLOG.md, "cli.py
decomposition").
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any


def resolve_budget_tokens(raw: Any) -> int | None:
    """Normalize a --budget-tokens value: 0, negative, or absent means unlimited."""
    if raw is None:
        return None
    value = int(raw)
    return value if value > 0 else None


def run_translate_sse(args: Any) -> int:
    pack_dir = Path(args.pack)
    if not pack_dir.exists():
        print(f"Error: pack directory not found: {pack_dir}", file=sys.stderr)
        return 2

    manifest_path = pack_dir / "manifest.json"
    if not manifest_path.exists():
        print(f"Error: no manifest.json in {pack_dir}", file=sys.stderr)
        return 2

    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))

    # Skip only fully translated packs; a previous run with failed sections
    # must resume by default (the translation cache absorbs the rework cost).
    previous_translation = manifest_data.get("translation")
    if not args.force and previous_translation and not previous_translation.get("failed_sections"):
        print("Pack already translated. Use --force to re-translate.", file=sys.stderr)
        return 0

    async def _run() -> int:
        from .cache import TranslationCache, provider_namespace
        from .deepinfra import (
            PROMPT_VERSION,
            DeepInfraConfigurationError,
            DeepInfraTranslator,
        )
        from .glossary import FinancialGlossary
        from .numbers import tag_numbers
        from .preprocess import preprocess_paragraphs
        from .router import ROUTER_VERSION, SectionRouter
        from .validators import (
            VALIDATOR_VERSION,
            GlossaryConsistencyValidator,
            validate_translation,
        )

        sections_dir = pack_dir / "sections"
        if not sections_dir.exists():
            print(f"Error: no sections/ directory in {pack_dir}", file=sys.stderr)
            return 1

        # Find Chinese section files (exclude .en.md)
        zh_files = sorted(f for f in sections_dir.glob("*.md") if not f.name.endswith(".en.md"))
        if not zh_files:
            print("No Chinese section files found", file=sys.stderr)
            return 1

        # Derive stock_code from pack path (packs/sse/{stock_code}/...)
        stock_code = manifest_data.get("filing", {}).get("stock_code", "")
        packs_dir = pack_dir.parent.parent.parent  # sse/{code}/{filing_id} -> packs
        max_concurrency = int(getattr(args, "concurrency", 5) or 5)
        if max_concurrency < 1:
            print("Error: --concurrency must be at least 1", file=sys.stderr)
            return 2
        batch_size = int(getattr(args, "batch_size", 25) or 25)
        if batch_size < 1:
            print("Error: --batch-size must be at least 1", file=sys.stderr)
            return 2
        budget_tokens = resolve_budget_tokens(getattr(args, "budget_tokens", None))

        glossary = FinancialGlossary.with_company_overlay(stock_code, packs_dir)
        try:
            translator = DeepInfraTranslator(
                glossary=glossary,
                model=args.model,
                max_concurrency=max_concurrency,
            )
        except DeepInfraConfigurationError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2
        router = SectionRouter(translator)
        strategy_fingerprint = (
            f"prompt-{PROMPT_VERSION}/router-{ROUTER_VERSION}/validator-{VALIDATOR_VERSION}"
        )
        cache = TranslationCache(
            namespace=provider_namespace(
                translator.provider,
                strategy_fingerprint=strategy_fingerprint,
            )
        )
        glossary_validator = GlossaryConsistencyValidator()

        cached_count = 0
        translated_count = 0
        validation_warning_count = 0
        validation_error_count = 0
        en_sections: list[str] = []
        failed_sections: list[str] = []
        translated_sections: list[str] = []
        failure_records: list[dict[str, Any]] = []
        recorded_failure_keys: set[tuple[str, int | None]] = set()
        budget_exceeded = False

        def _excerpt(text: str, limit: int = 220) -> str:
            compact = " ".join(text.split())
            if len(compact) <= limit:
                return compact
            return compact[: limit - 3] + "..."

        def _record_validation_failure(
            section_id: str,
            index: int,
            text_zh: str,
            text_en: str,
            report: Any,
        ) -> list[str]:
            key = (section_id, index)
            if key not in recorded_failure_keys:
                recorded_failure_keys.add(key)
                failure_records.append(
                    {
                        "section_id": section_id,
                        "paragraph_index": index,
                        "source": text_zh,
                        "target": text_en,
                        "source_excerpt": _excerpt(text_zh),
                        "target_excerpt": _excerpt(text_en),
                        "issues": [
                            {
                                "validator": issue.validator,
                                "message": issue.message,
                                "severity": issue.severity,
                            }
                            for issue in report.issues
                        ],
                    }
                )
            return [
                f"p{index}: {issue.message} "
                f"(source: {_excerpt(text_zh, 90)}; target: {_excerpt(text_en, 90)})"
                for issue in report.issues
                if issue.severity == "error"
            ]

        def _record_exception_failure(
            section_id: str,
            exc: Exception,
            batch_texts: list[str],
        ) -> None:
            key = (section_id, None)
            if key in recorded_failure_keys:
                return
            recorded_failure_keys.add(key)
            failure_records.append(
                {
                    "section_id": section_id,
                    "paragraph_index": None,
                    "source": "\n\n".join(batch_texts),
                    "target": "",
                    "source_excerpt": _excerpt("\n\n".join(batch_texts)),
                    "target_excerpt": "",
                    "issues": [
                        {
                            "validator": "translation_exception",
                            "message": f"{type(exc).__name__}: {exc}",
                            "severity": "error",
                        }
                    ],
                }
            )

        for zh_file in zh_files:
            section_id = zh_file.stem

            if budget_exceeded:
                if section_id not in failed_sections:
                    failed_sections.append(section_id)
                continue

            content = zh_file.read_text(encoding="utf-8")
            paragraphs = [p for p in content.split("\n\n") if p.strip()]
            decisions = preprocess_paragraphs(paragraphs)

            uncached_indices: list[int] = []
            uncached_texts: list[str] = []
            translation_sources: list[str | None] = [None] * len(decisions)
            para_results: list[str | None] = [None] * len(decisions)

            for i, decision in enumerate(decisions):
                if decision.action == "drop":
                    continue
                if decision.action == "passthrough":
                    para_results[i] = decision.cleaned
                    translation_sources[i] = "passthrough"
                    continue

                cached = cache.get(decision.cleaned)
                if cached is not None:
                    para_results[i] = cached.text_en
                    cached_count += 1
                    translation_sources[i] = "cache"
                else:
                    uncached_indices.append(i)
                    uncached_texts.append(decision.cleaned)

            def _validate(index: int, text_zh: str, text_en: str) -> Any:
                nonlocal validation_warning_count, validation_error_count
                _, number_tags = tag_numbers(text_zh)
                report = validate_translation(
                    text_zh=text_zh,
                    text_en=text_en,
                    number_tags=number_tags,
                    glossary_terms=glossary.terms,
                    glossary_validator=glossary_validator,
                    allow_han=False,
                    paragraph_index=index,
                )
                for issue in report.issues:
                    if issue.severity == "warning":
                        validation_warning_count += 1
                    elif issue.severity == "error":
                        validation_error_count += 1
                return report

            for i, decision in enumerate(decisions):
                cached_text = para_results[i]
                if translation_sources[i] != "cache" or cached_text is None:
                    continue
                report = _validate(i, decision.cleaned, cached_text)
                if report.has_errors:
                    uncached_indices.append(i)
                    uncached_texts.append(decision.cleaned)
                    para_results[i] = None
                    translation_sources[i] = None
                    cached_count -= 1

            print(
                f"  {section_id}: {len(paragraphs)} paragraphs "
                f"({len(uncached_texts)} uncached after preprocessing/cache)",
                flush=True,
            )

            section_failed = False
            section_error_messages: list[str] = []
            if uncached_texts:
                total_batches = (len(uncached_texts) + batch_size - 1) // batch_size
                for batch_number, batch_start in enumerate(
                    range(0, len(uncached_texts), batch_size),
                    1,
                ):
                    batch_indices = uncached_indices[batch_start : batch_start + batch_size]
                    batch_texts = uncached_texts[batch_start : batch_start + batch_size]
                    print(
                        f"    batch {batch_number}/{total_batches}: "
                        f"{len(batch_texts)} translation units",
                        flush=True,
                    )
                    try:
                        results = await router.translate_section(section_id, batch_texts)
                    except Exception as exc:
                        section_failed = True
                        section_error_messages.append(f"{type(exc).__name__}: {exc}")
                        _record_exception_failure(section_id, exc, batch_texts)
                        print(
                            f"  {section_id}: failed closed ({type(exc).__name__}: {exc})",
                            file=sys.stderr,
                        )
                        break

                    retry_indices: list[int] = []
                    retry_texts: list[str] = []
                    for idx, result in zip(batch_indices, results, strict=False):
                        report = _validate(idx, result.text_zh, result.text_en)
                        if report.has_errors:
                            retry_indices.append(idx)
                            retry_texts.append(result.text_zh)
                            continue
                        para_results[idx] = result.text_en
                        translation_sources[idx] = "translated"
                        cache.put(result)
                        translated_count += 1

                    if retry_texts:
                        try:
                            retry_results = await router.translate_section(
                                section_id,
                                retry_texts,
                                strict=True,
                            )
                        except Exception as exc:
                            section_failed = True
                            section_error_messages.append(f"{type(exc).__name__}: {exc}")
                            _record_exception_failure(section_id, exc, retry_texts)
                            print(
                                f"  {section_id}: failed closed ({type(exc).__name__}: {exc})",
                                file=sys.stderr,
                            )
                            break
                        for idx, result in zip(retry_indices, retry_results, strict=False):
                            report = _validate(idx, result.text_zh, result.text_en)
                            if report.has_errors:
                                section_failed = True
                                section_error_messages.extend(
                                    _record_validation_failure(
                                        section_id,
                                        idx,
                                        result.text_zh,
                                        result.text_en,
                                        report,
                                    )
                                )
                                break
                            para_results[idx] = result.text_en
                            translation_sources[idx] = "translated"
                            cache.put(result)
                            translated_count += 1
                    if section_failed:
                        break

                    if budget_tokens is not None and translator.total_tokens_used >= budget_tokens:
                        budget_exceeded = True
                        print(
                            f"  budget exhausted: {translator.total_tokens_used} tokens spent "
                            f"(limit {budget_tokens}); finishing this batch and stopping",
                            flush=True,
                        )
                        break

                    print(
                        f"    batch {batch_number}/{total_batches}: cached",
                        flush=True,
                    )

            if section_failed or any(
                translation_sources[i] is None and decisions[i].action == "translate"
                for i in range(len(decisions))
            ):
                for i, decision in enumerate(decisions):
                    if translation_sources[i] is not None or decision.action != "translate":
                        continue
                    if (section_id, i) in recorded_failure_keys:
                        continue
                    failure_records.append(
                        {
                            "section_id": section_id,
                            "paragraph_index": i,
                            "source": decision.cleaned,
                            "target": para_results[i] or "",
                            "source_excerpt": _excerpt(decision.cleaned),
                            "target_excerpt": _excerpt(para_results[i] or ""),
                            "issues": [
                                {
                                    "validator": "translation_missing",
                                    "message": "No valid translation was produced",
                                    "severity": "error",
                                }
                            ],
                        }
                    )
                    recorded_failure_keys.add((section_id, i))
                failed_sections.append(section_id)
                en_path = sections_dir / f"{section_id}.en.md"
                if en_path.exists():
                    en_path.unlink()
                print(f"  {section_id}: failed closed")
                for msg in section_error_messages[:3]:
                    print(f"    - {msg}")
                continue

            en_content = "\n\n".join(p for p in para_results if p)
            en_sections.append(en_content)
            en_path = sections_dir / f"{section_id}.en.md"
            en_path.write_text(en_content, encoding="utf-8")
            translated_sections.append(section_id)
            print(f"  {section_id}: wrote {en_path.name}", flush=True)

        # Write full English filing
        wrote_full_en = False
        if en_sections and not failed_sections:
            full_en = "\n\n---\n\n".join(en_sections)
            full_en_path = pack_dir / "filing.full.en.md"
            full_en_path.write_text(full_en, encoding="utf-8")
            wrote_full_en = True
        else:
            full_en_path = pack_dir / "filing.full.en.md"
            if full_en_path.exists():
                full_en_path.unlink()

        failure_artifact: str | None = None
        failure_path = pack_dir / "translation.failures.json"
        if failure_records:
            failure_artifact = "translation.failures.json"
            failure_path.write_text(
                json.dumps(failure_records, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            print(f"  wrote {failure_artifact}")
        elif failure_path.exists():
            failure_path.unlink()

        # Update manifest
        translation_metadata = {
            "provider": translator.provider,
            "model": args.model,
            "glossary_version": glossary.version,
            "strategy_fingerprint": strategy_fingerprint,
            "cached_paragraphs": cached_count,
            "translated_paragraphs": translated_count,
            "failed_sections": failed_sections,
            "translated_sections": translated_sections,
            "full_filing_written": wrote_full_en,
            "validation_warning_count": validation_warning_count,
            "validation_error_count": validation_error_count,
        }
        if failure_artifact is not None:
            translation_metadata["failure_artifact"] = failure_artifact
        manifest_data["translation"] = translation_metadata
        manifest_path.write_text(
            json.dumps(manifest_data, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        await translator.close()
        cache.close()
        print(f"\nTranslated: {translated_count} paragraphs, {cached_count} from cache")
        if budget_exceeded:
            print(
                f"Budget exhausted: spent {translator.total_tokens_used} tokens "
                f"(limit {budget_tokens}). Re-run the same command to resume "
                f"({len(failed_sections)} section(s) pending: {', '.join(failed_sections)})."
            )
        return 1 if failed_sections else 0

    return asyncio.run(_run())
