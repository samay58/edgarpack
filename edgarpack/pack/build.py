"""Core pack builder orchestrating the full pipeline."""

from __future__ import annotations

import asyncio
import json
import shutil
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from ..config import SEC_ARCHIVES_BASE
from ..parse.html_clean import clean_html
from ..parse.ixbrl_strip import strip_ixbrl
from ..parse.md_polish import polish
from ..parse.md_render import render_markdown
from ..parse.sectionize import sectionize
from ..parse.semantic_html import reduce_to_semantic
from ..parse.tokenize import count_tokens, has_tiktoken
from ..sec.archives import fetch_primary_filing_html
from ..sec.submissions import (
    get_filing_by_accession,
    get_latest_filing,
    is_registration_form,
    list_filings,
)
from ..sec.xbrl import fetch_xbrl_facts
from .assets import describe_asset, download_assets
from .chunks import generate_chunks, write_chunks_ndjson
from .llms_txt import generate_llms_txt, write_llms_txt
from .manifest import compute_sha256, create_manifest, write_manifest


class PackResult(BaseModel):
    """Result of building a pack."""

    model_config = {"arbitrary_types_allowed": True}

    output_dir: Path
    filing_meta: dict[str, Any]
    sections_count: int
    tokens_total: int
    warnings: list[str]
    artifacts: list[str]


def _remove_empty_pack_dir(pack_dir: Path) -> None:
    """Remove a newly-created pack dir if no files were written."""
    if not pack_dir.exists():
        return
    if any(path.is_file() for path in pack_dir.rglob("*")):
        return
    shutil.rmtree(pack_dir, ignore_errors=True)


def _detect_sse_form_type(markdown: str, requested: str = "auto") -> str:
    """Resolve the SSE document type used for section IDs and metadata."""
    normalized = requested.strip().upper().replace("_", "-") if requested else "AUTO"
    if normalized not in {"", "AUTO"}:
        if normalized in {"ANNUAL", "ANNUAL-REPORT"}:
            return "ANNUAL-REPORT"
        if normalized in {"IPO", "IPO-PROSPECTUS", "PROSPECTUS"}:
            return "IPO-PROSPECTUS"
        return normalized

    head = markdown[:20_000]
    annual_markers = (
        "年度报告",
        "公司简介和主要财务指标",
        "管理层讨论与分析",
    )
    prospectus_markers = ("招股说明书", "本次发行概况", "发行人基本情况")
    if any(marker in head for marker in annual_markers):
        return "ANNUAL-REPORT"
    if any(marker in head for marker in prospectus_markers):
        return "IPO-PROSPECTUS"
    return "IPO-PROSPECTUS"


def _decode_html_blob(content: bytes) -> str:
    """Decode SEC filing bytes with utf-8 fallback to latin-1."""
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return content.decode("latin-1")


async def _process_html_files_for_form(
    html_files: list[tuple[str, bytes]],
    base_url: str,
    form_type: str,
    out_dir: Path,
    describe_images: bool = False,
) -> str:
    """Run the parse pipeline; for registration-class forms, preserve and
    download images and rewrite <img src> to local paths.

    For periodic forms the behavior is the standard strip-and-render pipeline.
    """
    from ..parse.s1_headings import inject_s1_headings

    combined_html = "\n".join(_decode_html_blob(content) for _, content in html_files)
    html_stripped = strip_ixbrl(combined_html)

    preserve = is_registration_form(form_type)
    # Inject TOC-driven <h2> tags before clean_html strips id= attributes.
    # S-1 bodies have no large-font headings; section boundaries live in the
    # TOC's href="#anchor" links and matching body id="anchor" markers.
    if preserve:
        html_stripped = inject_s1_headings(html_stripped)
    html_cleaned = (
        clean_html(html_stripped, preserve_images=preserve)
        if preserve
        else clean_html(html_stripped)
    )
    html_semantic = reduce_to_semantic(html_cleaned, base_url=base_url)

    asset_map: dict[str, str] = {}
    if preserve:
        asset_map = await download_assets(base_url, html_cleaned, Path(out_dir))
        if describe_images and asset_map:
            cache_path = Path(out_dir) / "assets" / ".descriptions.json"
            for src, local_rel in asset_map.items():
                image_path = Path(out_dir) / local_rel
                try:
                    desc = await describe_asset(image_path, cache_path=cache_path)
                except Exception:
                    desc = ""
                if desc:
                    (image_path.parent / f"{image_path.stem}.desc.txt").write_text(
                        desc, encoding="utf-8"
                    )

    md = (
        render_markdown(html_semantic, asset_map=asset_map)
        if asset_map
        else render_markdown(html_semantic)
    )
    return polish(md)


async def build_pack(
    cik: str,
    accession: str | None = None,
    form_type: str | None = None,
    out_dir: Path = Path("."),
    with_chunks: bool = False,
    with_xbrl: bool = False,
    force: bool = False,
    describe_images: bool = False,
) -> PackResult:
    """Build a complete filing pack.

    Args:
        cik: CIK number
        accession: Specific accession number (optional)
        form_type: Form type for latest filing lookup
        out_dir: Output directory
        with_chunks: Generate chunks.ndjson
        with_xbrl: Generate xbrl.json
        force: Bypass cache
        describe_images: Generate VLM descriptions for images in registration filings

    Returns:
        PackResult with build info
    """
    warnings: list[str] = []
    artifacts: list[str] = []

    # Step 1: Resolve filing metadata
    if accession:
        meta = await get_filing_by_accession(cik, accession, force=force)
    elif form_type:
        meta = await get_latest_filing(cik, form_type, force=force)
    else:
        raise ValueError("Either accession or form_type must be provided")

    # Step 2: Create output directory structure
    pack_dir = out_dir / meta.cik / meta.accession
    legacy_pack_dir = out_dir / meta.cik / meta.accession_nodash
    sections_dir = pack_dir / "sections"

    # Check if already exists
    if pack_dir.exists() and not force:
        manifest_path = pack_dir / "manifest.json"
        if manifest_path.exists():
            # Already built, return existing result
            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
            return PackResult(
                output_dir=pack_dir,
                filing_meta=manifest_data.get("filing", {}),
                sections_count=len(manifest_data.get("sections", [])),
                tokens_total=manifest_data.get("tokens_total", 0),
                warnings=["Pack already exists, use --force to rebuild"],
                artifacts=list(manifest_data.get("artifacts", {}).keys()),
            )

    # Backward-compatible read: older versions used accession_nodash as directory name.
    if legacy_pack_dir.exists() and not pack_dir.exists() and not force:
        legacy_manifest = legacy_pack_dir / "manifest.json"
        if legacy_manifest.exists():
            manifest_data = json.loads(legacy_manifest.read_text(encoding="utf-8"))
            return PackResult(
                output_dir=legacy_pack_dir,
                filing_meta=manifest_data.get("filing", {}),
                sections_count=len(manifest_data.get("sections", [])),
                tokens_total=manifest_data.get("tokens_total", 0),
                warnings=["Pack already exists (legacy layout), use --force to rebuild"],
                artifacts=list(manifest_data.get("artifacts", {}).keys()),
            )

    if pack_dir.exists() and force:
        shutil.rmtree(pack_dir)

    pack_dir_existed = pack_dir.exists()
    pack_dir.mkdir(parents=True, exist_ok=True)
    sections_dir.mkdir(exist_ok=True)

    # Step 3: Fetch HTML files
    try:
        html_files = await fetch_primary_filing_html(meta, force=force)
        if not html_files:
            raise ValueError(f"No HTML files found for filing {meta.accession}")
    except Exception:
        if not pack_dir_existed:
            _remove_empty_pack_dir(pack_dir)
        raise

    # Step 4: Process HTML to markdown
    base_url = f"{SEC_ARCHIVES_BASE}/{meta.cik}/{meta.accession_nodash}/"
    # Prefer the resolved meta.form_type over the caller-supplied form_type:
    # harvest-driven builds pass form_type=None because the accession already
    # identifies the filing, and the registration-class pipeline gate
    # (`is_registration_form`) needs the real form string.
    effective_form_type = form_type or meta.form_type or ""
    markdown = await _process_html_files_for_form(
        html_files=html_files,
        base_url=base_url,
        form_type=effective_form_type,
        out_dir=pack_dir,
        describe_images=describe_images,
    )

    # Step 4b: Prepend filing title
    filed = meta.filing_date.isoformat()
    filing_title = f"# {meta.company_name} | {meta.form_type} | Filed {filed}"
    markdown = f"{filing_title}\n\n{markdown}"

    # Step 5: Sectionize
    sections = sectionize(markdown, meta.form_type)

    # Collect section warnings
    for section in sections:
        warnings.extend(section.warnings)

    # Step 6: Write full filing markdown
    full_md_path = pack_dir / "filing.full.md"
    full_md_path.write_text(markdown, encoding="utf-8")
    artifacts.append("filing.full.md")

    # Step 7: Write section files
    for section in sections:
        section_path = sections_dir / f"{section.id}.md"
        section_path.write_text(section.content, encoding="utf-8")
        artifacts.append(f"sections/{section.id}.md")

    # Step 8: Optional - generate chunks
    if with_chunks:
        try:
            chunks = generate_chunks(sections)
            write_chunks_ndjson(chunks, pack_dir)
            artifacts.append("optional/chunks.ndjson")
        except Exception as e:
            warnings.append(f"Failed to generate chunks: {e}")

    # Step 9: Optional - fetch XBRL
    if with_xbrl:
        try:
            xbrl_data = await fetch_xbrl_facts(cik, meta.accession, force=force)
            if xbrl_data:
                optional_dir = pack_dir / "optional"
                optional_dir.mkdir(exist_ok=True)
                xbrl_path = optional_dir / "xbrl.json"
                xbrl_path.write_text(
                    json.dumps(xbrl_data, indent=2, sort_keys=True),
                    encoding="utf-8",
                )
                artifacts.append("optional/xbrl.json")
            else:
                warnings.append("No XBRL data available for this filing")
        except Exception as e:
            warnings.append(f"Failed to fetch XBRL data: {e}")

    # Step 10: Calculate total tokens
    tokens_total = count_tokens(markdown)
    if not has_tiktoken():
        warnings.append("Token counts are approximate (tiktoken not installed)")

    # Step 11: Write llms.txt (needed before hashing artifacts)
    llms_content = generate_llms_txt(
        meta,
        sections,
        has_chunks=with_chunks and "optional/chunks.ndjson" in artifacts,
        has_xbrl=with_xbrl and "optional/xbrl.json" in artifacts,
    )
    write_llms_txt(llms_content, pack_dir)
    artifacts.append("llms.txt")

    # Step 12: Compute hashes for all artifacts (excluding manifest.json itself)
    artifact_hashes: dict[str, str] = {}
    for artifact in sorted(set(artifacts)):
        artifact_path = pack_dir / artifact
        if artifact_path.exists() and artifact != "manifest.json":
            artifact_hashes[artifact] = compute_sha256(artifact_path.read_bytes())

    # Step 13: Write manifest (deterministic)
    source_url = f"{SEC_ARCHIVES_BASE}/{meta.cik}/{meta.accession_nodash}/{meta.primary_document}"
    manifest = create_manifest(
        filing_meta=meta,
        sections=sections,
        artifacts=artifact_hashes,
        warnings=warnings,
        tokens_total=tokens_total,
        source_url=source_url,
    )
    write_manifest(manifest, pack_dir)
    artifacts.append("manifest.json")

    return PackResult(
        output_dir=pack_dir,
        filing_meta={
            "cik": meta.cik,
            "accession": meta.accession,
            "form_type": meta.form_type,
            "filing_date": meta.filing_date.isoformat(),
            "company_name": meta.company_name,
        },
        sections_count=len(sections),
        tokens_total=tokens_total,
        warnings=warnings,
        artifacts=artifacts,
    )


class _SSEFilingMeta:
    """Adapter to make SSE metadata duck-type compatible with create_manifest."""

    def __init__(
        self,
        stock_code: str,
        company_name: str,
        filing_date: date,
        form_type: str = "IPO-PROSPECTUS",
        exchange: str = "SSE",
    ):
        self.stock_code = stock_code
        self.company_name = company_name
        self.filing_date = filing_date
        self.form_type = form_type
        self.exchange = exchange
        self.cik = ""
        self.accession = ""


async def build_sse_pack(
    url: str,
    stock_code: str,
    company_name: str,
    filing_date: date,
    out_dir: Path = Path("."),
    pdf_path: Path | None = None,
    with_chunks: bool = False,
    force: bool = False,
    translate: bool = False,
    translate_model: str = "deepseek-ai/DeepSeek-V3",
    translate_concurrency: int = 5,
    translate_batch_size: int = 25,
    form_type: str = "auto",
) -> PackResult:
    """Build a pack from an SSE PDF.

    Args:
        url: URL of the PDF on SSE disclosure platform
        stock_code: SSE stock code (e.g. 301536)
        company_name: Company name
        filing_date: Filing date
        out_dir: Output directory
        pdf_path: Local PDF override (skip download)
        with_chunks: Generate chunks.ndjson
        force: Rebuild even if pack exists
        translate: Run zh->en translation pipeline
        translate_model: DeepInfra model ID for translation
        translate_concurrency: Max concurrent DeepInfra translation requests
        translate_batch_size: Translation units to validate/cache per progress batch
        form_type: Document type override (auto, annual-report, ipo-prospectus)

    Returns:
        PackResult with build info
    """
    from ..sse.pdf_to_md import pdf_to_markdown
    from ..sse.sectionize_cn import find_sections_cn

    warnings: list[str] = []
    artifacts: list[str] = []

    # Build filing ID from stock code + date
    filing_id = f"{stock_code}_{filing_date.isoformat()}"
    pack_dir = out_dir / "sse" / stock_code / filing_id
    sections_dir = pack_dir / "sections"

    # Check existing
    if pack_dir.exists() and not force:
        manifest_path = pack_dir / "manifest.json"
        if manifest_path.exists():
            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
            return PackResult(
                output_dir=pack_dir,
                filing_meta=manifest_data.get("filing", {}),
                sections_count=len(manifest_data.get("sections", [])),
                tokens_total=manifest_data.get("tokens_total", 0),
                warnings=["Pack already exists, use --force to rebuild"],
                artifacts=list(manifest_data.get("artifacts", {}).keys()),
            )

    if pack_dir.exists() and force:
        shutil.rmtree(pack_dir)

    pack_dir.mkdir(parents=True, exist_ok=True)
    sections_dir.mkdir(exist_ok=True)

    # Step 1: Get PDF
    if pdf_path and pdf_path.exists():
        local_pdf = pdf_path
    else:
        from ..config import CACHE_DIR
        from ..sse.client import download_sse_pdf

        local_pdf = download_sse_pdf(url, CACHE_DIR)

    # Step 2: Convert to markdown
    markdown = pdf_to_markdown(local_pdf)

    # Step 3: Sectionize
    detected_form_type = _detect_sse_form_type(markdown, form_type)
    sections = find_sections_cn(markdown, document_type=detected_form_type)
    for section in sections:
        warnings.extend(section.warnings)

    # Step 4: Write full filing markdown
    full_md_path = pack_dir / "filing.full.md"
    full_md_path.write_text(markdown, encoding="utf-8")
    artifacts.append("filing.full.md")

    # Step 5: Write section files
    for section in sections:
        section_path = sections_dir / f"{section.id}.md"
        section_path.write_text(section.content, encoding="utf-8")
        artifacts.append(f"sections/{section.id}.md")

    # Step 5b: Deterministic annual-report fact extraction
    if detected_form_type == "ANNUAL-REPORT":
        try:
            from ..sse.annual_facts import write_annual_facts

            facts_path = write_annual_facts(
                pack_dir,
                sections,
                stock_code=stock_code,
                company_name=company_name,
                filing_date=filing_date,
                source_url=url,
            )
            if facts_path is not None:
                artifacts.append("facts.json")
            else:
                warnings.append("No annual-report fact rows detected")
        except Exception as e:
            warnings.append(f"Annual fact extraction failed: {type(e).__name__}: {e}")

    # Step 6: Optional translation
    translation_meta: dict[str, Any] | None = None
    if translate:
        try:
            translation_meta = await _translate_sections(
                sections=sections,
                sections_dir=sections_dir,
                pack_dir=pack_dir,
                stock_code=stock_code,
                out_dir=out_dir,
                model=translate_model,
                max_concurrency=translate_concurrency,
                batch_size=translate_batch_size,
                warnings=warnings,
                artifacts=artifacts,
            )
        except Exception as e:
            warnings.append(f"Translation failed: {type(e).__name__}: {e}")

    # Step 7: Optional chunks
    if with_chunks:
        try:
            chunks = generate_chunks(sections)
            write_chunks_ndjson(chunks, pack_dir)
            artifacts.append("optional/chunks.ndjson")
        except Exception as e:
            warnings.append(f"Failed to generate chunks: {e}")

    # Step 8: Tokens
    tokens_total = count_tokens(markdown)
    if not has_tiktoken():
        warnings.append("Token counts are approximate (tiktoken not installed)")

    # Step 9: llms.txt
    meta = _SSEFilingMeta(
        stock_code=stock_code,
        company_name=company_name,
        filing_date=filing_date,
        form_type=detected_form_type,
        exchange="SSE",
    )
    has_chunks_artifact = "optional/chunks.ndjson" in artifacts
    has_translation = translation_meta is not None
    translated_sections = (
        set(translation_meta.get("translated_sections", [])) if translation_meta else set()
    )
    has_full_translation = bool(translation_meta and translation_meta.get("full_filing_written"))
    llms_content = _generate_sse_llms_txt(
        meta,
        sections,
        has_chunks=has_chunks_artifact,
        has_translation=has_translation,
        translated_sections=translated_sections,
        has_full_translation=has_full_translation,
    )
    write_llms_txt(llms_content, pack_dir)
    artifacts.append("llms.txt")

    # Step 10: Copy source PDF
    optional_dir = pack_dir / "optional"
    optional_dir.mkdir(exist_ok=True)
    shutil.copy2(local_pdf, optional_dir / "source.pdf")
    artifacts.append("optional/source.pdf")

    # Step 11: Compute artifact hashes
    artifact_hashes: dict[str, str] = {}
    for artifact in sorted(set(artifacts)):
        artifact_path = pack_dir / artifact
        if artifact_path.exists() and artifact != "manifest.json":
            artifact_hashes[artifact] = compute_sha256(artifact_path.read_bytes())

    # Step 12: Write manifest
    manifest = create_manifest(
        filing_meta=meta,
        sections=sections,
        artifacts=artifact_hashes,
        warnings=warnings,
        tokens_total=tokens_total,
        source_url=url,
    )
    manifest_path = write_manifest(manifest, pack_dir)
    # Inject translation metadata into manifest JSON if present
    if translation_meta is not None:
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_data["translation"] = translation_meta
        manifest_path.write_text(
            json.dumps(manifest_data, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    artifacts.append("manifest.json")

    return PackResult(
        output_dir=pack_dir,
        filing_meta={
            "stock_code": stock_code,
            "company_name": company_name,
            "form_type": detected_form_type,
            "filing_date": filing_date.isoformat(),
            "exchange": "SSE",
        },
        sections_count=len(sections),
        tokens_total=tokens_total,
        warnings=warnings,
        artifacts=artifacts,
    )


async def _translate_sections(
    sections: list[Any],
    sections_dir: Path,
    pack_dir: Path,
    stock_code: str,
    out_dir: Path,
    model: str,
    warnings: list[str],
    artifacts: list[str],
    max_concurrency: int = 5,
    batch_size: int = 25,
) -> dict[str, Any]:
    """Run translation pipeline on all sections. Returns translation metadata dict."""
    from ..china.translate.cache import TranslationCache, provider_namespace
    from ..china.translate.deepinfra import PROMPT_VERSION, DeepInfraTranslator
    from ..china.translate.glossary import FinancialGlossary
    from ..china.translate.numbers import tag_numbers
    from ..china.translate.preprocess import preprocess_paragraphs
    from ..china.translate.router import ROUTER_VERSION, SectionRouter
    from ..china.translate.validators import (
        VALIDATOR_VERSION,
        GlossaryConsistencyValidator,
        validate_translation,
    )

    glossary = FinancialGlossary.with_company_overlay(stock_code, out_dir)
    translator = DeepInfraTranslator(
        glossary=glossary,
        model=model,
        max_concurrency=max(1, max_concurrency),
    )
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

    cached_paragraphs = 0
    translated_paragraphs = 0
    validation_warnings: list[str] = []
    failed_sections: list[str] = []
    translated_section_ids: list[str] = []
    en_sections: list[str] = []
    batch_size = max(1, batch_size)

    import sys

    for si, section in enumerate(sections, 1):
        paragraphs = [p for p in section.content.split("\n\n") if p.strip()]
        decisions = preprocess_paragraphs(paragraphs)

        # Check cache for each paragraph
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
                cached_paragraphs += 1
                translation_sources[i] = "cache"
            else:
                uncached_indices.append(i)
                uncached_texts.append(decision.cleaned)

        section_failed = False
        section_error_messages: list[str] = []

        def _validate_paragraph(index: int, text_zh: str, text_en: str, allow_han: bool) -> Any:
            _, number_tags = tag_numbers(text_zh)
            return validate_translation(
                text_zh=text_zh,
                text_en=text_en,
                number_tags=number_tags,
                glossary_terms=glossary.terms,
                glossary_validator=glossary_validator,
                allow_han=allow_han,
                paragraph_index=index,
            )

        # Validate cached translations before reusing them.
        for i, decision in enumerate(decisions):
            if translation_sources[i] != "cache" or para_results[i] is None:
                continue
            report = _validate_paragraph(i, decision.cleaned, para_results[i], allow_han=False)
            for issue in report.warnings:
                validation_warnings.append(f"[{section.id}] p{i}: {issue.message}")
            if report.has_errors:
                uncached_indices.append(i)
                uncached_texts.append(decision.cleaned)
                para_results[i] = None
                translation_sources[i] = None
                cached_paragraphs -= 1

        print(
            f"  [{si}/{len(sections)}] {section.id}: "
            f"{len(paragraphs)} paragraphs "
            f"({len(uncached_texts)} uncached after preprocessing/cache)",
            file=sys.stderr,
        )

        # Translate uncached paragraphs via router
        if uncached_texts:
            total_batches = (len(uncached_texts) + batch_size - 1) // batch_size
            for batch_number, batch_start in enumerate(
                range(0, len(uncached_texts), batch_size), 1
            ):
                batch_indices = uncached_indices[batch_start : batch_start + batch_size]
                batch_texts = uncached_texts[batch_start : batch_start + batch_size]
                print(
                    f"    batch {batch_number}/{total_batches}: "
                    f"{len(batch_texts)} translation units",
                    file=sys.stderr,
                )
                try:
                    results = await router.translate_section(section.id, batch_texts)
                except Exception as e:
                    err = f"[{section.id}] {type(e).__name__}: {e}"
                    print(f"  WARN: {err}", file=sys.stderr)
                    warnings.append(f"Translation error: {err}")
                    section_failed = True
                    section_error_messages.append(err)
                    break

                retry_indices: list[int] = []
                retry_texts: list[str] = []

                for idx, result in zip(batch_indices, results, strict=False):
                    report = _validate_paragraph(
                        idx, result.text_zh, result.text_en, allow_han=False
                    )
                    for issue in report.warnings:
                        validation_warnings.append(f"[{section.id}] p{idx}: {issue.message}")
                    if report.has_errors:
                        retry_indices.append(idx)
                        retry_texts.append(result.text_zh)
                        continue

                    para_results[idx] = result.text_en
                    translation_sources[idx] = "translated"
                    cache.put(result)
                    translated_paragraphs += 1

                if retry_texts:
                    try:
                        retry_results = await router.translate_section(
                            section.id, retry_texts, strict=True
                        )
                    except Exception as e:
                        err = f"[{section.id}] {type(e).__name__}: {e}"
                        print(f"  WARN: {err}", file=sys.stderr)
                        warnings.append(f"Translation error: {err}")
                        section_failed = True
                        section_error_messages.append(err)
                        break
                    for idx, result in zip(retry_indices, retry_results, strict=False):
                        report = _validate_paragraph(
                            idx, result.text_zh, result.text_en, allow_han=False
                        )
                        for issue in report.warnings:
                            validation_warnings.append(f"[{section.id}] p{idx}: {issue.message}")
                        if report.has_errors:
                            section_failed = True
                            for issue in report.issues:
                                msg = f"[{section.id}] p{idx}: {issue.message}"
                                validation_warnings.append(msg)
                                if issue.severity == "error":
                                    section_error_messages.append(msg)
                            break
                        para_results[idx] = result.text_en
                        translation_sources[idx] = "translated"
                        cache.put(result)
                        translated_paragraphs += 1
                if section_failed:
                    break
                print(f"    batch {batch_number}/{total_batches}: cached", file=sys.stderr)

        if section_failed or any(
            translation_sources[i] is None and decisions[i].action == "translate"
            for i in range(len(decisions))
        ):
            failed_sections.append(section.id)
            warnings.append(f"Translation failed closed for section {section.id}")
            for msg in section_error_messages[:3]:
                warnings.append(f"Translation failure detail: {msg}")
            en_path = sections_dir / f"{section.id}.en.md"
            if en_path.exists():
                en_path.unlink()
            continue

        en_content = "\n\n".join(p for p in para_results if p)
        en_sections.append(en_content)
        en_path = sections_dir / f"{section.id}.en.md"
        en_path.write_text(en_content, encoding="utf-8")
        artifacts.append(f"sections/{section.id}.en.md")
        translated_section_ids.append(section.id)

    # Write concatenated English full filing
    wrote_full_en = False
    if en_sections and not failed_sections:
        full_en = "\n\n---\n\n".join(en_sections)
        full_en_path = pack_dir / "filing.full.en.md"
        full_en_path.write_text(full_en, encoding="utf-8")
        artifacts.append("filing.full.en.md")
        wrote_full_en = True
    else:
        full_en_path = pack_dir / "filing.full.en.md"
        if full_en_path.exists():
            full_en_path.unlink()

    if validation_warnings:
        for vw in validation_warnings[:20]:
            warnings.append(f"Translation: {vw}")
        if len(validation_warnings) > 20:
            warnings.append(f"Translation: ... and {len(validation_warnings) - 20} more warnings")

    await translator.close()
    cache.close()

    return {
        "provider": translator.provider,
        "model": model,
        "glossary_version": glossary.version,
        "strategy_fingerprint": strategy_fingerprint,
        "cached_paragraphs": cached_paragraphs,
        "translated_paragraphs": translated_paragraphs,
        "validation_warnings": len(validation_warnings),
        "failed_sections": failed_sections,
        "translated_sections": translated_section_ids,
        "full_filing_written": wrote_full_en,
    }


def _generate_sse_llms_txt(
    meta: _SSEFilingMeta,
    sections: list[Any],
    has_chunks: bool = False,
    has_translation: bool = False,
    translated_sections: set[str] | None = None,
    has_full_translation: bool = False,
) -> str:
    """Generate llms.txt for an SSE filing pack."""
    lines = []
    lines.append(f"# {meta.company_name} {meta.form_type} ({meta.filing_date.isoformat()})")
    lines.append("")
    lines.append(f"> Stock Code: {meta.stock_code} | Exchange: {meta.exchange}")
    lines.append("")
    lines.append("## Filing Pack")
    lines.append("")
    lines.append("- [Full Filing (Chinese)](filing.full.md)")
    if has_full_translation:
        lines.append("- [Full Filing (English)](filing.full.en.md)")
    lines.append("- [Manifest](manifest.json)")
    lines.append("- [Source PDF](optional/source.pdf)")
    lines.append("")
    lines.append("## Sections")
    lines.append("")
    translated = translated_sections or set()
    for section in sections:
        section_path = f"sections/{section.id}.md"
        lines.append(f"- [{section.title} (Chinese)]({section_path})")
        if has_translation and section.id in translated:
            en_path = f"sections/{section.id}.en.md"
            lines.append(f"- [{section.title} (English)]({en_path})")
    lines.append("")
    if has_chunks:
        lines.append("## Optional")
        lines.append("")
        lines.append("- [Chunks](optional/chunks.ndjson)")
        lines.append("")
    return "\n".join(lines)


async def build_company_llms(
    cik: str,
    out_dir: Path,
) -> Path:
    """Generate company-level llms.txt listing all processed filings.

    Args:
        cik: CIK number
        out_dir: Output directory containing filing packs

    Returns:
        Path to generated llms.txt
    """
    from ..sec.submissions import fetch_submissions, normalize_cik
    from .llms_txt import generate_company_llms_txt, scan_filings_for_company_llms

    cik = normalize_cik(cik)
    cik_dir = out_dir / cik

    if not cik_dir.exists():
        raise ValueError(f"No filings found for CIK {cik} in {out_dir}")

    # Get company name from submissions
    submissions = await fetch_submissions(cik)
    company_name = submissions.get("name", f"CIK {cik}")

    # Scan for existing filings
    filings = scan_filings_for_company_llms(cik_dir)

    if not filings:
        raise ValueError(f"No processed filings found in {cik_dir}")

    # Generate llms.txt
    content = generate_company_llms_txt(company_name, cik, filings)

    llms_path = cik_dir / "llms.txt"
    llms_path.write_text(content, encoding="utf-8")

    return llms_path


async def build_pack_range(
    cik: str,
    form_type: str,
    *,
    last: int | None = None,
    after: date | None = None,
    before: date | None = None,
    out_dir: Path,
    with_chunks: bool,
    with_xbrl: bool,
    force: bool,
    concurrency: int = 3,
    describe_images: bool = False,
) -> list[PackResult]:
    fetch_limit = max(last or 50, 50)
    candidates = await list_filings(cik, form_type=form_type, limit=fetch_limit)

    filtered: list = []
    for meta in candidates:
        if after is not None and meta.filing_date < after:
            continue
        if before is not None and meta.filing_date > before:
            continue
        filtered.append(meta)

    filtered.sort(key=lambda m: m.filing_date, reverse=True)
    if last is not None:
        filtered = filtered[:last]

    if not filtered:
        return []

    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def _one(accession: str) -> PackResult:
        async with semaphore:
            return await build_pack(
                cik=cik,
                accession=accession,
                form_type=None,
                out_dir=out_dir,
                with_chunks=with_chunks,
                with_xbrl=with_xbrl,
                force=force,
                describe_images=describe_images,
            )

    tasks = [asyncio.create_task(_one(m.accession)) for m in filtered]
    try:
        return await asyncio.gather(*tasks)
    except Exception:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
