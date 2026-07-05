"""FastAPI application entry point for the Observatory API.

The China Lens Evidence Explorer routers that used to mount here were
removed with the parked workspace (docs/STREAMLINE-PLAN.md, Phase 1).
"""

from __future__ import annotations

from importlib.util import find_spec
from typing import Any


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

    from fastapi.middleware.cors import CORSMiddleware

    from .observatory import observatory_router

    app = fastapi_cls(
        title="EdgarPack Observatory API",
        version="0.1.0",
        summary="Filing diff, timeline, and search over local packs.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/healthz", tags=["infra"])  # type: ignore[untyped-decorator]
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(observatory_router, prefix="/api/v1")
    return app


app = create_app() if find_spec("fastapi") is not None else None
