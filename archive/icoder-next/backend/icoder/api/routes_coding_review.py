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

from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from ..report.render import render_html
from ..runtime.gateway import CredentialMissing, LLMGateway, ProviderError
from ..runtime.registry import default_registry
from ..runtime.runner import AgentRunner, ExpertMissing, RulesetMissing
from ..runtime.store import RunStore
from ..runtime.types import RunResult, new_id
from ..experts.coding_expert import CodingExpert
from ..experts.compliance import (
    DocumentEvidenceRuleSet,
    DrgDipRuleSet,
    InsuranceAuditRuleSet,
    MedicalCodingRuleSet,
)
from ..experts.registry import default_expert_registry
from .auth import require_auth

router = APIRouter(prefix="/api/coding-review", tags=["coding-review"])

_experts = default_expert_registry()
_agents = default_registry()

# Ordered catalog of every wired compliance domain (编码→分组→结算→病历). An agent runs
# only the subset it declares via rule_sets; the browser shows all four but marks which
# this agent enforces, so a coder sees both what gates them now and the platform's breadth.
_RULESET_CLASSES = [
    MedicalCodingRuleSet,
    DrgDipRuleSet,
    InsuranceAuditRuleSet,
    DocumentEvidenceRuleSet,
]


def _runner() -> AgentRunner:
    coding = cast(CodingExpert, _experts.get(CodingExpert.id))
    gateway = LLMGateway.from_env(coding.lexicon())
    return AgentRunner(gateway=gateway, agents=_agents, experts=_experts)


def get_store(request: Request) -> RunStore:
    return request.app.state.store


class RunRequest(BaseModel):
    text: str
    coding_system: str = "ICD-10-CN"
    agent_id: str = "icoder/homepage-coding-review-agent"


class BatchRequest(BaseModel):
    records: list[str]
    coding_system: str = "ICD-10-CN"
    agent_id: str = "icoder/homepage-coding-review-agent"


# One coder rarely submits more than a daily worklist at once; the slice runs the
# pipeline synchronously (deterministic-local is ms/record), so cap the loop. A
# hospital deployment would queue these instead.
_BATCH_MAX = 20


def _summary(run: RunResult) -> dict:
    """Denormalize a RunResult into the same shape store.list_runs returns, so batch
    rows and run-history rows render identically and drill down by run_id the same way."""
    primary_code = next((c.code for c in run.codes if c.is_primary), None)
    if primary_code is None and run.codes:
        primary_code = run.codes[0].code
    return {
        "run_id": run.run_id,
        "agent_id": run.agent_id,
        "agent_version": run.agent_version,
        "created_at": run.created_at,
        "passed": int(run.compliance.passed),
        "human_review_required": int(run.compliance.human_review_required),
        "primary_code": primary_code,
        "drg": run.drg_route.drg if run.drg_route else None,
        "dip_code": run.drg_route.dip_code if run.drg_route else None,
        "reviewed": int(run.human_review is not None),
    }


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
    except ProviderError as exc:
        # With a key but the LLM endpoint is unreachable/errored — a clean 503, never a
        # fabricated report. str(ProviderError) carries no credential material.
        raise HTTPException(status_code=503,
                            detail={"code": "llm_unavailable", "message": str(exc)})
    except RulesetMissing as exc:
        raise HTTPException(status_code=409,
                            detail={"code": "ruleset_missing", "message": str(exc)})
    except ExpertMissing as exc:
        raise HTTPException(status_code=409,
                            detail={"code": "expert_missing", "message": str(exc)})
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


@router.post("/batch")
def run_batch(body: BatchRequest, auth: dict = Depends(require_auth),
              store: RunStore = Depends(get_store)):
    records = [r for r in body.records if r.strip()]
    if not records:
        raise HTTPException(status_code=422, detail="at least one non-empty record is required")
    if len(records) > _BATCH_MAX:
        raise HTTPException(status_code=422,
                            detail=f"batch is capped at {_BATCH_MAX} records (got {len(records)})")
    # Build the runner once, then orchestrate the *identical* single-run pipeline per
    # record — no new inference path, so the "don't fabricate predictions" line holds.
    runner = _runner()
    batch_id = new_id("batch")
    results = []
    for i, text in enumerate(records):
        try:
            run = runner.run(body.agent_id, text, coding_system=body.coding_system)
        except CredentialMissing as exc:
            # Global config faults (missing key / ruleset / expert / agent) fail the whole
            # batch — retrying the remaining records can't succeed either.
            raise HTTPException(status_code=503,
                                detail={"code": "llm_credential_missing", "message": str(exc)})
        except ProviderError as exc:
            # LLM endpoint unreachable/errored — fail the whole batch (no fabrication).
            raise HTTPException(status_code=503,
                                detail={"code": "llm_unavailable", "message": str(exc)})
        except RulesetMissing as exc:
            raise HTTPException(status_code=409,
                                detail={"code": "ruleset_missing", "message": str(exc)})
        except ExpertMissing as exc:
            raise HTTPException(status_code=409,
                                detail={"code": "expert_missing", "message": str(exc)})
        except KeyError:
            raise HTTPException(status_code=404, detail="unknown agent")
        store.save_run(run)
        store.append_audit(run.run_id, auth, "run.created", {
            "agent_id": run.agent_id,
            "n_codes": len(run.codes),
            "passed": run.compliance.passed,
            "human_review_required": run.compliance.human_review_required,
            "batch_id": batch_id,
            "batch_index": i,
        })
        results.append({**_summary(run), "index": i})
    return {
        "batch_id": batch_id,
        "total": len(results),
        "passed": sum(1 for r in results if r["passed"]),
        "needs_review": sum(1 for r in results if r["human_review_required"]),
        "results": results,
    }


@router.get("/runs")
def list_runs(limit: int = Query(50, ge=1, le=1000),
              offset: int = Query(0, ge=0),
              agent_id: str | None = Query(None),
              auth: dict = Depends(require_auth),
              store: RunStore = Depends(get_store)):
    return {"runs": store.list_runs(limit=limit, offset=offset, agent_id=agent_id),
            "limit": limit, "offset": offset, "agent_id": agent_id}


@router.get("/rulesets")
def list_rulesets(agent_id: str | None = Query(None), auth: dict = Depends(require_auth)):
    enforced: set[str] = set()
    if agent_id is not None:
        agent = _agents.get(agent_id)
        if agent is None:
            raise HTTPException(status_code=404, detail="unknown agent")
        enforced = set(agent.rule_sets)
    return {
        "agent_id": agent_id,
        # How the engine folds hits into one gate (see RuleEngine.evaluate).
        "gate_policy": {
            "passed": "无 Critical 命中即通过门禁。",
            "human_review_required": "任一 Critical 或 Moderate 命中即需人工复核。",
        },
        "rule_sets": [
            {
                "rule_set": rs.rule_set,
                "label": rs.label,
                "version": rs.version,
                "enforced": rs.rule_set in enforced,
                "rules": rs.rules,
            }
            for rs in _RULESET_CLASSES
        ],
    }


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
