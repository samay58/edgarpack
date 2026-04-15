"""China Lens service layer.

The service owns workflow logic, while persistence and binary storage live
behind repository/object-store adapters.
"""

from __future__ import annotations

import os
import re
from datetime import date
from hashlib import sha256
from threading import RLock
from uuid import uuid4

from pydantic import ValidationError

from .acquire.cninfo import (
    ManifestDocument,
    build_acquisition_event,
    document_from_cninfo,
    load_cninfo_manifest,
)
from .extract.pdf_extract import extract_pdf_pages
from .index.search import rank_chunks
from .jobs.runner import cancel_job, create_stage_progress, pack_status_from_job, progress_job
from .models import (
    AskAnswerBlock,
    AskRequest,
    AskResponse,
    CitationRef,
    CninfoSyncRequest,
    CninfoSyncResponse,
    Company,
    CreatePackRequest,
    CreatePackResponse,
    Document,
    DocumentPageResponse,
    EvidenceChunk,
    ExtractionMethod,
    Finding,
    FindingStatus,
    JobStatus,
    Pack,
    PackJob,
    PackStatus,
    PackStatusResponse,
    PipelineStage,
    ResolvedCitation,
    SearchEvidenceHit,
    SearchEvidenceRequest,
    SearchEvidenceResponse,
    utc_now,
)
from .qa.validators import run_publish_checks
from .storage import (
    ChinaLensRepository,
    ObjectStore,
    create_default_object_store,
    create_default_repository,
)
from .synthesis.pack_builder import (
    build_empty_sections,
    citation_label,
    inject_findings,
)

_NUMERIC_TOKEN_RE = re.compile(r"\d+[\d,.%]*")


class ChinaLensService:
    """Stateful service that powers API routes for the MVP."""

    def __init__(
        self,
        repository: ChinaLensRepository | None = None,
        object_store: ObjectStore | None = None,
        seed_fixtures: bool = True,
    ) -> None:
        self._lock = RLock()
        self._repository = repository or create_default_repository()
        self._object_store = object_store or create_default_object_store()
        if seed_fixtures and not self._repository.list_companies():
            self._seed_fixtures()

    def _seed_fixtures(self) -> None:
        company = Company(
            id="cmp_tencent_0700",
            display_name_en="Tencent Holdings Limited",
            display_name_zh="腾讯控股有限公司",
            ticker="0700.HK",
            exchange="HKEX",
            aliases=["Tencent", "腾讯"],
        )
        self._repository.upsert_company(company)

        evt_id = "acq_seed_2024"
        doc_annual = document_from_cninfo(
            doc_id="doc_tencent_2024_annual",
            company=company,
            title="Tencent 2024 Annual Report",
            filing_date="2025-03-20",
            source_url="https://www.cninfo.com.cn/mock/tencent-2024-annual.pdf",
            pages=188,
            acquisition_log_id=evt_id,
        )
        doc_interim = document_from_cninfo(
            doc_id="doc_tencent_2024_interim",
            company=company,
            title="Tencent 2024 Interim Report",
            filing_date="2024-08-21",
            source_url="https://www.cninfo.com.cn/mock/tencent-2024-interim.pdf",
            pages=104,
            acquisition_log_id=evt_id,
        )
        self._repository.upsert_document(doc_annual)
        self._repository.upsert_document(doc_interim)

        chunks = [
            EvidenceChunk(
                id="chunk_top_customers",
                doc_id=doc_annual.id,
                page_start=87,
                page_end=87,
                text_zh="前五大客户收入占集团总收入24.3%，未披露客户名称。",
                text_en=(
                    "Top five customers represented 24.3% of group revenue; "
                    "customer names were not disclosed."
                ),
                language="zh",
                extraction_method=ExtractionMethod.EMBEDDED_TEXT,
                confidence=0.98,
            ),
            EvidenceChunk(
                id="chunk_segment_fintech",
                doc_id=doc_annual.id,
                page_start=42,
                page_end=42,
                text_zh="金融科技及企业服务业务收入同比增长15%至人民币2030亿元。",
                text_en=(
                    "FinTech and Business Services revenue increased 15% year over "
                    "year to RMB 203.0 billion."
                ),
                language="zh",
                extraction_method=ExtractionMethod.EMBEDDED_TEXT,
                confidence=0.96,
            ),
            EvidenceChunk(
                id="chunk_risk_regulation",
                doc_id=doc_interim.id,
                page_start=15,
                page_end=15,
                text_zh="监管政策变化可能影响部分增值服务业务的商业化节奏。",
                text_en=(
                    "Regulatory policy changes may affect monetization cadence for "
                    "value-added services."
                ),
                language="zh",
                extraction_method=ExtractionMethod.OCR,
                confidence=0.73,
            ),
            EvidenceChunk(
                id="chunk_governance",
                doc_id=doc_annual.id,
                page_start=121,
                page_end=121,
                text_zh="董事会由九名董事组成，其中四名为独立非执行董事。",
                text_en=(
                    "The board comprises nine directors, including four independent "
                    "non-executive directors."
                ),
                language="zh",
                extraction_method=ExtractionMethod.EMBEDDED_TEXT,
                confidence=0.95,
            ),
        ]

        for chunk in chunks:
            self._repository.upsert_chunk(chunk)

        seed_event = build_acquisition_event(
            event_id=evt_id,
            company_id=company.id,
            source_url=doc_annual.source_url,
            file_hash=doc_annual.file_hash,
            outcome="cached",
            details="Seeded fixture filing metadata for local China Lens development.",
        )
        self._repository.append_acquisition_event(seed_event)

    def list_companies(self) -> list[Company]:
        with self._lock:
            companies = self._repository.list_companies()
            return sorted(companies, key=lambda company: company.display_name_en)

    def list_documents(self, company_id: str | None = None) -> list[Document]:
        with self._lock:
            docs = self._repository.list_documents(company_id=company_id)
            docs.sort(key=lambda doc: doc.filing_date, reverse=True)
            return docs

    def get_document(self, doc_id: str) -> Document:
        with self._lock:
            doc = self._repository.get_document(doc_id)
            if doc is None:
                raise KeyError(f"Unknown document: {doc_id}")
            return doc

    def get_document_page(self, doc_id: str, page: int) -> DocumentPageResponse:
        with self._lock:
            doc = self.get_document(doc_id)
            snippets = [
                chunk
                for chunk in self._repository.list_chunks(doc_id=doc_id)
                if chunk.page_start <= page <= chunk.page_end
            ]
            if snippets:
                snippet = snippets[0]
                snippet_zh = snippet.text_zh
                snippet_en = snippet.text_en
            else:
                snippet_zh = "未在已索引证据中找到该页片段。"
                snippet_en = "No indexed snippet available for this page."
            return DocumentPageResponse(
                doc_id=doc.id,
                page=page,
                snippet_zh=snippet_zh,
                snippet_en=snippet_en,
                image_url=f"{(doc.storage_url or doc.source_url)}#page={page}",
            )

    def create_pack_job(self, req: CreatePackRequest) -> CreatePackResponse:
        with self._lock:
            if self._repository.get_company(req.company_id) is None:
                raise KeyError(f"Unknown company: {req.company_id}")

            pack_id = f"pack_{uuid4().hex[:12]}"
            job_id = f"job_{uuid4().hex[:12]}"
            now = utc_now()
            doc_set = req.doc_selection or [
                doc.id for doc in self.list_documents(company_id=req.company_id)
            ]

            pack = Pack(
                id=pack_id,
                company_id=req.company_id,
                created_at=now,
                updated_at=now,
                doc_set=doc_set,
                time_range=req.time_range,
                translation_mode=req.translation_mode,
                template=req.template,
                status=PackStatus.RUNNING,
                sections=build_empty_sections(),
                build_logs=["Pack job created."],
                errors=[],
            )
            job = PackJob(
                id=job_id,
                pack_id=pack_id,
                status=JobStatus.RUNNING,
                stage=PipelineStage.DOWNLOAD,
                stage_progress=create_stage_progress(),
                progress_pct=0,
                stage_logs=["Downloading filings from CNINFO..."],
            )

            self._repository.upsert_pack(pack)
            self._repository.upsert_job(job)
            self._repository.set_job_for_pack(pack.id, job.id)

            return CreatePackResponse(pack_id=pack.id, job_id=job.id, status=pack.status)

    @staticmethod
    def _finding_id(pack_id: str, section_id: str, chunk_id: str) -> str:
        payload = f"{pack_id}|{section_id}|{chunk_id}".encode()
        return f"finding_{sha256(payload).hexdigest()[:12]}"

    @staticmethod
    def _claim_text_from_chunk(chunk: EvidenceChunk) -> str:
        text = " ".join((chunk.text_en or chunk.text_zh).split())
        if not text:
            return ""
        if text[-1] not in {".", "!", "?", "。"}:
            return f"{text}."
        return text

    @staticmethod
    def _key_numbers(text: str) -> list[str]:
        return _NUMERIC_TOKEN_RE.findall(text)

    @staticmethod
    def _section_for_chunk(chunk: EvidenceChunk) -> tuple[str, str]:
        haystack = f"{chunk.text_en} {chunk.text_zh}".lower()
        classifiers: tuple[tuple[str, str, tuple[str, ...]], ...] = (
            (
                "customers_suppliers",
                "customer_supplier_disclosure",
                ("customer", "supplier", "concentration", "客户", "供应商"),
            ),
            (
                "financials",
                "financial_disclosure",
                ("revenue", "profit", "income", "cash flow", "收入", "利润", "现金"),
            ),
            (
                "ownership_governance",
                "governance_disclosure",
                ("board", "director", "independent", "shareholder", "董事", "治理", "股东"),
            ),
            (
                "risk_register",
                "risk_disclosure",
                ("risk", "regulat", "compliance", "policy", "风险", "监管", "合规", "政策"),
            ),
        )
        for section_id, claim_type, terms in classifiers:
            if any(term in haystack for term in terms):
                return section_id, claim_type
        return "summary", "indexed_disclosure"

    def _finding_from_chunk(
        self,
        pack: Pack,
        chunk: EvidenceChunk,
        section_id: str,
        claim_type: str,
    ) -> Finding | None:
        claim_text = self._claim_text_from_chunk(chunk)
        if not claim_text:
            return None
        return Finding(
            id=self._finding_id(pack.id, section_id, chunk.id),
            pack_id=pack.id,
            section_id=section_id,
            claim_text=claim_text,
            claim_type=claim_type,
            key_numbers=self._key_numbers(claim_text),
            citations=[
                CitationRef(
                    chunk_id=chunk.id,
                    doc_id=chunk.doc_id,
                    page=chunk.page_start,
                    quote_start=0,
                    quote_end=0,
                    citation_label=self._citation_label_for_chunk(chunk),
                )
            ],
            status=FindingStatus.SUPPORTED,
        )

    def _build_findings_from_evidence(self, pack: Pack) -> list[Finding]:
        allowed_doc_ids = set(pack.doc_set)
        chunks = [
            chunk
            for chunk in self._repository.list_chunks()
            if chunk.doc_id in allowed_doc_ids and (chunk.text_en or chunk.text_zh).strip()
        ]
        chunks.sort(key=lambda chunk: (chunk.doc_id, chunk.page_start, chunk.id))

        findings: list[Finding] = []
        finding_keys: set[tuple[str, str]] = set()
        for chunk in chunks:
            section_id, claim_type = self._section_for_chunk(chunk)
            finding = self._finding_from_chunk(pack, chunk, section_id, claim_type)
            if finding is not None:
                findings.append(finding)
                finding_keys.add((section_id, chunk.id))

        for chunk in chunks[:2]:
            if ("summary", chunk.id) in finding_keys:
                continue
            summary = self._finding_from_chunk(pack, chunk, "summary", "summary_signal")
            if summary is not None:
                findings.append(summary)
                finding_keys.add(("summary", chunk.id))

        return findings

    def _finalize_pack(self, pack_id: str) -> None:
        pack = self.get_pack(pack_id)
        for section in pack.sections:
            section.findings = []
            section.key_points = []
            section.unknowns = []

        findings = self._build_findings_from_evidence(pack)
        inject_findings(pack, findings)

        chunks_by_id = {chunk.id: chunk for chunk in self._repository.list_chunks()}
        report = run_publish_checks(pack, chunks_by_id=chunks_by_id, min_citations_per_section=2)
        pack.updated_at = utc_now()

        if report.passed and findings:
            pack.status = PackStatus.READY
            pack.build_logs.append("Pack QA checks passed.")
        else:
            pack.status = PackStatus.PARTIAL
            if not findings:
                pack.errors.append("No indexed evidence was available for the selected documents.")
            pack.errors.extend(issue.message for issue in report.issues)
            pack.build_logs.append(
                "Pack QA checks reported "
                f"{len(report.issues)} issue(s); unsupported findings were flagged."
            )

        for section in pack.sections:
            if not section.findings and not section.unknowns:
                section.unknowns.append("No indexed evidence matched this section.")
            section.updated_at = utc_now()
        self._repository.upsert_pack(pack)

    def _get_job_by_pack(self, pack_id: str) -> PackJob:
        job = self._repository.get_job_by_pack(pack_id)
        if job is None:
            raise KeyError(f"Unknown pack: {pack_id}")
        return job

    def tick_pack_job(self, pack_id: str) -> PackJob:
        with self._lock:
            pack = self.get_pack(pack_id)
            job = self._get_job_by_pack(pack_id)
            if job.status in {JobStatus.COMPLETED, JobStatus.CANCELED, JobStatus.FAILED}:
                return job

            if job.cancel_requested:
                cancel_job(job)
                pack.status = PackStatus.CANCELED
                pack.updated_at = utc_now()
                pack.build_logs.append("Pack job canceled by user.")
                self._repository.upsert_job(job)
                self._repository.upsert_pack(pack)
                return job

            before_stage = job.stage
            progress_job(job)
            if job.stage != before_stage:
                job.stage_logs.append(f"Stage complete: {before_stage.value}")
                job.stage_logs.append(f"Now running: {job.stage.value}")

            pack.status = pack_status_from_job(job)
            pack.updated_at = utc_now()
            pack.build_logs.append(
                f"Pipeline stage {job.stage.value} at {job.stage_progress.get(job.stage, 0)}%."
            )
            self._repository.upsert_job(job)
            self._repository.upsert_pack(pack)

            if job.status == JobStatus.COMPLETED:
                self._finalize_pack(pack_id)

            return job

    def cancel_pack_job(self, pack_id: str) -> PackJob:
        with self._lock:
            job = self._get_job_by_pack(pack_id)
            job.cancel_requested = True
            if job.status == JobStatus.RUNNING:
                cancel_job(job)
            pack = self.get_pack(pack_id)
            pack.status = PackStatus.CANCELED
            pack.updated_at = utc_now()
            pack.build_logs.append("Cancellation requested.")
            self._repository.upsert_job(job)
            self._repository.upsert_pack(pack)
            return job

    def get_pack(self, pack_id: str) -> Pack:
        pack = self._repository.get_pack(pack_id)
        if pack is None:
            raise KeyError(f"Unknown pack: {pack_id}")
        return pack

    def get_pack_status(self, pack_id: str, auto_tick: bool = True) -> PackStatusResponse:
        with self._lock:
            if auto_tick:
                self.tick_pack_job(pack_id)
            job = self._get_job_by_pack(pack_id)
            return PackStatusResponse(
                pack_id=pack_id,
                job_id=job.id,
                status=job.status,
                stage=job.stage,
                progress_pct=job.progress_pct,
                stage_progress=job.stage_progress,
                cancel_requested=job.cancel_requested,
                logs=job.stage_logs,
            )

    def search_evidence(self, req: SearchEvidenceRequest) -> SearchEvidenceResponse:
        with self._lock:
            chunks = self._repository.list_chunks()
            if req.company_id:
                doc_ids = {doc.id for doc in self.list_documents(company_id=req.company_id)}
                chunks = [chunk for chunk in chunks if chunk.doc_id in doc_ids]

            if req.pack_id:
                pack = self.get_pack(req.pack_id)
                allowed = set(pack.doc_set)
                chunks = [chunk for chunk in chunks if chunk.doc_id in allowed]

            ranked = rank_chunks(req.query, chunks, limit=req.limit)
            hits = [
                SearchEvidenceHit(
                    chunk_id=chunk.id,
                    doc_id=chunk.doc_id,
                    page=chunk.page_start,
                    score=score,
                    text_zh=chunk.text_zh,
                    text_en=chunk.text_en,
                    citation_label=self._citation_label_for_chunk(chunk),
                )
                for chunk, score in ranked
            ]
            return SearchEvidenceResponse(hits=hits)

    def _citation_label_for_chunk(self, chunk: EvidenceChunk) -> str:
        doc = self.get_document(chunk.doc_id)
        year = doc.filing_date[:4]
        return citation_label(doc.source, year, chunk.page_start)

    def resolve_citation(self, chunk_id: str) -> ResolvedCitation:
        with self._lock:
            chunk = self._repository.get_chunk(chunk_id)
            if chunk is None:
                raise KeyError(f"Unknown chunk: {chunk_id}")
            return ResolvedCitation(
                chunk_id=chunk.id,
                doc_id=chunk.doc_id,
                page=chunk.page_start,
                text_zh=chunk.text_zh,
                text_en=chunk.text_en,
                citation_label=self._citation_label_for_chunk(chunk),
            )

    def ask(self, req: AskRequest) -> AskResponse:
        search = self.search_evidence(
            SearchEvidenceRequest(
                query=req.question,
                company_id=req.company_id,
                pack_id=req.pack_id,
                limit=req.top_k,
            )
        )

        if not search.hits:
            return AskResponse(
                answer=[
                    AskAnswerBlock(
                        text="Not found in indexed sources.",
                        citations=[],
                    )
                ],
                not_found=True,
                guidance=(
                    "Try Evidence Explorer search for customer concentration, "
                    "named customers, or related-party disclosures."
                ),
            )

        blocks: list[AskAnswerBlock] = []
        for hit in search.hits:
            snippet = " ".join((hit.text_en or hit.text_zh).split())
            if not snippet:
                continue
            blocks.append(
                AskAnswerBlock(
                    text=snippet,
                    citations=[
                        CitationRef(
                            chunk_id=hit.chunk_id,
                            doc_id=hit.doc_id,
                            page=hit.page,
                            quote_start=0,
                            quote_end=0,
                            citation_label=hit.citation_label,
                        )
                    ],
                )
            )
            if len(blocks) >= 3:
                break

        if not blocks:
            return AskResponse(
                answer=[
                    AskAnswerBlock(
                        text="Not found in indexed sources.",
                        citations=[],
                    )
                ],
                not_found=True,
                guidance="Try Evidence Explorer search with terms from the source filing.",
            )

        return AskResponse(
            answer=blocks,
            not_found=False,
            guidance=("Open citations to verify the original Chinese source in Evidence Explorer."),
        )

    def _remove_company_documents(self, company_id: str) -> None:
        """Delete documents/chunks for one company while preserving packs/jobs."""
        doc_ids = self._repository.delete_documents_for_company(company_id)
        for doc_id in doc_ids:
            self._repository.delete_chunks_for_doc(doc_id)

    @staticmethod
    def _within_date_window(
        filing_date: str,
        start_date: str | None,
        end_date: str | None,
    ) -> bool:
        """Check whether a filing date is within optional sync bounds."""
        try:
            filing = date.fromisoformat(filing_date)
        except ValueError:
            return False

        if start_date:
            try:
                start = date.fromisoformat(start_date)
            except ValueError:
                start = None
            if start and filing < start:
                return False

        if end_date:
            try:
                end = date.fromisoformat(end_date)
            except ValueError:
                end = None
            if end and filing > end:
                return False

        return True

    def _ingest_manifest_document(
        self,
        company: Company,
        manifest_doc: ManifestDocument,
        acquisition_log_id: str,
    ) -> tuple[Document, int]:
        """Upsert one manifest document and its evidence chunks."""
        object_key = ""
        storage_url = ""
        if manifest_doc.local_pdf_path:
            object_key = f"documents/{company.id}/{manifest_doc.doc_id}.pdf"
            storage_url = self._object_store.put_file(manifest_doc.local_pdf_path, object_key)

        doc = document_from_cninfo(
            doc_id=manifest_doc.doc_id,
            company=company,
            title=manifest_doc.title,
            filing_date=manifest_doc.filing_date,
            source_url=manifest_doc.source_url,
            pages=manifest_doc.pages,
            acquisition_log_id=acquisition_log_id,
            file_hash=manifest_doc.file_hash,
            object_key=object_key,
            storage_url=storage_url,
        )
        self._repository.upsert_document(doc)
        self._repository.delete_chunks_for_doc(doc.id)

        chunk_count = 0
        if manifest_doc.snippets:
            for snippet in manifest_doc.snippets:
                chunk = EvidenceChunk(
                    id=f"chunk_{doc.id}_p{snippet.page:04d}",
                    doc_id=doc.id,
                    page_start=snippet.page,
                    page_end=snippet.page,
                    text_zh=snippet.text_zh,
                    text_en=snippet.text_en or snippet.text_zh,
                    language="zh",
                    extraction_method=snippet.extraction_method,
                    confidence=snippet.confidence,
                )
                self._repository.upsert_chunk(chunk)
                chunk_count += 1
            return doc, chunk_count

        if manifest_doc.local_pdf_path:
            pages = extract_pdf_pages(manifest_doc.local_pdf_path)
            for page in pages:
                if not page.text.strip():
                    continue
                chunk = EvidenceChunk(
                    id=f"chunk_{doc.id}_p{page.page:04d}",
                    doc_id=doc.id,
                    page_start=page.page,
                    page_end=page.page,
                    text_zh=page.text,
                    text_en=page.text,
                    language="zh",
                    extraction_method=page.method,
                    confidence=page.confidence,
                )
                self._repository.upsert_chunk(chunk)
                chunk_count += 1

        return doc, chunk_count

    def cninfo_sync(self, req: CninfoSyncRequest) -> CninfoSyncResponse:
        with self._lock:
            company = self._repository.get_company(req.company_id)
            if company is None:
                raise KeyError(f"Unknown company: {req.company_id}")

            if req.clear_existing:
                self._remove_company_documents(req.company_id)

            docs = self.list_documents(company_id=req.company_id)
            ingested_chunks = 0
            sync_event_id = f"acq_{uuid4().hex[:10]}"
            details = (
                "Connector sync completed. "
                f"Window: {req.start_date or 'open'} to {req.end_date or 'open'}."
            )

            if req.manifest_path:
                try:
                    manifest_docs = load_cninfo_manifest(
                        req.manifest_path,
                        company_id=req.company_id,
                    )
                except (FileNotFoundError, ValidationError, ValueError) as exc:
                    raise ValueError(f"Invalid CNINFO manifest: {exc}") from exc

                ingested_docs = 0
                for manifest_doc in manifest_docs:
                    if not self._within_date_window(
                        manifest_doc.filing_date,
                        req.start_date,
                        req.end_date,
                    ):
                        continue
                    _, chunk_count = self._ingest_manifest_document(
                        company,
                        manifest_doc,
                        acquisition_log_id=sync_event_id,
                    )
                    ingested_docs += 1
                    ingested_chunks += chunk_count

                docs = self.list_documents(company_id=req.company_id)
                details = (
                    f"Manifest sync completed from {req.manifest_path}. "
                    f"Ingested {ingested_docs} document(s) and {ingested_chunks} chunk(s). "
                    f"Window: {req.start_date or 'open'} to {req.end_date or 'open'}."
                )

            event = build_acquisition_event(
                event_id=sync_event_id,
                company_id=req.company_id,
                source_url="https://www.cninfo.com.cn",
                file_hash=docs[0].file_hash if docs else "",
                outcome="ok",
                details=details,
            )
            self._repository.append_acquisition_event(event)
            return CninfoSyncResponse(
                events=[event],
                documents=docs,
                ingested_chunks=ingested_chunks,
            )


def create_default_service() -> ChinaLensService:
    """Factory used by API startup."""
    seed_fixtures = True
    seed_env = os.environ.get("EDGARPACK_CHINA_SEED_FIXTURES")
    if seed_env is not None:
        seed_fixtures = seed_env.strip().lower() not in {"0", "false", "no"}
    return ChinaLensService(seed_fixtures=seed_fixtures)
