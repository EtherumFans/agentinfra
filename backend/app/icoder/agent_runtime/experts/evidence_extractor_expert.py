"""EvidenceExtractorExpert — iCoDer Runtime expert for Stage 1 of MedCodER.

Implements the disease-facts + procedure-facts + negated-findings +
historical-conditions extraction that the MedCodER 5-stage pipeline's
Stage 1 (Extraction) needs. Backed by the LLM gateway (DeepSeek V4
default) with a deterministic offline fallback so the expert is
exercised in tests without a real LLM.

Phase 2 / D2 — 4 atomic experts. Layered: the
:class:`CodingExpert` (M1) orchestrates the 5-stage pipeline; this
expert is the "Stage 1 extract" building block that other methods
(e.g. future ``medcoder.prompt+retrieve`` refactors) can reuse.

Public contract
---------------
Same as :class:`CodingExpert` — sync ``__call__(invocation) -> dict``
for the Phase 1 Delegator, async ``invoke_async(text, ctx) -> dict``
for the Phase 2 native path. ``invoke_async`` is the canonical
implementation; ``invoke_sync`` drives it via ``asyncio.run``.

Error handling
--------------
Generic exceptions are translated to :class:`ExpertInvocationError`
with ``stage="extracting"`` so the Delegator's retry / backoff layer
sees a uniform error type.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import TYPE_CHECKING, Any

from app.icoder.agent_runtime.orchestrator.delegator import (
    ExpertInvocation,
    ExpertInvocationError,
)

if TYPE_CHECKING:
    from icoder_runtime.core.llm_gateway import LLMGateway

logger = logging.getLogger(__name__)


# ── Patterns used by the offline fallback ──────────────────────────

# Strip whitespace and trailing punctuation for char-span snapping.
_SENTENCE_END = re.compile(r"[。！？!?\n;；]")


class EvidenceExtractorExpert:
    """Stage 1 extractor: parse EMR into structured clinical facts.

    Output schema (matches ``agent_pack.json#output_contract.facts``):
        {
          "diagnosis_facts":   [{"fact": str, "evidence_text": str,
                                 "char_start": int, "char_end": int,
                                 "doc_type": str}],
          "procedure_facts":   [{"fact": str, "evidence_text": str,
                                 "char_start": int, "char_end": int}],
          "negated_findings":  [{"fact": str, "reason": str}],
          "historical_conditions": [{"fact": str, "years_ago": int | None}],
          "is_mock":           bool,        # present iff offline fallback ran
          "expert_id":         "evidence-extractor",
        }
    """

    EXPERT_ID: str = "evidence-extractor"
    EXPERT_NAME: str = "Evidence Extractor (MedCodER Stage 1)"

    def __init__(
        self,
        llm_gateway: "LLMGateway | None" = None,
        *,
        model: str = "deepseek-v4",
        temperature: float = 0.0,
    ) -> None:
        """Construct the expert.

        ``llm_gateway`` is injected so tests can pass a stub. When None,
        ``invoke_async`` falls back to the offline deterministic
        extractor (``_extract_offline``) and marks the result with
        ``is_mock=True`` — this keeps the runtime exercisable in CI
        without a real DeepSeek key.
        """
        self._gateway = llm_gateway
        self._model = model
        self._temperature = temperature

    # ── Phase 1 sync interface (Delegator still sync) ─────────────

    def invoke_sync(self, invocation: ExpertInvocation) -> dict:
        """Phase 1 entry — Delegator calls this with ``ExpertInvocation``."""
        return self._run_sync(invocation.subtask_input or "", invocation.context or {})

    __call__ = invoke_sync

    # ── Phase 2 async interface (native) ──────────────────────────

    async def invoke_async(
        self,
        emr_text: str,
        ctx: dict | None = None,
    ) -> dict:
        """Native async entry. Phase 2 will wire it directly.

        Strategy:
          1. If ``ctx`` pins ``offline_only=True`` or no gateway is
             configured, run the offline extractor.
          2. Otherwise call the LLM gateway; on any error, fall back
             to the offline path and surface ``is_mock=True`` so the
             recorder can attribute the result to a missing capability.
        """
        ctx = ctx or {}
        try:
            if ctx.get("offline_only") or self._gateway is None:
                result = self._extract_offline(emr_text)
            else:
                result = await self._extract_via_llm(emr_text, ctx)
        except ExpertInvocationError:
            raise
        except Exception as exc:  # translate to ExpertInvocationError
            logger.exception("EvidenceExtractorExpert: extraction failed")
            raise ExpertInvocationError(
                f"EvidenceExtractorExpert: extraction failed "
                f"[{type(exc).__name__}]: {exc}",
                stage="extracting",
            ) from exc

        if isinstance(result, dict):
            result.setdefault("expert_id", self.EXPERT_ID)
        return result

    # ── helpers ───────────────────────────────────────────────────

    def _run_sync(self, emr_text: str, ctx: dict) -> dict:
        async def _invoke() -> dict:
            return await self.invoke_async(emr_text, ctx)
        return asyncio.run(_invoke())

    async def _extract_via_llm(self, emr_text: str, ctx: dict) -> dict:
        """LLM-backed extraction path. Falls back to offline on any
        provider error so the call site is robust to LLM outage.
        """
        if self._gateway is None:  # belt-and-suspenders
            return self._extract_offline(emr_text)
        messages = self._build_messages(emr_text)
        try:
            response = await self._gateway.generate(
                messages,
                provider="",
                response_schema={
                    "type": "object",
                    "properties": {
                        "diagnosis_facts": {"type": "array"},
                        "procedure_facts": {"type": "array"},
                        "negated_findings": {"type": "array"},
                        "historical_conditions": {"type": "array"},
                    },
                },
                context={"model": self._model, "temperature": self._temperature, **(ctx or {})},
            )
        except Exception as exc:
            logger.warning(
                "EvidenceExtractorExpert: LLM call failed, falling back to offline: %s",
                exc,
            )
            return self._extract_offline(emr_text)

        content = response.get("content", "") if isinstance(response, dict) else ""
        try:
            return json.loads(content) if content else self._extract_offline(emr_text)
        except json.JSONDecodeError:
            logger.warning("EvidenceExtractorExpert: LLM JSON parse failed, offline fallback")
            return self._extract_offline(emr_text)

    def _build_messages(self, emr_text: str) -> list[dict[str, str]]:
        """Build the LLM messages for evidence extraction."""
        system = (
            "你是一个病历证据提取专家。从病历中提取诊断事实、手术事实、"
            "否定发现、既往病史。输出 JSON，必须包含 diagnosis_facts / "
            "procedure_facts / negated_findings / historical_conditions "
            "四个数组，每个 fact 必须附 evidence_text 和 char_start/char_end。"
        )
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": emr_text},
        ]

    # ── Offline deterministic extractor (tests + LLM fallback) ───

    def _extract_offline(self, emr_text: str) -> dict:
        """Deterministic offline extractor — used when the LLM gateway
        is unavailable or ``offline_only=True``.

        Heuristics (good enough for tests + structure verification,
        NOT a clinical extractor):
          - Sentences ending in 。！？ that contain disease-like
            keywords ("炎", "癌", "症", "病", "瘤") → diagnosis_facts
          - "否认"/"无"/"未见" prefixes → negated_findings
          - "X 年前"/"既往"/"史" → historical_conditions
          - "术"/"镜"/"切"/"PCI"/"支架" → procedure_facts
        """
        text = emr_text or ""
        out: dict[str, list] = {
            "diagnosis_facts": [],
            "procedure_facts": [],
            "negated_findings": [],
            "historical_conditions": [],
        }
        if not text.strip():
            out["is_mock"] = True
            return out

        # Split into sentences on common Chinese + ASCII terminators
        sentences: list[tuple[int, int, str]] = []
        last = 0
        for m in _SENTENCE_END.finditer(text):
            s, e = last, m.end()
            chunk = text[s:e].strip()
            if chunk:
                sentences.append((s, e, chunk))
            last = e
        # Trailing chunk without terminator
        if last < len(text):
            chunk = text[last:].strip()
            if chunk:
                sentences.append((last, len(text), chunk))

        disease_kw = ("炎", "癌", "症", "病", "瘤", "硬化", "梗死", "栓塞")
        procedure_kw = ("术", "镜", "切", "PCI", "支架", "造影", "活检")
        neg_prefix = ("否认", "无", "未见", "排除", "未发现")

        for start, end, sentence in sentences:
            if any(kw in sentence for kw in disease_kw):
                out["diagnosis_facts"].append({
                    "fact": sentence,
                    "evidence_text": sentence,
                    "char_start": start,
                    "char_end": end,
                    "doc_type": "present_illness",
                })
            elif any(kw in sentence for kw in procedure_kw):
                out["procedure_facts"].append({
                    "fact": sentence,
                    "evidence_text": sentence,
                    "char_start": start,
                    "char_end": end,
                })
            for prefix in neg_prefix:
                if prefix in sentence:
                    out["negated_findings"].append({"fact": sentence, "reason": prefix})
                    break

        # Historical conditions: "X 年前" / "病史 X 年" / "X 年病史" patterns
        for m in re.finditer(
            r"([^，。；,;]{2,30}?)(?:史|有)\s*(\d+)\s*年(?:\s*前)?"
            r"|"
            r"([^，。；,;]{2,30}?)\s*(\d+)\s*年(?:前)?\s*(?:史|患|罹患|得)",
            text,
        ):
            fact = (m.group(1) or m.group(3) or "").strip()
            years = m.group(2) or m.group(4)
            if fact and years:
                out["historical_conditions"].append({
                    "fact": fact,
                    "years_ago": int(years),
                })

        out["is_mock"] = True
        return out


__all__ = ["EvidenceExtractorExpert"]
