"""Connector management routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from edgarpack.api.dependencies import get_service
from edgarpack.china.models import CninfoSyncRequest, CninfoSyncResponse
from edgarpack.china.service import ChinaLensService

router = APIRouter(prefix="/connectors", tags=["connectors"])


@router.post("/cninfo/sync", response_model=CninfoSyncResponse)
def sync_cninfo(
    request: CninfoSyncRequest,
    service: ChinaLensService = Depends(get_service),
) -> CninfoSyncResponse:
    """Run CNINFO sync and return logged acquisition events."""
    try:
        return service.cninfo_sync(request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
