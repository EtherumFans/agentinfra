"""M2a API routes — Runtime 技术闭环。

Endpoints:
- POST /api/m2a/runs                      开始一个真实 run（生成 run_id + trace_id）
- POST /api/m2a/runs/{run_id}/tools       添加一个工具调用（生成 tool_run_id）
- PATCH /api/m2a/runs/{run_id}/tools/{tool_run_id}  完成工具调用
- POST /api/m2a/runs/{run_id}/finalize    结束 run（写入 trace）
- GET  /api/m2a/runs/{run_id}             获取完整 run trace
- GET  /api/m2a/runs                      列出 production runs（sample 永远排除）
- POST /api/m2a/safety-gate/evaluate      计算医学安全门禁（直接接 metrics）
- POST /api/m2a/risk-route                计算风险路由（不入库）
- POST /api/m2a/runs/{run_id}/human-review  提交人工复核写回
- GET  /api/m2a/runs/{run_id}/reviews     查询某 run 的人工复核记录
- GET  /api/m2a/learning-loop             查询学习闭环条目（仅真实人工修改）
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from app.middleware.auth import get_current_user
from app.models.user import User

from icoder_runtime.m2a.human_review import HumanReviewService
from icoder_runtime.m2a.risk_router import RiskRouter
from icoder_runtime.m2a.run_trace import RunTraceService
from icoder_runtime.m2a.safety_gate import MedicalSafetyGate
from icoder_runtime.m2a.store import M2aStore


router = APIRouter(prefix="/api/m2a", tags=["m2a"])

# 共享单例（无状态）
_store = M2aStore()
_run_trace = RunTraceService(store=_store)
_risk_router = RiskRouter()
_safety_gate = MedicalSafetyGate()
_human_review = HumanReviewService(store=_store, run_trace=_run_trace)


# ============================================================
# Run Trace
# ============================================================

class StartRunRequest(BaseModel):
    agent_ref: str
    data_source: str = "real"
    is_sample: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class StartRunResponse(BaseModel):
    run_id: str
    trace_id: str
    agent_ref: str
    data_source: str
    is_sample: bool
    production_allowed: bool
    started_at: str


@router.post("/runs", response_model=StartRunResponse)
async def start_run(body: StartRunRequest, user: User = Depends(get_current_user)):
    """开始一个真实 run，返回 run_id + trace_id。"""
    trace = _run_trace.start_run(
        agent_ref=body.agent_ref,
        data_source=body.data_source,
        is_sample=body.is_sample,
        metadata=body.metadata,
    )
    return StartRunResponse(
        run_id=trace.run_id,
        trace_id=trace.trace_id,
        agent_ref=trace.agent_ref,
        data_source=trace.data_source,
        is_sample=trace.is_sample,
        production_allowed=trace.production_allowed,
        started_at=trace.started_at,
    )


class ToolCallRequest(BaseModel):
    tool_name: str
    tool_input: dict[str, Any] = Field(default_factory=dict)


@router.post("/runs/{run_id}/tools")
async def add_tool_call(run_id: str, body: ToolCallRequest, user: User = Depends(get_current_user)):
    """添加一次工具调用，返回 tool_run_id。"""
    try:
        tc = _run_trace.add_tool_call(run_id, body.tool_name, body.tool_input)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"tool_run_id": tc.tool_run_id, "tool_name": tc.tool_name, "started_at": tc.started_at}


class CompleteToolRequest(BaseModel):
    tool_output: dict[str, Any] = Field(default_factory=dict)
    status: str = "ok"
    error: str = ""


@router.patch("/runs/{run_id}/tools/{tool_run_id}")
async def complete_tool_call(
    run_id: str, tool_run_id: str, body: CompleteToolRequest, user: User = Depends(get_current_user)
):
    """结束一个工具调用。"""
    try:
        _run_trace.complete_tool_call(
            run_id, tool_run_id, body.tool_output, body.status, body.error
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"status": "completed", "tool_run_id": tool_run_id}


class FinalizeRunRequest(BaseModel):
    final_status: str = "success"
    risk_indicators: dict[str, Any] = Field(default_factory=dict)
    safety_metrics: dict[str, float] = Field(default_factory=dict)
    primary_dx_change_attempted: bool = False
    evidence_grounded: bool = True


@router.post("/runs/{run_id}/finalize")
async def finalize_run(run_id: str, body: FinalizeRunRequest, user: User = Depends(get_current_user)):
    """结束 run，写入 trace。"""
    try:
        run = _run_trace.get_run(run_id)
        if not run:
            raise KeyError(run_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    is_sample = run.get("is_sample", False)

    # 计算风险路由
    risk = _risk_router.route(
        indicators=body.risk_indicators,
        is_sample=is_sample,
        data_source=run.get("data_source", "real"),
        production_allowed=run.get("production_allowed", True),
    )

    # 计算医学安全门禁
    safety = _safety_gate.evaluate(
        metrics=body.safety_metrics,
        primary_dx_change_attempted=body.primary_dx_change_attempted,
        evidence_grounded=body.evidence_grounded,
    )

    try:
        finalized = _run_trace.finalize_run(
            run_id, body.final_status, risk.to_dict(), safety.to_dict()
        )
    except ValueError as e:
        # sample 被写入 production 时拒绝
        raise HTTPException(status_code=400, detail=str(e))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {
        "run_id": finalized.run_id,
        "final_status": finalized.final_status,
        "risk_route": risk.to_dict(),
        "safety_gate": safety.to_dict(),
    }


@router.get("/runs/{run_id}")
async def get_run(run_id: str, user: User = Depends(get_current_user)):
    """获取完整 run trace。"""
    run = _run_trace.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return run


@router.get("/runs")
async def list_runs(limit: int = 50, agent_ref: str = "", user: User = Depends(get_current_user)):
    """列出 production runs（sample 永远排除）。"""
    runs = _run_trace.list_production(limit=limit, agent_ref=agent_ref)
    return {"runs": runs, "count": len(runs), "sample_excluded": True}


# ============================================================
# Safety Gate
# ============================================================

class SafetyGateRequest(BaseModel):
    metrics: dict[str, float] = Field(default_factory=dict)
    primary_dx_change_attempted: bool = False
    evidence_grounded: bool = True


@router.post("/safety-gate/evaluate")
async def evaluate_safety_gate(body: SafetyGateRequest, user: User = Depends(get_current_user)):
    """计算医学安全门禁（不入库）。"""
    result = _safety_gate.evaluate(
        metrics=body.metrics,
        primary_dx_change_attempted=body.primary_dx_change_attempted,
        evidence_grounded=body.evidence_grounded,
    )
    return result.to_dict()


# ============================================================
# Risk Router
# ============================================================

class RiskRouteRequest(BaseModel):
    indicators: dict[str, Any] = Field(default_factory=dict)
    is_sample: bool = False
    data_source: str = "real"
    production_allowed: bool = True


@router.post("/risk-route")
async def evaluate_risk_route(body: RiskRouteRequest, user: User = Depends(get_current_user)):
    """计算风险路由（不入库）。"""
    result = _risk_router.route(
        indicators=body.indicators,
        is_sample=body.is_sample,
        data_source=body.data_source,
        production_allowed=body.production_allowed,
    )
    return result.to_dict()


# ============================================================
# Human Review
# ============================================================

class HumanReviewRequest(BaseModel):
    reviewer: str
    decision: str  # approve | reject | modify
    reason_code: str
    rationale: str
    primary_dx_change: bool = False
    modifications: dict[str, Any] = Field(default_factory=dict)


@router.post("/runs/{run_id}/human-review")
async def submit_human_review(
    run_id: str, body: HumanReviewRequest, user: User = Depends(get_current_user)
):
    """提交人工复核写回。"""
    try:
        record = _human_review.submit_review(
            run_id=run_id,
            reviewer=body.reviewer,
            decision=body.decision,
            reason_code=body.reason_code,
            rationale=body.rationale,
            primary_dx_change=body.primary_dx_change,
            modifications=body.modifications,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return record.to_dict()


@router.get("/runs/{run_id}/reviews")
async def list_reviews(run_id: str, user: User = Depends(get_current_user)):
    """查询某 run 的人工复核记录。"""
    return {"run_id": run_id, "reviews": _human_review.list_reviews(run_id=run_id)}


@router.get("/learning-loop")
async def list_learning_loop(limit: int = 100, user: User = Depends(get_current_user)):
    """查询学习闭环条目（仅真实人工修改）。"""
    return {"entries": _human_review.list_learning_loop(limit=limit)}
