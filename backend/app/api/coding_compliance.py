"""POST /api/v1/coding-compliance/run — 7-stage coding compliance mainline.

Phase 5 Track C Gate 5 (2026-07-11): exposes the
CodingComplianceOrchestrator as an HTTP endpoint so the frontend
CodingComplianceWorkbench can drive the full pipeline.

Per PDF §9 the endpoint:
  - accepts raw discharge text
  - runs 7 stages via the orchestrator
  - returns CaseState (stage_outputs + review_gate_status + case_id)

Stage invocation is **in-process** (provider.invoke directly), NOT
HTTP. The HTTP-callback approach deadlocks on a single-worker uvicorn
because the sync urllib call blocks the event loop while the inner
request needs the loop to be dispatched. Instead, the runner creates
a fresh event loop per stage call and drives the async provider via
``asyncio.run()``. This works because we're already in a worker
thread (``asyncio.to_thread`` at the handler level).

Each stage still produces a real run_id + trace_events entry because
provider.invoke goes through the same machinery as the public
``/api/v1/agents/{id}/run`` endpoint.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.middleware.auth import get_current_user
from app.models.user import User
from app.icoder.agent_runtime.orchestrator.coding_compliance_orchestrator import (
    CaseState,
    CodingComplianceConfig,
    CodingComplianceOrchestrator,
    STAGE_ORDER,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/coding-compliance", tags=["coding-compliance"])


# ── Schemas ─────────────────────────────────────────────────────────────


class CodingComplianceRunRequest(BaseModel):
    """Request body for the 7-stage mainline endpoint."""

    input_text: str = Field(
        ..., min_length=1, max_length=32000,
        description="Raw discharge summary text (Chinese or English).",
    )
    case_id: str | None = Field(
        default=None,
        description="Optional case ID. Auto-generated UUID if omitted.",
    )


    model_config = {"json_schema_extra": {"example": {
        "input_text": "患者男性,78岁,T12椎体压缩性骨折,行后路椎体成形术...",
        "case_id": "CASE-2026-07-11-001",
    }}}


# ── In-process agent runner ─────────────────────────────────────────────


def _build_in_process_runner(current_user: User, request: Request | None = None):
    """Build an agent_runner that drives the unified agent_run facade.

    Each call creates a fresh event loop (we're in a worker thread, so
    no conflict with the main loop) and runs the async ``run_agent``
    facade, which routes medical-coding-agent → corti_like_fast path
    and everything else → provider.invoke directly. Returns the
    AgentRunResponse as a dict for the orchestrator.
    """

    def _runner(agent_id: str, input_text: str, context: dict | None = None) -> dict:
        from app.api.agent_run import (
            AgentRunRequest,
            AgentRunRequestInput,
            run_agent,
        )

        async def _drive() -> dict:
            body = AgentRunRequest(
                input=AgentRunRequestInput(text=input_text),
            )
            response = await run_agent(
                agent_id=agent_id,
                body=body,
                request=request,
                current_user=current_user,
            )
            return response.model_dump(mode="json") if hasattr(response, "model_dump") else dict(response)

        return asyncio.run(_drive())

    return _runner


# ── Endpoint ────────────────────────────────────────────────────────────


@router.post(
    "/run",
    operation_id="coding_compliance_run_v1",
)
async def coding_compliance_run(
    body: CodingComplianceRunRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Run the 7-stage coding compliance mainline. Returns CaseState dict."""
    runner = _build_in_process_runner(current_user, request=request)
    orch = CodingComplianceOrchestrator(runner)

    t0 = time.monotonic()
    try:
        # Run the sync orchestrator chain in a worker thread so the
        # event loop stays free to dispatch inner HTTP requests back to
        # uvicorn. Without this, the sync urllib call deadlocks.
        case: CaseState = await asyncio.to_thread(
            orch.run,
            input_text=body.input_text,
            case_id=body.case_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("coding_compliance.run failed")
        raise HTTPException(status_code=500, detail=f"orchestrator crashed: {e}") from e

    total_ms = int((time.monotonic() - t0) * 1000)
    return _serialize_case(case, total_ms)


def _serialize_case(case: CaseState, total_ms: int) -> dict[str, Any]:
    """Project CaseState into a JSON-serializable dict for the wire."""
    return {
        "case_id": case.case_id,
        "agent_id": case.agent_id,
        "input_text_preview": case.input_text[:200],
        "input_text_length": len(case.input_text),
        "stages": [
            {
                "stage_id": stage,
                "stage_name": _stage_display_name(stage),
                "stage_index": i,
                "output": case.stage_outputs.get(stage, {}),
                "error": case.stage_errors.get(stage, ""),
                "latency_ms": case.stage_latencies_ms.get(stage, 0),
                "normalized": case.normalized.get(stage, {}).to_dict() if stage in case.normalized else None,
            }
            for i, stage in enumerate(STAGE_ORDER)
        ],
        "conflicts": [
            {
                "field_path": c.field_path,
                "strategy": c.strategy,
                "resolved_value": c.resolved_value,
                "rationale": c.rationale,
                "deferred_to_human": c.deferred_to_human,
                "candidates": c.candidates,
            }
            for c in case.conflicts
        ],
        "completion": {
            "status": case.completion.status if case.completion else "UNKNOWN",
            "reasons": case.completion.reasons if case.completion else [],
            "must_replan": case.completion.must_replan if case.completion else False,
            "review_required": case.completion.review_required if case.completion else False,
        },
        "review_gate": {
            "status": case.review_gate_status,
            "blocker": case.review_gate_blocker,
            "reasons": case.review_gate_reasons,
        },
        "total_latency_ms": total_ms,
    }


def _stage_display_name(stage_id: str) -> str:
    return {
        "discharge-summary-structuring": "出院小结结构化",
        "medical-coding-agent": "ICD 编码",
        "principal-diagnosis-review": "主诊断复核",
        "evidence-extractor": "证据强度",
        "compliance-guardrail": "合规审查",
        "note-completeness": "病历完整度",
        "drg-analyzer": "DRG/DIP 风险",
    }.get(stage_id, stage_id)


__all__ = ["router", "CodingComplianceRunRequest"]
