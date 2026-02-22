"""Document metadata and page routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from edgarpack.api.dependencies import get_service
from edgarpack.china.models import Document, DocumentPageResponse
from edgarpack.china.service import ChinaLensService

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=list[Document])
def list_documents(
    company_id: str | None = Query(default=None),
    service: ChinaLensService = Depends(get_service),
) -> list[Document]:
    """List indexed documents, optionally scoped to one company."""
    return service.list_documents(company_id=company_id)


@router.get("/{doc_id}", response_model=Document)
def get_document(doc_id: str, service: ChinaLensService = Depends(get_service)) -> Document:
    """Return one document metadata object."""
    try:
        return service.get_document(doc_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{doc_id}/pages/{page}", response_model=DocumentPageResponse)
def get_document_page(
    doc_id: str,
    page: int,
    service: ChinaLensService = Depends(get_service),
) -> DocumentPageResponse:
    """Return one page view payload for Evidence Explorer."""
    try:
        return service.get_document_page(doc_id, page)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
