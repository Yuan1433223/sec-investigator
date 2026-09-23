"""
FastAPI application factory.

No module-level singletons — CLAUDE.md hard rule 4.
Import and call create_app() to get the configured FastAPI instance.

Startup:
  uv run sec-investigator              # via project script
  uv run uvicorn surfaces.api.app:app --reload   # dev
"""
from __future__ import annotations

from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from surfaces.api.investigation import router as investigation_router
from surfaces.webhook.router import router as grafana_webhook_router

# Built web frontend (Vite) lives at <repo>/web/dist. Surface stays thin: the
# app serves it only when the build exists; API routes always take precedence.
_WEB_DIST = Path(__file__).resolve().parents[3] / "web" / "dist"


def create_app() -> FastAPI:
    app = FastAPI(title="sec-investigator", version="0.1.0")
    app.include_router(investigation_router)
    app.include_router(grafana_webhook_router)

    _mount_web(app)
    return app


def _mount_web(app: FastAPI) -> None:
    """Serve the built SPA (web/dist) with an index.html fallback, if present."""
    if not (_WEB_DIST / "index.html").exists():
        return
    assets = _WEB_DIST / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str) -> FileResponse:
        candidate = _WEB_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(_WEB_DIST / "index.html"))


# Module-level app instance for uvicorn direct use
app = create_app()


def _serve() -> None:
    """Entry point for `uv run sec-investigator`."""
    uvicorn.run(
        "surfaces.api.app:app",
        host="0.0.0.0",
        port=18230,
        reload=False,
        log_level="info",
    )
