"""CodeReconcilerExpert — iCoDer Runtime expert for MedCodER Stage 4 (re-rank).

Takes the candidate set from :class:`IndexNavigatorExpert` (Stage 2)
and ranks them down to a final top-K per disease. LLM-backed (DeepSeek
V4 RankGPT-style) with a deterministic offline fallback that picks
the highest-scoring candidate per disease.

Phase 2 / D2 — 4 atomic experts. This is the "Stage 4 re-rank"
building block that the MedCodER 5-stage pipeline uses to produce
the final primary + secondary + procedure coding set.

Public contract
---------------
Same as :class:`CodingExpert` — sync ``__call__(invocation) -> dict``
for Phase 1, async ``invoke_async(payload, ctx) -> dict`` for
Phase 2.

Error handling
--------------
Generic exceptions translated to :class:`ExpertInvocationError` with
``stage="reconciling"``.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

from app.icoder.agent_runtime.orchestrator.delegator import (
    ExpertInvocation,
    ExpertInvocationError,
)

if TYPE_CHECKING:
    from icoder_runtime.core.llm_gateway import LLMGateway

logger = logging.getLogger(__name__)


class CodeReconcilerExpert:
    """Stage 4 re-ranker: candidate set → final coding set.

    Input shape (matches ``agent_pack.json#input_contract``):
        {
          "diagnosis_candidates": [{"fact": str, "candidates": [...]}],
          "procedure_candidates": [{"fact": str, "candidates": [...]}],
        }

    Output shape (matches ``agent_pack.json#output_contract``):
        {
          "primary_diagnosis":   {"code": str, "name": str, "confidence": float,
                                  "evidence": [...], "justification": str,
                                  "fact": str},
          "secondary_diagnoses": [{"code": str, "name": str, "confidence": float,
                                  "evidence": [...], "fact": str}],
          "procedures":          [{"code": str, "name": str, "confidence": float,
                                  "evidence": [...], "fact": str}],
          "issues_found":        [{"severity": str, "code": str, "message": str,
                                   "suggestion": str}],
          "manual_review_required": bool,
          "review_conclusion":   "PASS" | "WARNING" | "FAIL",
          "is_mock":             bool,        # true if offline fallback ran
          "expert_id":           "code-reconciler",
        }
    """

    EXPERT_ID: str = "code-reconciler"
    EXPERT_NAME: str = "Code Reconciler (MedCodER Stage 4)"

    def __init__(
        self,
        llm_gateway: "LLMGateway | None" = None,
        *,
        model: str = "deepseek-v4",
        temperature: float = 0.0,
        top_k: int = 5,
        confidence_floor: float = 0.5,
    ) -> None:
        """Construct the expert.

        ``llm_gateway`` is injected so tests can pass a stub. When None,
        ``invoke_async`` falls back to the deterministic offline
        re-ranker (``_rerank_offline``) and marks the result with
        ``is_mock=True``.
        """
        self._gateway = llm_gateway
        self._model = model
        self._temperature = temperature
        self._top_k = top_k
        self._confidence_floor = confidence_floor

    # ── Phase 1 sync interface (Delegator still sync) ─────────────

    def invoke_sync(self, invocation: ExpertInvocation) -> dict:
        """Phase 1 entry — Delegator calls this with ``ExpertInvocation``.

        ``invocation.subtask_input`` is a JSON-serialized payload from
        the upstream IndexNavigatorExpert.
        """
        ctx = invocation.context or {}
        try:
            payload = json.loads(invocation.subtask_input) if invocation.subtask_input else {}
        except (ValueError, TypeError):
            payload = {}
        return self._run_sync(payload, ctx)

    __call__ = invoke_sync

    # ── Phase 2 async interface (native) ──────────────────────────

    async def invoke_async(
        self,
        payload: dict[str, Any] | None = None,
        ctx: dict | None = None,
    ) -> dict:
        """Native async entry. Phase 2 will wire it directly."""
        payload = payload or {}
        ctx = ctx or {}
        try:
            if ctx.get("offline_only") or self._gateway is None:
                result = self._rerank_offline(payload, ctx)
            else:
                result = await self._rerank_via_llm(payload, ctx)
        except ExpertInvocationError:
            raise
        except Exception as exc:  # translate to ExpertInvocationError
            logger.exception("CodeReconcilerExpert: re-ranking failed")
            raise ExpertInvocationError(
                f"CodeReconcilerExpert: re-ranking failed "
                f"[{type(exc).__name__}]: {exc}",
                stage="reconciling",
            ) from exc

        if isinstance(result, dict):
            result.setdefault("expert_id", self.EXPERT_ID)
        return result

    # ── helpers ───────────────────────────────────────────────────

    def _run_sync(self, payload: dict, ctx: dict) -> dict:
        async def _invoke() -> dict:
            return await self.invoke_async(payload, ctx)
        return asyncio.run(_invoke())

    async def _rerank_via_llm(self, payload: dict, ctx: dict) -> dict:
        """LLM-backed re-rank. Falls back to offline on any provider error."""
        if self._gateway is None:
            return self._rerank_offline(payload, ctx)
        messages = self._build_messages(payload)
        try:
            response = await self._gateway.generate(
                messages,
                provider="",
                response_schema={
                    "type": "object",
                    "properties": {
                        "primary_diagnosis": {"type": "object"},
                        "secondary_diagnoses": {"type": "array"},
                        "procedures": {"type": "array"},
                        "issues_found": {"type": "array"},
                    },
                },
                context={"model": self._model, "temperature": self._temperature, **(ctx or {})},
            )
        except Exception as exc:
            logger.warning(
                "CodeReconcilerExpert: LLM call failed, falling back to offline: %s",
                exc,
            )
            return self._rerank_offline(payload, ctx)
        content = response.get("content", "") if isinstance(response, dict) else ""
        try:
            parsed = json.loads(content) if content else None
        except json.JSONDecodeError:
            parsed = None
        if not isinstance(parsed, dict):
            return self._rerank_offline(payload, ctx)
        parsed.setdefault("expert_id", self.EXPERT_ID)
        parsed["is_mock"] = False
        return parsed

    def _build_messages(self, payload: dict) -> list[dict[str, str]]:
        system = (
            "你是一个编码协调专家。基于候选编码列表，对每个诊断 / 手术"
            "重排成 top-K 并选定主诊断 / 主手术。输出 JSON 包含 "
            "primary_diagnosis / secondary_diagnoses / procedures / "
            "issues_found 四个字段。每个最终编码必须附 confidence "
            "(0-1) 和 evidence (list of strings from original EMR)。"
        )
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]

    # ── Offline deterministic re-ranker ─────────────────────────

    def _rerank_offline(self, payload: dict, ctx: dict) -> dict:
        """Deterministic re-ranker: per-fact, pick top-K by score.

        Strategy:
          - For each disease fact: take top-K candidates by score.
            If only one fact has candidates, its top-1 becomes the
            primary diagnosis; the rest of the disease top-K become
            secondary.
          - Same for procedures (assigned to procedures list).
          - manual_review_required: True if any confidence < confidence_floor
            OR no primary could be assigned.
        """
        dx_blocks = payload.get("diagnosis_candidates", []) or []
        px_blocks = payload.get("procedure_candidates", []) or []
        top_k = int(ctx.get("top_k") or self._top_k)
        floor = float(ctx.get("confidence_floor") or self._confidence_floor)

        primary: dict | None = None
        secondary: list[dict] = []
        procedures: list[dict] = []
        issues: list[dict] = []

        for block in dx_blocks:
            fact = (block.get("fact") or "").strip()
            cands = list(block.get("candidates", []))
            cands.sort(key=lambda c: float(c.get("score", 0.0)), reverse=True)
            top = cands[:top_k]
            if not top:
                issues.append({
                    "severity": "medium",
                    "code": "MC-R-NO-CANDIDATES",
                    "message": f"诊断事实 {fact!r} 没有候选编码",
                    "suggestion": "请人工审核或补充证据",
                })
                continue
            for c in top:
                entry = {
                    "code": c.get("code", ""),
                    "name": c.get("name", ""),
                    "confidence": float(c.get("score", 0.0)),
                    "evidence": [fact] if fact else [],
                    "fact": fact,
                }
                if primary is None and c.get("code"):
                    primary = {**entry, "justification": f"top-1 by score for {fact!r}"}
                else:
                    secondary.append(entry)

        for block in px_blocks:
            fact = (block.get("fact") or "").strip()
            cands = list(block.get("candidates", []))
            cands.sort(key=lambda c: float(c.get("score", 0.0)), reverse=True)
            top = cands[:top_k]
            for c in top:
                procedures.append({
                    "code": c.get("code", ""),
                    "name": c.get("name", ""),
                    "confidence": float(c.get("score", 0.0)),
                    "evidence": [fact] if fact else [],
                    "fact": fact,
                })
            if not top and fact:
                issues.append({
                    "severity": "medium",
                    "code": "MC-R-NO-PX-CANDIDATES",
                    "message": f"手术事实 {fact!r} 没有候选编码",
                    "suggestion": "请人工审核或补充证据",
                })

        # Manual review decision
        manual_review = primary is None
        if primary is not None and primary.get("confidence", 0.0) < floor:
            manual_review = True
            issues.append({
                "severity": "high",
                "code": "MC-R-LOW-CONFIDENCE",
                "message": f"主诊断 {primary.get('code')} 置信度 {primary.get('confidence'):.2f} 低于阈值 {floor}",
                "suggestion": "请人工复核该编码",
            })
        if not primary:
            issues.append({
                "severity": "critical",
                "code": "MC-R-NO-PRIMARY",
                "message": "未选出主诊断",
                "suggestion": "请人工审核或补充候选",
            })

        if primary is None:
            conclusion = "FAIL"
        elif manual_review:
            conclusion = "WARNING"
        else:
            conclusion = "PASS"

        return {
            "primary_diagnosis": primary or {},
            "secondary_diagnoses": secondary,
            "procedures": procedures,
            "issues_found": issues,
            "manual_review_required": manual_review,
            "review_conclusion": conclusion,
            "is_mock": True,
        }


__all__ = ["CodeReconcilerExpert"]
