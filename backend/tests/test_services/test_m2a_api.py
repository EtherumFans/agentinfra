"""M2a API integration tests (in-process FastAPI client).

Verifies:
- test_m2a_api_runs_end_to_end
- test_m2a_api_safety_gate_endpoint
- test_m2a_api_human_review_rejects_sample
- test_m2a_api_run_listing_excludes_sample
"""

from __future__ import annotations

import pytest
import tempfile
import shutil
import os
from pathlib import Path

# 设置测试环境变量（在 import app.main 之前）
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("LLM_API_KEY", "")


@pytest.fixture(scope="module", autouse=True)
def _patch_m2a_store_dir(tmp_path_factory):
    """将 M2aStore 指向临时目录，避免污染 .icoder/m2a。"""
    from app.api import m2a as m2a_api
    from icoder_runtime.m2a.store import M2aStore
    from icoder_runtime.m2a.run_trace import RunTraceService
    from icoder_runtime.m2a.human_review import HumanReviewService
    from icoder_runtime.m2a.risk_router import RiskRouter
    from icoder_runtime.m2a.safety_gate import MedicalSafetyGate

    tmp = tmp_path_factory.mktemp("m2a_api_")
    store = M2aStore(tmp)
    m2a_api._store = store
    m2a_api._run_trace = RunTraceService(store=store)
    m2a_api._risk_router = RiskRouter()
    m2a_api._safety_gate = MedicalSafetyGate()
    m2a_api._human_review = HumanReviewService(store=store, run_trace=m2a_api._run_trace)
    yield tmp


@pytest.fixture
def client():
    """FastAPI test client（绕过 auth 依赖以便单测）。"""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.middleware.auth import get_current_user

    async def _override_user():
        from app.models.user import User
        u = User()
        u.id = "test-user"
        u.username = "tester"
        u.full_name = "Tester"
        u.email = "tester@example.com"
        return u

    app.dependency_overrides[get_current_user] = _override_user
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_m2a_api_runs_end_to_end(client):
    """端到端：start → tool → finalize → get。"""
    # 1. start
    r = client.post("/api/m2a/runs", json={
        "agent_ref": "agent.front-sheet-coder-001",
        "data_source": "real",
        "is_sample": False,
    })
    assert r.status_code == 200, r.text
    run_id = r.json()["run_id"]
    trace_id = r.json()["trace_id"]
    assert run_id and trace_id

    # 2. tool call
    r = client.post(f"/api/m2a/runs/{run_id}/tools", json={
        "tool_name": "icd_search",
        "tool_input": {"q": "I50"},
    })
    assert r.status_code == 200
    tool_run_id = r.json()["tool_run_id"]
    assert tool_run_id

    r = client.patch(f"/api/m2a/runs/{run_id}/tools/{tool_run_id}", json={
        "tool_output": {"count": 3},
        "status": "ok",
    })
    assert r.status_code == 200

    # 3. finalize
    r = client.post(f"/api/m2a/runs/{run_id}/finalize", json={
        "final_status": "success",
        "risk_indicators": {"evidence_grounded": True},
        "safety_metrics": {"evidence_grounding_rate": 0.98, "primary_dx_damage_rate": 0.0},
        "primary_dx_change_attempted": False,
        "evidence_grounded": True,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["risk_route"]["risk_level"] == "low"
    assert body["safety_gate"]["status"] == "pass"

    # 4. get
    r = client.get(f"/api/m2a/runs/{run_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["run_id"] == run_id
    assert len(body["tool_calls"]) == 1

    # 5. list
    r = client.get("/api/m2a/runs?limit=10")
    assert r.status_code == 200
    assert body["run_id"] in [e["run_id"] for e in r.json()["runs"]]


def test_m2a_api_safety_gate_endpoint(client):
    """安全门禁端点（不入库）。"""
    r = client.post("/api/m2a/safety-gate/evaluate", json={
        "metrics": {
            "primary_dx_damage_rate": 0.01,
            "evidence_grounding_rate": 0.99,
        },
    })
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "block"
    assert "REL-001" in body["triggered_rules"]
    assert body["release_blocked"] is True


def test_m2a_api_human_review_rejects_sample(client, _patch_m2a_store_dir):
    """sample run 人工复核写回应返回 400。"""
    # 先 start 一个 sample run
    r = client.post("/api/m2a/runs", json={
        "agent_ref": "agent.demo",
        "is_sample": True,
        "data_source": "sample",
    })
    sample_run_id = r.json()["run_id"]
    client.post(f"/api/m2a/runs/{sample_run_id}/finalize", json={
        "final_status": "ok",
        "risk_indicators": {},
        "safety_metrics": {},
    })
    # 尝试人工写回
    r = client.post(f"/api/m2a/runs/{sample_run_id}/human-review", json={
        "reviewer": "tester",
        "decision": "approve",
        "reason_code": "primary_dx_confirmed",
        "rationale": "should fail",
    })
    assert r.status_code == 400
    assert "REJECTED" in r.json()["detail"]


def test_m2a_api_run_listing_excludes_sample(client, _patch_m2a_store_dir):
    """列出 runs 应只包含 production。"""
    # real run
    r = client.post("/api/m2a/runs", json={
        "agent_ref": "agent.real",
        "is_sample": False,
    })
    real_id = r.json()["run_id"]
    client.post(f"/api/m2a/runs/{real_id}/finalize", json={
        "final_status": "success",
        "risk_indicators": {"evidence_grounded": True},
        "safety_metrics": {},
    })
    # sample run
    r = client.post("/api/m2a/runs", json={
        "agent_ref": "agent.sample",
        "is_sample": True,
        "data_source": "sample",
    })
    sample_id = r.json()["run_id"]
    client.post(f"/api/m2a/runs/{sample_id}/finalize", json={
        "final_status": "ok",
        "risk_indicators": {},
        "safety_metrics": {},
    })
    r = client.get("/api/m2a/runs")
    run_ids = [e["run_id"] for e in r.json()["runs"]]
    assert real_id in run_ids
    assert sample_id not in run_ids
    assert r.json()["sample_excluded"] is True
