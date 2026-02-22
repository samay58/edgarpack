"""FastAPI dependency helpers for China Lens API."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import Request

from edgarpack.china.service import ChinaLensService


def get_service(request: Request) -> ChinaLensService:
    """Return the shared China Lens service instance."""
    service = getattr(request.app.state, "china_service", None)
    if service is None:
        raise RuntimeError("China Lens service not configured on app state")
    return service
