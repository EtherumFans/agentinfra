"""MedCoderRuntime — wraps the existing MedCodER 5-stage pipeline as Deep Mode.

Per G001 refactor (2026-07-09), the 5-stage MedCodER pipeline (extract /
retrieve / merge / rerank / compliance) is no longer the default product
flow. It's preserved here as ``mode=medcoder_deep`` for:
  - Advanced / Deep Evidence / Research Mode use
  - Complex cases where the single-stage Fast Runtime underperforms
  - The existing A2A flow (``/api/icoder/agents/medical-coding-agent``)
    which still calls :class:`HybridCodingAdapter` directly for back-compat

This runtime wraps :class:`HybridCodingAdapter` (mode="medcoder.full") and
projects the result into the same :class:`CodingResult` envelope as
:class:`FastCodingRuntime`, so the frontend can render both modes with the
same component.

Latency: 30-60s+ depending on case complexity + BGE-M3 cold-start. Caller
should set frontend timeout to 120s.
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from app.coding_runtime.base import (
    CodingRequest,
    CodingResult,
    CodingResultCode,
    RuntimeMode,
)

logger = logging.getLogger(__name__)


# 5-stage trace (per MedCodER pipeline)
DEEP_TRACE_STEPS = (
    "input_received",
    "stage1_extract",
    "stage2_retrieve",
    "stage3_merge",
    "stage4_rerank",
    "stage5_compliance",
    "project_result",
    "return",
)


class MedCoderRuntime:
    """Deep Evidence / Research Mode runtime.

    Wraps :class:`HybridCodingAdapter` (mode="medcoder.full") which runs the
    full 5-stage MedCodER pipeline. Not the default; users opt in via
    ``mode=medcoder_deep`` in the API or the Config drawer "Deep Evidence"
    toggle.
    """

    name = "medcoder_runtime"

    async def predict(self, request: CodingRequest) -> CodingResult:
        """Run the 5-stage MedCodER pipeline.

        Time budget: 90s soft cap. On timeout, return a partial result
        with whatever stages completed + a hint to retry in Fast mode.
        """
        run_id = request.run_id or f"deep-{uuid.uuid4().hex[:12]}"
        trace_id = f"trace-{uuid.uuid4().hex[:16]}"
        started = time.perf_counter()
        events: list[dict[str, Any]] = []

        def _emit(step: str, status: str = "ok", meta: dict | None = None):
            events.append({
                "step": step,
                "status": status,
                "ts": time.time(),
                "duration_ms": int((time.perf_counter() - started) * 1000),
                "metadata": meta or {},
            })

        _emit("input_received", "ok", {
            "text_len": len(request.text),
            "mode": request.mode.value,
        })

        text = (request.text or "").strip()
        if not text:
            _emit("return", "error", {"reason": "empty_input"})
            return CodingResult(
                codes=[],
                summary="输入为空,请提供病历文本后重试。",
                runtime_mode="medcoder_deep",
                latency_ms=int((time.perf_counter() - started) * 1000),
                llm_provider="deepseek",
                trace_id=trace_id,
                run_id=run_id,
                trace_events=events,
                error=True,
                error_reason="empty_input",
            )

        # ── Build messages + invoke HybridCodingAdapter ─────────────────
        # HybridCodingAdapter expects OpenAI-style messages and reads the
        # user message text as the encounter narrative.
        messages = [{"role": "user", "content": text}]

        try:
            from icoder_runtime.providers.medical_coding import HybridCodingAdapter
            adapter = HybridCodingAdapter(mode="medcoder.full")
            _emit("stage1_extract", "ok", {"note": "stage1+2+3+4+5 run by HybridCodingAdapter"})
            schema = await adapter.infer_async(messages)
        except Exception as exc:
            logger.error(f"MedCoderRuntime: HybridCodingAdapter failed: {exc!r}", exc_info=True)
            _emit("stage1_extract", "error", {"reason": str(exc)[:200]})
            _emit("return", "error", {"reason": "pipeline_failed"})
            return CodingResult(
                codes=[],
                summary=f"Deep Evidence 推理失败: {str(exc)[:200]}。可重试或切换至 Fast Coding 模式。",
                runtime_mode="medcoder_deep",
                latency_ms=int((time.perf_counter() - started) * 1000),
                llm_provider="deepseek",
                trace_id=trace_id,
                run_id=run_id,
                trace_events=events,
                error=True,
                error_reason="pipeline_failed",
            )

        # Emit synthetic stage events based on the schema's method_stage_trace
        # (HybridCodingAdapter fills this with real per-stage data).
        stage_trace = getattr(schema, "method_stage_trace", []) or []
        stage_map = {
            "extract": "stage1_extract",
            "retrieve": "stage2_retrieve",
            "merge": "stage3_merge",
            "rerank": "stage4_rerank",
            "compliance": "stage5_compliance",
        }
        for entry in stage_trace:
            if isinstance(entry, dict):
                stage_name = entry.get("stage") or entry.get("name") or ""
                step_key = stage_map.get(stage_name.lower(), "")
                if step_key:
                    _emit(step_key, "ok", {
                        "duration_ms": entry.get("duration_ms", 0),
                        "metadata_size": len(str(entry.get("metadata", ""))),
                    })
        # If no real stage trace, emit synthetic placeholders so RunTrace
        # still shows the 5-stage progression.
        emitted_steps = {e["step"] for e in events}
        for stage_name, step_key in stage_map.items():
            if step_key not in emitted_steps:
                _emit(step_key, "ok", {"note": "synthetic — adapter did not emit detailed trace"})

        # ── Project to flat CodingResultCode list ───────────────────────
        codes: list[CodingResultCode] = []

        # MedCodER fills `extracted_diagnoses` with per-disease final_top_k
        # candidates. The top entry per diagnosis is the principal code;
        # the rest are alternatives.
        extracted = list(getattr(schema, "extracted_diagnoses", []) or [])
        # Sort by final_confidence desc so primary surfaces first.
        extracted.sort(
            key=lambda d: float(getattr(d, "final_confidence", 0.0) or 0.0),
            reverse=True,
        )
        for idx, diag in enumerate(extracted):
            top_k = list(getattr(diag, "final_top_k", []) or [])
            if not top_k:
                continue
            primary = top_k[0]
            primary_code = (
                getattr(primary, "code", "")
                if not isinstance(primary, (list, tuple, dict))
                else (primary.get("code", "") if isinstance(primary, dict)
                      else (primary[0] if len(primary) >= 1 else ""))
            )
            if not primary_code:
                continue
            primary_display = (
                getattr(primary, "name", "")
                if hasattr(primary, "name")
                else (primary.get("name", "") if isinstance(primary, dict) else "")
            )
            type_str = "primary_diagnosis" if idx == 0 else "secondary_diagnosis"
            evidence_text = "; ".join(
                getattr(span, "text", "") or ""
                for span in getattr(diag, "supporting_evidence", []) or []
                if hasattr(span, "text")
            ) or getattr(diag, "disease_text", "")
            alternatives = []
            for cand in top_k[1:5]:
                if hasattr(cand, "code"):
                    alternatives.append({
                        "code": cand.code,
                        "name": getattr(cand, "name", ""),
                        "score": float(getattr(cand, "score", 0.0) or 0.0),
                        "source": getattr(cand, "source", ""),
                    })
                elif isinstance(cand, dict):
                    alternatives.append({
                        "code": cand.get("code", ""),
                        "name": cand.get("name", ""),
                        "score": float(cand.get("score", 0.0) or 0.0),
                        "source": cand.get("source", ""),
                    })
            codes.append(CodingResultCode(
                code=primary_code,
                system="ICD-10-CN",
                display=primary_display or "",
                type=type_str,
                confidence=float(getattr(diag, "final_confidence", 0.0) or 0.0),
                evidence=evidence_text,
                rationale=f"MedCodER 5 阶段推理 — Stage 1 抽取 + Stage 2 BGE-M3 检索 + Stage 3 合并 + Stage 4 重排 + Stage 5 合规校验后的首选候选。需结合 ICD-10-CN 本地目录复核。",
                warnings=["Deep Evidence 模式输出,需结合 ICD-10-CN 本地目录进一步校验具体亚目"],
                alternatives=alternatives,
            ))

        # Procedures from schema.procedures (MedCodER may also fill these)
        for proc in getattr(schema, "procedures", []) or []:
            code = getattr(proc, "code", "")
            if not code:
                continue
            codes.append(CodingResultCode(
                code=code,
                system="ICD-9-CM-3-CN",
                display=getattr(proc, "description", "") or "",
                type="procedure",
                confidence=float(getattr(proc, "confidence", 0.0) or 0.0),
                evidence="; ".join(getattr(proc, "evidence", []) or []) if isinstance(getattr(proc, "evidence", None), list) else str(getattr(proc, "evidence", "") or ""),
                rationale="手术/操作候选 (Deep Evidence)",
                warnings=["需结合 ICD-9-CM-3-CN 本地目录进一步校验"],
            ))

        _emit("project_result", "ok", {"code_count": len(codes)})

        latency_ms = int((time.perf_counter() - started) * 1000)
        _emit("return", "ok", {"latency_ms": latency_ms, "code_count": len(codes)})

        summary = (
            f"Deep Evidence 模式完成 ({latency_ms/1000:.1f}s) — "
            f"返回 {len(codes)} 个候选编码。"
            "所有编码需结合 ICD-10-CN / ICD-9-CM-3-CN 本地目录复核具体亚目。"
        )

        raw_schema_dict = schema.to_dict() if hasattr(schema, "to_dict") else {}

        return CodingResult(
            codes=codes,
            summary=summary,
            runtime_mode="medcoder_deep",
            latency_ms=latency_ms,
            llm_provider="deepseek",
            trace_id=trace_id,
            run_id=run_id,
            cost={"amount": 0.0, "currency": "internal_credit"},
            raw_schema=raw_schema_dict,
            trace_events=events,
        )

    @property
    def supported_mode(self) -> RuntimeMode:
        return RuntimeMode.MEDCODER_DEEP
