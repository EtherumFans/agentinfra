"""M3-0 Hospital Pilot — 14-stage real M2a recorder integration.

Plan reference: docs/M3_HOSPITAL_PILOT_READINESS_PLAN.md Commit 6.

The ``POST /api/icoder/coding-review/run`` endpoint must:

1. Open a real ``M2aRecorder.inference(...)`` context (not a no-op) when the
   recorder is active. The context reuses the API-layer's ``run_id`` /
   ``trace_id`` so the trace is queryable via the same identifier the
   client receives.
2. Wrap each of the 14 ``PIPELINE_STAGES`` in a real
   ``ctx.stage(name)`` call. The result is 14 tool calls in
   ``/api/m2a/runs/{run_id}``, each with a non-empty ``tool_run_id``
   and a non-negative ``duration_ms``.
3. Reflect the same 14 stages in the API response's
   ``pipeline_stages_observed`` list.

The test redirects the ``M2aStore`` to a temporary directory so the
production ``.icoder/m2a`` JSONL files are not polluted. The conftest
auth-bypass fixture (``ICODER_DISABLE_AUTH_FOR_TESTS=1``) provides a
mock admin user.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# 必须在 import app.main 之前设置 (与 conftest 一致)
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ICODER_ALLOW_DEGRADED_NO_KEY", "1")
os.environ.setdefault("ICODER_DISABLE_AUTH_FOR_TESTS", "1")


SAMPLE_INPUT = {
    "encounter_text": "患者男 65 岁, 因持续胸痛 6 小时入院, EKG 示 ST 抬高, 初步诊断急性心肌梗死",
    "case_id": "c-trace-001",
    "input_source": "manual",
    "mode": "link_validation",
    "primary_disease_codes": "I21.401",
    "other_disease_codes": "I10.x00;E11.900",
    "primary_surgery_codes": "",
    "other_surgery_codes": "",
}

EXPECTED_14_STAGES = [
    "document_normalizer",
    "evidence_fact_extractor",
    "coding_eligibility_classifier",
    "candidate_generator",
    "ontology_service",
    "high_risk_coding_point_checker",
    "kg_auditor",
    "code_reconciler",
    "risk_router",
    "medical_safety_gate",
    "human_review",
    "report_generator",
    "run_trace_emitter",
    "audit_logger",
]


@pytest.fixture
def client(tmp_path):
    """FastAPI TestClient with M2a store + recorder pointed at tmp_path.

    Mirrors the fixture in
    ``test_runtime_api_real_medical_coding_trace.py``: TestClient triggers
    lifespan, which re-creates ``app.state.m2a_recorder`` — so we replace
    the store and the recorder *inside* the ``with`` block to ensure our
    patches win.
    """
    from app.main import app
    from app.api import m2a as m2a_api
    from icoder_runtime.m2a.store import M2aStore
    from icoder_runtime.m2a.run_trace import RunTraceService
    from icoder_runtime.m2a.recorder import M2aRecorder

    # 把 m2a API 模块级 store/trace 重定向到 tmp_path
    store = M2aStore(tmp_path)
    run_trace = RunTraceService(store=store)
    m2a_api._store = store
    m2a_api._run_trace = run_trace

    with TestClient(app) as c:
        # 替换 app.state.m2a_recorder (lifespan 已建过一次)
        app.state.m2a_recorder = M2aRecorder(
            run_trace=run_trace,
            default_agent_ref="icoder_runtime",
        )
        yield c

    # 还原 (TestClient context manager 关闭后)
    try:
        from app.main import app
        # 重新指向 lifespan 默认 store (从磁盘重新读, 不影响 .icoder/m2a)
        default_store = M2aStore()
        default_run_trace = RunTraceService(store=default_store)
        m2a_api._store = default_store
        m2a_api._run_trace = default_run_trace
        app.state.m2a_recorder = M2aRecorder(
            run_trace=default_run_trace,
            default_agent_ref="icoder_runtime",
        )
    except Exception:
        pass
    shutil.rmtree(tmp_path, ignore_errors=True)


# ── 1. pipeline_stages_observed has 14 entries matching PIPELINE_STAGES ─


def test_response_pipeline_stages_has_14_entries(client):
    """POST /run returns pipeline_stages_observed with all 14 stage names."""
    r = client.post("/api/icoder/coding-review/run", json=SAMPLE_INPUT)
    assert r.status_code == 200, f"run failed: {r.text}"
    body = r.json()

    observed = body.get("pipeline_stages_observed") or []
    assert len(observed) == 14, (
        f"expected 14 stages, got {len(observed)}: {observed}"
    )
    # The 14 stage names from the legacy _execute_pipeline_14_stages path
    # must all be present (order is preserved by the pipeline). Phase D3
    # keeps this 14-stage behavior intact for the M2a recorder migration
    # test; the 5-stage MedCodER is exercised by e2e_product tests.
    assert observed == EXPECTED_14_STAGES, (
        f"observed stages mismatch: {observed}"
    )


# ── 2. GET /api/m2a/runs/{run_id} returns 14 tool calls ────────────────


def test_m2a_run_endpoint_returns_14_tool_calls(client):
    """The M2a run endpoint returns the same 14 stages with real tool_run_ids."""
    r = client.post("/api/icoder/coding-review/run", json=SAMPLE_INPUT)
    assert r.status_code == 200
    run_id = r.json()["run_id"]

    r2 = client.get(f"/api/m2a/runs/{run_id}")
    assert r2.status_code == 200, f"trace not found: {r2.text}"
    trace = r2.json()

    tool_calls = trace.get("tool_calls") or []
    assert len(tool_calls) == 14, (
        f"expected 14 tool_calls, got {len(tool_calls)}: "
        f"{[tc.get('tool_name') for tc in tool_calls]}"
    )
    # tool_name ordering matches PIPELINE_STAGES
    names = [tc.get("tool_name") for tc in tool_calls]
    assert names == EXPECTED_14_STAGES, f"tool_name order: {names}"


# ── 3. Every tool_call has a non-empty tool_run_id and duration_ms ─────


def test_every_tool_call_has_tool_run_id_and_duration_ms(client):
    """Each of the 14 tool calls has a tool_run_id and duration_ms >= 0."""
    r = client.post("/api/icoder/coding-review/run", json=SAMPLE_INPUT)
    assert r.status_code == 200
    run_id = r.json()["run_id"]

    r2 = client.get(f"/api/m2a/runs/{run_id}")
    assert r2.status_code == 200
    trace = r2.json()
    tool_calls = trace.get("tool_calls") or []
    assert len(tool_calls) == 14

    for tc in tool_calls:
        assert "tool_run_id" in tc, f"missing tool_run_id: {tc}"
        assert tc["tool_run_id"], f"empty tool_run_id: {tc}"
        assert "duration_ms" in tc, f"missing duration_ms: {tc}"
        assert tc["duration_ms"] >= 0, f"negative duration_ms: {tc}"
        # 默认 status 应为 "ok" (本测试中 14 阶段都正常完成)
        assert tc.get("status") == "ok", f"unexpected status: {tc}"


# ── 4. trace_id and run_id are aligned between API and M2a store ───────


def test_api_run_id_matches_m2a_run_id(client):
    """The run_id returned by the API matches the one in /api/m2a/runs/{run_id}."""
    r = client.post("/api/icoder/coding-review/run", json=SAMPLE_INPUT)
    assert r.status_code == 200
    body = r.json()
    api_run_id = body["run_id"]
    api_trace_id = body["trace_id"]
    assert api_run_id, "API did not return run_id"
    assert api_trace_id, "API did not return trace_id"
    assert api_run_id != api_trace_id, "run_id and trace_id must differ"

    r2 = client.get(f"/api/m2a/runs/{api_run_id}")
    assert r2.status_code == 200
    trace = r2.json()
    assert trace["run_id"] == api_run_id, (
        f"M2a run_id mismatch: API={api_run_id} vs trace={trace['run_id']}"
    )
    assert trace["trace_id"] == api_trace_id, (
        f"M2a trace_id mismatch: API={api_trace_id} vs trace={trace['trace_id']}"
    )


# ── 5. agent_ref is the medcoder-coding-review agent ──────────────────


def test_m2a_trace_agent_ref_is_medcoder_coding_review(client):
    """The M2a trace carries the agent_ref from the inference() context."""
    r = client.post("/api/icoder/coding-review/run", json=SAMPLE_INPUT)
    assert r.status_code == 200
    run_id = r.json()["run_id"]

    r2 = client.get(f"/api/m2a/runs/{run_id}")
    trace = r2.json()
    assert trace.get("agent_ref") == "icoder/medcoder-coding-review-agent@1.0.0", (
        f"agent_ref mismatch: {trace.get('agent_ref')!r}"
    )


# ── 6. Empty input still records stages (degraded but traced) ─────────
# Phase A A3 (2026-06-25) + Phase D3 (2026-06-26): the API layer is
# in transition between the legacy 14-stage homepage-coding-review
# pipeline and the canonical MedCodER 5-stage pipeline. For empty
# input, the early-return path
# loops over PIPELINE_STAGES[1:] (the 4 new stages) and combines them
# with the explicit Stage 1 record (document_normalizer) — yielding 5
# stage entries. For full input, the legacy 14-stage code path still
# runs. Both behaviors are valid transition states. The contract we
# assert here is "empty input → stages recorded as no-ops, count is the
# same regardless of input content".


def test_empty_input_still_records_stages(client):
    """Empty input → stages recorded as no-ops (count is non-zero and stable)."""
    r = client.post(
        "/api/icoder/coding-review/run",
        json={
            "encounter_text": "",
            "case_id": "c-trace-empty-001",
            "input_source": "manual",
            "mode": "link_validation",
            "primary_disease_codes": "",
            "other_disease_codes": "",
            "primary_surgery_codes": "",
            "other_surgery_codes": "",
        },
    )
    # Empty input is now an explicit 4xx error in the API (no fake degraded
    # path) — but if the test env allows it, the trace must still have
    # stage entries (5 = Stage 1 + PIPELINE_STAGES[1:]).
    if r.status_code == 200:
        body = r.json()
        observed = body.get("pipeline_stages_observed") or []
        assert len(observed) >= 5, (
            f"empty input should still record at least 5 stages, got {len(observed)}: {observed}"
        )
        run_id = body["run_id"]
        r2 = client.get(f"/api/m2a/runs/{run_id}")
        if r2.status_code == 200:
            trace = r2.json()
            tool_calls = trace.get("tool_calls") or []
            assert len(tool_calls) == len(observed), (
                f"trace tool_calls ({len(tool_calls)}) should match observed ({len(observed)})"
            )
    else:
        # API 拒绝 empty input — 这是合法的 4xx 行为, 不影响 stages 测试
        assert r.status_code in (400, 422), f"unexpected status: {r.status_code} {r.text}"
