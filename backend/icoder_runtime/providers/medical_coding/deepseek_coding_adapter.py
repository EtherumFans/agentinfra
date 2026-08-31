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
from functools import lru_cache
import json
import logging
import os
import re
from typing import Any

from official_agents.medical_coding.schema import (
    CodingEngineAdapter, MedicalCodingOutputSchema,
    CodingIssue, DiagnosisEntry, ProcedureEntry,
)
from .dictionary_rag import (
    lookup_candidate_codes,
    format_candidates_block,
    _extract_user_text,
)
from .project_policy import apply_medical_coding_project_policy

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
    "code": "完整 ICD-10-CN code, e.g. I21.100",
    "description": "Chinese diagnosis name",
    "confidence": 0.0-1.0,
    "category": "principal",
    "evidence": ["exact quote from medical record"]
  },
  "secondary_diagnoses": [
    {
      "code": "完整 ICD-10-CN code",
      "description": "Chinese diagnosis name",
      "confidence": 0.0-1.0,
      "category": "comorbidity" | "complication" | "secondary",
      "evidence": ["exact quote from medical record"]
    }
  ],
  "procedures": [
    {
      "code": "完整 ICD-9-CM-3 code, e.g. 36.0601",
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
- 只能输出受控候选目录中的完整编码字符串，必须原样保留大小写、x 占位位和所有尾码，不得缩写或自行补位
- ICD-10-CN 示例：I21.100、S22.000x003；ICD-9-CM-3 示例：36.0601、47.0100
- primary_diagnosis 只有一个（主要诊断）
- 次要诊断可以有多个
- evidence 必须从病历原文中引用，不得自己编造

编码精度要求（重要）：
- 仅在病历明确描述具体类型、部位、病因、分期或并发症时选择对应子码；不得为了“更精确”而推断未记录事实
- 病历只支持未特指诊断时，允许且应当使用目录中的未特指编码
- 具体类型（如充血性心衰、阵发性房颤、过敏性哮喘、糖尿病周围神经病变）只能在原文明确记载且候选目录提供完整子码时编码
- 示例：只有病历明确记载“骨质疏松性/病理性骨折”或明确因果关系时才可使用 M80 组合编码；骨质疏松与骨折并存不得自动推断因果
- 组合编码同样要求病历明确支持其因果关系，不得仅因两个诊断同时出现就合并"""


@lru_cache(maxsize=1)
def _governed_catalog_maps() -> tuple[dict[str, str], dict[str, str]]:
    """Return case-insensitive maps to canonical governed catalog codes."""

    try:
        from data.code_dicts.icd_data import ICD10_CN_CODES, ICD9_CM3_CODES
    except Exception:
        return {}, {}
    diagnosis = {
        str(code).strip().upper(): str(code).strip()
        for code, _name, _group in ICD10_CN_CODES
        if str(code).strip()
    }
    procedures = {
        str(code).strip().upper(): str(code).strip()
        for code, _name, _group in ICD9_CM3_CODES
        if str(code).strip()
    }
    return diagnosis, procedures


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

    async def _build_prompt_with_candidates(
        self,
        base_prompt: str,
        encounter_text: str,
        coding_systems: set[str] | None = None,
    ) -> str:
        """Inject ICD-10 candidate codes (RAG) into the system prompt.

        If RAG fails or returns no candidates, the base prompt is returned
        unchanged so the call still works in degraded mode.
        """
        if not encounter_text:
            return base_prompt
        try:
            candidates = await lookup_candidate_codes(
                encounter_text,
                max_total=12,
                coding_systems=coding_systems,
            )
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
        requested_systems = set((context or {}).get("coding_systems") or [])
        system_prompt = await self._build_prompt_with_candidates(
            CODING_SYSTEM_PROMPT,
            encounter_text,
            requested_systems,
        )
        system_prompt = apply_medical_coding_project_policy(
            system_prompt,
            str((context or {}).get("project_policy") or ""),
        )
        if requested_systems == {"icd10cn"}:
            system_prompt += (
                "\n\n本次仅请求 ICD-10-CN 诊断编码。必须将 procedures 设为空数组，"
                "不得返回 ICD-9-CM-3 手术或操作编码。"
            )
        elif requested_systems == {"icd9cm3"}:
            system_prompt += (
                "\n\n本次仅请求 ICD-9-CM-3 手术与操作编码。必须将 primary_diagnosis "
                "设为空对象、secondary_diagnoses 设为空数组，只在 procedures 返回编码。"
            )
        elif requested_systems == {"icd10cn", "icd9cm3"}:
            system_prompt += (
                "\n\n本次同时请求 ICD-10-CN 诊断和 ICD-9-CM-3 手术操作编码，"
                "分别填入诊断字段与 procedures。"
            )
        full_messages = [{"role": "system", "content": system_prompt}] + list(messages)

        last_error = None
        provider_failures = 0
        structured_retry_used = False
        while True:
            try:
                result = await self._gateway.generate(
                    full_messages,
                    provider="deepseek",
                )
                schema = self._parse_response(result)
                invalid_response = (
                    not bool(getattr(schema, "is_mock", False))
                    and getattr(schema, "degraded_reason", "") == "invalid_response"
                )
                if invalid_response and not structured_retry_used:
                    structured_retry_used = True
                    full_messages = [
                        {
                            "role": "system",
                            "content": (
                                system_prompt
                                + "\n\nThe prior response did not satisfy the JSON contract. "
                                "Return exactly one valid JSON object matching the schema; "
                                "do not add markdown or prose."
                            ),
                        },
                        *list(messages),
                    ]
                    logger.warning(
                        "DeepSeekCodingAdapter: invalid structured output; "
                        "performing one bounded repair retry"
                    )
                    continue
                return self._enforce_governed_catalog(schema)
            except Exception as e:
                last_error = e
                provider_failures += 1
                logger.warning(
                    "DeepSeekCodingAdapter provider attempt %s/%s failed: type=%s",
                    provider_failures,
                    self._max_retries + 1,
                    type(e).__name__,
                )
                if provider_failures <= self._max_retries:
                    await asyncio.sleep(provider_failures)  # bounded backoff
                    continue
                break

        logger.error(
            "DeepSeekCodingAdapter: provider retries exhausted: attempts=%s type=%s",
            provider_failures,
            type(last_error).__name__ if last_error is not None else "unknown",
        )
        return self._error_schema("provider_call_failed")

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
            schema = MedicalCodingOutputSchema.from_dict(
                data,
                provider="deepseek_coding_adapter",
                is_mock=gateway_mock,
            )
            return self._attach_gateway_accounting(schema, result)

        # Try JSON repair — fix common LLM output issues
        repaired = self._repair_json(content)
        if repaired:
            logger.warning("DeepSeekCodingAdapter: JSON repaired after initial parse failure")
            schema = MedicalCodingOutputSchema.from_dict(
                repaired,
                provider="deepseek_coding_adapter",
                is_mock=gateway_mock,
            )
            return self._attach_gateway_accounting(schema, result)

        logger.error(
            "DeepSeekCodingAdapter: failed to parse structured response: length=%s",
            len(content) if isinstance(content, str) else 0,
        )
        schema = self._error_schema(
            "Failed to parse DeepSeek response as JSON",
            is_mock=gateway_mock,
            degraded_reason=gateway_reason,
        )
        if not gateway_mock:
            schema.degraded_reason = "invalid_response"
        return schema

    @staticmethod
    def _enforce_governed_catalog(
        schema: MedicalCodingOutputSchema,
    ) -> MedicalCodingOutputSchema:
        """Canonicalize catalog codes and withhold every directory miss.

        The model is a candidate generator, never the source of truth for a
        billable code.  Exact catalog membership is therefore a publication
        boundary, not a warning-only validation rule.
        """

        diagnosis_catalog, procedure_catalog = _governed_catalog_maps()
        withheld: list[tuple[str, str]] = []

        def canonical(code: str, catalog: dict[str, str], kind: str) -> str:
            raw = str(code or "").strip()
            if not raw:
                return ""
            value = catalog.get(raw.upper())
            if value is None:
                withheld.append((kind, raw))
                return ""
            return value

        primary = schema.primary_diagnosis
        primary_code = canonical(primary.code, diagnosis_catalog, "diagnosis")
        if primary.code and not primary_code:
            schema.primary_diagnosis = DiagnosisEntry(category="principal")
        else:
            primary.code = primary_code

        retained_diagnoses = []
        for diagnosis in schema.secondary_diagnoses:
            diagnosis_code = canonical(
                diagnosis.code, diagnosis_catalog, "diagnosis"
            )
            if not diagnosis_code:
                continue
            diagnosis.code = diagnosis_code
            retained_diagnoses.append(diagnosis)
        schema.secondary_diagnoses = retained_diagnoses

        retained_procedures = []
        for procedure in schema.procedures:
            procedure_code = canonical(
                procedure.code, procedure_catalog, "procedure"
            )
            if not procedure_code:
                continue
            procedure.code = procedure_code
            retained_procedures.append(procedure)
        schema.procedures = retained_procedures

        if withheld:
            for kind, code in withheld:
                schema.issues_found.append(CodingIssue(
                    severity="high",
                    code="CATALOG_CODE_WITHHELD",
                    message=(
                        f"The proposed {kind} code {code} is absent from the "
                        "governed local catalog and was withheld."
                    ),
                    suggestion=(
                        "Select an exact code from the approved ICD-10-CN or "
                        "ICD-9-CM-3 catalog and retain source evidence."
                    ),
                ))
            schema.manual_review_required = True
            if str(schema.review_conclusion).upper() == "PASS":
                schema.review_conclusion = "WARNING"
        return schema

    @staticmethod
    def _attach_gateway_accounting(
        schema: MedicalCodingOutputSchema,
        result: dict,
    ) -> MedicalCodingOutputSchema:
        """Preserve provider-reported usage without mutable adapter state."""

        usage = result.get("usage") if isinstance(result, dict) else None
        if isinstance(usage, dict):
            schema.token_usage = {
                "input_tokens": int(usage.get("input_tokens", 0) or 0),
                "output_tokens": int(usage.get("output_tokens", 0) or 0),
            }
        schema.cost_usd = max(float(result.get("cost_usd", 0.0) or 0.0), 0.0)
        return schema

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
        schema = MedicalCodingOutputSchema.failure_result(
            self.name,
            reason=degraded_reason or "deepseek_inference_failed",
            issue_code="DS001",
        )
        if is_mock:
            # Preserve the gateway-side mock marker + reason so downstream
            # runtimes can branch on schema.is_mock without re-reading the
            # gateway envelope.
            schema.is_mock = True
            schema.degraded_reason = degraded_reason or "mock_provider"
            schema.notes = (
                "[DeepSeek degraded] "
                f"reason={schema.degraded_reason}; no clinical result was produced."
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
            schema.degraded_reason = ""
            schema.notes = "DeepSeek inference failed; no clinical result was produced."
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
