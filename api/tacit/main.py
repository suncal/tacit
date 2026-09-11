"""FastAPI application factory. `uvicorn tacit.main:app`"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .app import TacitApp
from .db import Base, engine
from .routers import auth, core, playbooks, webhooks, work
from .settings import get_settings

logging.basicConfig(level=logging.INFO, format='{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}')
log = logging.getLogger("tacit")


def create_app(tacit: TacitApp | None = None, background: bool = True) -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        Base.metadata.create_all(engine)          # alembic owns migrations; create_all is the zero-config path
        t = tacit or TacitApp(settings)
        app.state.tacit = t
        if background:
            t.start_background()
        b = t.brain_info()
        log.info("Tacit %s up — brain=%s%s db=%s", __version__, b["provider"], "" if b["llm"] else " (no LLM: local planner)", settings.database_url)
        yield
        t.stop_background()

    app = FastAPI(title="Tacit", version=__version__, lifespan=lifespan,
                  description="The AI teammate that learns your job by watching, proves it can do it, then asks to take over.",
                  docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
    for r in (auth.router, core.router, playbooks.router, work.router, webhooks.router):
        app.include_router(r, prefix="/api/v1")

    @app.get("/api/health", tags=["meta"])
    def health(request: Request):
        return {"ok": True, "version": __version__, "brain": request.app.state.tacit.brain_info()}

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        log.exception("unhandled: %s", exc)
        return JSONResponse({"detail": f"{type(exc).__name__}: {exc}"}, status_code=500)

    dist = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", settings.web_dist))
    if os.path.isdir(dist):
        app.mount("/assets", StaticFiles(directory=os.path.join(dist, "assets")), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            full = os.path.join(dist, path)
            if path and os.path.isfile(full):
                return FileResponse(full)
            return FileResponse(os.path.join(dist, "index.html"))
    return app


app = create_app()
