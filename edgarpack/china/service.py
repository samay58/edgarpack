"""In-memory China Lens service for MVP vertical slice.

This service exposes deterministic behavior suitable for local development,
contract testing, and UI integration before database wiring is introduced.
"""

from __future__ import annotations

from collections import defaultdict
from threading import RLock
from uuid import uuid4

from .acquire.cninfo import build_acquisition_event, document_from_cninfo
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
from .synthesis.pack_builder import (
    build_empty_sections,
    citation_label,
    inject_findings,
    make_citation,
)


class ChinaLensService:
    """Stateful service that powers API routes for the MVP."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._companies: dict[str, Company] = {}
        self._documents: dict[str, Document] = {}
        self._chunks: dict[str, EvidenceChunk] = {}
        self._chunks_by_doc: dict[str, list[str]] = defaultdict(list)
        self._packs: dict[str, Pack] = {}
        self._jobs: dict[str, PackJob] = {}
        self._jobs_by_pack: dict[str, str] = {}
        self._acquisition_events: list = []
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
        self._companies[company.id] = company

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
        self._documents[doc_annual.id] = doc_annual
        self._documents[doc_interim.id] = doc_interim

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
            self._chunks[chunk.id] = chunk
            self._chunks_by_doc[chunk.doc_id].append(chunk.id)

        seed_event = build_acquisition_event(
            event_id=evt_id,
            company_id=company.id,
            source_url=doc_annual.source_url,
            file_hash=doc_annual.file_hash,
            outcome="cached",
            details="Seeded fixture filing metadata for local China Lens development.",
        )
        self._acquisition_events.append(seed_event)

    def list_companies(self) -> list[Company]:
        with self._lock:
            return sorted(self._companies.values(), key=lambda company: company.display_name_en)

    def list_documents(self, company_id: str | None = None) -> list[Document]:
        with self._lock:
            docs = list(self._documents.values())
            if company_id:
                docs = [doc for doc in docs if doc.company_id == company_id]
            docs.sort(key=lambda doc: doc.filing_date, reverse=True)
            return docs

    def get_document(self, doc_id: str) -> Document:
        with self._lock:
            if doc_id not in self._documents:
                raise KeyError(f"Unknown document: {doc_id}")
            return self._documents[doc_id]

    def get_document_page(self, doc_id: str, page: int) -> DocumentPageResponse:
        with self._lock:
            doc = self.get_document(doc_id)
            snippets = [
                chunk
                for chunk_id in self._chunks_by_doc.get(doc_id, [])
                for chunk in [self._chunks[chunk_id]]
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
                image_url=f"{doc.source_url}#page={page}",
            )

    def create_pack_job(self, req: CreatePackRequest) -> CreatePackResponse:
        with self._lock:
            if req.company_id not in self._companies:
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

            self._packs[pack.id] = pack
            self._jobs[job.id] = job
            self._jobs_by_pack[pack.id] = job.id

            return CreatePackResponse(pack_id=pack.id, job_id=job.id, status=pack.status)

    def _build_fixture_findings(self, pack: Pack) -> list[Finding]:
        tencent_label = citation_label("CNINFO", "2024", 87, table="Table 12")
        risk_label = citation_label("CNINFO", "2024", 15)
        governance_label = citation_label("CNINFO", "2024", 121)

        findings = [
            Finding(
                id=f"finding_{uuid4().hex[:10]}",
                pack_id=pack.id,
                section_id="customers_suppliers",
                claim_text=(
                    "Top five customers represented 24.3% of revenue; customer names "
                    "were not disclosed."
                ),
                claim_type="customer_concentration",
                key_numbers=["24.3%"],
                citations=[
                    make_citation(
                        "chunk_top_customers", "doc_tencent_2024_annual", 87, tencent_label
                    )
                ],
                status=FindingStatus.SUPPORTED,
            ),
            Finding(
                id=f"finding_{uuid4().hex[:10]}",
                pack_id=pack.id,
                section_id="risk_register",
                claim_text=(
                    "Regulatory policy changes may affect commercialization cadence in "
                    "value-added services."
                ),
                claim_type="regulatory_risk",
                citations=[
                    make_citation(
                        "chunk_risk_regulation", "doc_tencent_2024_interim", 15, risk_label
                    )
                ],
                status=FindingStatus.SUPPORTED,
            ),
            Finding(
                id=f"finding_{uuid4().hex[:10]}",
                pack_id=pack.id,
                section_id="ownership_governance",
                claim_text="The board has nine directors, including four independent directors.",
                claim_type="governance_structure",
                key_numbers=["9", "4"],
                citations=[
                    make_citation(
                        "chunk_governance", "doc_tencent_2024_annual", 121, governance_label
                    )
                ],
                status=FindingStatus.SUPPORTED,
            ),
            Finding(
                id=f"finding_{uuid4().hex[:10]}",
                pack_id=pack.id,
                section_id="summary",
                claim_text="Management disclosed confidence in long-term cloud demand.",
                claim_type="management_outlook",
                citations=[],
                status=FindingStatus.SUPPORTED,
            ),
        ]
        return findings

    def _finalize_pack(self, pack_id: str) -> None:
        pack = self.get_pack(pack_id)
        findings = self._build_fixture_findings(pack)
        inject_findings(pack, findings)

        report = run_publish_checks(pack, chunks_by_id=self._chunks, min_citations_per_section=2)
        pack.updated_at = utc_now()

        if report.passed:
            pack.status = PackStatus.READY
            pack.build_logs.append("Pack QA checks passed.")
        else:
            pack.status = PackStatus.PARTIAL
            pack.errors.extend(issue.message for issue in report.issues)
            pack.build_logs.append(
                "Pack QA checks reported "
                f"{len(report.issues)} issue(s); unsupported findings were flagged."
            )

        for section in pack.sections:
            if section.id == "summary" and not section.unknowns:
                section.unknowns.append("Not disclosed: named top customers in annual filing")
            section.updated_at = utc_now()

    def _get_job_by_pack(self, pack_id: str) -> PackJob:
        if pack_id not in self._jobs_by_pack:
            raise KeyError(f"Unknown pack: {pack_id}")
        job_id = self._jobs_by_pack[pack_id]
        return self._jobs[job_id]

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
            return job

    def get_pack(self, pack_id: str) -> Pack:
        if pack_id not in self._packs:
            raise KeyError(f"Unknown pack: {pack_id}")
        return self._packs[pack_id]

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
            chunks = list(self._chunks.values())
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
            if chunk_id not in self._chunks:
                raise KeyError(f"Unknown chunk: {chunk_id}")
            chunk = self._chunks[chunk_id]
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

        question_lc = req.question.lower()
        blocks: list[AskAnswerBlock] = []

        if "customer" in question_lc or "concentration" in question_lc:
            customer_hits = [hit for hit in search.hits if "customer" in hit.text_en.lower()]
            if customer_hits:
                refs = [
                    CitationRef(
                        chunk_id=hit.chunk_id,
                        doc_id=hit.doc_id,
                        page=hit.page,
                        quote_start=0,
                        quote_end=0,
                        citation_label=hit.citation_label,
                    )
                    for hit in customer_hits[:2]
                ]
                blocks.append(
                    AskAnswerBlock(
                        text=(
                            "Top customer concentration is disclosed as 24.3% for the "
                            "top five customers, "
                            "and customer names are not disclosed by name."
                        ),
                        citations=refs,
                    )
                )

        if not blocks:
            top = search.hits[0]
            blocks.append(
                AskAnswerBlock(
                    text=f"Best available evidence: {top.text_en}",
                    citations=[
                        CitationRef(
                            chunk_id=top.chunk_id,
                            doc_id=top.doc_id,
                            page=top.page,
                            quote_start=0,
                            quote_end=0,
                            citation_label=top.citation_label,
                        )
                    ],
                )
            )

        return AskResponse(
            answer=blocks,
            not_found=False,
            guidance="Open citations to verify the original Chinese source in Evidence Explorer.",
        )

    def cninfo_sync(self, req: CninfoSyncRequest) -> CninfoSyncResponse:
        with self._lock:
            if req.company_id not in self._companies:
                raise KeyError(f"Unknown company: {req.company_id}")

            docs = self.list_documents(company_id=req.company_id)
            event = build_acquisition_event(
                event_id=f"acq_{uuid4().hex[:10]}",
                company_id=req.company_id,
                source_url="https://www.cninfo.com.cn",
                file_hash=docs[0].file_hash if docs else "",
                outcome="ok",
                details=(
                    "Connector sync completed. "
                    f"Window: {req.start_date or 'open'} to {req.end_date or 'open'}."
                ),
            )
            self._acquisition_events.append(event)
            return CninfoSyncResponse(events=[event], documents=docs)


def create_default_service() -> ChinaLensService:
    """Factory used by API startup."""
    return ChinaLensService()
