"""Coding-review endpoints (the iCoDer analog of Corti's Predict Codes API, but on-prem
and ICD-10-CN/DRG-aware, with an evidence-linked report + human-review loop).

  POST /api/coding-review/run                -> RunResult
  GET  /api/coding-review/runs               -> run history (summaries)
  GET  /api/coding-review/{run_id}           -> RunResult
  GET  /api/coding-review/{run_id}/report    -> RunResult (json) | HTML
  POST /api/coding-review/{run_id}/human-review (role: coder|admin)
  GET  /api/coding-review/{run_id}/audit     -> append-only audit trail
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from ..report.render import render_html
from ..runtime.gateway import CredentialMissing, LLMGateway
from ..runtime.registry import default_registry
from ..runtime.runner import AgentRunner, RulesetMissing
from ..runtime.store import RunStore
from ..runtime.types import RunResult
from ..experts.coding_expert import CodingExpert
from .auth import require_auth

router = APIRouter(prefix="/api/coding-review", tags=["coding-review"])

_expert = CodingExpert()
_agents = default_registry()


def _runner() -> AgentRunner:
    gateway = LLMGateway.from_env(_expert.lexicon())
    return AgentRunner(gateway=gateway, agents=_agents, expert=_expert)


def get_store(request: Request) -> RunStore:
    return request.app.state.store


class RunRequest(BaseModel):
    text: str
    coding_system: str = "ICD-10-CN"
    agent_id: str = "icoder/homepage-coding-review-agent"


class HumanReview(BaseModel):
    decision: str  # accept | override | reject
    code: str | None = None
    override_code: str | None = None
    note: str = ""


@router.post("/run", response_model=RunResult)
def run_review(body: RunRequest, auth: dict = Depends(require_auth),
               store: RunStore = Depends(get_store)) -> RunResult:
    if not body.text.strip():
        raise HTTPException(status_code=422, detail="text is required")
    try:
        result = _runner().run(body.agent_id, body.text, coding_system=body.coding_system)
    except CredentialMissing as exc:
        raise HTTPException(status_code=503,
                            detail={"code": "llm_credential_missing", "message": str(exc)})
    except RulesetMissing as exc:
        raise HTTPException(status_code=409,
                            detail={"code": "ruleset_missing", "message": str(exc)})
    except KeyError:
        raise HTTPException(status_code=404, detail="unknown agent")
    store.save_run(result)
    store.append_audit(result.run_id, auth, "run.created", {
        "agent_id": result.agent_id,
        "n_codes": len(result.codes),
        "n_candidates": len(result.candidates),
        "passed": result.compliance.passed,
        "human_review_required": result.compliance.human_review_required,
    })
    return result


@router.get("/runs")
def list_runs(limit: int = Query(50, ge=1, le=1000),
              offset: int = Query(0, ge=0),
              auth: dict = Depends(require_auth),
              store: RunStore = Depends(get_store)):
    return {"runs": store.list_runs(limit=limit, offset=offset),
            "limit": limit, "offset": offset}


@router.get("/{run_id}", response_model=RunResult)
def get_run(run_id: str, auth: dict = Depends(require_auth),
            store: RunStore = Depends(get_store)) -> RunResult:
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    return run


@router.get("/{run_id}/report")
def get_report(run_id: str, format: str = Query("json"), auth: dict = Depends(require_auth),
               store: RunStore = Depends(get_store)):
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    store.append_audit(run_id, auth, "report.viewed", {"format": format})
    if format == "html":
        return HTMLResponse(render_html(run))
    return run


@router.post("/{run_id}/human-review")
def human_review(run_id: str, body: HumanReview, auth: dict = Depends(require_auth),
                 store: RunStore = Depends(get_store)):
    if auth["role"] not in ("coder", "admin"):
        raise HTTPException(status_code=403, detail="human review requires coder or admin role")
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    run.human_review = {
        "reviewer_role": auth["role"],  # from token, not body
        "decision": body.decision,
        "code": body.code,
        "override_code": body.override_code,
        "note": body.note,
    }
    store.save_run(run)
    store.append_audit(run_id, auth, "human_review", {
        "decision": body.decision,
        "code": body.code,
        "override_code": body.override_code,
    })
    return {"ok": True, "run_id": run_id, "human_review": run.human_review}


@router.get("/{run_id}/audit")
def get_run_audit(run_id: str, auth: dict = Depends(require_auth),
                  store: RunStore = Depends(get_store)):
    if store.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="run not found")
    return {"run_id": run_id, "events": store.get_audit(run_id)}
