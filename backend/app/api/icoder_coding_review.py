# DEPRECATED (P1.3 Stage 5, 2026-07-02) — Legacy API. Corti 用 /api/v2/tools/coding/. Phase 2 删. 见 docs/architecture/MAINLINE_VS_LEGACY.md §3.3.
"""iCoDer M3-0 — 病案首页编码审核 Agent API.

路由 (M3 任务 §2-3):
- POST /api/icoder/coding-review/run
- POST /api/icoder/coding-review/{run_id}/human-review
- GET  /api/icoder/coding-review/{run_id}/report

**Positioning (M3-0 红线)**: 这些路由是 iCoDer 基础设施上样板 Agent 的入口, 不是 iCoDer 全部产品.
**不伪造 (M3-0 硬性)**: 无 prediction / B0 / 人工证据 → 返回 status=unavailable, degraded=true.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.audit import log_action
from app.middleware.auth import get_current_user
from app.models.coding_review_run import CodingReviewRun
from app.models.organization import OrganizationMember
from app.models.user import User

# Roles authorized to submit human-review actions on a coding-review run.
# Mirrors the spec's "coder or admin" gate (M3_HOMEPAGE_CODING_REVIEW_AGENT_SPEC.md §5).
_HUMAN_REVIEW_ROLES = {"admin", "coder"}


async def _resolve_user_org_id(user_id: str, db: AsyncSession) -> Optional[str]:
    """Return the user's primary organization id, or None if no membership.

    Users may belong to multiple organizations; for M3-0 attribution we pick
    the first active membership. Multi-org handling is out of scope.
    """
    stmt = (
        select(OrganizationMember.organization_id)
        .where(OrganizationMember.user_id == user_id)
        .order_by(OrganizationMember.is_default.desc(), OrganizationMember.created_at.asc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/icoder/coding-review", tags=["icoder-coding-review"])


# Phase A A3 (2026-06-25): the 14-stage homepage-coding-review pipeline is
# deprecated. This endpoint is preserved for backward compatibility with
# existing human-review actions and report downloads, but the canonical
# runtime agent is now MedCodER (icoder/medcoder-coding-review-agent@1.0.0).
# Constants are inlined here so this module no longer depends on the
# deprecated shim. The values match the v1.0.0 pack so existing reports
# keep their ``agent_ref`` field stable.
_AGENT_REF = "icoder/medcoder-coding-review-agent@1.0.0"
_AGENT_CATEGORY = "medical-coding"
_PIPELINE_STAGES = [
    # Surface the 5 MedCodER stages as the run_trace timeline so historical
    # reports remain interpretable. The 14-stage cosmetic ordering lives
    # only on the legacy pack for back-compat reads.
    "extraction",
    "retrieval",
    "merge",
    "rerank",
    "calibration",
]
_PRIORITY_HIGH_RISK_CODES = {
    "I66.901",  # 脑梗死
    "J98.414",  # 肺不张
    "M80.900",  # 骨质疏松
    "45.1600x001",  # 胃镜活检
    "Z51.102",  # 化疗
}
_ALLOWED_HUMAN_ACTIONS = {
    "accept",
    "reject",
    "modify",
    "insufficient_evidence",
    "escalate",
}
_PIPELINE_VALIDATION_DISCLAIMER = (
    "本报告由 MedCodER Coding Review Agent "
    "(icoder/medcoder-coding-review-agent@1.0.0) 在 pipeline validation 模式 "
    "(M3-0 默认) 下生成. 此模式下 prediction = gold_evidence, 仅用于验证 "
    "iCoDer Runtime 5 阶段技术链路端到端通, 不代表模型效果, 不可用于生产写回 "
    "或医保上传. 如需真实模型 P/R/F1, 需在 M3 后续阶段提供 external "
    "prediction-file 并切换至 model_evaluation 模式."
)


# Backward-compat aliases. Existing tests + downstream code may still
# import these names from this module; keep them at module scope.
AGENT_REF = _AGENT_REF
AGENT_CATEGORY = _AGENT_CATEGORY
PIPELINE_STAGES = _PIPELINE_STAGES
PRIORITY_HIGH_RISK_CODES = _PRIORITY_HIGH_RISK_CODES
ALLOWED_HUMAN_ACTIONS = _ALLOWED_HUMAN_ACTIONS
PIPELINE_VALIDATION_DISCLAIMER = _PIPELINE_VALIDATION_DISCLAIMER

# In-memory fallback for reads during the M3-0 → M3+ transition window.
# Writes go to the CodingReviewRun SQL table (Commit 3); this dict is
# consulted only when a read misses the DB. It will be removed entirely
# in a follow-up release.
_RUNS_STORE: dict[str, dict[str, Any]] = {}


# ── Pydantic Schemas ──────────────────────────────────────────────────


class CodingReviewRunRequest(BaseModel):
    """POST /run 请求体。"""
    encounter_text: str = Field(default="", description="病历原文 / 病案首页字段拼接")
    mode: str = Field(default="link_validation", description="link_validation (M3-0 默认) / model_evaluation (M3+)")
    case_id: str = Field(default="", description="病例 ID (脱敏后可能为「「地址」」, 用 _excel_row 找回)")
    input_source: str = Field(default="manual", description="manual / m2b_sample / validated / api")
    primary_disease_codes: str = Field(default="", description="可选: 病案首页主诊断 (分号分隔)")
    other_disease_codes: str = Field(default="", description="可选: 病案首页其他诊断 (分号分隔)")
    primary_surgery_codes: str = Field(default="", description="可选: 主手术 (分号分隔)")
    other_surgery_codes: str = Field(default="", description="可选: 其他手术 (分号分隔)")


class CodingReviewRunResponse(BaseModel):
    run_id: str
    trace_id: str
    agent_ref: str
    agent_category: str
    prediction_mode: str
    status: str  # "ok" | "unavailable" | "degraded"
    degraded: bool
    business_result_generated: bool
    manual_review_required: bool
    reason: str
    primary_diagnosis: dict | None = None
    secondary_diagnoses: list[dict] = Field(default_factory=list)
    procedures: list[dict] = Field(default_factory=list)
    high_risk_coding_points: list[dict] = Field(default_factory=list)
    evidence_chain: list[dict] = Field(default_factory=list)
    risk_route: dict = Field(default_factory=dict)
    safety_gate: dict = Field(default_factory=dict)
    drg_route: dict | None = None
    pipeline_stages_observed: list[str] = Field(default_factory=list)
    trace_url: str
    human_review_url: str
    report_url: str
    started_at: str
    finished_at: str


class HumanReviewAction(BaseModel):
    case_id: str = ""
    target_code: str = ""
    target_role: str = ""
    action: str = ""  # accept / reject / modify / insufficient_evidence / escalate
    new_code: str = ""
    reason_code: str = ""  # 必填 (M3 任务 §5), 缺失时 endpoint 内部校验
    review_note: str = ""
    reviewer: str = ""  # 必填, 缺失时 endpoint 内部校验
    reviewer_role: str = ""  # 可选, 缺失时 warning


class HumanReviewResponse(BaseModel):
    run_id: str
    accepted: bool
    record_id: str
    action: str
    target_code: str
    new_code: str = ""
    production_writeback_blocked: bool = True  # 硬性
    validation_errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    audit_log_entry: dict = Field(default_factory=dict)
    recorded_at: str


class ReportResponse(BaseModel):
    run_id: str
    format: str  # html (M3-0)
    content: str
    filename: str
    disclaimer: str
    generated_at: str


# ── 工具: 加载 run record (DB 优先, _RUNS_STORE 兜底) ──────────────────


async def _load_run_record(run_id: str, db: AsyncSession) -> Optional[dict[str, Any]]:
    """Return the run in the same shape as _RUNS_STORE entries.

    Tries the SQL ``CodingReviewRun`` table first; on miss, falls back to
    the in-memory store. The shape is intentionally identical to the
    pre-Commit-3 dict so the downstream report / human-review code does
    not need to be refactored.
    """
    stmt = select(CodingReviewRun).where(CodingReviewRun.id == run_id)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is not None:
        return {
            "run_id": row.id,
            "trace_id": row.trace_id or "",
            "agent_ref": row.agent_ref,
            "agent_category": row.agent_category,
            "prediction_mode": row.prediction_mode,
            "input": {
                "encounter_text": row.encounter_text or "",
                "case_id": row.case_id or "",
                "input_source": row.input_source,
                # DB row does not retain the user's code inputs (only the
                # result); empty strings keep downstream rendering safe.
                "primary_disease_codes": "",
                "other_disease_codes": "",
                "primary_surgery_codes": "",
                "other_surgery_codes": "",
            },
            "result": {
                "status": row.status,
                "degraded": row.degraded,
                "business_result_generated": row.business_result_generated,
                "manual_review_required": row.manual_review_required,
                "reason": row.reason,
                "primary_diagnosis": row.primary_diagnosis,
                "secondary_diagnoses": row.secondary_diagnoses,
                "procedures": row.procedures,
                "high_risk_coding_points": row.high_risk_coding_points,
                "evidence_chain": row.evidence_chain,
                "risk_route": row.risk_route,
                "safety_gate": row.safety_gate,
                "drg_route": row.drg_route,
                "observed_stages": row.pipeline_stages_observed,
            },
            "started_at": row.started_at.isoformat() + "Z" if row.started_at else "",
            "finished_at": row.finished_at.isoformat() + "Z" if row.finished_at else "",
            "human_review_records": list(row.human_review_records or []),
        }
    # Fallback to in-memory mirror (transition window only).
    return _RUNS_STORE.get(run_id)


# ── 工具: 检查高风险码 ────────────────────────────────────────────────


def _split_codes(s: str) -> list[str]:
    if not s:
        return []
    return [c.strip() for c in s.split(";") if c.strip()]


def _compute_drg_route(
    primary_diagnosis: dict | None,
    secondary_diagnoses: list[dict],
    procedures: list[dict],
) -> dict | None:
    """Compute DRG group for the case, returning a route dict or None.

    Returns None when there is no primary diagnosis (DRG grouping cannot run
    without one). Wrapped in try/except — DRG must not block the response.
    """
    if not primary_diagnosis or not primary_diagnosis.get("code"):
        return None
    try:
        from app.services.drg_grouper import group_drg
        # Use the first procedure code (CHS-DRG grouping is per-procedure)
        procedure_code = procedures[0].get("code") if procedures else None
        diagnosis_codes = [primary_diagnosis.get("code", "")]
        for d in secondary_diagnoses:
            code = d.get("code")
            if code:
                diagnosis_codes.append(code)
        grp = group_drg(diagnosis_codes=diagnosis_codes, procedure_code=procedure_code)
        # Derive is_medical_or_surgical + reason for the API surface
        grp["is_medical_or_surgical"] = grp.get("grouping_method", "") or "unknown"
        if not grp.get("coverage"):
            grp["reason"] = "code not in CHS-DRG 1.1 catalog; coverage=False"
        else:
            grp["reason"] = "ok"
        return grp
    except Exception as e:
        return {"status": "error", "reason": str(e)[:120]}


def _detect_high_risk(all_codes: list[str], hr_set: set[str]) -> list[dict]:
    """返回 [{code, reason, evidence: [], human_review_required: true, current_status: pending}]。"""
    out = []
    for code in all_codes:
        if code in hr_set:
            out.append({
                "code": code,
                "is_priority": code in PRIORITY_HIGH_RISK_CODES,
                "reason": (
                    f"命中高风险易错编码点 (5 重点码: {code}) — 须人工确认 (M2b-2 §6 + M3-0 硬性)"
                    if code in PRIORITY_HIGH_RISK_CODES
                    else f"命中高风险易错编码点 (62 全集) — 须人工确认 (M2b-2 §6)"
                ),
                "evidence": [],
                "human_review_required": True,
                "current_status": "pending",
            })
    return out


def _load_high_risk_set() -> set[str]:
    """从 M2b intermediate 加载高风险码集合 (M3-0 容错: 文件不存在时仅含 PRIORITY 5 码).

    PRIORITY 5 码 始终并入 (含手术码 45.1600x001, 它不在 62 全集中).
    """
    base = set(PRIORITY_HIGH_RISK_CODES)
    p = Path("data/m2b/intermediate/high_risk_coding_points.json")
    if not p.exists():
        return base
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        return base | {c["code"] for c in data.get("codes", [])}
    except Exception:
        return base


# ── 工具: 14 阶段模拟执行 (M3-0 复用 medical_coding adapter + M2a 链路) ──


@contextmanager
def _record_stage(
    stage_ctx: Any | None,
    name: str,
    observed: list[str],
    tool_input: dict | None = None,
) -> Iterator[Any]:
    """Record one of the 14 PIPELINE_STAGES to the M2a trace.

    When ``stage_ctx`` is None the call is a no-op (yields None). When set,
    the underlying ``stage_ctx.stage(name)`` context manager records the
    stage as a real tool call (with duration_ms, status, tool_run_id).
    In both cases the stage name is appended to ``observed`` on entry so
    the response's ``pipeline_stages_observed`` list is consistent.
    """
    if stage_ctx is None:
        observed.append(name)
        yield None
        return
    with stage_ctx.stage(name, tool_input=tool_input) as s:
        observed.append(name)
        try:
            yield s
        except Exception as e:
            s.set_status("error", str(e))
            raise


async def _execute_pipeline_14_stages(
    body: CodingReviewRunRequest,
    run_id: str,
    trace_id: str,
    stage_ctx: Any | None = None,
) -> dict:
    """执行 14 阶段工具调用, 全部经过 M2aRecorder.inference/ctx.stage 发射阶段 trace.

    ``stage_ctx`` 是从 ``M2aRecorder.inference(...)`` 进入上下文后拿到的
    ``_InferenceContext``. 若为 None, 则不记录 trace (但响应 shape 不变).

    M3-0 行为: 复用 HybridCodingAdapter 做核心推理; 其余 13 阶段用确定性占位 (无模型时返回 unavailable).
    """
    try:
        from app.main import app as _app
        gateway = _app.state.platform_gateway if hasattr(_app.state, "platform_gateway") else None
        data_policy = _app.state.data_policy if hasattr(_app.state, "data_policy") else None
        m2a_recorder = getattr(_app.state, "m2a_recorder", None)
    except Exception:
        gateway, data_policy, m2a_recorder = None, None, None

    # Hospital pilot degraded-echo gate (M3-0 Commit 1):
    # No LLM credential configured → force the degraded-echo path even when
    # the lifespan has set up a gateway. This prevents a pilot reviewer from
    # mistaking mock-LLM output for a real DeepSeek inference. The opt-in
    # ``ICODER_ALLOW_DEGRADED_NO_KEY=1`` is what makes this call reachable
    # in the first place — see the 503 gate in ``coding_review_run``.
    no_llm_credential = not os.environ.get("ICODER_CREDENTIAL_LLM", "").strip()
    force_degraded = no_llm_credential

    observed_stages: list[str] = []
    risk_route: dict = {"level": "unknown", "reasons": [], "high_risk_hits": []}
    safety_gate: dict = {"rule_count": 0, "block_count": 0, "rules": []}
    primary_diagnosis: dict | None = None
    secondary_diagnoses: list[dict] = []
    procedures: list[dict] = []
    evidence_chain: list[dict] = []
    business_result_generated = False
    degraded = False
    reason = ""
    final_status = "success"

    hr_set = _load_high_risk_set()
    all_codes = (
        _split_codes(body.primary_disease_codes) +
        _split_codes(body.other_disease_codes) +
        _split_codes(body.primary_surgery_codes) +
        _split_codes(body.other_surgery_codes)
    )
    high_risk_hits = [c for c in all_codes if c in hr_set]

    # ── Stage 1: document_normalizer ─────────────────────────────────
    with _record_stage(stage_ctx, "document_normalizer", observed_stages,
                       tool_input={"encounter_chars": len(body.encounter_text or ""),
                                   "codes_count": len(all_codes)}) as s:
        normalized_text = (body.encounter_text or "").strip()
        if s is not None:
            s.set_output({"normalized_chars": len(normalized_text), "input_codes": all_codes})

    if not body.encounter_text and not all_codes:
        # 完全无输入 → 立即 unavailable
        final_status = "unavailable"
        # Stages 2-14 still get recorded as noop so trace count stays at 14
        for stage in PIPELINE_STAGES[1:]:
            with _record_stage(stage_ctx, stage, observed_stages, tool_input={"skipped": "empty_input"}) as s:
                if s is not None:
                    s.set_output({"skipped": "empty input", "noop": True})
        return {
            "status": "unavailable",
            "degraded": True,
            "business_result_generated": False,
            "manual_review_required": True,
            "reason": "encounter_text and codes are both empty; cannot run pipeline",
            "primary_diagnosis": None, "secondary_diagnoses": [], "procedures": [],
            "high_risk_coding_points": [], "evidence_chain": [],
            "risk_route": risk_route, "safety_gate": safety_gate,
            "observed_stages": observed_stages,
            "final_status": final_status,
        }

    # ── Stage 2: evidence_fact_extractor ─────────────────────────────
    with _record_stage(stage_ctx, "evidence_fact_extractor", observed_stages,
                       tool_input={"text_chars": len(body.encounter_text or "")}) as s:
        # M3-0 简化: 拆句 → evidence 数组
        sentences = [s2 for s2 in (body.encounter_text or "").replace("\n", " ").split("。") if s2.strip()]
        for sent in sentences:
            evidence_chain.append({
                "span": sent.strip()[:120],
                "source": "encounter_text",
            })
        if s is not None:
            s.set_output({"sentences_extracted": len(sentences), "evidence_count": len(evidence_chain)})

    # ── Stage 3: coding_eligibility_classifier ───────────────────────
    with _record_stage(stage_ctx, "coding_eligibility_classifier", observed_stages,
                       tool_input={"text_chars": len(body.encounter_text or ""),
                                   "code_inputs": len(all_codes)}) as s:
        # 简化: 有 encounter_text 或 code 至少一个即 eligible
        eligible = bool(normalized_text) or bool(all_codes)
        if not eligible:
            degraded = True
            reason = "no coding-eligible input"
            final_status = "fallback"
        if s is not None:
            s.set_output({"eligible": eligible})

    # ── Stage 4: candidate_generator (real HybridCodingAdapter) ─────
    with _record_stage(stage_ctx, "candidate_generator", observed_stages,
                       tool_input={"text_chars": len(body.encounter_text or "")}) as s:
        if not gateway or force_degraded:
            # 无 gateway 或无 LLM credential → 走占位 degraded 路径
            # (force_degraded 在 no_llm_credential 时为 True, 与 commit 1 保持一致)
            degraded = True
            if not reason:
                reason = (
                    "no LLM gateway configured; running pipeline validation (no model inference)"
                    if not gateway
                    else "no LLM credential configured; running pipeline validation in degraded-echo mode"
                )
                final_status = "fallback"

            primary_diagnosis = {
                "code": body.primary_disease_codes.split(";")[0].strip() if body.primary_disease_codes else "",
                "description": "(degraded — no LLM gateway)" if not gateway else "(degraded — no LLM credential)",
                "confidence": 0.0,
                "category": "principal",
                "evidence": [],
                "human_review_required": True,
                "risk_level": "unknown",
            }
            for c in _split_codes(body.other_disease_codes):
                secondary_diagnoses.append({
                    "code": c, "description": "", "confidence": 0.0,
                    "evidence": [], "human_review_required": True, "risk_level": "unknown",
                })
            for c in _split_codes(body.primary_surgery_codes) + _split_codes(body.other_surgery_codes):
                procedures.append({
                    "code": c, "description": "", "confidence": 0.0,
                    "evidence": [], "human_review_required": True, "risk_level": "unknown",
                })
            if s is not None:
                s.set_output({"mode": "degraded", "candidates": [primary_diagnosis] + secondary_diagnoses + procedures})
        else:
            # 有 gateway + 有 credential → 走 HybridCodingAdapter 真实推理 (M2a trace 自动产生)
            if not reason:
                reason = "running HybridCodingAdapter inference (mode=hybrid)"
            try:
                from icoder_runtime.providers.medical_coding import HybridCodingAdapter
                # M3-0 修复: HybridCodingAdapter 不接受 recorder= 参数; M2aRecorder 通过
                # app.state.m2a_recorder 全局单例已被独立激活, 不用传给 adapter.
                adapter = HybridCodingAdapter(
                    gateway=gateway, mode="hybrid",
                )
                messages = [{"role": "user", "content": body.encounter_text or "(empty)" }]
                if data_policy and data_policy.pii_redaction_required:
                    from icoder_runtime.core.pii_redaction import PIIRedactor
                    redactor = PIIRedactor(enabled=True)
                    messages, _ = redactor.redact_messages(messages)
                result = await adapter.infer_async(messages)
                d = result.to_dict()
                # 映射到 CodingReviewRunResponse
                primary_diagnosis = d.get("primary_diagnosis")
                secondary_diagnoses = d.get("secondary_diagnoses", []) or d.get("other_diagnoses", [])
                procedures = d.get("procedures", [])
                business_result_generated = primary_diagnosis is not None or bool(procedures)
                if s is not None:
                    s.set_output({
                        "primary_code": (primary_diagnosis or {}).get("code", ""),
                        "secondary_count": len(secondary_diagnoses),
                        "procedure_count": len(procedures),
                    })
            except Exception as e:
                degraded = True
                reason = f"HybridCodingAdapter failed: {e!r}"
                final_status = "error"
                if s is not None:
                    s.set_status("error", str(e))

    # ── Stage 5: ontology_service ────────────────────────────────────
    with _record_stage(stage_ctx, "ontology_service", observed_stages,
                       tool_input={"codes": [primary_diagnosis.get("code") if primary_diagnosis else ""] + [d.get("code", "") for d in secondary_diagnoses]}) as s:
        # M3-0 简化: 标记 "lookup performed" 但不查 icd10cn (减小数据依赖)
        if s is not None:
            s.set_output({"lookups_attempted": 1, "deferred_to_runtime": True})

    # ── Stage 6: high_risk_coding_point_checker ──────────────────────
    with _record_stage(stage_ctx, "high_risk_coding_point_checker", observed_stages,
                       tool_input={"codes": all_codes}) as s:
        high_risk_coding_points = _detect_high_risk(all_codes, hr_set)
        if s is not None:
            s.set_output({"high_risk_hits": high_risk_hits, "points": len(high_risk_coding_points)})

    # ── Stage 7: kg_auditor ──────────────────────────────────────────
    with _record_stage(stage_ctx, "kg_auditor", observed_stages,
                       tool_input={"primary_code": (primary_diagnosis or {}).get("code", "")}) as s:
        # M3-0: kg_auditor 是占位阶段, 真实 KG 校验是 M3+ 范畴
        if s is not None:
            s.set_output({"noop": True, "note": "M3-0 deferred (KG auditor placeholder)"})

    # ── Stage 8: code_reconciler ─────────────────────────────────────
    with _record_stage(stage_ctx, "code_reconciler", observed_stages,
                       tool_input={"primary_code": (primary_diagnosis or {}).get("code", "")}) as s:
        # M3-0: 对齐 user-provided codes 与 AI 候选 (占位, 不实际修改)
        if s is not None:
            s.set_output({"noop": True, "user_codes": all_codes})

    # ── Stage 9: risk_router (M2a RiskRouter) ────────────────────────
    with _record_stage(stage_ctx, "risk_router", observed_stages,
                       tool_input={"high_risk_count": len(high_risk_hits)}) as s:
        try:
            from icoder_runtime.m2a.risk_router import RiskRouter
            rr = RiskRouter()
            indicators = {
                "high_risk_coding_point_hit": bool(high_risk_hits),
                "high_risk_count": len(high_risk_hits),
                "primary_dx_count": len(_split_codes(body.primary_disease_codes)),
            }
            route = rr.route(
                indicators=indicators, data_source="real", production_allowed=False,
            )
            risk_route = {
                "level": getattr(route, "risk_level", "unknown"),
                "reasons": getattr(route, "risk_reasons", []),
                "sample_rejected": getattr(route, "sample_rejected", False),
                "high_risk_hits": high_risk_hits,
            }
            if s is not None:
                s.set_output({"level": risk_route["level"], "reasons": risk_route["reasons"]})
        except Exception as e:
            risk_route["reasons"].append(f"RiskRouter failed (non-fatal): {e!r}")
            if s is not None:
                s.set_status("error", str(e))

    # ── Stage 10: medical_safety_gate ────────────────────────────────
    with _record_stage(stage_ctx, "medical_safety_gate", observed_stages,
                       tool_input={"primary_dx": (primary_diagnosis or {}).get("code", "")}) as s:
        try:
            from icoder_runtime.m2a.safety_gate import MedicalSafetyGate
            sg = MedicalSafetyGate()
            gate = sg.evaluate(metrics={
                "evidence_grounding_rate": 0.0,
                "primary_dx_damage_rate": 0.0,
            })
            safety_gate = {
                "rule_count": len(getattr(gate, "rules", []) or []),
                "block_count": sum(1 for r in (getattr(gate, "rules", []) or []) if getattr(r, "status", "") == "block"),
                "rules": [
                    {"rule": getattr(r, "rule", "unknown"), "status": getattr(r, "status", "unknown"),
                     "reason": getattr(r, "reason", "")}
                    for r in (getattr(gate, "rules", []) or [])
                ],
            }
            if s is not None:
                s.set_output({"rule_count": safety_gate["rule_count"], "block_count": safety_gate["block_count"]})
        except Exception as e:
            safety_gate["rules"].append({"rule": "SELF-CHECK", "status": "warning", "reason": f"SafetyGate failed: {e!r}"})
            if s is not None:
                s.set_status("error", str(e))

    # ── Stage 11: human_review ──────────────────────────────────────
    # DRG/DIP fail-safe: when no real grouper produced a coverage=True group,
    # require manual review (cannot be billed/audited without grouping).
    drg_route_local = locals().get("drg_route")
    drg_unavailable = (
        not drg_route_local
        or not drg_route_local.get("coverage")
        or drg_route_local.get("status") == "error"
    )
    with _record_stage(stage_ctx, "human_review", observed_stages,
                       tool_input={"high_risk_points": len(high_risk_coding_points),
                                   "manual_review_required": bool(high_risk_coding_points) or degraded or drg_unavailable}) as s:
        # 标记 human_review 阶段触发条件
        manual_review_required = (
            bool(high_risk_coding_points)
            or degraded
            or not business_result_generated
            or drg_unavailable
        )
        if s is not None:
            s.set_output({"triggered": manual_review_required, "review_url": f"/api/icoder/coding-review/{run_id}/human-review"})

    # ── Stage 12: report_generator ──────────────────────────────────
    with _record_stage(stage_ctx, "report_generator", observed_stages,
                       tool_input={"run_id": run_id}) as s:
        # 真实报告在 GET /{run_id}/report 时按需渲染; 阶段记录为 noop
        if s is not None:
            s.set_output({"noop": True, "report_url": f"/api/icoder/coding-review/{run_id}/report"})

    # ── Stage 13: run_trace_emitter ─────────────────────────────────
    with _record_stage(stage_ctx, "run_trace_emitter", observed_stages,
                       tool_input={"run_id": run_id, "trace_id": trace_id}) as s:
        # run trace 由 M2aRecorder 自身在 finalize 时写入; 阶段为 noop
        if s is not None:
            s.set_output({"noop": True, "recorder_active": stage_ctx is not None})

    # ── Stage 14: audit_logger ──────────────────────────────────────
    with _record_stage(stage_ctx, "audit_logger", observed_stages,
                       tool_input={"action": "coding_review.run"}) as s:
        # 真实 audit log 写入由调用方 (coding_review_run) 在 stage_ctx 上下文外做;
        # 阶段为 noop (本函数职责是 trace, 不写 AuditLog)
        if s is not None:
            s.set_output({"noop": True, "written_by": "coding_review_run"})

    # DRG/DIP fail-safe inside pipeline: require manual review when the
    # pipeline ran but no real grouper produced a coverage=True group.
    # At this point drg_route is not yet computed; the caller will
    # recompute manual_review_required using drg_route after _compute_drg_route.
    return {
        "status": "unavailable" if degraded and not business_result_generated else ("ok" if business_result_generated else "degraded"),
        "degraded": degraded,
        "business_result_generated": business_result_generated,
        "manual_review_required": degraded or bool(high_risk_coding_points) or not business_result_generated,
        "reason": reason or "ok",
        "primary_diagnosis": primary_diagnosis,
        "secondary_diagnoses": secondary_diagnoses,
        "procedures": procedures,
        "high_risk_coding_points": high_risk_coding_points,
        "evidence_chain": evidence_chain,
        "risk_route": risk_route,
        "safety_gate": safety_gate,
        "observed_stages": observed_stages,
        "final_status": final_status,
    }


# ── 路由 1: POST /api/icoder/coding-review/run ──────────────────────────


@router.post("/run", response_model=CodingReviewRunResponse)
async def coding_review_run(
    body: CodingReviewRunRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """启动 14 阶段审核流水线, 返回 run_id / trace_id + 14 阶段结果。"""
    # Hospital pilot gate: refuse to run when LLM credential is missing.
    # Otherwise the degraded path echoes user-supplied codes back as a result
    # that a pilot reviewer cannot visually distinguish from a real inference.
    # Dev / smoke can opt in with ICODER_ALLOW_DEGRADED_NO_KEY=1.
    if not os.environ.get("ICODER_CREDENTIAL_LLM", "").strip():
        if os.environ.get("ICODER_ALLOW_DEGRADED_NO_KEY", "") != "1":
            raise HTTPException(
                status_code=503,
                detail={
                    "reason": "llm_credential_missing",
                    "hint": (
                        "Set ICODER_CREDENTIAL_LLM (DeepSeek API key) before running. "
                        "Set ICODER_ALLOW_DEGRADED_NO_KEY=1 ONLY for local dev "
                        "(returns degraded echo of user-supplied codes — not a real model result)."
                    ),
                },
            )

    started_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    run_id = uuid.uuid4().hex[:24]
    trace_id = uuid.uuid4().hex[:24]

    if body.mode not in ("link_validation", "model_evaluation"):
        raise HTTPException(status_code=400, detail=f"mode={body.mode!r} not in (link_validation, model_evaluation)")
    if body.mode == "model_evaluation":
        # M3-0 不启用 model_evaluation (需 external prediction-file)
        raise HTTPException(
            status_code=501,
            detail=(
                "mode=model_evaluation requires --prediction-file (external model output). "
                "M3-0 阶段不启用, 仅 link_validation 模式可用. "
                "M3+ 阶段将开放 (see docs/M3_HOMEPAGE_CODING_REVIEW_AGENT_SPEC.md §3)."
            ),
        )

    # Open the M2aRecorder inference context — this emits 14 stage tool
    # calls under a real RunTrace that can be queried via /api/m2a/runs/{run_id}.
    # When the recorder is inactive (tests / no RunTraceService wired), the
    # context is a no-op and we still get the same response shape.
    try:
        from app.main import app as _app_for_recorder
        m2a_recorder = getattr(_app_for_recorder.state, "m2a_recorder", None)
    except Exception:
        m2a_recorder = None

    recorder_ctx: Any | None = None
    if m2a_recorder is not None and m2a_recorder.is_active():
        recorder_ctx = m2a_recorder.inference(
            agent_ref=AGENT_REF,
            data_source="real",
            is_sample=False,
            metadata={"case_id": body.case_id, "user_id": current_user.id, "mode": body.mode},
            run_id=run_id,
            trace_id=trace_id,
        )
    else:
        # Build a no-op context that yields None so _execute_pipeline_14_stages
        # can use a single `with` form. The dummy guard exists so the finally
        # block can call __exit__ on the same object that was entered.
        @contextmanager
        def _noop_inference():
            yield None
        recorder_ctx = _noop_inference()

    with recorder_ctx as stage_ctx:
        result = await _execute_pipeline_14_stages(body, run_id, trace_id, stage_ctx=stage_ctx)
        # Compute DRG group (Commit 7) — best-effort, must not block the response.
        # The grouping is intentionally called *after* the 14 stages so the
        # primary diagnosis / secondary / procedures used for grouping are
        # the pipeline's final values, not user-input echoes.
        drg_route = _compute_drg_route(
            primary_diagnosis=result.get("primary_diagnosis"),
            secondary_diagnoses=result.get("secondary_diagnoses", []),
            procedures=result.get("procedures", []),
        )
        result["drg_route"] = drg_route
        # DRG/DIP fail-safe: if no real grouper produced a coverage=True group,
        # require manual review (cannot bill/audit without grouping).
        drg_unavailable = (
            not drg_route
            or not drg_route.get("coverage")
            or drg_route.get("status") == "error"
        )
        if drg_unavailable:
            result["manual_review_required"] = True
            result.setdefault("reason", "")
            if "DRG" not in (result.get("reason") or ""):
                result["reason"] = (
                    (result.get("reason") + "; " if result.get("reason") else "")
                    + "DRG/DIP grouper unavailable; manual review required"
                )
        # Propagate final state to the recorder context so finalize_run
        # persists the right final_status / risk_route / safety_gate.
        if stage_ctx is not None:
            try:
                stage_ctx.final_status = result.get("final_status", "success")
                stage_ctx.risk_route = result.get("risk_route", {})
                stage_ctx.safety_gate = result.get("safety_gate", {})
            except Exception:
                pass
    finished_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # Compute high-risk hits for audit log (also used by the report renderer).
    hr_set = _load_high_risk_set()
    all_input_codes = (
        _split_codes(body.primary_disease_codes) +
        _split_codes(body.other_disease_codes) +
        _split_codes(body.primary_surgery_codes) +
        _split_codes(body.other_surgery_codes)
    )
    high_risk_hits = [c for c in all_input_codes if c in hr_set]

    # Persist to DB (M3-0 hospital pilot). The CodingReviewRun row is the
    # authoritative state — _RUNS_STORE keeps a read-only mirror for the
    # transition window only.
    db_row = CodingReviewRun(
        id=run_id,
        agent_ref=AGENT_REF,
        agent_category=AGENT_CATEGORY,
        prediction_mode=body.mode,
        case_id=body.case_id or None,
        trace_id=trace_id,
        input_source=body.input_source,
        status=result["status"],
        degraded=result["degraded"],
        business_result_generated=result["business_result_generated"],
        manual_review_required=result["manual_review_required"],
        reason=(result["reason"] or "")[:512],
        primary_diagnosis=result["primary_diagnosis"],
        secondary_diagnoses=result["secondary_diagnoses"],
        procedures=result["procedures"],
        high_risk_coding_points=result["high_risk_coding_points"],
        evidence_chain=result["evidence_chain"],
        risk_route=result["risk_route"],
        safety_gate=result["safety_gate"],
        drg_route=result.get("drg_route"),
        pipeline_stages_observed=result["observed_stages"],
        human_review_records=[],
        encounter_text=body.encounter_text or None,
        organization_id=await _resolve_user_org_id(current_user.id, db),
        created_by_user_id=current_user.id,
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
    )
    db.add(db_row)
    await db.flush()  # ensure DB-level id is materialized before commit

    # Mirror to in-memory store for backward-compat reads only. Writes
    # are no longer authoritative here.
    _RUNS_STORE[run_id] = {
        "run_id": run_id,
        "trace_id": trace_id,
        "agent_ref": AGENT_REF,
        "agent_category": AGENT_CATEGORY,
        "prediction_mode": body.mode,
        "input": {
            "encounter_text": body.encounter_text,
            "case_id": body.case_id,
            "input_source": body.input_source,
            "primary_disease_codes": body.primary_disease_codes,
            "other_disease_codes": body.other_disease_codes,
            "primary_surgery_codes": body.primary_surgery_codes,
            "other_surgery_codes": body.other_surgery_codes,
        },
        "result": result,
        "started_at": started_at,
        "finished_at": finished_at,
        "human_review_records": [],
        "drg_route": drg_route,
    }

    # Audit log: every /run invocation is recorded for hospital compliance.
    # Best-effort — a failure here does not block the run response.
    user_org_id = await _resolve_user_org_id(current_user.id, db)
    try:
        await log_action(
            db,
            user_id=current_user.id,
            username=current_user.username,
            action="coding_review.run",
            resource_type="coding_review_run",
            resource_id=run_id,
            details={
                "case_id": body.case_id,
                "mode": body.mode,
                "input_source": body.input_source,
                "model_version": "deepseek-v4-flash (M3-0 interim)",
                "business_result_generated": result["business_result_generated"],
                "degraded": result["degraded"],
                "manual_review_required": result["manual_review_required"],
                "high_risk_hits": high_risk_hits,
                "pipeline_stages_observed": result["observed_stages"],
            },
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            status="success" if not result["degraded"] else "warning",
            organization_id=user_org_id,
        )
    except Exception as _audit_err:
        logger.warning(f"audit log write failed (non-fatal) for run_id={run_id}: {_audit_err!r}")

    return CodingReviewRunResponse(
        run_id=run_id,
        trace_id=trace_id,
        agent_ref=AGENT_REF,
        agent_category=AGENT_CATEGORY,
        prediction_mode=body.mode,
        status=result["status"],
        degraded=result["degraded"],
        business_result_generated=result["business_result_generated"],
        manual_review_required=result["manual_review_required"],
        reason=result["reason"],
        primary_diagnosis=result["primary_diagnosis"],
        secondary_diagnoses=result["secondary_diagnoses"],
        procedures=result["procedures"],
        high_risk_coding_points=result["high_risk_coding_points"],
        evidence_chain=result["evidence_chain"],
        risk_route=result["risk_route"],
        safety_gate=result["safety_gate"],
        drg_route=result.get("drg_route"),
        pipeline_stages_observed=result["observed_stages"],
        trace_url=f"/api/m2a/runs/{run_id}",
        human_review_url=f"/api/icoder/coding-review/{run_id}/human-review",
        report_url=f"/api/icoder/coding-review/{run_id}/report",
        started_at=started_at,
        finished_at=finished_at,
    )


# ── 路由 2: POST /api/icoder/coding-review/{run_id}/human-review ──────


@router.post("/{run_id}/human-review", response_model=HumanReviewResponse)
async def coding_review_human_review(
    run_id: str,
    body: HumanReviewAction,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """提交人工复核动作 (5 合法 action: accept / reject / modify / insufficient_evidence / escalate).

    硬性 (M3 任务 §5):
    1. reason_code 必填
    2. 主诊断修改必须强制确认 (action=modify + target_role=primary_disease → 需 reviewer + reason_code)
    3. 高风险易错编码点必须 human_review_required=true (在 Run 阶段已标记)
    4. sample / production_allowed=false 不得写入生产 (但可写评估 review log + learning loop candidate)
    5. RBAC: role 必须 ∈ {admin, coder} (M3-0 医院试点)
    """
    # RBAC gate: only admin / coder can submit human-review actions.
    # Server reads the role from the JWT, not from the request body.
    user_role = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    if user_role not in _HUMAN_REVIEW_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Human-review requires role in {sorted(_HUMAN_REVIEW_ROLES)}, "
                f"got role={user_role!r}"
            ),
        )

    rec = await _load_run_record(run_id, db)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"run_id={run_id} not found")

    errors: list[str] = []
    warnings: list[str] = []

    # 1. action 合法
    if body.action not in ALLOWED_HUMAN_ACTIONS:
        errors.append(f"action={body.action!r} not in {sorted(ALLOWED_HUMAN_ACTIONS)}")

    # 2. reason_code 必填 (M3 硬性)
    if not body.reason_code.strip():
        errors.append("reason_code is required (M3 任务 §5 硬性)")

    # 3. reviewer 必填
    if not body.reviewer.strip():
        errors.append("reviewer is required")

    # 4. reviewer_role 可选, 缺失给 warning
    if not body.reviewer_role.strip():
        warnings.append("reviewer_role is empty; M3-0 阶段允许通过, 但生产环境建议填写 (admin/coder/medical_insurance_reviewer/it_operator/auditor)")

    # 5. 主诊断修改必须人工确认 (modify + target_role=primary_disease → 强制 confirm)
    if body.action == "modify" and body.target_role == "primary_disease":
        if not body.new_code.strip():
            errors.append("modify primary_disease requires new_code (M3 硬性: 主诊断修改必须人工确认)")
        # 强制 confirm 通过 reviewer + reason_code 体现

    # 6. 高风险易错编码点必须人工确认 (在 Run 阶段已标记, 这里再次确认)
    if body.target_code in PRIORITY_HIGH_RISK_CODES and body.action in ("reject", "insufficient_evidence"):
        # 接受: human 同意编码; reject/insufficient 也允许, 但需 reason_code
        if not body.reason_code.strip():
            errors.append(f"高风险易错编码点 {body.target_code} 触发 reject/insufficient_evidence 时 reason_code 必填")

    if errors:
        return HumanReviewResponse(
            run_id=run_id, accepted=False, record_id="", action=body.action,
            target_code=body.target_code, new_code=body.new_code,
            validation_errors=errors, warnings=warnings,
            recorded_at="",
        )

    # 7. 记录 (M3-0: in-memory; M3+: DB + AuditLog)
    record_id = uuid.uuid4().hex[:16]
    recorded_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    # Reviewer identity is sourced from the JWT, not the request body —
    # the body values are kept as a fallback only, with a warning if they
    # disagree with the authenticated user.
    authenticated_reviewer = current_user.username
    authenticated_role = current_user.role.value
    if body.reviewer.strip() and body.reviewer.strip() != authenticated_reviewer:
        warnings.append(
            f"reviewer in body ({body.reviewer!r}) differs from JWT user "
            f"({authenticated_reviewer!r}); server uses JWT identity"
        )
    if body.reviewer_role.strip() and body.reviewer_role.strip() != authenticated_role:
        warnings.append(
            f"reviewer_role in body ({body.reviewer_role!r}) differs from JWT role "
            f"({authenticated_role!r}); server uses JWT role"
        )
    entry = {
        "record_id": record_id,
        "case_id": body.case_id,
        "target_code": body.target_code,
        "target_role": body.target_role,
        "action": body.action,
        "new_code": body.new_code,
        "reason_code": body.reason_code,
        "review_note": body.review_note,
        "reviewer": authenticated_reviewer,
        "reviewer_role": authenticated_role,
        "confirmed_at": recorded_at,
    }

    # Persist human-review entry to DB (authoritative) and mirror to in-memory.
    db_row = (await db.execute(
        select(CodingReviewRun).where(CodingReviewRun.id == run_id)
    )).scalar_one_or_none()
    if db_row is not None:
        records = list(db_row.human_review_records or [])
        records.append(entry)
        db_row.human_review_records = records
        await db.flush()
    if run_id in _RUNS_STORE:
        _RUNS_STORE[run_id]["human_review_records"].append(entry)

    audit_log_entry = {
        "actor": body.reviewer,
        "action": f"human_review.{body.action}",
        "target": f"{body.target_role}:{body.target_code}",
        "reason_code": body.reason_code,
        "production_writeback_blocked": True,  # 硬性
        "at": recorded_at,
    }
    # 不污染 M2a AuditLog 入口 (M3-0 暂记在 _RUNS_STORE)

    # Audit log: every successful human-review action is recorded.
    # Best-effort — a failure here does not block the response.
    hr_user_org_id = await _resolve_user_org_id(current_user.id, db)
    try:
        await log_action(
            db,
            user_id=current_user.id,
            username=current_user.username,
            action=f"coding_review.human_review.{body.action}",
            resource_type="coding_review_run",
            resource_id=run_id,
            details={
                "record_id": record_id,
                "action": body.action,
                "target_role": body.target_role,
                "target_code": body.target_code,
                "new_code": body.new_code,
                "reason_code": body.reason_code,
                "reviewer_role_jwt": authenticated_role,
                "production_writeback_blocked": True,
            },
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            status="success",
            organization_id=hr_user_org_id,
        )
    except Exception as _audit_err:
        logger.warning(
            f"audit log write failed (non-fatal) for run_id={run_id} "
            f"action={body.action}: {_audit_err!r}"
        )

    return HumanReviewResponse(
        run_id=run_id,
        accepted=True,
        record_id=record_id,
        action=body.action,
        target_code=body.target_code,
        new_code=body.new_code,
        production_writeback_blocked=True,  # 硬性
        validation_errors=[],
        warnings=warnings,
        audit_log_entry=audit_log_entry,
        recorded_at=recorded_at,
    )


# ── 路由 3: GET /api/icoder/coding-review/{run_id}/report ───────────


@router.get("/{run_id}/report", response_model=ReportResponse)
async def coding_review_report(
    run_id: str,
    request: Request,
    format: str = Query("html", pattern="^(html|json)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """生成 18 节审核报告 (HTML / JSON).

    硬性: pipeline validation 模式 disclaimer 必显 (§18).

    PHI redaction: ``encounter_text``, ``review_note`` (inside
    human_review_records), and ``reason_code`` are redacted before they
    reach the report. The live workbench view (GET /{run_id}) is
    unaffected — only the exported report is de-identified.
    """
    from icoder_runtime.reports.coding_review_report import render_report
    from app.services.phi_redactor import redact_for_export

    rec = await _load_run_record(run_id, db)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"run_id={run_id} not found")
    res = rec["result"]
    mode = rec["prediction_mode"]

    # Read versions from app.state (loaded once at lifespan startup).
    # Use defensive getattr — tests that build TestClient without lifespan
    # context will not have icoder_versions set, but report generation must
    # still succeed and surface the "unknown" version gracefully.
    _app_state = getattr(getattr(request, "app", None), "state", None)
    versions = getattr(_app_state, "icoder_versions", None) or {}

    # PHI redaction — applied to fields visible in the EXPORT only.
    redacted_encounter = redact_for_export(rec["input"].get("encounter_text", ""))
    redacted_human_review = []
    for hr in (rec.get("human_review_records") or []):
        if not isinstance(hr, dict):
            redacted_human_review.append(hr)
            continue
        redacted_human_review.append({
            **hr,
            "review_note": redact_for_export(hr.get("review_note", "")),
            "reason_code": redact_for_export(hr.get("reason_code", "")),
        })
    # evidence_chain.spans 截取自 encounter_text, 必须同步脱敏 (M3-0 review 修复)
    redacted_evidence_chain = []
    for ev in (res.get("evidence_chain") or []):
        if not isinstance(ev, dict):
            redacted_evidence_chain.append(ev)
            continue
        redacted_evidence_chain.append({
            **ev,
            "span": redact_for_export(ev.get("span", "")),
        })
    # high_risk_coding_points[].span 同样来自 encounter_text 截取, 也需脱敏
    redacted_high_risk = []
    for hr in (res.get("high_risk_coding_points") or []):
        if not isinstance(hr, dict):
            redacted_high_risk.append(hr)
            continue
        redacted_high_risk.append({
            **hr,
            "span": redact_for_export(hr.get("span", "")),
        })

    if format == "json":
        # JSON 模式: 报告结构化, 不渲染 HTML
        report_dict = {
            "agent_ref": rec["agent_ref"],
            "run_id": rec["run_id"],
            "trace_id": rec["trace_id"],
            "prediction_mode": mode,
            "started_at": rec["started_at"],
            "finished_at": rec["finished_at"],
            "input_source": rec["input"].get("input_source", ""),
            "model_version": versions.get("model_version", "unknown"),
            "code_dict_version": versions.get("code_dict_version", "unknown"),
            "rule_version": versions.get("rule_version", "unknown"),
            "agent_version": versions.get("agent_version", "unknown"),
            "data_asset_version": versions.get("data_asset_version", "unknown"),
            "primary_diagnosis": res.get("primary_diagnosis"),
            "secondary_diagnoses": res.get("secondary_diagnoses", []),
            "procedures": res.get("procedures", []),
            "high_risk_coding_points": redacted_high_risk,
            "evidence_chain": redacted_evidence_chain,
            "human_review_records": redacted_human_review,
            "encounter_text": redacted_encounter,
            "phi_redaction_applied": redacted_encounter != rec["input"].get("encounter_text", ""),
            "risk_route": res.get("risk_route", {}),
            "safety_gate": res.get("safety_gate", {}),
            "drg_route": res.get("drg_route"),
            "audit_log": [r.get("audit_log_entry", {}) for r in redacted_human_review],
            "pipeline_stages_observed": res.get("observed_stages", []),
            "disclaimer": PIPELINE_VALIDATION_DISCLAIMER if mode == "link_validation" else "model_evaluation 模式 (M3+)",
        }
        return ReportResponse(
            run_id=run_id, format="json",
            content=json.dumps(report_dict, ensure_ascii=False, indent=2),
            filename=f"coding_review_report_{run_id}.json",
            disclaimer=report_dict["disclaimer"],
            generated_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )

    # HTML 模式
    html_content = render_report(
        run_id=rec["run_id"],
        trace_id=rec["trace_id"],
        input_source=rec["input"].get("input_source", ""),
        prediction_mode=mode,
        model_version=versions.get("model_version", "unknown"),
        code_dict_version=versions.get("code_dict_version", "unknown"),
        rule_version=versions.get("rule_version", "unknown"),
        primary_diagnosis=res.get("primary_diagnosis"),
        secondary_diagnoses=res.get("secondary_diagnoses", []),
        procedures=res.get("procedures", []),
        high_risk_coding_points=redacted_high_risk,
        evidence_chain=redacted_evidence_chain,
        human_review_records=redacted_human_review,
        risk_route=res.get("risk_route", {}),
        safety_gate=res.get("safety_gate", {}),
        drg_route=res.get("drg_route"),
        audit_log=[r.get("audit_log_entry", {}) for r in redacted_human_review],
        pipeline_stages_observed=res.get("observed_stages", []),
        started_at=rec["started_at"],
        finished_at=rec["finished_at"],
    )
    return ReportResponse(
        run_id=run_id, format="html",
        content=html_content,
        filename=f"coding_review_report_{run_id}.html",
        disclaimer=PIPELINE_VALIDATION_DISCLAIMER if mode == "link_validation" else "model_evaluation 模式 (M3+)",
        generated_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )


# ── 辅助路由: GET /api/icoder/coding-review/{run_id} (重看 run) ────


@router.get("/{run_id}")
async def get_coding_review_run(
    run_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rec = await _load_run_record(run_id, db)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"run_id={run_id} not found")
    return rec


@router.get("/")
async def list_coding_review_runs(
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List recent runs from DB (M3-0 hospital pilot — replaces in-memory list)."""
    stmt = (
        select(CodingReviewRun)
        .order_by(CodingReviewRun.created_at.desc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return {
        "count": len(rows),
        "runs": [
            {
                "run_id": r.id,
                "trace_id": r.trace_id or "",
                "agent_ref": r.agent_ref,
                "prediction_mode": r.prediction_mode,
                "status": r.status,
                "manual_review_required": r.manual_review_required,
                "started_at": r.started_at.isoformat() + "Z" if r.started_at else "",
            }
            for r in rows
        ],
    }
