"""Phase 5 Track D P0 Gate 2 — Real CDI Runner unit tests.

PDF §A1 + §A2 invariants:

- stub_runner must NOT be in production path
- Experts must actually be invoked, not just declared
- Per-stage trace metadata (provider/model/latency/tokens/run_id/trace_id)
  must be captured for audit evidence
- Provider failure must produce a DEGRADED marker (not raise)

These tests inject a mock LLM to keep them hermetic. The production
path uses the singleton ``llm_service`` (DeepSeek V4).
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from app.icoder.agent_runtime.cdi import CDICase, CDIOrchestrator, RealCDIRunner
from app.icoder.agent_runtime.cdi.real_runner import StageTrace


# ---------------------------------------------------------------------------
# Mock LLM
# ---------------------------------------------------------------------------


class _MockLLM:
    """Records calls + returns canned JSON per stage."""

    def __init__(self, *, fail_stages: set[str] | None = None):
        self.calls: list[tuple[str, list[dict], str | None]] = []
        self.fail_stages = fail_stages or set()

    async def chat(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: str | None = None,
    ) -> dict:
        # Detect stage from the user prompt or system_prompt
        user_text = next((m.get("content", "") for m in messages if m.get("role") == "user"), "")
        sys_text = system_prompt or ""
        # Expert calls have specialist-role text in system_prompt.
        expert_markers = (
            ("coding-specialist Expert", "coding-expert"),
            ("PubMed literature Expert", "pubmed-expert"),
            ("clinical web-search Expert", "web-search-expert"),
            ("medical-calculator Expert", "medical-calculator-expert"),
        )
        for marker, eid in expert_markers:
            if marker in sys_text:
                self.calls.append((eid, messages, system_prompt))
                if eid in self.fail_stages:
                    raise RuntimeError(f"mock LLM failure for {eid}")
                return {
                    "content": f"Specialist advice from {eid}.",
                    "usage": {"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70},
                }

        if "Extract the key clinical points" in user_text:
            stage = "encounter_synthesis"
        elif "Identify documentation gaps" in user_text:
            stage = "gap_identification"
        elif "draft a NON-LEADING provider query" in user_text:
            stage = "query_generation"
        else:
            stage = "unknown"

        self.calls.append((stage, messages, system_prompt))
        if stage in self.fail_stages:
            raise RuntimeError(f"mock LLM failure for {stage}")

        if stage == "encounter_synthesis":
            content = json.dumps({
                "key_points": ["肺炎诊断", "痰培养阳性"],
                "encounter_metadata": {"patient_age": "58岁", "patient_sex": "男"},
            })
        elif stage == "gap_identification":
            content = json.dumps({
                "gaps": [
                    {
                        "gap_id": "g1",
                        "description": "肺炎病原体未明确",
                        "why_it_matters": "影响编码特异性",
                        "evidence_span": {
                            "document_id": "入院记录",
                            "quote": "诊断: 肺炎",
                            "char_start": 0, "char_end": 6,
                        },
                        "priority": "routine",
                    }
                ]
            })
        elif stage == "query_generation":
            content = json.dumps({
                "queries": [
                    {
                        "query_id": "q1",
                        "gap_id": "g1",
                        "topic": "肺炎病原体",
                        "reason": "特异性不足",
                        "evidence_span": {"document_id": "入院记录", "quote": "诊断: 肺炎"},
                        "query_text": "请说明痰培养结果及临床判断:",
                        "response_options": [
                            "A. 痰培养为肺炎链球菌",
                            "B. 其他病原体",
                            "C. 痰培养为定植菌",
                            "D. 无法确定",
                        ],
                        "priority": "routine",
                    }
                ]
            })
        else:
            content = "{}"

        return {
            "content": content,
            "usage": {"prompt_tokens": 100, "completion_tokens": 80, "total_tokens": 180},
        }


# ---------------------------------------------------------------------------
# Stage trace capture
# ---------------------------------------------------------------------------


def test_real_runner_captures_stage_traces() -> None:
    """Every LLM-backed stage records provider/model/latency/tokens."""
    mock = _MockLLM()
    runner = RealCDIRunner(llm=mock)
    case = CDICase(case_id="c1", chart_excerpt="患者男性,58岁,诊断肺炎。")

    orch = CDIOrchestrator(runner=runner)
    orch.run(case)

    # encounter_synthesis, gap_identification, query_generation each
    # produce a StageTrace.
    assert "encounter_synthesis" in runner.stage_traces
    assert "gap_identification" in runner.stage_traces
    assert "query_generation" in runner.stage_traces

    for stage_name, trace in runner.stage_traces.items():
        assert isinstance(trace, StageTrace)
        assert trace.stage == stage_name
        assert trace.provider == "deepseek"
        assert trace.model  # non-empty
        assert trace.latency_ms >= 0
        assert trace.total_tokens > 0
        assert trace.run_id.startswith("run-")
        assert trace.trace_id.startswith("trace-")
        assert not trace.degraded


def test_real_runner_captures_expert_traces() -> None:
    """Expert consultation must produce 4 expert_traces (PDF §A2)."""
    mock = _MockLLM()
    runner = RealCDIRunner(llm=mock)
    case = CDICase(case_id="c1", chart_excerpt="患者男性,58岁,诊断肺炎。")

    orch = CDIOrchestrator(runner=runner)
    orch.run(case)

    # 4 experts each consulted
    assert len(runner.expert_traces) == 4
    expert_ids = {t.expert_id for t in runner.expert_traces}
    assert expert_ids == {
        "coding-expert",
        "pubmed-expert",
        "web-search-expert",
        "medical-calculator-expert",
    }
    for trace in runner.expert_traces:
        assert trace.stage == "expert_consultation"
        assert trace.provider == "deepseek"
        assert trace.total_tokens > 0
        assert not trace.degraded


# ---------------------------------------------------------------------------
# Real LLM output flows through to case state
# ---------------------------------------------------------------------------


def test_real_runner_populates_encounter_summary() -> None:
    mock = _MockLLM()
    runner = RealCDIRunner(llm=mock)
    case = CDICase(case_id="c1", chart_excerpt="患者男性,58岁,诊断肺炎。")
    CDIOrchestrator(runner=runner).run(case)

    assert case.encounter_summary is not None
    assert "肺炎诊断" in case.encounter_summary.key_points
    assert case.encounter_summary.encounter_metadata.get("patient_sex") == "男"


def test_real_runner_populates_documentation_gaps() -> None:
    mock = _MockLLM()
    runner = RealCDIRunner(llm=mock)
    case = CDICase(case_id="c1", chart_excerpt="患者男性,58岁,诊断肺炎。")
    CDIOrchestrator(runner=runner).run(case)

    assert len(case.documentation_gaps) == 1
    gap = case.documentation_gaps[0]
    assert gap.description == "肺炎病原体未明确"
    assert gap.evidence_span.quote == "诊断: 肺炎"


def test_real_runner_populates_provider_queries() -> None:
    mock = _MockLLM()
    runner = RealCDIRunner(llm=mock)
    case = CDICase(case_id="c1", chart_excerpt="患者男性,58岁,诊断肺炎。")
    CDIOrchestrator(runner=runner).run(case)

    assert len(case.proposed_provider_queries) == 1
    q = case.proposed_provider_queries[0]
    assert q.topic == "肺炎病原体"
    assert len(q.response_options) == 4
    assert any("无法确定" in opt for opt in q.response_options)  # escape hatch


def test_real_runner_records_run_ids_and_trace_ids_per_stage() -> None:
    mock = _MockLLM()
    runner = RealCDIRunner(llm=mock)
    case = CDICase(case_id="c1", chart_excerpt="患者男性,58岁,诊断肺炎。")
    CDIOrchestrator(runner=runner).run(case)

    # 5 stages with run_id/trace_id (excluding compliance_gate which is
    # pure-logic and doesn't call the runner).
    expected_stages = {
        "encounter_synthesis",
        "gap_identification",
        "expert_consultation",
        "query_generation",
        "specialist_trace_emit",
    }
    for stage in expected_stages:
        assert case.stage_run_ids.get(stage, "").startswith("run-"), (
            f"missing run_id for {stage}"
        )
        assert case.stage_trace_ids.get(stage, "").startswith("trace-"), (
            f"missing trace_id for {stage}"
        )


# ---------------------------------------------------------------------------
# DEGRADED state
# ---------------------------------------------------------------------------


def test_real_runner_marks_degraded_on_llm_failure() -> None:
    """When LLM fails, the stage must NOT raise — it must record degraded=True
    and return empty outputs so the orchestrator can complete gracefully."""
    mock = _MockLLM(fail_stages={"gap_identification"})
    runner = RealCDIRunner(llm=mock)
    case = CDICase(case_id="c1", chart_excerpt="患者男性,58岁,诊断肺炎。")

    # Must not raise
    CDIOrchestrator(runner=runner).run(case)

    # gap_identification stage trace is marked degraded
    gap_trace = runner.stage_traces["gap_identification"]
    assert gap_trace.degraded is True
    assert gap_trace.error_reason  # populated
    # Other stages still completed normally
    assert not runner.stage_traces["encounter_synthesis"].degraded
    # No gaps produced (degraded → empty)
    assert case.documentation_gaps == []


def test_real_runner_marks_degraded_on_expert_failure() -> None:
    """If one Expert fails, others should still succeed and the failed one
    is marked degraded (not raising)."""
    mock = _MockLLM(fail_stages={"pubmed-expert"})
    runner = RealCDIRunner(llm=mock)
    case = CDICase(case_id="c1", chart_excerpt="患者男性,58岁,诊断肺炎。")

    CDIOrchestrator(runner=runner).run(case)

    expert_traces = {t.expert_id: t for t in runner.expert_traces}
    assert expert_traces["pubmed-expert"].degraded is True
    assert not expert_traces["coding-expert"].degraded
    assert not expert_traces["web-search-expert"].degraded
    assert not expert_traces["medical-calculator-expert"].degraded


# ---------------------------------------------------------------------------
# Stub runner is NOT in production path
# ---------------------------------------------------------------------------


def test_real_runner_does_not_use_stub_runner() -> None:
    """PDF §A1: stub_runner must NOT be in production path.

    This test imports the production cdi.py router and asserts that
    RealCDIRunner is the default runner (not stub_runner).
    """
    from app.api.cdi import run_cdi
    import inspect
    src = inspect.getsource(run_cdi)
    assert "RealCDIRunner()" in src
    assert "ICODER_CDI_FORCE_STUB_FOR_TESTS" in src  # explicit gate
    # stub_runner is still imported but only used under the env override
    assert "stub_runner" in src


def test_stub_runner_still_available_for_unit_tests() -> None:
    """stub_runner remains importable for unit-test purposes only."""
    from app.icoder.agent_runtime.cdi import stub_runner
    case = CDICase(case_id="c1", chart_excerpt="any")
    result = stub_runner("encounter_synthesis", case, {})
    assert "key_points" in result
