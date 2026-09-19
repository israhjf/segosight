"""SegoSight API and static host.

One process owns the DuckDB warehouse, serves the JSON API and, in production
mode, the built React bundle. That keeps the evaluator's path to a running
system a single command, and it is what allows the pipeline to be an action in
the product rather than a competing writer.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ..paths import REPO_ROOT
from .dependencies import close_connection, configure, get_database
from .routes import alerts, overview, pipeline, review

UI_DIST = REPO_ROOT / "ui" / "dist"

#: The Vite dev server runs on 5173 and proxies /api here; in production the
#: bundle is served from this same origin and CORS is irrelevant.
DEV_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_database()
    yield
    close_connection()


def create_app(warehouse: Path | str | None = None) -> FastAPI:
    configure(warehouse)
    app = FastAPI(
        title="SegoSight",
        description="Operational attention system for Sego Industrial Water.",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(DEV_ORIGINS),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for module in (overview, review, alerts, pipeline):
        app.include_router(module.router)

    if UI_DIST.is_dir():
        app.mount(
            "/assets", StaticFiles(directory=UI_DIST / "assets"), name="assets"
        )

        @app.get("/{full_path:path}", include_in_schema=False)
        def serve_ui(full_path: str):
            """Serve the SPA, letting client-side routing own unknown paths."""
            candidate = UI_DIST / full_path
            if full_path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(UI_DIST / "index.html")

    return app


app = create_app()
