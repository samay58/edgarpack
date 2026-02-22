"""Citation resolution routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from edgarpack.api.dependencies import get_service
from edgarpack.china.models import CitationResolveRequest, ResolvedCitation
from edgarpack.china.service import ChinaLensService

router = APIRouter(prefix="/citations", tags=["citations"])


@router.post("/resolve", response_model=ResolvedCitation)
def resolve_citation(
    request: CitationResolveRequest,
    service: ChinaLensService = Depends(get_service),
) -> ResolvedCitation:
    """Resolve a citation target to doc/page/snippet details."""
    try:
        return service.resolve_citation(request.chunk_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
