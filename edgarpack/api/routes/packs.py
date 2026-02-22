"""Pack creation and status routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from edgarpack.api.dependencies import get_service
from edgarpack.china.models import (
    CreatePackRequest,
    CreatePackResponse,
    Pack,
    PackStatusResponse,
)
from edgarpack.china.service import ChinaLensService

router = APIRouter(prefix="/packs", tags=["packs"])


@router.post("", response_model=CreatePackResponse)
def create_pack(
    request: CreatePackRequest,
    service: ChinaLensService = Depends(get_service),
) -> CreatePackResponse:
    """Create a pack build job."""
    try:
        return service.create_pack_job(request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{pack_id}", response_model=Pack)
def get_pack(pack_id: str, service: ChinaLensService = Depends(get_service)) -> Pack:
    """Return pack content and current section state."""
    try:
        return service.get_pack(pack_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{pack_id}/status", response_model=PackStatusResponse)
def get_pack_status(
    pack_id: str,
    service: ChinaLensService = Depends(get_service),
) -> PackStatusResponse:
    """Return staged progress, updating one deterministic tick per request."""
    try:
        return service.get_pack_status(pack_id=pack_id, auto_tick=True)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{pack_id}/cancel", response_model=PackStatusResponse)
def cancel_pack(
    pack_id: str,
    service: ChinaLensService = Depends(get_service),
) -> PackStatusResponse:
    """Cancel a running pack job."""
    try:
        service.cancel_pack_job(pack_id)
        return service.get_pack_status(pack_id=pack_id, auto_tick=False)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
