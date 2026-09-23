"""
FastAPI application factory.

No module-level singletons — CLAUDE.md hard rule 4.
Import and call create_app() to get the configured FastAPI instance.

Startup:
  uv run kks-serve              # via project script
  uv run uvicorn kks_surfaces.api.app:app --reload   # dev
"""
from __future__ import annotations

import uvicorn
from fastapi import FastAPI

from kks_surfaces.api.investigation import router as investigation_router
from kks_surfaces.webhook.router import router as grafana_webhook_router


def create_app() -> FastAPI:
    app = FastAPI(title="kks-next", version="0.1.0")
    app.include_router(investigation_router)
    app.include_router(grafana_webhook_router)
    return app


# Module-level app instance for uvicorn direct use
app = create_app()


def _serve() -> None:
    """Entry point for `uv run kks-serve`."""
    uvicorn.run(
        "kks_surfaces.api.app:app",
        host="0.0.0.0",
        port=18230,
        reload=False,
        log_level="info",
    )
