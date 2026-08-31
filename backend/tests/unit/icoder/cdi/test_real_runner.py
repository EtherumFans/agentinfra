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
from app.services.llm_service import LLMProviderCallError


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
        elif "Repair the compound drafts below" in user_text:
            stage = "query_dimension_rewrite"
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
                            "quote": "肺炎",
                            "char_start": 0, "char_end": 2,
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
                        "evidence_span": {"document_id": "入院记录", "quote": "肺炎"},
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
        elif stage == "query_dimension_rewrite":
            content = json.dumps({"queries": []})
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
    case = CDICase(case_id="c1", chart_excerpt="患者男性,58岁,诊断: 肺炎。")

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


def test_cdi_run_reuses_one_event_loop_across_all_llm_stages() -> None:
    class LoopBoundLLM(_MockLLM):
        def __init__(self):
            super().__init__()
            self.loop_ids: list[int] = []

        async def chat(self, *args, **kwargs):
            self.loop_ids.append(id(asyncio.get_running_loop()))
            return await super().chat(*args, **kwargs)

    llm = LoopBoundLLM()
    runner = RealCDIRunner(llm=llm)
    case = CDICase(case_id="c-loop", chart_excerpt="患者男性,58岁,诊断肺炎。")

    CDIOrchestrator(runner=runner).run(case)

    assert len(llm.loop_ids) >= 3
    assert len(set(llm.loop_ids)) == 1


def test_default_cdi_runner_closes_request_scoped_llm_client(monkeypatch) -> None:
    from app.services import llm_service as llm_service_module

    class OwnedLLM(_MockLLM):
        closed = False
        created_loop_id: int | None = None
        closed_loop_id: int | None = None

        def __init__(self) -> None:
            super().__init__()
            self.created_loop_id = id(asyncio.get_running_loop())

        async def aclose(self) -> None:
            self.closed = True
            self.closed_loop_id = id(asyncio.get_running_loop())

    created: list[OwnedLLM] = []

    def create_owned_llm() -> OwnedLLM:
        llm = OwnedLLM()
        created.append(llm)
        return llm

    monkeypatch.setattr(llm_service_module, "LLMService", create_owned_llm)
    runner = RealCDIRunner()
    case = CDICase(case_id="c-close", chart_excerpt="患者男性,58岁,诊断肺炎。")

    CDIOrchestrator(runner=runner).run(case)

    assert len(created) == 1
    llm = created[0]
    assert llm.closed is True
    assert llm.created_loop_id is not None
    assert llm.closed_loop_id == llm.created_loop_id
    assert runner.llm is None


def test_real_runner_captures_expert_traces() -> None:
    """Expert consultation must produce 4 expert_traces (PDF §A2).

    Phase 5 Track D P0.5 Gate 5 update: the router now decides per-Expert
    whether to invoke. All 4 Experts still appear in the trace (audit
    trail records the route decision) but only the needed ones consume
    tokens. For this fixture (chart=诊断肺炎, gap=病原体未明确) the
    coding-expert is needed; pubmed/web/calculator are SKIPPED_NOT_NEEDED.
    """
    mock = _MockLLM()
    runner = RealCDIRunner(llm=mock)
    case = CDICase(case_id="c1", chart_excerpt="患者男性,58岁,诊断肺炎。")

    orch = CDIOrchestrator(runner=runner)
    orch.run(case)

    # All 4 Experts are ROUTED — trace has one entry per Expert.
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
        assert not trace.degraded

    # Only the needed Expert actually called the LLM → tokens > 0.
    coding_trace = next(t for t in runner.expert_traces if t.expert_id == "coding-expert")
    assert coding_trace.total_tokens > 0

    # The other three are SKIPPED_NOT_NEEDED → no LLM call → tokens = 0.
    for eid in ("pubmed-expert", "web-search-expert", "medical-calculator-expert"):
        skipped = next(t for t in runner.expert_traces if t.expert_id == eid)
        assert skipped.total_tokens == 0
        assert skipped.latency_ms == 0

    # case.specialist_trace is populated with route metadata for audit.
    assert len(case.specialist_trace) == 4
    coding_entry = next(e for e in case.specialist_trace if e.expert_id == "coding-expert")
    assert coding_entry.consulted is True
    assert coding_entry.execution_mode == "LLM_KNOWLEDGE_ONLY"
    assert coding_entry.route_decision == "needed"
    for eid in ("pubmed-expert", "web-search-expert", "medical-calculator-expert"):
        skipped_entry = next(e for e in case.specialist_trace if e.expert_id == eid)
        assert skipped_entry.consulted is False
        assert skipped_entry.execution_mode == "SKIPPED_NOT_NEEDED"
        assert skipped_entry.route_decision == "not_needed"


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
    assert gap.evidence_span.quote == "肺炎"


def test_real_runner_populates_provider_queries() -> None:
    mock = _MockLLM()
    runner = RealCDIRunner(llm=mock)
    case = CDICase(case_id="c1", chart_excerpt="患者男性,58岁,诊断: 肺炎。")
    CDIOrchestrator(runner=runner).run(case)

    assert len(case.proposed_provider_queries) == 1
    q = case.proposed_provider_queries[0]
    assert q.topic == "肺炎病原体"
    assert len(q.response_options) == 4
    assert any("无法确定" in opt for opt in q.response_options)  # escape hatch


def test_query_generation_prompt_requires_one_gap_and_dimension_per_query() -> None:
    mock = _MockLLM()
    runner = RealCDIRunner(llm=mock)
    case = CDICase(case_id="c_prompt", chart_excerpt="诊断: 肺炎")

    CDIOrchestrator(runner=runner).run(case)

    _, messages, system_prompt = next(
        call for call in mock.calls if call[0] == "query_generation"
    )
    user_prompt = next(
        message["content"] for message in messages if message["role"] == "user"
    )
    assert "exactly ONE gap and ONE clinical dimension" in (system_prompt or "")
    assert "Never merge separate gap_ids" in (system_prompt or "")
    assert "GAP COVERAGE (mandatory)" in user_prompt
    assert "exactly one listed gap_id" in user_prompt


def test_query_dimension_rewrite_prompt_is_bounded_to_source_gap() -> None:
    mock = _MockLLM()
    runner = RealCDIRunner(llm=mock)
    case = CDICase(
        case_id="c-rewrite-prompt",
        chart_excerpt="入院诊断：急性胰腺炎。既往：胆石症。",
    )

    result = runner("query_dimension_rewrite", case, {
        "rewrite_items": [{
            "source_query_id": "q-compound",
            "gap_id": "g-etiology",
            "gap_description": "急性胰腺炎病因未明确",
            "compound_query_text": "请说明病因和严重程度。",
            "target_axis": "etiology",
        }],
    })

    assert result["queries"] == []
    _, messages, system_prompt = next(
        call for call in mock.calls if call[0] == "query_dimension_rewrite"
    )
    user_prompt = next(
        message["content"] for message in messages if message["role"] == "user"
    )
    assert "at most one replacement per source_query_id" in user_prompt
    assert '"gap_id": "g-etiology"' in user_prompt
    assert '"target_axis": "etiology"' in user_prompt
    assert "keep the exact source_query_id and gap_id" in (system_prompt or "")
    assert "detected axis set is not exactly {target_axis}" in (system_prompt or "")
    assert "Do not add a new diagnosis" in (system_prompt or "")


@pytest.mark.asyncio
async def test_sync_runner_inside_active_loop_uses_worker_without_coroutine_leak(
    recwarn: pytest.WarningsRecorder,
) -> None:
    """The compatibility bridge must not construct an abandoned coroutine."""

    runner = RealCDIRunner(llm=_MockLLM(), invoke_experts=False)
    case = CDICase(case_id="c-active-loop", chart_excerpt="诊断：肺炎。")

    result = runner("encounter_synthesis", case, {})

    assert result["key_points"] == ["肺炎诊断", "痰培养阳性"]
    assert not any("was never awaited" in str(item.message) for item in recwarn)


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


def test_real_runner_captures_content_free_provider_failure_diagnostics() -> None:
    class DiagnosticLLM(_MockLLM):
        async def chat(self, *args, **kwargs):
            raise LLMProviderCallError(
                category="rate_limit",
                status_code=429,
                attempts=3,
                retryable=True,
            )

    runner = RealCDIRunner(llm=DiagnosticLLM())
    case = CDICase(case_id="c1", chart_excerpt="患者男性,58岁,诊断肺炎。")

    CDIOrchestrator(runner=runner).run(case)

    trace = runner.stage_traces["encounter_synthesis"]
    assert trace.degraded is True
    assert trace.error_reason == "llm_call_failed:rate_limit"
    assert trace.provider_error_category == "rate_limit"
    assert trace.provider_http_status == 429
    assert trace.provider_attempt_count == 3
    assert trace.provider_retryable is True


def test_cdi_invalid_structured_response_gets_one_bounded_repair_retry() -> None:
    class RepairLLM:
        def __init__(self) -> None:
            self.calls = 0
            self.system_prompts: list[str] = []

        async def chat(self, *args, **kwargs):
            self.calls += 1
            self.system_prompts.append(str(kwargs.get("system_prompt") or ""))
            content = (
                "not-json"
                if self.calls == 1
                else json.dumps({"key_points": ["diagnosis"], "encounter_metadata": {}})
            )
            return {
                "content": content,
                "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
            }

    llm = RepairLLM()
    runner = RealCDIRunner(llm=llm, invoke_experts=False)
    case = CDICase(case_id="c-repair", chart_excerpt="diagnosis")

    CDIOrchestrator(runner=runner).run(case, stages=("encounter_synthesis",))

    trace = runner.stage_traces["encounter_synthesis"]
    assert llm.calls == 2
    assert "prior response did not satisfy the JSON contract" in llm.system_prompts[1]
    assert trace.degraded is False
    assert trace.total_tokens == 10
    assert case.encounter_summary is not None


def test_cdi_invalid_structured_response_fails_closed_after_one_retry() -> None:
    class AlwaysInvalidLLM:
        calls = 0

        async def chat(self, *args, **kwargs):
            self.calls += 1
            return {
                "content": "not-json",
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }

    llm = AlwaysInvalidLLM()
    runner = RealCDIRunner(llm=llm, invoke_experts=False)
    case = CDICase(case_id="c-invalid", chart_excerpt="diagnosis")

    CDIOrchestrator(runner=runner).run(case, stages=("encounter_synthesis",))

    trace = runner.stage_traces["encounter_synthesis"]
    assert llm.calls == 2
    assert trace.degraded is True
    assert trace.provider_error_category == "invalid_response"
    assert trace.provider_attempt_count == 2
    assert trace.provider_retryable is False


def test_real_runner_marks_degraded_on_expert_failure() -> None:
    """If one Expert fails, others should still succeed and the failed one
    is marked degraded (not raising).

    Phase 5 Track D P0.5 Gate 5 update: chart must contain a pubmed-marker
    (诊断标准 / 定义 etc.) so the router routes pubmed-expert to LLM.
    Without the marker, the router SKIPS pubmed and the failure is
    never triggered.
    """
    mock = _MockLLM(fail_stages={"pubmed-expert"})
    runner = RealCDIRunner(llm=mock)
    case = CDICase(
        case_id="c1",
        chart_excerpt="患者男性,58岁,诊断肺炎。需要明确诊断标准。",
    )

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
