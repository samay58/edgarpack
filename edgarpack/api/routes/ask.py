"""Bounded ask route backed only by indexed evidence."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from edgarpack.api.dependencies import get_service
from edgarpack.china.models import AskRequest, AskResponse
from edgarpack.china.service import ChinaLensService

router = APIRouter(prefix="/ask", tags=["ask"])


@router.post("", response_model=AskResponse)
def ask(request: AskRequest, service: ChinaLensService = Depends(get_service)) -> AskResponse:
    """Answer a question with evidence-only responses and citations."""
    return service.ask(request)
