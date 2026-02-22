"""Evidence retrieval routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from edgarpack.api.dependencies import get_service
from edgarpack.china.models import SearchEvidenceRequest, SearchEvidenceResponse
from edgarpack.china.service import ChinaLensService

router = APIRouter(prefix="/evidence", tags=["evidence"])


@router.post("/search", response_model=SearchEvidenceResponse)
def search_evidence(
    request: SearchEvidenceRequest,
    service: ChinaLensService = Depends(get_service),
) -> SearchEvidenceResponse:
    """Search indexed evidence chunks with provenance-aware response payload."""
    return service.search_evidence(request)
