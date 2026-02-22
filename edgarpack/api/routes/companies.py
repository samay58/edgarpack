"""Company routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from edgarpack.api.dependencies import get_service
from edgarpack.china.models import Company
from edgarpack.china.service import ChinaLensService

router = APIRouter(prefix="/companies", tags=["companies"])


@router.get("", response_model=list[Company])
def list_companies(service: ChinaLensService = Depends(get_service)) -> list[Company]:
    """Return all companies available to the workspace."""
    return service.list_companies()
