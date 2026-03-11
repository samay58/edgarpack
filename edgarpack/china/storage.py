"""Persistence and object-store adapters for China Lens.

The service layer should not own storage details directly. This module provides
small repository/object-store interfaces plus concrete adapters for:

- in-memory state (default for tests and local dev)
- JSON-file persistence (durable local backend)
- PostgreSQL JSONB persistence (production-oriented backend, optional dependency)
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

from .models import AcquisitionEvent, Company, Document, EvidenceChunk, Pack, PackJob

_ModelT = TypeVar("_ModelT", bound=BaseModel)


class ObjectStore(Protocol):
    """Binary object store contract."""

    def put_bytes(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Store bytes under a stable key and return a storage URI."""

    def put_file(self, local_path: str, key: str) -> str:
        """Store a local file under a stable key and return a storage URI."""

    def get_bytes(self, key: str) -> bytes:
        """Read a stored object."""

    def exists(self, key: str) -> bool:
        """Check whether a stored object exists."""


class MemoryObjectStore:
    """In-memory object store for tests and default local workflows."""

    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}

    def put_bytes(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        del content_type
        self._objects[key] = data
        return f"memory://{key}"

    def put_file(self, local_path: str, key: str) -> str:
        data = Path(local_path).read_bytes()
        return self.put_bytes(key, data)

    def get_bytes(self, key: str) -> bytes:
        if key not in self._objects:
            raise KeyError(f"Unknown object key: {key}")
        return self._objects[key]

    def exists(self, key: str) -> bool:
        return key in self._objects


class LocalObjectStore:
    """Filesystem-backed object store for durable local workflows."""

    def __init__(self, root_dir: str) -> None:
        self._root = Path(root_dir).expanduser().resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def put_bytes(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        del content_type
        target = self._root / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return str(target)

    def put_file(self, local_path: str, key: str) -> str:
        target = self._root / key
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_path, target)
        return str(target)

    def get_bytes(self, key: str) -> bytes:
        target = self._root / key
        return target.read_bytes()

    def exists(self, key: str) -> bool:
        return (self._root / key).exists()


class ChinaLensRepository(Protocol):
    """Repository contract used by ChinaLensService."""

    def list_companies(self) -> list[Company]:
        """List all known companies."""

    def get_company(self, company_id: str) -> Company | None:
        """Fetch one company."""

    def upsert_company(self, company: Company) -> None:
        """Insert or update a company."""

    def list_documents(self, company_id: str | None = None) -> list[Document]:
        """List documents, optionally filtered by company."""

    def get_document(self, doc_id: str) -> Document | None:
        """Fetch one document."""

    def upsert_document(self, doc: Document) -> None:
        """Insert or update a document."""

    def delete_documents_for_company(self, company_id: str) -> list[str]:
        """Delete all documents for a company and return removed doc IDs."""

    def list_chunks(self, doc_id: str | None = None) -> list[EvidenceChunk]:
        """List evidence chunks, optionally filtered by document."""

    def get_chunk(self, chunk_id: str) -> EvidenceChunk | None:
        """Fetch one evidence chunk."""

    def upsert_chunk(self, chunk: EvidenceChunk) -> None:
        """Insert or update a chunk."""

    def delete_chunks_for_doc(self, doc_id: str) -> list[str]:
        """Delete chunks for one document and return removed chunk IDs."""

    def get_pack(self, pack_id: str) -> Pack | None:
        """Fetch one pack."""

    def upsert_pack(self, pack: Pack) -> None:
        """Insert or update a pack."""

    def get_job(self, job_id: str) -> PackJob | None:
        """Fetch one job."""

    def upsert_job(self, job: PackJob) -> None:
        """Insert or update a job."""

    def get_job_by_pack(self, pack_id: str) -> PackJob | None:
        """Fetch the job linked to one pack."""

    def set_job_for_pack(self, pack_id: str, job_id: str) -> None:
        """Link a pack to its job."""

    def append_acquisition_event(self, event: AcquisitionEvent) -> None:
        """Append an acquisition event."""

    def list_acquisition_events(
        self, company_id: str | None = None
    ) -> list[AcquisitionEvent]:
        """List acquisition events, optionally filtered by company."""


class _DictBackedRepository:
    """Shared dict-backed repository behavior."""

    def __init__(self) -> None:
        self._companies: dict[str, Company] = {}
        self._documents: dict[str, Document] = {}
        self._chunks: dict[str, EvidenceChunk] = {}
        self._chunks_by_doc: dict[str, list[str]] = {}
        self._packs: dict[str, Pack] = {}
        self._jobs: dict[str, PackJob] = {}
        self._jobs_by_pack: dict[str, str] = {}
        self._acquisition_events: list[AcquisitionEvent] = []

    def _on_write(self) -> None:
        """Hook for durable adapters."""

    def list_companies(self) -> list[Company]:
        return list(self._companies.values())

    def get_company(self, company_id: str) -> Company | None:
        return self._companies.get(company_id)

    def upsert_company(self, company: Company) -> None:
        self._companies[company.id] = company
        self._on_write()

    def list_documents(self, company_id: str | None = None) -> list[Document]:
        docs = list(self._documents.values())
        if company_id:
            docs = [doc for doc in docs if doc.company_id == company_id]
        return docs

    def get_document(self, doc_id: str) -> Document | None:
        return self._documents.get(doc_id)

    def upsert_document(self, doc: Document) -> None:
        self._documents[doc.id] = doc
        self._on_write()

    def delete_documents_for_company(self, company_id: str) -> list[str]:
        doc_ids = [doc.id for doc in self._documents.values() if doc.company_id == company_id]
        for doc_id in doc_ids:
            self._documents.pop(doc_id, None)
        self._on_write()
        return doc_ids

    def list_chunks(self, doc_id: str | None = None) -> list[EvidenceChunk]:
        if doc_id is None:
            return list(self._chunks.values())
        return [self._chunks[chunk_id] for chunk_id in self._chunks_by_doc.get(doc_id, [])]

    def get_chunk(self, chunk_id: str) -> EvidenceChunk | None:
        return self._chunks.get(chunk_id)

    def upsert_chunk(self, chunk: EvidenceChunk) -> None:
        existing = self._chunks.get(chunk.id)
        if existing and existing.doc_id != chunk.doc_id:
            prior_ids = self._chunks_by_doc.get(existing.doc_id, [])
            self._chunks_by_doc[existing.doc_id] = [cid for cid in prior_ids if cid != chunk.id]
        self._chunks[chunk.id] = chunk
        doc_chunk_ids = self._chunks_by_doc.setdefault(chunk.doc_id, [])
        if chunk.id not in doc_chunk_ids:
            doc_chunk_ids.append(chunk.id)
        self._on_write()

    def delete_chunks_for_doc(self, doc_id: str) -> list[str]:
        chunk_ids = list(self._chunks_by_doc.pop(doc_id, []))
        for chunk_id in chunk_ids:
            self._chunks.pop(chunk_id, None)
        self._on_write()
        return chunk_ids

    def get_pack(self, pack_id: str) -> Pack | None:
        return self._packs.get(pack_id)

    def upsert_pack(self, pack: Pack) -> None:
        self._packs[pack.id] = pack
        self._on_write()

    def get_job(self, job_id: str) -> PackJob | None:
        return self._jobs.get(job_id)

    def upsert_job(self, job: PackJob) -> None:
        self._jobs[job.id] = job
        self._on_write()

    def get_job_by_pack(self, pack_id: str) -> PackJob | None:
        job_id = self._jobs_by_pack.get(pack_id)
        if not job_id:
            return None
        return self._jobs.get(job_id)

    def set_job_for_pack(self, pack_id: str, job_id: str) -> None:
        self._jobs_by_pack[pack_id] = job_id
        self._on_write()

    def append_acquisition_event(self, event: AcquisitionEvent) -> None:
        self._acquisition_events.append(event)
        self._on_write()

    def list_acquisition_events(
        self, company_id: str | None = None
    ) -> list[AcquisitionEvent]:
        if company_id is None:
            return list(self._acquisition_events)
        return [event for event in self._acquisition_events if event.company_id == company_id]


class InMemoryChinaLensRepository(_DictBackedRepository):
    """Ephemeral repository for tests and local development."""


class JsonFileChinaLensRepository(_DictBackedRepository):
    """Durable local repository backed by JSON files."""

    def __init__(self, root_dir: str) -> None:
        super().__init__()
        self._root = Path(root_dir).expanduser().resolve()
        self._root.mkdir(parents=True, exist_ok=True)
        self._load()

    def _path(self, name: str) -> Path:
        return self._root / f"{name}.json"

    def _load_model_map(self, name: str, model_type: type[_ModelT]) -> dict[str, _ModelT]:
        path = self._path(name)
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return {item["id"]: model_type.model_validate(item) for item in payload}

    def _load_model_list(self, name: str, model_type: type[_ModelT]) -> list[_ModelT]:
        path = self._path(name)
        if not path.exists():
            return []
        payload = json.loads(path.read_text(encoding="utf-8"))
        return [model_type.model_validate(item) for item in payload]

    def _write_json(self, name: str, payload: Any) -> None:
        self._path(name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _load(self) -> None:
        self._companies = self._load_model_map("companies", Company)
        self._documents = self._load_model_map("documents", Document)
        self._chunks = self._load_model_map("chunks", EvidenceChunk)
        self._packs = self._load_model_map("packs", Pack)
        self._jobs = self._load_model_map("jobs", PackJob)
        self._acquisition_events = self._load_model_list("acquisition_events", AcquisitionEvent)

        jobs_by_pack_path = self._path("jobs_by_pack")
        if jobs_by_pack_path.exists():
            self._jobs_by_pack = json.loads(jobs_by_pack_path.read_text(encoding="utf-8"))

        chunks_by_doc_path = self._path("chunks_by_doc")
        if chunks_by_doc_path.exists():
            payload = json.loads(chunks_by_doc_path.read_text(encoding="utf-8"))
            self._chunks_by_doc = {doc_id: list(chunk_ids) for doc_id, chunk_ids in payload.items()}

    def _on_write(self) -> None:
        self._write_json(
            "companies",
            [company.model_dump(mode="json") for company in self._companies.values()],
        )
        self._write_json(
            "documents",
            [doc.model_dump(mode="json") for doc in self._documents.values()],
        )
        self._write_json(
            "chunks",
            [chunk.model_dump(mode="json") for chunk in self._chunks.values()],
        )
        self._write_json(
            "packs",
            [pack.model_dump(mode="json") for pack in self._packs.values()],
        )
        self._write_json(
            "jobs",
            [job.model_dump(mode="json") for job in self._jobs.values()],
        )
        self._write_json("jobs_by_pack", self._jobs_by_pack)
        self._write_json("chunks_by_doc", self._chunks_by_doc)
        self._write_json(
            "acquisition_events",
            [event.model_dump(mode="json") for event in self._acquisition_events],
        )


class PostgresChinaLensRepository:
    """PostgreSQL JSONB repository.

    The current China Lens stack still uses lexical ranking in Python, so this
    adapter persists embeddings but does not yet issue pgvector similarity
    queries. It still attempts to enable the extension so later upgrades remain
    additive instead of structural.
    """

    def __init__(self, dsn: str) -> None:
        if not dsn:
            raise ValueError("Postgres DSN is required for the postgres repository backend")
        self._dsn = dsn
        self._psycopg = self._load_driver()
        self._ensure_schema()

    @staticmethod
    def _load_driver() -> Any:
        try:
            import psycopg  # type: ignore[import-not-found]
        except Exception as exc:
            raise RuntimeError(
                "psycopg is required for the postgres China Lens backend. "
                "Install with: uv pip install 'psycopg[binary]>=3.2'"
            ) from exc
        return psycopg

    def _connect(self) -> Any:
        return self._psycopg.connect(self._dsn)

    def _ensure_schema(self) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS china_companies (
                id TEXT PRIMARY KEY,
                payload JSONB NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS china_documents (
                id TEXT PRIMARY KEY,
                company_id TEXT NOT NULL,
                filing_date TEXT NOT NULL,
                payload JSONB NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS china_chunks (
                id TEXT PRIMARY KEY,
                doc_id TEXT NOT NULL,
                page_start INTEGER NOT NULL,
                payload JSONB NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS china_packs (
                id TEXT PRIMARY KEY,
                company_id TEXT NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL,
                payload JSONB NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS china_jobs (
                id TEXT PRIMARY KEY,
                pack_id TEXT NOT NULL,
                status TEXT NOT NULL,
                payload JSONB NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS china_pack_jobs (
                pack_id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS china_acquisition_events (
                id TEXT PRIMARY KEY,
                company_id TEXT NOT NULL,
                occurred_at TIMESTAMPTZ NOT NULL,
                payload JSONB NOT NULL
            )
            """,
            (
                "CREATE INDEX IF NOT EXISTS idx_china_documents_company_id "
                "ON china_documents(company_id)"
            ),
            "CREATE INDEX IF NOT EXISTS idx_china_chunks_doc_id ON china_chunks(doc_id)",
            "CREATE INDEX IF NOT EXISTS idx_china_jobs_pack_id ON china_jobs(pack_id)",
            "CREATE INDEX IF NOT EXISTS idx_china_packs_company_id ON china_packs(company_id)",
            (
                "CREATE INDEX IF NOT EXISTS idx_china_acquisition_events_company_id "
                "ON china_acquisition_events(company_id)"
            ),
        ]

        with self._connect() as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                except Exception:
                    conn.rollback()
                for statement in statements:
                    cur.execute(statement)
            conn.commit()

    @staticmethod
    def _payload(model: BaseModel) -> str:
        return json.dumps(model.model_dump(mode="json"), ensure_ascii=False)

    @staticmethod
    def _hydrate(model_type: type[_ModelT], payload: Any) -> _ModelT:
        if isinstance(payload, str):
            return model_type.model_validate_json(payload)
        return model_type.model_validate(payload)

    def list_companies(self) -> list[Company]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT payload FROM china_companies")
                return [self._hydrate(Company, row[0]) for row in cur.fetchall()]

    def get_company(self, company_id: str) -> Company | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT payload FROM china_companies WHERE id = %s", (company_id,))
                row = cur.fetchone()
                return self._hydrate(Company, row[0]) if row else None

    def upsert_company(self, company: Company) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO china_companies (id, payload)
                    VALUES (%s, %s::jsonb)
                    ON CONFLICT (id) DO UPDATE SET payload = EXCLUDED.payload
                    """,
                    (company.id, self._payload(company)),
                )
            conn.commit()

    def list_documents(self, company_id: str | None = None) -> list[Document]:
        sql = "SELECT payload FROM china_documents"
        params: tuple[Any, ...] = ()
        if company_id:
            sql += " WHERE company_id = %s"
            params = (company_id,)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return [self._hydrate(Document, row[0]) for row in cur.fetchall()]

    def get_document(self, doc_id: str) -> Document | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT payload FROM china_documents WHERE id = %s", (doc_id,))
                row = cur.fetchone()
                return self._hydrate(Document, row[0]) if row else None

    def upsert_document(self, doc: Document) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO china_documents (id, company_id, filing_date, payload)
                    VALUES (%s, %s, %s, %s::jsonb)
                    ON CONFLICT (id) DO UPDATE SET
                        company_id = EXCLUDED.company_id,
                        filing_date = EXCLUDED.filing_date,
                        payload = EXCLUDED.payload
                    """,
                    (doc.id, doc.company_id, doc.filing_date, self._payload(doc)),
                )
            conn.commit()

    def delete_documents_for_company(self, company_id: str) -> list[str]:
        docs = self.list_documents(company_id=company_id)
        if not docs:
            return []
        doc_ids = [doc.id for doc in docs]
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM china_documents WHERE company_id = %s", (company_id,))
            conn.commit()
        return doc_ids

    def list_chunks(self, doc_id: str | None = None) -> list[EvidenceChunk]:
        sql = "SELECT payload FROM china_chunks"
        params: tuple[Any, ...] = ()
        if doc_id:
            sql += " WHERE doc_id = %s"
            params = (doc_id,)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return [self._hydrate(EvidenceChunk, row[0]) for row in cur.fetchall()]

    def get_chunk(self, chunk_id: str) -> EvidenceChunk | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT payload FROM china_chunks WHERE id = %s", (chunk_id,))
                row = cur.fetchone()
                return self._hydrate(EvidenceChunk, row[0]) if row else None

    def upsert_chunk(self, chunk: EvidenceChunk) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO china_chunks (id, doc_id, page_start, payload)
                    VALUES (%s, %s, %s, %s::jsonb)
                    ON CONFLICT (id) DO UPDATE SET
                        doc_id = EXCLUDED.doc_id,
                        page_start = EXCLUDED.page_start,
                        payload = EXCLUDED.payload
                    """,
                    (chunk.id, chunk.doc_id, chunk.page_start, self._payload(chunk)),
                )
            conn.commit()

    def delete_chunks_for_doc(self, doc_id: str) -> list[str]:
        chunks = self.list_chunks(doc_id=doc_id)
        if not chunks:
            return []
        chunk_ids = [chunk.id for chunk in chunks]
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM china_chunks WHERE doc_id = %s", (doc_id,))
            conn.commit()
        return chunk_ids

    def get_pack(self, pack_id: str) -> Pack | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT payload FROM china_packs WHERE id = %s", (pack_id,))
                row = cur.fetchone()
                return self._hydrate(Pack, row[0]) if row else None

    def upsert_pack(self, pack: Pack) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO china_packs (id, company_id, updated_at, payload)
                    VALUES (%s, %s, %s, %s::jsonb)
                    ON CONFLICT (id) DO UPDATE SET
                        company_id = EXCLUDED.company_id,
                        updated_at = EXCLUDED.updated_at,
                        payload = EXCLUDED.payload
                    """,
                    (pack.id, pack.company_id, pack.updated_at, self._payload(pack)),
                )
            conn.commit()

    def get_job(self, job_id: str) -> PackJob | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT payload FROM china_jobs WHERE id = %s", (job_id,))
                row = cur.fetchone()
                return self._hydrate(PackJob, row[0]) if row else None

    def upsert_job(self, job: PackJob) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO china_jobs (id, pack_id, status, payload)
                    VALUES (%s, %s, %s, %s::jsonb)
                    ON CONFLICT (id) DO UPDATE SET
                        pack_id = EXCLUDED.pack_id,
                        status = EXCLUDED.status,
                        payload = EXCLUDED.payload
                    """,
                    (job.id, job.pack_id, job.status.value, self._payload(job)),
                )
            conn.commit()

    def get_job_by_pack(self, pack_id: str) -> PackJob | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT j.payload
                    FROM china_pack_jobs pj
                    JOIN china_jobs j ON j.id = pj.job_id
                    WHERE pj.pack_id = %s
                    """,
                    (pack_id,),
                )
                row = cur.fetchone()
                return self._hydrate(PackJob, row[0]) if row else None

    def set_job_for_pack(self, pack_id: str, job_id: str) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO china_pack_jobs (pack_id, job_id)
                    VALUES (%s, %s)
                    ON CONFLICT (pack_id) DO UPDATE SET job_id = EXCLUDED.job_id
                    """,
                    (pack_id, job_id),
                )
            conn.commit()

    def append_acquisition_event(self, event: AcquisitionEvent) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO china_acquisition_events (id, company_id, occurred_at, payload)
                    VALUES (%s, %s, %s, %s::jsonb)
                    ON CONFLICT (id) DO UPDATE SET
                        company_id = EXCLUDED.company_id,
                        occurred_at = EXCLUDED.occurred_at,
                        payload = EXCLUDED.payload
                    """,
                    (event.id, event.company_id, event.occurred_at, self._payload(event)),
                )
            conn.commit()

    def list_acquisition_events(
        self, company_id: str | None = None
    ) -> list[AcquisitionEvent]:
        sql = "SELECT payload FROM china_acquisition_events"
        params: tuple[Any, ...] = ()
        if company_id:
            sql += " WHERE company_id = %s"
            params = (company_id,)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return [self._hydrate(AcquisitionEvent, row[0]) for row in cur.fetchall()]


def create_default_object_store() -> ObjectStore:
    """Create the default object-store adapter from environment variables."""
    root_dir = os.environ.get("EDGARPACK_CHINA_OBJECT_STORE_DIR")
    if root_dir:
        return LocalObjectStore(root_dir)
    return MemoryObjectStore()


def create_default_repository() -> ChinaLensRepository:
    """Create the default repository adapter from environment variables."""
    backend = os.environ.get("EDGARPACK_CHINA_STORAGE_BACKEND", "").strip().lower()
    if not backend:
        if os.environ.get("EDGARPACK_CHINA_POSTGRES_DSN"):
            backend = "postgres"
        elif os.environ.get("EDGARPACK_CHINA_STORAGE_DIR"):
            backend = "json"
        else:
            backend = "memory"

    if backend == "memory":
        return InMemoryChinaLensRepository()
    if backend == "json":
        root_dir = os.environ.get("EDGARPACK_CHINA_STORAGE_DIR")
        if not root_dir:
            raise ValueError("EDGARPACK_CHINA_STORAGE_DIR is required for json backend")
        return JsonFileChinaLensRepository(root_dir)
    if backend == "postgres":
        dsn = os.environ.get("EDGARPACK_CHINA_POSTGRES_DSN", "")
        return PostgresChinaLensRepository(dsn)
    raise ValueError(f"Unknown China Lens storage backend: {backend}")
