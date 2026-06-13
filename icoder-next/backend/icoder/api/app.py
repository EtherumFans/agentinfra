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
from fastapi.staticfiles import StaticFiles

from ..runtime.store import RunStore
from .routes_agentic import router as agentic_router
from .routes_coding_review import router as coding_router

FRONTEND_DIR = Path(__file__).resolve().parents[3] / "frontend"


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
    app.include_router(agentic_router)

    @app.get("/healthz", tags=["meta"])
    def healthz():
        return {"ok": True, "service": "icoder-next", "version": "0.1.0"}

    # Static frontend last, so API routes win. html=True serves index.html at "/".
    if FRONTEND_DIR.exists():
        app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

    return app


app = create_app()
