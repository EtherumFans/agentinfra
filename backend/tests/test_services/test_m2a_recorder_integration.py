"""M2a Task 5 — Recorder integration tests.

Verifies that the M2aRecorder properly bridges HybridCodingAdapter
and AgentRunner to the RunTraceService.

Tests:
- test_recorder_inactive_no_op: no recorder → no exceptions, no impact
- test_recorder_active_hybrid_records_stages: recorder set → stages recorded
- test_recorder_active_agent_records_stages: recorder set on AgentRunner → stages recorded
- test_recorder_failure_does_not_block_business_logic: recorder errors → business logic still works
- test_recorder_records_to_production_jsonl: finalize writes to production_runs.jsonl
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest

# 设置测试环境变量
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("LLM_API_KEY", "")


@pytest.fixture
def m2a_dir():
    tmp = tempfile.mkdtemp(prefix="m2a_rec_")
    yield Path(tmp)
    shutil.rmtree(tmp, ignore_errors=True)


def test_recorder_inactive_no_op(m2a_dir):
    """当 recorder=None 时，HybridCodingAdapter 仍正常工作，零 trace 写入。"""
    from icoder_runtime.providers.medical_coding.hybrid_adapter import HybridCodingAdapter

    a = HybridCodingAdapter(mode="prompt_llm")
    assert a._recorder is None

    async def go():
        r = await a.infer_async([{"role": "user", "content": "I50.900"}])
        return r

    r = asyncio.run(go())
    assert r.primary_diagnosis.code
    # No production file should be created
    assert not (m2a_dir / "production_runs.jsonl").exists()


def test_recorder_active_hybrid_records_stages(m2a_dir):
    """recorder 设置后，infer_async 会自动记录 stages 到 production trace。"""
    from icoder_runtime.providers.medical_coding.hybrid_adapter import HybridCodingAdapter
    from icoder_runtime.m2a.store import M2aStore
    from icoder_runtime.m2a.run_trace import RunTraceService
    from icoder_runtime.m2a.recorder import M2aRecorder

    store = M2aStore(m2a_dir)
    rt = RunTraceService(store=store)
    recorder = M2aRecorder(run_trace=rt, default_agent_ref="hybrid_test")

    a = HybridCodingAdapter(mode="prompt_llm", recorder=recorder)

    async def go():
        return await a.infer_async([{"role": "user", "content": "I50.900 心力衰竭"}])

    r = asyncio.run(go())
    assert r.primary_diagnosis.code

    # Verify production_runs.jsonl was written
    prod_path = m2a_dir / "production_runs.jsonl"
    assert prod_path.exists(), "Production trace should be written"

    with open(prod_path, encoding="utf-8") as f:
        record = json.loads(f.readline())

    assert record["is_sample"] is False
    assert record["production_allowed"] is True
    assert record["agent_ref"] == "hybrid_coding_adapter:prompt_llm"
    assert record["final_status"] == "success"
    # Stages recorded
    stage_names = [tc["tool_name"] for tc in record["tool_calls"]]
    assert "inference" in stage_names
    assert "rule_validation" in stage_names
    assert "calibration" in stage_names


def test_recorder_active_agent_records_stages(m2a_dir):
    """Phase 2.1-A (2026-07-02): SKIPPED — AgentRunner stub deleted.

    The legacy ``icoder_runtime.agent_runner.AgentRunner`` execution path
    was removed in Phase 2.1-A. The M2aRecorder integration for the
    HybridCodingAdapter path is still covered by
    ``test_recorder_active_hybrid_records_stages``.
    """
    pytest.skip(
        "AgentRunner stub removed in Phase 2.1-A; M2aRecorder on AgentRunner "
        "is no longer testable. HybridCodingAdapter path is still covered."
    )


def test_recorder_failure_does_not_block_business_logic(m2a_dir):
    """recorder 内部异常不能阻塞业务逻辑（fail-soft）。"""
    from icoder_runtime.providers.medical_coding.hybrid_adapter import HybridCodingAdapter
    from icoder_runtime.m2a.recorder import M2aRecorder

    # Pass a fake run_trace that raises on every call
    class BrokenRunTrace:
        def start_run(self, *a, **kw):
            raise RuntimeError("disk full")
        def add_tool_call(self, *a, **kw):
            raise RuntimeError("disk full")
        def complete_tool_call(self, *a, **kw):
            raise RuntimeError("disk full")
        def finalize_run(self, *a, **kw):
            raise RuntimeError("disk full")

    recorder = M2aRecorder(run_trace=BrokenRunTrace())
    a = HybridCodingAdapter(mode="prompt_llm", recorder=recorder)

    async def go():
        return await a.infer_async([{"role": "user", "content": "I50.900"}])

    # Should not raise even though recorder always fails
    r = asyncio.run(go())
    assert r.primary_diagnosis.code


def test_recorder_sample_payload_rejected(m2a_dir):
    """recorder 不允许 sample 数据进入 production trace。"""
    from icoder_runtime.providers.medical_coding.hybrid_adapter import HybridCodingAdapter
    from icoder_runtime.m2a.store import M2aStore
    from icoder_runtime.m2a.run_trace import RunTraceService
    from icoder_runtime.m2a.recorder import M2aRecorder

    store = M2aStore(m2a_dir)
    rt = RunTraceService(store=store)
    recorder = M2aRecorder(run_trace=rt, default_agent_ref="sample_test")
    a = HybridCodingAdapter(mode="prompt_llm", recorder=recorder)

    async def go():
        # Force is_sample=True via metadata (recorder doesn't take is_sample,
        # but we exercise the no-sample-mixing contract: even if user
        # manually tries to set is_sample in the recorder context, the
        # store would reject.)
        with recorder.inference(agent_ref="sample_demo", is_sample=True, data_source="sample"):
            return await a.infer_async([{"role": "user", "content": "I50.900"}])

    asyncio.run(go())

    # Production file should NOT have a sample run
    prod_path = m2a_dir / "production_runs.jsonl"
    sample_path = m2a_dir / "sample_runs.jsonl"
    if prod_path.exists():
        for line in prod_path.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            assert r["is_sample"] is False
    # Sample file should have the sample run
    assert sample_path.exists()
    with open(sample_path, encoding="utf-8") as f:
        record = json.loads(f.readline())
    assert record["is_sample"] is True
    assert record["production_allowed"] is False
