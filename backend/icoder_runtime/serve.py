"""Local HTTP server for iCoDer Runtime.

Usage: icoder-runtime serve --port 8765
"""

import argparse
import json
import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .types import AgentDefinition, ExpertDefinition
from .agent_runner import AgentRunner
from .evidence_pack import build_evidence_pack

logger = logging.getLogger(__name__)


class RunRequest(BaseModel):
    agent: dict  # AgentDefinition as dict
    input: str
    experts: list[dict] = []  # ExpertDefinition list
    permission_preset: str = ""


def create_app(runner: AgentRunner | None = None) -> FastAPI:
    app = FastAPI(title="iCoDer Runtime", version="1.0.0")

    _runner = runner or AgentRunner()

    @app.get("/health")
    async def health():
        return {"status": "healthy", "runtime": "iCoDer", "version": "1.0.0"}

    @app.post("/run")
    async def run_agent(req: RunRequest):
        agent = AgentDefinition(**req.agent)
        for e in req.experts:
            exp = ExpertDefinition(**e)
            _runner.register_expert(exp)

        result = await _runner.run(agent, req.input)
        return result

    @app.post("/run/evidence-pack")
    async def run_and_export(req: RunRequest):
        agent = AgentDefinition(**req.agent)
        for e in req.experts:
            _runner.register_expert(ExpertDefinition(**e))

        result = await _runner.run(agent, req.input)
        pack = build_evidence_pack(result)
        return pack

    return app


def main():
    parser = argparse.ArgumentParser(description="iCoDer Runtime Server")
    parser.add_argument("--port", type=int, default=8765, help="Port to listen on")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind")
    args = parser.parse_args()

    import uvicorn
    app = create_app()
    logger.info(f"iCoDer Runtime starting on {args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
