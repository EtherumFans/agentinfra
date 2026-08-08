"""DeepSeekCodingAdapter — uses DeepSeek V4 for medical coding inference.

Stage 1 real coding engine. Calls DeepSeek V4 API to generate:
- Candidate diagnosis codes with evidence, confidence
- Candidate procedure codes with evidence
- Structured reasoning per code
- Quality flags and manual review signals

Output is always normalized to MedicalCodingOutputSchema.

Configuration via environment variables (fallback to app config):
  ICODER_DEEPSEEK_MODEL=deepseek-v4
  ICODER_DEEPSEEK_TIMEOUT_SECONDS=60
  ICODER_DEEPSEEK_MAX_RETRIES=2
  ICODER_DEEPSEEK_TEMPERATURE=0.1
  ICODER_DEEPSEEK_REQUIRE_STRUCTURED_OUTPUT=true
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any

from official_agents.medical_coding.schema import (
    CodingEngineAdapter, MedicalCodingOutputSchema,
    DiagnosisEntry, ProcedureEntry, CodingIssue,
)
from .dictionary_rag import (
    lookup_candidate_codes,
    format_candidates_block,
    _extract_user_text,
)

logger = logging.getLogger(__name__)

# ── System Prompt ──

CODING_SYSTEM_PROMPT = """你是中国医院病案编码审核助手。你必须基于病历证据生成候选编码。

核心要求：
1. 你必须基于病历证据生成编码，不得编造证据
2. 你不能仅根据常识推断编码，必须给出病历证据引用
3. 你输出的是编码审核建议，不是最终编码结论
4. 低置信度（<0.7）、证据不足、主诊断不明确时，必须设置 manual_review_required=true
5. 你必须严格返回 JSON，不输出 Markdown，不输出解释文字

返回 JSON 格式（与 MedicalCodingOutputSchema 对齐）：

{
  "review_conclusion": "PASS" | "WARNING" | "FAIL",
  "primary_diagnosis": {
    "code": "ICD-10 code, e.g. I21.0",
    "description": "Chinese diagnosis name",
    "confidence": 0.0-1.0,
    "category": "principal",
    "evidence": ["exact quote from medical record"]
  },
  "secondary_diagnoses": [
    {
      "code": "ICD-10 code",
      "description": "Chinese diagnosis name",
      "confidence": 0.0-1.0,
      "category": "comorbidity" | "complication" | "secondary",
      "evidence": ["exact quote from medical record"]
    }
  ],
  "procedures": [
    {
      "code": "ICD-9-CM-3 code, e.g. 00.66",
      "description": "Chinese procedure name",
      "confidence": 0.0-1.0,
      "category": "principal" | "secondary" | "diagnostic" | "therapeutic",
      "evidence": ["exact quote from medical record"]
    }
  ],
  "issues_found": [
    {
      "severity": "critical" | "high" | "medium" | "low",
      "code": "rule code",
      "message": "issue description in Chinese",
      "suggestion": "fix suggestion in Chinese"
    }
  ],
  "drg_suggestion": "",
  "dip_suggestion": "",
  "manual_review_required": false,
  "confidence": 0.0-1.0,
  "notes": ""
}

编码规则：
- ICD-10 编码格式：字母 + 2位数字 + 可选小数点 + 1-4位数字，如 I21.0、J44.9
- ICD-9-CM-3 手术编码格式：2位数字 + 小数点 + 1-4位数字，如 00.66、39.95
- primary_diagnosis 只有一个（主要诊断）
- 次要诊断可以有多个
- evidence 必须从病历原文中引用，不得自己编造

编码精度要求（重要）：
- 优先使用最高精度的子类编码（4位或5位），避免使用 .9（未特指）编码
- 如果病历明确描述了疾病的具体类型、部位、病因、分期或并发症，必须选择对应的精准编码
- 示例：心衰有明确"充血性"描述 → I50.0 而非 I50.9
- 示例：房颤明确"阵发性" → I48.0 而非 I48.9
- 示例：哮喘明确"过敏性" → J45.0 而非 J45.9
- 示例：糖尿病明确"周围神经病变" → E11.4 而非 E11.9
- 示例：骨关节炎明确"原发性双侧膝" → M17.0 而非 M17.9
- 示例：骨质疏松症 + 椎体压缩骨折 + 高龄 → M80.0 而非 M48.56
- 只在确实无法从病历中确定具体类型时，才使用 .8（其他特指）或 .9（未特指）
- 对于存在组合编码的情况，优先使用组合编码而非多个独立编码"""


# ── DeepSeekCodingAdapter ──

class DeepSeekCodingAdapter(CodingEngineAdapter):
    """Calls DeepSeek V4 for medical coding inference.

    Uses the existing DeepSeekProvider from icoder_runtime.core.llm_gateway
    for HTTP client, auth, retry, and error handling. Does NOT duplicate API client.
    """

    name = "deepseek_coding_adapter"

    def __init__(
        self,
        gateway=None,
        model: str = "",
        temperature: float = -1,
        max_retries: int = -1,
        timeout: int = -1,
    ):
        """
        Args:
            gateway: LLMGateway with a DeepSeekProvider registered.
            model: Override model name (default: ICODER_DEEPSEEK_MODEL env or 'deepseek-v4').
            temperature: Override temperature (default: ICODER_DEEPSEEK_TEMPERATURE env or 0.1).
            max_retries: Max retries on failure (default: ICODER_DEEPSEEK_MAX_RETRIES env or 2).
            timeout: Timeout seconds (default: ICODER_DEEPSEEK_TIMEOUT_SECONDS env or 60).
        """
        self._gateway = gateway
        self._model = model or os.environ.get("ICODER_DEEPSEEK_MODEL", "deepseek-v4")
        self._temperature = temperature if temperature >= 0 else float(
            os.environ.get("ICODER_DEEPSEEK_TEMPERATURE", "0.1")
        )
        self._max_retries = max_retries if max_retries >= 0 else int(
            os.environ.get("ICODER_DEEPSEEK_MAX_RETRIES", "2")
        )
        self._timeout = timeout if timeout > 0 else int(
            os.environ.get("ICODER_DEEPSEEK_TIMEOUT_SECONDS", "60")
        )
        self._require_structured = os.environ.get(
            "ICODER_DEEPSEEK_REQUIRE_STRUCTURED_OUTPUT", "true"
        ).lower() == "true"

    async def _build_prompt_with_candidates(self, base_prompt: str, encounter_text: str) -> str:
        """Inject ICD-10 candidate codes (RAG) into the system prompt.

        If RAG fails or returns no candidates, the base prompt is returned
        unchanged so the call still works in degraded mode.
        """
        if not encounter_text:
            return base_prompt
        try:
            candidates = await lookup_candidate_codes(encounter_text, max_total=8)
        except Exception as e:
            logger.warning(f"DeepSeekCodingAdapter: RAG lookup failed: {e}")
            return base_prompt
        block = format_candidates_block(candidates)
        if not block:
            return base_prompt
        return f"{base_prompt}\n\n{block}"

    async def infer_async(
        self,
        messages: list[dict[str, str]],
        tools: list[dict] | None = None,
        response_schema: dict | None = None,
        context: dict[str, Any] | None = None,
    ) -> MedicalCodingOutputSchema:
        """Call DeepSeek V4 and parse the response into MedicalCodingOutputSchema."""
        if not self._gateway or not self._gateway.is_configured:
            logger.error("DeepSeekCodingAdapter: gateway not configured")
            return self._error_schema("LLM gateway not configured")

        # RAG: inject candidate ICD-10 codes from dictionary lookup
        encounter_text = _extract_user_text(messages)
        system_prompt = await self._build_prompt_with_candidates(CODING_SYSTEM_PROMPT, encounter_text)
        full_messages = [{"role": "system", "content": system_prompt}] + list(messages)

        last_error = None
        for attempt in range(self._max_retries + 1):
            try:
                result = await self._gateway.generate(
                    full_messages,
                    provider="deepseek",
                )
                return self._parse_response(result)
            except Exception as e:
                last_error = e
                logger.warning(f"DeepSeekCodingAdapter attempt {attempt + 1}/{self._max_retries + 1} failed: {e}")
                if attempt < self._max_retries:
                    await asyncio.sleep(1 * (attempt + 1))  # backoff

        # All retries exhausted — try repair from raw text
        logger.error(f"DeepSeekCodingAdapter: all {self._max_retries + 1} attempts failed: {last_error}")
        return self._error_schema(f"DeepSeek V4 call failed after {self._max_retries + 1} attempts: {last_error}")

    def _parse_response(self, result: dict) -> MedicalCodingOutputSchema:
        """Parse DeepSeek response into MedicalCodingOutputSchema. Includes JSON repair.

        B-003 layer 2: propagate the LLM gateway's ``degraded`` / ``is_mock``
        flags onto the schema. Previously the gateway's mock fallback envelope
        (no_api_key / provider_http_4xx / network_error / 429_503 / circuit_open)
        was parsed into a real-looking schema with ``is_mock=False``, which then
        tripped a false-success cascade through CodingResult → AgentRunResponse →
        frontend "通过" badge. Per Charter §二十六.24 ZERO TOLERANCE for
        false-success UI, the mock envelope MUST be visible end-to-end.
        """
        content = result.get("content", "")
        # Gateway-side mock markers (see LLMGateway._mock_fallback_response).
        gateway_mock = bool(result.get("degraded") or result.get("is_mock"))
        gateway_reason = result.get("degraded_reason", "")

        # Try direct JSON parse
        data = self._extract_json(content)
        if data:
            return MedicalCodingOutputSchema.from_dict(
                data,
                provider="deepseek_coding_adapter",
                is_mock=gateway_mock,
            )

        # Try JSON repair — fix common LLM output issues
        repaired = self._repair_json(content)
        if repaired:
            logger.warning("DeepSeekCodingAdapter: JSON repaired after initial parse failure")
            return MedicalCodingOutputSchema.from_dict(
                repaired,
                provider="deepseek_coding_adapter",
                is_mock=gateway_mock,
            )

        logger.error(f"DeepSeekCodingAdapter: failed to parse response: {content[:200]}")
        return self._error_schema(
            "Failed to parse DeepSeek response as JSON",
            is_mock=gateway_mock,
            degraded_reason=gateway_reason,
        )

    def _extract_json(self, text: str) -> dict | None:
        """Extract JSON object from text (handles markdown code blocks)."""
        # Remove markdown fences
        text = re.sub(r'```(?:json)?\s*', '', text)
        text = re.sub(r'```\s*$', '', text)
        text = text.strip()

        # Find the first { and matching }
        start = text.find('{')
        if start == -1:
            return None

        # Try parsing from start
        try:
            return json.loads(text[start:])
        except json.JSONDecodeError:
            pass

        # Try finding the matching } by bracket counting
        depth = 0
        end = -1
        for i in range(start, len(text)):
            if text[i] == '{':
                depth += 1
            elif text[i] == '}':
                depth -= 1
                if depth == 0:
                    end = i
                    break

        if end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass

        return None

    def _repair_json(self, text: str) -> dict | None:
        """Attempt to repair common LLM JSON output issues."""
        # Remove trailing commas
        text = re.sub(r',\s*}', '}', text)
        text = re.sub(r',\s*]', ']', text)
        # Remove markdown
        text = re.sub(r'```(?:json)?\s*', '', text)
        text = re.sub(r'```\s*$', '', text)
        # Remove leading/trailing non-JSON text
        start = text.find('{')
        if start > 0:
            text = text[start:]
        # Find matching }
        depth = 0
        end = -1
        for i, c in enumerate(text):
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end > 0:
            text = text[:end + 1]

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    def _error_schema(
        self,
        message: str,
        *,
        is_mock: bool = False,
        degraded_reason: str = "",
    ) -> MedicalCodingOutputSchema:
        """Return an error schema when inference fails.

        B-003 layer 2b: ``is_mock`` / ``degraded_reason`` kwargs let callers
        that received a gateway-side mock envelope propagate the marker onto
        the error schema, so downstream consumers (FastCodingRuntime /
        MedCoderRuntime) can short-circuit on ``schema.is_mock``.
        """
        schema = MedicalCodingOutputSchema.mock_result()
        schema.review_conclusion = "FAIL"
        schema.issues_found = [
            CodingIssue(severity="critical", code="DS001",
                        message=f"DeepSeekCodingAdapter 错误: {message}",
                        suggestion="请检查 DeepSeek API 配置或切换到其他 coding mode")
        ]
        schema.manual_review_required = True
        schema.confidence = 0.0
        if is_mock:
            # Preserve the gateway-side mock marker + reason so downstream
            # runtimes can branch on schema.is_mock without re-reading the
            # gateway envelope.
            schema.is_mock = True
            schema.notes = (
                f"[DeepSeek degraded] {degraded_reason or 'unknown'}. "
                f"Mock response, not a real LLM call. "
                f"Underlying error: {message}"
            )
        else:
            # Reset is_mock=False to override mock_result()'s default True,
            # so legitimate DeepSeek failures (HTTP 5xx after retries, parse
            # failure on a real LLM response, etc.) do NOT trigger the
            # B-003 layer 4 short-circuit. Only gateway-side mock envelopes
            # should short-circuit; real-call failures go through the normal
            # error path (FastCodingRuntime returns error_reason="llm_call_failed"
            # or "schema_returned_error").
            schema.is_mock = False
            schema.notes = f"DeepSeek inference failed: {message}"
        return schema

    @property
    def is_configured(self) -> bool:
        """DeepSeek is configured when gateway is available and has a DeepSeekProvider with API key."""
        if not self._gateway:
            return False
        try:
            ds = self._gateway.get("deepseek")
            hc = ds.health_check()
            return hc.get("status") == "configured" and bool(hc.get("model"))
        except Exception:
            return False

    def health_check(self) -> dict:
        ds_status = "no_gateway"
        ds_model = self._model
        ds_api_key_ok = False
        if self._gateway:
            try:
                ds = self._gateway.get("deepseek")
                hc = ds.health_check()
                ds_status = hc.get("status", "unknown")
                ds_model = hc.get("model", ds_model)
                ds_api_key_ok = (ds_status == "configured")
            except Exception:
                pass

        return {
            "engine": self.name,
            "model": ds_model,
            "temperature": self._temperature,
            "max_retries": self._max_retries,
            "timeout_seconds": self._timeout,
            "require_structured_output": self._require_structured,
            "status": "configured" if ds_api_key_ok else ds_status,
            "api_key_configured": ds_api_key_ok,
            "ready_for_real_call": ds_api_key_ok and self._gateway is not None,
        }
