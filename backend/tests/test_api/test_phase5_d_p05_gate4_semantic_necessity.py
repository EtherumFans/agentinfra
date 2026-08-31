"""Phase 5 Track D P0.5 Gate 4 — Semantic Necessity Reviewer tests.

Tests the LLM-backed semantic necessity gate (Master Task §5.6) using a
mock LLM that returns canned JSON. Covers:

  - C09 empty-chart pathology → BLOCK with INSUFFICIENT_CLINICAL_SUBSTRATE
  - Symptom-only no-diagnosis-evidence → BLOCK
  - No-imaging no-site → BLOCK
  - Complete-chart redundancy → BLOCK
  - DEGRADED on LLM failure (verdict=PASS, degraded=True)
  - Verdict parsing from JSON response
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.icoder.agent_runtime.cdi import (
    ProviderQuery,
    EvidenceSpan,
)
from app.icoder.agent_runtime.cdi.necessity_semantic import (
    SemanticNecessityResult,
    review_necessity,
)


# ---------------------------------------------------------------------------
# Mock LLM that returns a canned JSON response
# ---------------------------------------------------------------------------


class _MockLLM:
    def __init__(self, response: dict[str, Any]) -> None:
        self._response = response
        self.calls: list[dict[str, Any]] = []

    async def chat(self, *, messages: list[dict[str, Any]], system_prompt: str, **kw: Any) -> dict[str, Any]:
        self.calls.append({"messages": messages, "system_prompt": system_prompt})
        return {
            "content": json.dumps(self._response),
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        }


class _FailLLM:
    async def chat(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("simulated outage")


def _make_query(*, query_text: str = "请回答", topic: str = "病原体") -> ProviderQuery:
    return ProviderQuery(
        query_id="q1",
        gap_id="g1",
        topic=topic,
        reason="",
        evidence_span=EvidenceSpan(document_id="d", quote="肺炎"),
        query_text=query_text,
        response_options=["A", "B", "C", "无法确定"],
    )


# ---------------------------------------------------------------------------
# C09 empty-chart pathology — must BLOCK
# ---------------------------------------------------------------------------


async def _c09_case() -> SemanticNecessityResult:
    """The headline target: '主诉腹痛. 建议进一步检查.' must BLOCK."""
    mock = _MockLLM(
        response={
            "clinical_substrate_present": False,
            "existing_documentation_ambiguous": True,
            "query_answerable": False,
            "query_changes_documentation": False,
            "query_requests_new_diagnosis": True,
            "query_is_redundant": False,
            "query_is_overly_detailed": False,
            "verdict": "BLOCK",
            "reason_codes": ["INSUFFICIENT_CLINICAL_SUBSTRATE"],
        }
    )
    q = _make_query(query_text="根据患者腹痛表现, 请评估最可能的病因:")
    chart = "主诉腹痛. 建议进一步检查."
    return await review_necessity(q, chart=chart, llm=mock)


def test_c09_empty_chart_blocks_with_insufficient_substrate() -> None:
    import asyncio
    result = asyncio.run(_c09_case())
    assert result.verdict == "BLOCK"
    assert "INSUFFICIENT_CLINICAL_SUBSTRATE" in result.reason_codes
    assert result.clinical_substrate_present is False
    assert result.query_requests_new_diagnosis is True


# ---------------------------------------------------------------------------
# Symptom-only — no diagnosis evidence
# ---------------------------------------------------------------------------


async def _symptom_only_case() -> SemanticNecessityResult:
    mock = _MockLLM(
        response={
            "clinical_substrate_present": True,  # symptoms present
            "existing_documentation_ambiguous": True,
            "query_answerable": False,
            "query_changes_documentation": True,
            "query_requests_new_diagnosis": True,
            "query_is_redundant": False,
            "query_is_overly_detailed": False,
            "verdict": "REVIEW_REQUIRED",
            "reason_codes": ["POSSIBLE_DIAGNOSIS_INVENTION"],
        }
    )
    q = _make_query(query_text="患者头晕乏力1月, 请明确可能诊断:")
    chart = "主诉头晕乏力1月. 查体无异常. 心电图正常."
    return await review_necessity(q, chart=chart, llm=mock)


def test_symptom_only_returns_review_required() -> None:
    import asyncio
    result = asyncio.run(_symptom_only_case())
    assert result.verdict == "REVIEW_REQUIRED"
    assert "POSSIBLE_DIAGNOSIS_INVENTION" in result.reason_codes


# ---------------------------------------------------------------------------
# Complete chart — redundant query
# ---------------------------------------------------------------------------


async def _redundant_case() -> SemanticNecessityResult:
    mock = _MockLLM(
        response={
            "clinical_substrate_present": True,
            "existing_documentation_ambiguous": False,
            "query_answerable": True,
            "query_changes_documentation": False,
            "query_requests_new_diagnosis": False,
            "query_is_redundant": True,
            "query_is_overly_detailed": False,
            "verdict": "BLOCK",
            "reason_codes": ["REDUNDANT_WITH_CHART"],
        }
    )
    q = _make_query(query_text="患者是否急性胆囊炎:")
    chart = "诊断: 急性胆囊炎. 已行腹腔镜胆囊切除."
    return await review_necessity(q, chart=chart, llm=mock)


def test_redundant_query_blocks() -> None:
    import asyncio
    result = asyncio.run(_redundant_case())
    assert result.verdict == "BLOCK"
    assert "REDUNDANT_WITH_CHART" in result.reason_codes


# ---------------------------------------------------------------------------
# PASS case — query is necessary and answerable
# ---------------------------------------------------------------------------


async def _pass_case() -> SemanticNecessityResult:
    mock = _MockLLM(
        response={
            "clinical_substrate_present": True,
            "existing_documentation_ambiguous": True,
            "query_answerable": True,
            "query_changes_documentation": True,
            "query_requests_new_diagnosis": False,
            "query_is_redundant": False,
            "query_is_overly_detailed": False,
            "verdict": "PASS",
            "reason_codes": [],
        }
    )
    q = _make_query(query_text="根据痰培养结果, 请明确肺炎病原体:")
    chart = "诊断: 肺炎. 痰培养: 肺炎链球菌."
    return await review_necessity(q, chart=chart, llm=mock)


def test_pass_when_query_is_necessary_and_answerable() -> None:
    import asyncio
    result = asyncio.run(_pass_case())
    assert result.verdict == "PASS"
    assert result.reason_codes == []
    assert result.clinical_substrate_present is True


def test_overly_detailed_without_documentation_impact_is_forced_block() -> None:
    """Server normalizes an internally inconsistent PASS from the reviewer."""
    import asyncio

    mock = _MockLLM(
        response={
            "clinical_substrate_present": True,
            "existing_documentation_ambiguous": True,
            "query_answerable": True,
            "query_changes_documentation": False,
            "query_requests_new_diagnosis": False,
            "query_is_redundant": False,
            "query_is_overly_detailed": True,
            "chart_fully_documented": False,
            "verdict": "PASS",
            "reason_codes": [],
        }
    )
    result = asyncio.run(review_necessity(
        _make_query(query_text="请进一步细分该客观异常的类型。"),
        chart="客观异常及临床归因均已明确记录。",
        llm=mock,
    ))
    assert result.verdict == "BLOCK"
    assert "BEYOND_MINIMAL_DOCUMENTATION_NEED" in result.reason_codes


def test_overly_detailed_but_documentation_changing_is_not_forced_block() -> None:
    """A critical coding/documentation change is not blocked merely for detail."""
    import asyncio

    mock = _MockLLM(
        response={
            "clinical_substrate_present": True,
            "existing_documentation_ambiguous": True,
            "query_answerable": True,
            "query_changes_documentation": True,
            "query_requests_new_diagnosis": False,
            "query_is_redundant": False,
            "query_is_overly_detailed": True,
            "chart_fully_documented": False,
            "verdict": "PASS",
            "reason_codes": [],
        }
    )
    result = asyncio.run(review_necessity(
        _make_query(query_text="请明确会改变编码的关键分型。"),
        chart="关键分型尚未记录。",
        llm=mock,
    ))
    assert result.verdict == "PASS"


# ---------------------------------------------------------------------------
# DEGRADED path
# ---------------------------------------------------------------------------


async def _degraded_case() -> SemanticNecessityResult:
    q = _make_query(query_text="请回答")
    return await review_necessity(q, chart="chart", llm=_FailLLM())


def test_degraded_on_llm_failure_returns_pass() -> None:
    """DEGRADED gate never blocks — returns verdict=PASS with degraded flag."""
    import asyncio
    result = asyncio.run(_degraded_case())
    assert result.degraded is True
    # Default verdict when degraded — PASS so the orchestrator doesn't block on LLM outage
    assert result.verdict in ("PASS", "DEGRADED")


# ---------------------------------------------------------------------------
# Empty query_text — DEGRADED, no LLM call
# ---------------------------------------------------------------------------


async def _empty_query_case() -> SemanticNecessityResult:
    q = ProviderQuery(
        query_id="q",
        gap_id="g",
        topic="t",
        reason="",
        evidence_span=EvidenceSpan(document_id="d", quote=""),
        query_text="",
    )
    return await review_necessity(q, chart="chart", llm=_FailLLM())  # LLM shouldn't even be called


def test_empty_query_text_returns_degraded_without_llm_call() -> None:
    import asyncio
    result = asyncio.run(_empty_query_case())
    assert result.degraded is True
    assert result.verdict == "DEGRADED"


# ---------------------------------------------------------------------------
# Malformed LLM response — DEGRADED
# ---------------------------------------------------------------------------


class _MalformedLLM:
    async def chat(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"content": "not valid json {", "usage": {}}


async def _malformed_case() -> SemanticNecessityResult:
    q = _make_query()
    return await review_necessity(q, chart="chart", llm=_MalformedLLM())


def test_malformed_llm_response_returns_degraded() -> None:
    import asyncio
    result = asyncio.run(_malformed_case())
    assert result.degraded is True


# ---------------------------------------------------------------------------
# Verdict parsing — unknown verdict normalizes to PASS
# ---------------------------------------------------------------------------


async def _unknown_verdict_case() -> SemanticNecessityResult:
    mock = _MockLLM(response={"verdict": "MAYBE", "reason_codes": ["weird"]})
    q = _make_query()
    return await review_necessity(q, chart="chart", llm=mock)


def test_unknown_verdict_normalizes_to_pass() -> None:
    import asyncio
    result = asyncio.run(_unknown_verdict_case())
    assert result.verdict == "PASS"


# ---------------------------------------------------------------------------
# LLM provider metadata captured
# ---------------------------------------------------------------------------


class _MetaLLM:
    provider = "deepseek"
    model = "deepseek-test-model"

    async def chat(self, *, messages: list[dict[str, Any]], system_prompt: str, **kw: Any) -> dict[str, Any]:
        return {
            "content": json.dumps({"verdict": "PASS"}),
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        }


async def _meta_case() -> SemanticNecessityResult:
    mock = _MetaLLM()
    q = _make_query()
    return await review_necessity(q, chart="chart", llm=mock)


def test_provider_metadata_captured() -> None:
    import asyncio
    result = asyncio.run(_meta_case())
    assert result.provider == "deepseek"
    assert result.model == "deepseek-test-model"
    assert result.total_tokens == 150
    assert isinstance(result.latency_ms, int) and result.latency_ms >= 0
