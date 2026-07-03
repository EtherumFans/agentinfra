"""FastAPI app — single on-prem process that serves the API *and* the embeddable
frontend (icoder-embedded component + demo + llms.txt + .well-known/agent-skills),
mirroring the hospital "one server" deployment story.

Run:  uvicorn icoder.api.app:app --port 8000   (from the backend/ dir)
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from ..runtime.store import RunStore
from .routes_agent_run import router as agent_run_router
from .routes_agentic import router as agentic_router
from .routes_coding_lookup import router as coding_lookup_router
from .routes_coding_review import router as coding_router

FRONTEND_DIR = Path(__file__).resolve().parents[3] / "frontend"


def _spa_dir() -> Path:
    """Serve the built React console (frontend/dist) when present, else the raw
    frontend dir (still holds the vanilla embed assets if no build has run)."""
    dist = FRONTEND_DIR / "dist"
    return dist if dist.exists() else FRONTEND_DIR


def create_app(db_path: str | None = None) -> FastAPI:
    app = FastAPI(
        title="iCoDer-next Runtime",
        version="0.1.0",
        description="医疗收入合规 AI Runtime — 端到端薄竖切 (embed → API → Runtime → 证据回链报告)",
    )
    # The embed component is loaded cross-origin by host apps; allow it.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Persistence + audit (Runtime-Core observability), injected at the API edge so
    # the runner stays DB-free. db_path: arg > ICODER_DB_PATH > backend/data/icoder.db.
    if db_path is None:
        db_path = os.environ.get("ICODER_DB_PATH")
    if db_path is None:
        data_dir = Path(__file__).resolve().parents[2] / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        db_path = str(data_dir / "icoder.db")
    app.state.store = RunStore(db_path)

    @app.on_event("shutdown")
    def _close_store():
        app.state.store.close()

    app.include_router(coding_router)
    app.include_router(coding_lookup_router)
    app.include_router(agentic_router)
    app.include_router(agent_run_router)

    @app.get("/healthz", tags=["meta"])
    def healthz():
        return {"ok": True, "service": "icoder-next", "version": "0.1.0"}

    # Static frontend last, so API routes win. A catch-all that serves real files
    # (built assets, icoder-embedded.js, llms.txt, .well-known, /embed-demo) and falls
    # back to index.html for client-side deep links (e.g. /agents/icoder/...).
    spa = _spa_dir()

    if spa.exists():

        @app.get("/{full_path:path}", include_in_schema=False)
        def serve_spa(full_path: str):
            target = (spa / full_path).resolve()
            # path-traversal guard: stay inside the frontend dir
            if spa.resolve() in target.parents or target == spa.resolve():
                if target.is_dir():
                    target = target / "index.html"
                if target.is_file():
                    return FileResponse(target)
            return FileResponse(spa / "index.html")

    return app


app = create_app()
