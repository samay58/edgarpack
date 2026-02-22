"""FastAPI application entry point for China Lens."""

from __future__ import annotations

from importlib.util import find_spec
from typing import Any

from edgarpack.china.service import create_default_service


def _require_fastapi() -> Any:
    if find_spec("fastapi") is None:
        raise RuntimeError(
            "FastAPI is not installed. Install China Lens extras with: uv pip install -e '.[china]'"
        )
    from fastapi import FastAPI

    return FastAPI


def create_app() -> Any:
    """Create and configure the FastAPI app."""
    fastapi_cls = _require_fastapi()

    from .routes import (
        ask_router,
        citations_router,
        companies_router,
        connectors_router,
        documents_router,
        evidence_router,
        packs_router,
    )

    app = fastapi_cls(
        title="Rogo China Lens API",
        version="0.1.0",
        summary="Citation-backed research API for Chinese primary sources.",
    )
    app.state.china_service = create_default_service()

    @app.get("/healthz", tags=["infra"])
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    api_prefix = "/api/v1"
    app.include_router(companies_router, prefix=api_prefix)
    app.include_router(packs_router, prefix=api_prefix)
    app.include_router(documents_router, prefix=api_prefix)
    app.include_router(evidence_router, prefix=api_prefix)
    app.include_router(ask_router, prefix=api_prefix)
    app.include_router(citations_router, prefix=api_prefix)
    app.include_router(connectors_router, prefix=api_prefix)
    return app


app = create_app() if find_spec("fastapi") is not None else None
