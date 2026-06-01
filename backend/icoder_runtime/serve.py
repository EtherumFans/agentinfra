"""iCoDer Runtime Server — local HTTP API + Dashboard Console.

Usage:
    icoder dashboard                    Start Dashboard (127.0.0.1:8766)
    icoder dashboard --host 0.0.0.0    Expose to network (with warning)
    icoder serve --port 8765           Start API-only server
"""

import argparse
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, Request
from fastapi.responses import HTMLResponse, FileResponse, Response
from pydantic import BaseModel

from .types import AgentDefinition, ExpertDefinition, ToolDefinition
from .agent_runner import AgentRunner
from .agent_pack import validate_pack, import_pack, export_pack, save_pack, load_pack
from .evidence_pack import build_evidence_pack
from . import __version__

logger = logging.getLogger(__name__)

# ── Local persistent store ──

_STORE_DIR = Path.home() / ".icoder"
_STORE_DIR.mkdir(parents=True, exist_ok=True)
_AGENTS_FILE = _STORE_DIR / "agents.json"
_RUNS_FILE = _STORE_DIR / "runs.json"


def _load_store(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_store(path: Path, data: dict):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


class RunRequest(BaseModel):
    agent_id: str
    input: str
    review_id: Optional[str] = None


class ImportRequest(BaseModel):
    pack: dict  # .icoder-agent pack dict


class AgentInfo(BaseModel):
    id: str
    name: str
    version: str
    description: str
    category: str
    icon: str
    expert_count: int
    tool_count: int
    status: str  # ready | incompatible
    loaded_at: str


class RunInfo(BaseModel):
    id: str
    agent_id: str
    agent_name: str
    agent_version: str
    input_preview: str
    review_id: str
    status: str
    processing_time_ms: int
    audit_entries: int
    chain_valid: bool
    created_at: str


# ── App Factory ──

def create_app(runner: AgentRunner | None = None) -> FastAPI:
    app = FastAPI(title="iCoDer Runtime", version=__version__)

    _runner = runner or AgentRunner()

    # Load persisted agents
    agents_store = _load_store(_AGENTS_FILE)
    runs_store = _load_store(_RUNS_FILE)

    def _save_agents():
        _save_store(_AGENTS_FILE, agents_store)

    def _save_runs():
        _save_store(_RUNS_FILE, runs_store)

    # ── Dashboard ──

    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard():
        dashboard_html = (Path(__file__).parent / "dashboard.html")
        if dashboard_html.exists():
            return dashboard_html.read_text(encoding="utf-8")
        return "<h1>Dashboard not found</h1>"

    @app.get("/health")
    async def health():
        return {"status": "healthy", "runtime": "iCoDer", "version": __version__}

    @app.get("/api/runtime/status")
    async def runtime_status():
        return {
            "version": __version__,
            "agents_loaded": len(agents_store),
            "runs_recorded": len(runs_store),
        }

    # ── Agents API ──

    @app.get("/api/agents")
    async def list_agents():
        result = []
        for aid, data in agents_store.items():
            result.append({
                "id": aid,
                "name": data["name"],
                "version": data.get("version", "1.0.0"),
                "description": data.get("description", ""),
                "category": data.get("category", "general"),
                "icon": data.get("icon", "Bot"),
                "expert_count": len(data.get("experts", [])),
                "tool_count": len(data.get("tools", [])),
                "status": data.get("status", "ready"),
                "loaded_at": data.get("loaded_at", ""),
            })
        return {"agents": result, "total": len(result)}

    @app.get("/api/agents/{agent_id}")
    async def get_agent(agent_id: str):
        data = agents_store.get(agent_id)
        if not data:
            raise HTTPException(status_code=404, detail="Agent not found")
        return data

    @app.post("/api/agents/import")
    async def import_agent(req: ImportRequest):
        pack = req.pack
        errors = validate_pack(pack)
        if errors:
            raise HTTPException(status_code=400, detail={"errors": errors})

        try:
            agent, experts, tools, _ = import_pack(pack)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Import failed: {e}")

        aid = str(uuid.uuid4())[:12]
        agents_store[aid] = {
            "id": aid,
            "name": agent.name,
            "version": agent.version,
            "description": agent.description,
            "category": agent.category,
            "icon": agent.icon,
            "expert_ids": agent.expert_ids,
            "experts": [{"id": e.id, "name": e.name, "description": e.description,
                         "system_prompt": e.system_prompt, "capabilities": e.capabilities,
                         "config": e.config} for e in experts],
            "tools": [{"id": t.id, "name": t.name, "description": t.description,
                       "tier": t.tier.value, "category": t.category,
                       "requires": t.requires, "guarantees": t.guarantees,
                       "params": (t.input_schema or {}).get("properties", {}),
                       "accuracy_tags": t.accuracy_tags,
                       "is_injectable": t.is_injectable} for t in tools],
            "system_prompt": agent.system_prompt,
            "status": "ready",
            "loaded_at": datetime.now(timezone.utc).isoformat(),
            "integrity": pack.get("integrity", {}),
        }
        _save_agents()

        for e in experts:
            _runner.register_expert(e)
        for t in tools:
            _runner.register_tool(t)

        return {"id": aid, "name": agent.name, "status": "imported"}

    @app.get("/api/agents/{agent_id}/export")
    async def export_agent(agent_id: str):
        data = agents_store.get(agent_id)
        if not data:
            raise HTTPException(status_code=404, detail="Agent not found")

        agent = AgentDefinition(
            name=data["name"], version=data.get("version", "1.0.0"),
            description=data.get("description", ""), category=data.get("category", "general"),
            icon=data.get("icon", "Bot"), system_prompt=data.get("system_prompt", ""),
            expert_ids=data.get("expert_ids", []),
        )
        experts = [ExpertDefinition(**e) for e in data.get("experts", [])]
        tools = [ToolDefinition(
            id=t["id"], name=t["name"], description=t.get("description", ""),
            tier=__import__("icoder_runtime.types", fromlist=["ToolTier"]).ToolTier(t.get("tier", 2)),
            category=t.get("category", "general"), icon=t.get("icon", "Wrench"),
            requires=t.get("requires", []), guarantees=t.get("guarantees", {}),
            input_schema={"type":"object","properties":t.get("params",{})} if t.get("params") else None,
            accuracy_tags=t.get("accuracy_tags", []), is_injectable=t.get("is_injectable", False),
        ) for t in data.get("tools", [])]

        pack = export_pack(agent, experts, tools)
        return Response(
            content=json.dumps(pack, ensure_ascii=False, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{agent.name}.icoder-agent"'},
        )

    @app.delete("/api/agents/{agent_id}")
    async def delete_agent(agent_id: str):
        if agent_id not in agents_store:
            raise HTTPException(status_code=404, detail="Agent not found")
        del agents_store[agent_id]
        _save_agents()
        return {"status": "deleted"}

    # ── Runs API ──

    @app.post("/api/runs")
    async def create_run(req: RunRequest):
        data = agents_store.get(req.agent_id)
        if not data:
            raise HTTPException(status_code=404, detail="Agent not found")

        agent = AgentDefinition(
            name=data["name"], version=data.get("version", "1.0.0"),
            description=data.get("description", ""), category=data.get("category", "general"),
            system_prompt=data.get("system_prompt", ""),
            expert_ids=data.get("expert_ids", []),
        )

        # Register experts and tools for this run
        for e in data.get("experts", []):
            _runner.register_expert(ExpertDefinition(**e))
        for t in data.get("tools", []):
            _runner.register_tool(ToolDefinition(
                id=t["id"], name=t["name"], description=t.get("description",""),
                tier=__import__("icoder_runtime.types", fromlist=["ToolTier"]).ToolTier(t.get("tier",2)),
                category=t.get("category","general"),
                requires=t.get("requires",[]), guarantees=t.get("guarantees",{}),
                input_schema={"type":"object","properties":t.get("params",{})} if t.get("params") else None,
            ))

        result = await _runner.run(agent, req.input)
        run_id = result["review_id"]

        runs_store[run_id] = {
            "id": run_id,
            "agent_id": req.agent_id,
            "agent_name": agent.name,
            "agent_version": agent.version,
            "input_preview": req.input[:200],
            "review_id": run_id,
            "status": "completed",
            "processing_time_ms": result.get("processing_time_ms", 0),
            "audit_entries": result["state_log"]["entry_count"],
            "chain_valid": result["state_log"]["chain_valid"],
            "state_log": result["state_log"],
            "output": result.get("output", ""),
            "contract_valid": result.get("contract_valid", True),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        _save_runs()
        return runs_store[run_id]

    @app.get("/api/runs")
    async def list_runs(limit: int = 50, agent_id: str = ""):
        runs = list(runs_store.values())
        if agent_id:
            runs = [r for r in runs if r["agent_id"] == agent_id]
        runs.sort(key=lambda r: r["created_at"], reverse=True)
        result = []
        for r in runs[:limit]:
            result.append({
                "id": r["id"], "agent_id": r["agent_id"], "agent_name": r["agent_name"],
                "agent_version": r["agent_version"], "input_preview": r["input_preview"][:100],
                "review_id": r["review_id"], "status": r["status"],
                "processing_time_ms": r["processing_time_ms"],
                "audit_entries": r["audit_entries"], "chain_valid": r["chain_valid"],
                "created_at": r["created_at"],
            })
        return {"runs": result, "total": len(result)}

    @app.get("/api/runs/{run_id}")
    async def get_run(run_id: str):
        run = runs_store.get(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        return run

    return app


def main():
    parser = argparse.ArgumentParser(description="iCoDer Runtime Dashboard")
    parser.add_argument("--port", type=int, default=8766, help="Port to listen on")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind")
    args = parser.parse_args()

    if args.host != "127.0.0.1":
        import sys
        print(f"Warning: Dashboard is exposed to the network at {args.host}:{args.port}.")
        print("Use only in trusted environments.")
        print("Press Ctrl+C to abort, or wait 3 seconds to continue...")
        time.sleep(3)

    import uvicorn
    app = create_app()
    logger.info(f"iCoDer Runtime Dashboard: http://{args.host}:{args.port}/dashboard")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
