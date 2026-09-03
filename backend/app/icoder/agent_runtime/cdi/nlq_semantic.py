"""CDI NLQ Semantic Reviewer (Phase 5 Track D P0 Gate 4 Step 5).

LLM-backed semantic layer that complements the lexical + structural
``nlq_gate.py`` engine. Implements three rules that regex/keyword
matchers cannot reliably judge:

    NLQ-002  no_diagnosis_presumption
        Query must not assert a specific diagnosis in the body
        (chart verbatim is the only exception).

    NLQ-007  no_undiagnosed_condition_in_query
        A diagnosis referenced in the query must be substantiated by
        chart evidence — not just the query's own assertion.

    NLQ-008  no_single_diagnosis_suggested
        Response options must not implicitly steer the clinician to one
        answer (e.g. "the most likely cause is...").

Design:
    - Async — calls ``llm_service.chat`` directly.
    - DEGRADED on provider failure: never raises; returns ``verdict="PASS"``
      with ``degraded=True`` so the orchestrator can complete gracefully
      and a downstream auditor can see the LLM was unavailable.
    - JSON-schema constrained output via ``response_format="json"``.
    - Pure-logic fallback in ``nlq_gate.py`` remains the source of truth
      for NLQ-001/003/004/005/006/009/010 — semantic layer only overrides
      the three listed above.

Public API:

    SemanticReviewResult — dataclass returned by ``review_query``.
    review_query(query, *, llm=None) -> SemanticReviewResult
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from .nlq_gate import ProviderQueryForGate

logger = logging.getLogger(__name__)


def _extract_evidence_quote(query: Any) -> str:
    """Get evidence_quote from either ProviderQueryForGate (flat attr)
    or ProviderQuery domain object (nested in evidence_span.quote)."""

    quote = getattr(query, "evidence_quote", None)
    if quote:
        return quote
    ev = getattr(query, "evidence_span", None)
    if ev is not None:
        return getattr(ev, "quote", "") or ""
    return ""


def _extract_query_text(query: Any) -> str:
    return getattr(query, "query_text", "") or ""


def _extract_response_options(query: Any) -> list[str]:
    return list(getattr(query, "response_options", []) or [])


# ---------------------------------------------------------------------------
# System prompt — pinned for audit reproducibility
# ---------------------------------------------------------------------------


_SEMANTIC_REVIEW_PROMPT = """你是 CDI 临床澄清任务的语义审查者 (semantic reviewer). 你的工作是判断一个 Provider Query 是否违反三条语义红线:

NLQ-002 — query 正文中不得假设具体诊断 (chart verbatim 例外). 例如:
  违反: "鉴于患者已明确诊断为肺炎链球菌性肺炎, 请确认..."
  通过: "请根据痰培养结果回答病原体"

NLQ-007 — query 引用的诊断必须有 chart 证据. 例如:
  违反: query 提到 "急性肾损伤" 但 evidence_quote 不含 AKI/急性肾损伤/ARF 任何字眼
  通过: query 提到 "肺炎" 且 evidence_quote 为 "诊断: 肺炎"

NLQ-008 — response_options 不得通过措辞暗示某一答案为正确. 例如:
  违反: "A. 最可能是肺炎链球菌 (请优先考虑)"
  通过: "A. 肺炎链球菌"

输入:
  query_text: {query_text}
  evidence_quote (chart verbatim): {evidence_quote}
  response_options: {response_options}

严格按以下 JSON 格式输出 (无其他文本):
{{
  "nlq_002_pass": true | false,
  "nlq_002_reason": "short reason",
  "nlq_007_pass": true | false,
  "nlq_007_reason": "short reason",
  "nlq_008_pass": true | false,
  "nlq_008_reason": "short reason",
  "overall_verdict": "PASS" | "BLOCK",
  "block_reasons": ["NLQ-002 ...", "NLQ-007 ..."]
}}

如果 LLM/调用本身失败, 不要编造结果 — 直接返回 overall_verdict="PASS" 并把所有 *_pass 设为 true.
"""


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class SemanticReviewResult:
    """Outcome of the LLM-backed semantic review (NLQ-002/007/008)."""

    nlq_002_pass: bool = True
    nlq_002_reason: str = ""
    nlq_007_pass: bool = True
    nlq_007_reason: str = ""
    nlq_008_pass: bool = True
    nlq_008_reason: str = ""
    verdict: str = "PASS"  # "PASS" | "BLOCK"
    block_reasons: list[str] = field(default_factory=list)
    degraded: bool = False
    error_reason: str = ""
    provider: str = "deepseek"
    model: str = ""
    latency_ms: int = 0
    total_tokens: int = 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def review_query(
    query: Any,
    *,
    llm: Any | None = None,
) -> SemanticReviewResult:
    """Run the LLM-backed semantic reviewer on ``query``.

    Args:
        query: ProviderQueryForGate (flat evidence_quote) OR ProviderQuery
            domain object (evidence_quote nested in evidence_span.quote).
            Both shapes are accepted; fields are read defensively.
        llm: Optional LLM service object exposing ``async chat(messages,
            system_prompt=..., response_format="json")``. Defaults to the
            singleton ``app.services.llm_service.llm_service``.

    Returns:
        SemanticReviewResult. On provider failure, ``degraded=True`` and
        ``verdict="PASS"`` so the gate does not block on LLM outage.
    """

    if llm is None:
        from app.services.llm_service import llm_service as _default_llm
        llm = _default_llm

    import time
    t0 = time.monotonic()

    query_text = _extract_query_text(query)
    evidence_quote = _extract_evidence_quote(query)
    response_options = _extract_response_options(query)

    system_prompt = _SEMANTIC_REVIEW_PROMPT.format(
        query_text=query_text,
        evidence_quote=evidence_quote or "(empty)",
        response_options=", ".join(response_options) if response_options else "(empty)",
    )
    messages = [{"role": "user", "content": "请审查上面的 query 是否违反 NLQ-002/007/008."}]

    try:
        resp = await llm.chat(
            messages=messages,
            system_prompt=system_prompt,
            response_format="json",
            temperature=0.0,
            max_tokens=400,
        )
    except Exception as exc:  # DEGRADED — never raise out
        logger.warning("nlq_semantic LLM call failed: %s", exc)
        return SemanticReviewResult(
            degraded=True,
            error_reason=f"{type(exc).__name__}: {exc}",
            provider=getattr(llm, "provider", "deepseek"),
        )

    latency_ms = int((time.monotonic() - t0) * 1000)
    content = (resp.get("content") or "").strip()
    usage = resp.get("usage") or {}

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        # Malformed LLM response — degrade to PASS so we don't block.
        logger.warning("nlq_semantic LLM returned non-JSON: %r", content[:200])
        return SemanticReviewResult(
            degraded=True,
            error_reason="llm returned non-json content",
            provider=getattr(llm, "provider", "deepseek"),
            model=getattr(llm, "model", ""),
            latency_ms=latency_ms,
            total_tokens=int(usage.get("total_tokens", 0)),
        )

    block_reasons: list[str] = []
    nlq_002_pass = bool(data.get("nlq_002_pass", True))
    nlq_007_pass = bool(data.get("nlq_007_pass", True))
    nlq_008_pass = bool(data.get("nlq_008_pass", True))
    if not nlq_002_pass:
        block_reasons.append(f"NLQ-002 (semantic): {data.get('nlq_002_reason', '')}")
    if not nlq_007_pass:
        block_reasons.append(f"NLQ-007 (semantic): {data.get('nlq_007_reason', '')}")
    if not nlq_008_pass:
        block_reasons.append(f"NLQ-008 (semantic): {data.get('nlq_008_reason', '')}")

    verdict = "BLOCK" if block_reasons else "PASS"
    if data.get("overall_verdict") == "BLOCK" and not block_reasons:
        # LLM said BLOCK but didn't fill in a specific rule — trust the
        # overall but record an evidence-free reason.
        block_reasons.append("NLQ-SEMANTIC (overall): LLM flagged without rule-level detail")
        verdict = "BLOCK"

    return SemanticReviewResult(
        nlq_002_pass=nlq_002_pass,
        nlq_002_reason=str(data.get("nlq_002_reason", "")),
        nlq_007_pass=nlq_007_pass,
        nlq_007_reason=str(data.get("nlq_007_reason", "")),
        nlq_008_pass=nlq_008_pass,
        nlq_008_reason=str(data.get("nlq_008_reason", "")),
        verdict=verdict,
        block_reasons=block_reasons,
        degraded=False,
        provider=getattr(llm, "provider", "deepseek"),
        model=getattr(llm, "model", ""),
        latency_ms=latency_ms,
        total_tokens=int(usage.get("total_tokens", 0)),
    )


__all__ = [
    "SemanticReviewResult",
    "review_query",
]
