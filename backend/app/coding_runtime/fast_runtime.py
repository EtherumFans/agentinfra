"""FastCodingRuntime — Corti-like single-stage LLM coding.

Default product runtime per G001 refactor (2026-07-09). Wraps the existing
:class:`DeepSeekCodingAdapter` which already:
  - Calls DeepSeek via LLMGateway (single chat completion, ~5-8s)
  - Uses a curated Chinese medical coding system prompt
  - Injects ICD-10 candidate codes via lightweight dictionary RAG
    (curated trigger terms + stopword-stripped n-grams — no embeddings, no
    FAISS, so <100ms latency overhead)
  - Has JSON repair logic for fault-tolerant parsing
  - Returns :class:`MedicalCodingOutputSchema`

This runtime projects the schema into a flat :class:`CodingResult` with:
  - ``codes``: flat list of primary_diagnosis + secondary_diagnoses + procedures
  - ``summary``: notes field from the schema
  - ``runtime_mode``: "corti_like_fast"
  - ``latency_ms``: measured wall-clock
  - ``llm_provider``: "deepseek"
  - ``trace_id``: generated UUID
  - ``trace_events``: 7-step lightweight trace (received / language_detect
    / build_prompt / llm_call / parse_json / project_result / return)
  - ``raw_schema``: original schema dict (for back-compat consumers)

Target latency: <15s for typical cases (Corti returns in ~8s; we aim to
match or slightly exceed that since dictionary RAG adds <100ms).
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
from icoder_runtime.providers.medical_coding.deepseek_coding_adapter import (
    DeepSeekCodingAdapter,
)

logger = logging.getLogger(__name__)


# 7-step trace for Fast Runtime (per G001 §5.7 — "Fast Runtime 也应产生轻量 trace")
FAST_TRACE_STEPS = (
    "input_received",
    "language_detect",
    "build_prompt",
    "llm_call",
    "parse_json",
    "project_result",
    "return",
)


class FastCodingRuntime:
    """Corti-like single-stage LLM coding runtime.

    Default for ``mode=corti_like_fast``. Wraps :class:`DeepSeekCodingAdapter`
    which calls DeepSeek V4 with a Chinese medical coding prompt + JSON
    repair + dictionary RAG.
    """

    name = "fast_coding_runtime"

    def __init__(self, gateway=None):
        """Args:
            gateway: LLMGateway with a DeepSeekProvider registered. If None,
                the runtime lazily resolves the platform gateway from
                ``app.state.platform_gateway`` on first ``predict`` call.
        """
        self._gateway = gateway
        self._adapter: DeepSeekCodingAdapter | None = None

    def _resolve_adapter(self) -> DeepSeekCodingAdapter:
        """Lazy-init the DeepSeekCodingAdapter.

        If no gateway was injected, resolve from ``app.state.platform_gateway``
        so the runtime can be constructed at module-load time before the
        FastAPI app is fully wired.
        """
        if self._adapter is None:
            gateway = self._gateway
            if gateway is None:
                try:
                    from app.main import app as _app
                    gateway = getattr(_app.state, "platform_gateway", None)
                except Exception:
                    gateway = None
            self._adapter = DeepSeekCodingAdapter(gateway=gateway)
        return self._adapter

    async def predict(self, request: CodingRequest) -> CodingResult:
        """Run single-stage LLM coding. Returns a CodingResult envelope.

        Time budget: 30s hard cap. If the underlying DeepSeek call exceeds
        that, we return a :class:`CodingResult` with ``error=True`` and a
        user-visible message — never a silent timeout.
        """
        run_id = request.run_id or f"fast-{uuid.uuid4().hex[:12]}"
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

        # ── Empty / oversize input guard ────────────────────────────────
        text = (request.text or "").strip()
        if not text:
            _emit("return", "error", {"reason": "empty_input"})
            return CodingResult(
                codes=[],
                summary="输入为空,请提供病历文本后重试。",
                runtime_mode="corti_like_fast",
                latency_ms=int((time.perf_counter() - started) * 1000),
                llm_provider="deepseek",
                trace_id=trace_id,
                run_id=run_id,
                trace_events=events,
                error=True,
                error_reason="empty_input",
            )
        if len(text) > 16000:
            _emit("return", "error", {"reason": "input_too_long", "len": len(text)})
            return CodingResult(
                codes=[],
                summary=f"输入过长 ({len(text)} 字符),请缩减到 16000 字以内后重试。",
                runtime_mode="corti_like_fast",
                latency_ms=int((time.perf_counter() - started) * 1000),
                llm_provider="deepseek",
                trace_id=trace_id,
                run_id=run_id,
                trace_events=events,
                error=True,
                error_reason="input_too_long",
            )

        # ── Language detection (heuristic, <1ms) ────────────────────────
        has_cjk = any('一' <= ch <= '鿿' for ch in text[:200])
        language = "zh" if has_cjk else "en"
        _emit("language_detect", "ok", {"language": language})

        # ── Build prompt + LLM call ──────────────────────────────────────
        adapter = self._resolve_adapter()
        # Build the messages list — DeepSeekCodingAdapter expects OpenAI-style
        # messages: [{"role": "user", "content": "<text>"}]. It will inject
        # the system prompt + RAG candidates internally.
        messages = [{"role": "user", "content": text}]
        _emit("build_prompt", "ok", {
            "provider": "deepseek",
            "language": language,
            "system": "icd-10-cn",
        })

        try:
            schema = await adapter.infer_async(messages)
        except Exception as exc:
            logger.error(
                f"FastCodingRuntime: DeepSeekCodingAdapter.infer_async failed: {exc!r}",
                exc_info=True,
            )
            _emit("llm_call", "error", {"reason": str(exc)[:200]})
            _emit("return", "error", {"reason": "llm_call_failed"})
            latency_ms = int((time.perf_counter() - started) * 1000)
            return CodingResult(
                codes=[],
                summary=f"编码推理失败: {str(exc)[:200]}。可重试或切换至 Deep Evidence 模式。",
                runtime_mode="corti_like_fast",
                latency_ms=latency_ms,
                llm_provider="deepseek",
                trace_id=trace_id,
                run_id=run_id,
                trace_events=events,
                error=True,
                error_reason="llm_call_failed",
            )
        _emit("llm_call", "ok", {
            "provider": "deepseek",
            "model": getattr(schema, "model", "") or "deepseek-chat",
            "is_mock": getattr(schema, "is_mock", False),
        })

        # B-003 layer 4: short-circuit on gateway-side mock envelope. If
        # schema.is_mock is True, the LLM gateway returned a degraded fallback
        # (no_api_key / provider_http_4xx / network_error / 429_503 /
        # circuit_open) and there is no real LLM output to parse. Per Charter
        # §二十六.24 ZERO TOLERANCE for false-success UI, surface as error
        # end-to-end — never let an empty/mock schema reach the success branch.
        schema_is_mock = bool(getattr(schema, "is_mock", False))
        if schema_is_mock:
            degraded_reason = _extract_degraded_reason(getattr(schema, "notes", "") or "")
            _emit("parse_json", "degraded", {"reason": degraded_reason})
            _emit("return", "degraded", {"reason": degraded_reason})
            latency_ms = int((time.perf_counter() - started) * 1000)
            return CodingResult(
                codes=[],
                summary=(
                    f"LLM 提供方降级 ({degraded_reason})。编码推理未真实执行,"
                    "请检查 API 配置后重试。"
                ),
                runtime_mode="corti_like_fast",
                latency_ms=latency_ms,
                llm_provider="mock",
                trace_id=trace_id,
                run_id=run_id,
                trace_events=events,
                error=True,
                error_reason="llm_degraded",
                degraded=True,
                degraded_reason=degraded_reason,
            )

        # ── Parse JSON response (already done by DeepSeekCodingAdapter) ─
        # If schema is in error state (review_conclusion=FAIL + issues_found
        # has DS001), surface as error.
        is_error_schema = (
            getattr(schema, "review_conclusion", "") == "FAIL"
            and any(
                getattr(issue, "code", "") == "DS001"
                for issue in getattr(schema, "issues_found", [])
            )
        )
        if is_error_schema:
            _emit("parse_json", "error", {"reason": "schema_returned_error"})
            _emit("return", "error", {"reason": "schema_returned_error"})
            latency_ms = int((time.perf_counter() - started) * 1000)
            err_msg = next(
                (getattr(issue, "message", "") for issue in schema.issues_found
                 if getattr(issue, "code", "") == "DS001"),
                "DeepSeek inference failed",
            )
            return CodingResult(
                codes=[],
                summary=f"编码推理失败: {err_msg}",
                runtime_mode="corti_like_fast",
                latency_ms=latency_ms,
                llm_provider="deepseek",
                trace_id=trace_id,
                run_id=run_id,
                trace_events=events,
                error=True,
                error_reason="schema_returned_error",
            )
        _emit("parse_json", "ok")

        # ── Project to flat CodingResultCode list ────────────────────────
        codes: list[CodingResultCode] = []

        # Primary diagnosis
        pd = getattr(schema, "primary_diagnosis", None)
        if pd and getattr(pd, "code", ""):
            codes.append(CodingResultCode(
                code=pd.code,
                system="ICD-10-CN",
                display=getattr(pd, "description", "") or "",
                type="primary_diagnosis",
                confidence=float(getattr(pd, "confidence", 0.0) or 0.0),
                evidence="; ".join(getattr(pd, "evidence", []) or []) if isinstance(getattr(pd, "evidence", None), list) else str(getattr(pd, "evidence", "") or ""),
                rationale="主要诊断 — 基于病历证据的优先编码候选,需结合 ICD-10-CN 本地目录复核具体亚目。",
                warnings=["需结合国家医保版 ICD-10-CN 目录进一步校验具体亚目"],
            ))

        # Secondary diagnoses
        for sd in getattr(schema, "secondary_diagnoses", []) or []:
            code = getattr(sd, "code", "")
            if not code:
                continue
            cat = (getattr(sd, "category", "secondary") or "secondary").lower()
            type_str = "complication" if cat == "complication" else "secondary_diagnosis"
            codes.append(CodingResultCode(
                code=code,
                system="ICD-10-CN",
                display=getattr(sd, "description", "") or "",
                type=type_str,
                confidence=float(getattr(sd, "confidence", 0.0) or 0.0),
                evidence="; ".join(getattr(sd, "evidence", []) or []) if isinstance(getattr(sd, "evidence", None), list) else str(getattr(sd, "evidence", "") or ""),
                rationale=f"次要诊断 ({cat}) — 基于病历证据的候选编码,需结合 ICD-10-CN 本地目录复核。",
                warnings=["需结合 ICD-10-CN 本地目录进一步校验具体亚目"],
            ))

        # Procedures
        for proc in getattr(schema, "procedures", []) or []:
            code = getattr(proc, "code", "")
            if not code:
                continue
            cat = (getattr(proc, "category", "therapeutic") or "therapeutic").lower()
            codes.append(CodingResultCode(
                code=code,
                system="ICD-9-CM-3-CN",
                display=getattr(proc, "description", "") or "",
                type="procedure",
                confidence=float(getattr(proc, "confidence", 0.0) or 0.0),
                evidence="; ".join(getattr(proc, "evidence", []) or []) if isinstance(getattr(proc, "evidence", None), list) else str(getattr(proc, "evidence", "") or ""),
                rationale=f"手术/操作 ({cat}) — 基于 ICD-9-CM-3-CN 编码候选,需结合本地手术目录复核。",
                warnings=["需结合 ICD-9-CM-3-CN 本地目录进一步校验具体亚目"],
            ))

        _emit("project_result", "ok", {"code_count": len(codes)})

        # ── Return envelope ─────────────────────────────────────────────
        latency_ms = int((time.perf_counter() - started) * 1000)
        _emit("return", "ok", {"latency_ms": latency_ms, "code_count": len(codes)})

        # Build summary from schema.notes (which DeepSeekCodingAdapter fills with
        # any narrative text from the LLM response).
        summary = getattr(schema, "notes", "") or self._build_summary(codes, text)
        if not summary:
            summary = self._build_summary(codes, text)

        # raw_schema keeps the original MedicalCodingOutputSchema dict so
        # downstream consumers (DiagnosisCard, evaluation harness) work.
        raw_schema_dict = schema.to_dict() if hasattr(schema, "to_dict") else {}

        return CodingResult(
            codes=codes,
            summary=summary,
            runtime_mode="corti_like_fast",
            latency_ms=latency_ms,
            llm_provider="deepseek",
            trace_id=trace_id,
            run_id=run_id,
            cost={"amount": 0.0, "currency": "internal_credit"},
            raw_schema=raw_schema_dict,
            trace_events=events,
        )

    @staticmethod
    def _build_summary(codes: list[CodingResultCode], text: str) -> str:
        """Fallback summary when schema.notes is empty."""
        if not codes:
            return "未返回编码候选。请补充更完整的病历证据后重试,或切换至 Deep Evidence 模式。"
        primary = next((c for c in codes if c.type == "primary_diagnosis"), None)
        proc_count = sum(1 for c in codes if c.type == "procedure")
        sec_count = sum(1 for c in codes if c.type in ("secondary_diagnosis", "complication"))
        parts = []
        if primary:
            parts.append(f"主要诊断候选: {primary.code} ({primary.display})")
        if sec_count:
            parts.append(f"{sec_count} 项次要诊断候选")
        if proc_count:
            parts.append(f"{proc_count} 项手术/操作候选")
        parts.append("所有编码需结合 ICD-10-CN / ICD-9-CM-3-CN 本地目录复核具体亚目。")
        return "; ".join(parts)

    @property
    def supported_mode(self) -> RuntimeMode:
        return RuntimeMode.CORTI_LIKE_FAST


def _extract_degraded_reason(notes: str) -> str:
    """B-003 layer 4 helper: parse ``[DeepSeek degraded] <reason>.`` prefix.

    LLMGateway._mock_fallback_response stamps the mock envelope's ``notes``
    with ``[DeepSeek degraded] <reason>. Mock response, not a real LLM call.``
    so downstream layers can recover the original reason (no_api_key,
    provider_http_4xx, network_error, 429_503, circuit_open) for display.

    Returns the bare reason string, or ``"unknown"`` if the prefix is absent
    (defensive — callers should still treat the schema as degraded based on
    ``is_mock``, not the prefix).
    """
    if not notes:
        return "unknown"
    marker = "[DeepSeek degraded]"
    idx = notes.find(marker)
    if idx < 0:
        return "unknown"
    tail = notes[idx + len(marker):].lstrip()
    # Reason ends at the first period or end-of-string.
    end = tail.find(".")
    if end < 0:
        return tail.strip() or "unknown"
    return tail[:end].strip() or "unknown"
