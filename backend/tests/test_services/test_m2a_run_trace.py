"""M2a Task 1 — Real Run Trace tests.

Verifies:
- test_run_trace_created_for_real_run
- test_sample_run_not_written_to_production_trace
- test_tool_run_id_unique_per_call
- test_finalize_persists_risk_and_safety
- test_run_trace_queryable_by_run_id
"""

from __future__ import annotations

import pytest
import tempfile
import shutil
from pathlib import Path

from icoder_runtime.m2a.run_trace import RunTraceService
from icoder_runtime.m2a.store import M2aStore


@pytest.fixture
def m2a_dir():
    """临时 M2a 存储目录。"""
    tmp = tempfile.mkdtemp(prefix="m2a_test_")
    yield Path(tmp)
    shutil.rmtree(tmp, ignore_errors=True)


def test_default_store_uses_configured_registry_dir(tmp_path, monkeypatch):
    registry_dir = tmp_path / "registry"
    monkeypatch.setenv("ICODER_REGISTRY_DIR", str(registry_dir))

    store = M2aStore()

    assert store._dir == registry_dir / "m2a"
    assert store._dir.is_dir()


def test_run_trace_created_for_real_run(m2a_dir):
    """真实 run 应当生成 run_id 和 trace_id。"""
    svc = RunTraceService(store=M2aStore(m2a_dir))
    trace = svc.start_run(agent_ref="agent.front-sheet-coder-001")
    assert trace.run_id != ""
    assert trace.trace_id != ""
    assert trace.run_id != trace.trace_id
    assert trace.is_sample is False
    assert trace.production_allowed is True
    assert trace.data_source == "real"
    # finalize
    final = svc.finalize_run(trace.run_id, final_status="success")
    assert final.run_id == trace.run_id
    assert final.final_status == "success"


def test_sample_run_not_written_to_production_trace(m2a_dir):
    """sample run 应当写入 sample trace，绝不能写入 production trace。"""
    store = M2aStore(m2a_dir)
    svc = RunTraceService(store=store)
    # sample run
    trace = svc.start_run(agent_ref="agent.demo", is_sample=True, data_source="sample")
    svc.finalize_run(trace.run_id, final_status="ok")

    # 试图直接 append_production(sample record) 必须抛错
    sample_record = {
        "run_id": trace.run_id,
        "is_sample": True,
        "data_source": "sample",
        "production_allowed": False,
    }
    with pytest.raises(ValueError, match="REJECTED"):
        store.append_production(sample_record)

    # production trace 应为空
    assert store.production_count == 0
    # sample trace 应有 1 条
    assert store.sample_count == 1


def test_tool_run_id_unique_per_call(m2a_dir):
    """每个工具调用应生成独立的 tool_run_id。"""
    svc = RunTraceService(store=M2aStore(m2a_dir))
    trace = svc.start_run(agent_ref="agent.test")
    tc1 = svc.add_tool_call(trace.run_id, "icd_search", {"q": "I50"})
    tc2 = svc.add_tool_call(trace.run_id, "kg_audit", {"codes": ["I50.900"]})
    tc3 = svc.add_tool_call(trace.run_id, "llm_rerank", {"top_k": 5})
    ids = {tc1.tool_run_id, tc2.tool_run_id, tc3.tool_run_id}
    assert len(ids) == 3
    # complete one
    svc.complete_tool_call(trace.run_id, tc1.tool_run_id, {"results": []}, status="ok")
    # get final
    final = svc.finalize_run(trace.run_id, final_status="success")
    assert len(final.tool_calls) == 3
    assert final.tool_calls[0].tool_run_id == tc1.tool_run_id


def test_finalize_persists_risk_and_safety(m2a_dir):
    """finalize 时应同时记录 risk_route 和 safety_gate。"""
    svc = RunTraceService(store=M2aStore(m2a_dir))
    trace = svc.start_run(agent_ref="agent.test")
    risk = {"risk_level": "low", "risk_reasons": [], "actions": {}}
    safety = {"status": "pass", "blocked_metrics": [], "release_blocked": False}
    final = svc.finalize_run(trace.run_id, "success", risk_route=risk, safety_gate=safety)
    assert final.risk_route == risk
    assert final.safety_gate == safety
    # 重新读盘校验
    store = M2aStore(m2a_dir)
    persisted = store.get(trace.run_id)
    assert persisted is not None
    assert persisted["risk_route"]["risk_level"] == "low"
    assert persisted["safety_gate"]["status"] == "pass"


def test_run_trace_queryable_by_run_id(m2a_dir):
    """get_run 应当根据 run_id 返回完整 trace。"""
    svc = RunTraceService(store=M2aStore(m2a_dir))
    trace = svc.start_run(agent_ref="agent.test")
    tc = svc.add_tool_call(trace.run_id, "icd_search")
    svc.complete_tool_call(trace.run_id, tc.tool_run_id, {"count": 5})
    svc.finalize_run(trace.run_id, "success")

    # list_production 应能看到
    runs = svc.list_production(limit=10)
    assert any(r["run_id"] == trace.run_id for r in runs)

    # get_run by id
    fetched = svc.get_run(trace.run_id)
    assert fetched is not None
    assert fetched["run_id"] == trace.run_id
    assert fetched["trace_id"] == trace.trace_id
    assert len(fetched["tool_calls"]) == 1
    assert fetched["tool_calls"][0]["tool_name"] == "icd_search"
    assert fetched["tool_calls"][0]["status"] == "ok"
