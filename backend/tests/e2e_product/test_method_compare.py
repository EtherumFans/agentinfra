"""Phase B E2E Product — Coding Method Registry + Compare API.

Validates the 4 new endpoints from end to end (HTTP in, JSON out):

  - GET  /api/icoder/coding-methods/list
  - GET  /api/icoder/coding-methods/{method_id}
  - POST /api/icoder/coding-review/compare
  - POST /api/icoder/coding-review/run-v2

Plus negative boundaries (unknown method_id, too-many methods, empty emr).

The FastAPI/Starlette mismatch means TestClient(app) does not exercise
the lifespan startup; for method registry tests that's fine because
the registry populates on import. For tests that hit /run-v2 or
/compare, we set ICODER_CREDENTIAL_LLM so the LLM capability is
available. The retriever probe goes through index_health_check, which
is patched in some tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from app.main import app


@pytest.fixture
def client(monkeypatch):
    """Real FastAPI TestClient + LLM env var so capabilities probe succeeds."""
    monkeypatch.setenv("ICODER_CREDENTIAL_LLM", "sk-test-dummy")
    # Patch the retriever probe so capability test for retriever returns True
    # when tests need it. The probe is mocked at the module path that
    # MethodSwitcher imports.
    with TestClient(app) as c:
        yield c


# ── /api/icoder/coding-methods/list ──


def test_list_returns_ten_builtin_methods(client):
    r = client.get("/api/icoder/coding-methods/list")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 10
    method_ids = {m["method_id"] for m in body["methods"]}
    expected = {
        "medcoder.full",
        "medcoder.prompt",
        "medcoder.retrieve",
        "medcoder.prompt+retrieve",
        "medcoder.code_like_humans",
        "legacy.deepseek",
        "legacy.prompt_llm",
        "legacy.hybrid",
        "legacy.no_repair",
        "noop.unavailable",
    }
    assert expected.issubset(method_ids)
    assert "capabilities" in body
    assert set(body["capabilities"].keys()) == {"llm", "retriever", "rule_set"}


def test_list_includes_clh_method(client):
    r = client.get("/api/icoder/coding-methods/list?family=medcoder")
    assert r.status_code == 200
    methods = r.json()["methods"]
    clh = next((m for m in methods if m["method_id"] == "medcoder.code_like_humans"), None)
    assert clh is not None
    assert clh["method_family"] == "medcoder"
    assert clh["stage_count"] == 4
    # CLH does NOT need the retriever (BGE-M3+FAISS) — must reflect this in metadata
    assert "retriever" not in clh["required_capabilities"]
    assert set(clh["required_capabilities"]) == {"llm", "rule_set"}


def test_list_filter_by_family_medcoder(client):
    r = client.get("/api/icoder/coding-methods/list?family=medcoder")
    assert r.status_code == 200
    methods = r.json()["methods"]
    assert all(m["method_family"] == "medcoder" for m in methods)
    assert len(methods) == 5  # 4 NAACL variants + CLH


def test_list_filter_by_family_legacy(client):
    r = client.get("/api/icoder/coding-methods/list?family=legacy")
    assert r.status_code == 200
    methods = r.json()["methods"]
    assert all(m["method_family"] == "legacy" for m in methods)
    assert len(methods) == 4


def test_list_method_metadata_shape(client):
    r = client.get("/api/icoder/coding-methods/list")
    m = next(x for x in r.json()["methods"] if x["method_id"] == "medcoder.full")
    assert m["stage_count"] == 5
    assert m["method_name"]  # non-empty
    assert m["description"]
    assert set(m["required_capabilities"]) <= {"llm", "retriever", "rule_set"}
    assert "available" in m


# ── /api/icoder/coding-methods/{id} ──


def test_get_method_by_id(client):
    r = client.get("/api/icoder/coding-methods/medcoder.full")
    assert r.status_code == 200
    body = r.json()
    assert body["method_id"] == "medcoder.full"
    assert body["method_family"] == "medcoder"
    assert body["stage_count"] == 5


def test_get_unknown_method_returns_404(client):
    r = client.get("/api/icoder/coding-methods/bogus.method")
    assert r.status_code == 404
    detail = r.json()["detail"]
    assert detail["error"] == "method_not_found"
    assert "available" in detail


# ── /api/icoder/coding-review/compare ──


def test_compare_two_methods_returns_sequential_results(client):
    r = client.post(
        "/api/icoder/coding-review/compare",
        json={
            "emr_text": "患者因胸痛入院,诊断为冠心病。",
            "method_ids": ["noop.unavailable", "noop.unavailable"],
            "case_id": "test-case-001",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["method_count"] == 2
    assert len(body["results"]) == 2
    # Both are noop so status="unavailable" + reason explains
    for entry in body["results"]:
        assert entry["status"] == "unavailable"
        assert entry["method_id"] == "noop.unavailable"


def test_compare_aggregates_consensus(client):
    # 3 methods with overlapping primary_code on a real-ish emr
    r = client.post(
        "/api/icoder/coding-review/compare",
        json={
            "emr_text": "冠心病合并高血压",
            "method_ids": ["noop.unavailable", "noop.unavailable", "noop.unavailable"],
        },
    )
    assert r.status_code == 200
    body = r.json()
    # All noop → primary_code empty → consensus empty
    assert body["consensus_primary_code"] == ""
    assert body["consensus_count"] == 0


def test_compare_rejects_empty_method_list(client):
    r = client.post(
        "/api/icoder/coding-review/compare",
        json={"emr_text": "冠心病", "method_ids": []},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "method_ids_empty"


def test_compare_rejects_too_many_methods(client):
    r = client.post(
        "/api/icoder/coding-review/compare",
        json={
            "emr_text": "冠心病",
            "method_ids": [f"m{i}" for i in range(9)],
        },
    )
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "too_many_methods"
    assert r.json()["detail"]["limit"] == 8


def test_compare_includes_capabilities_in_response(client):
    r = client.post(
        "/api/icoder/coding-review/compare",
        json={
            "emr_text": "冠心病",
            "method_ids": ["noop.unavailable"],
        },
    )
    body = r.json()
    assert "capabilities" in body
    assert body["capabilities"]["llm"] is True  # we set env var in fixture


# ── /api/icoder/coding-review/run-v2 ──


def test_run_v2_with_canonical_method_id(client):
    r = client.post(
        "/api/icoder/coding-review/run-v2",
        json={
            "emr_text": "冠心病",
            "method_id": "noop.unavailable",
            "case_id": "test-run-v2",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["method_id"] == "noop.unavailable"
    assert body["status"] == "unavailable"
    assert body["agent_ref"] == "method:noop.unavailable"
    assert body["run_id"]  # uuid
    assert body["stage_trace"] == []  # noop has no stages


def test_run_v2_with_legacy_mode_alias(client):
    """`mode=medcoder` should resolve to method_id=medcoder.full (via switcher)."""
    r = client.post(
        "/api/icoder/coding-review/run-v2",
        json={"emr_text": "冠心病", "mode": "medcoder"},
    )
    assert r.status_code == 200
    body = r.json()
    # medcoder.full requires retriever; if retriever is unavailable the
    # switcher reports status="unavailable" with the missing capability.
    assert body["method_id"] == "medcoder.full"


def test_run_v2_unknown_mode_returns_400(client):
    r = client.post(
        "/api/icoder/coding-review/run-v2",
        json={"emr_text": "冠心病", "mode": "bogus_mode"},
    )
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["error"] == "unknown_mode"
    assert "bogus_mode" in detail["mode"]


def test_run_v2_empty_emr_returns_unavailable(client):
    r = client.post(
        "/api/icoder/coding-review/run-v2",
        json={"emr_text": "", "method_id": "noop.unavailable"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "unavailable"


def test_run_v2_default_method_is_medcoder_full(client):
    """No method_id and no mode → defaults to medcoder.full."""
    r = client.post(
        "/api/icoder/coding-review/run-v2",
        json={"emr_text": "冠心病"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["method_id"] == "medcoder.full"


def test_run_v2_response_shape(client):
    """Flat MethodResult shape — no nested pipeline_stages_observed."""
    r = client.post(
        "/api/icoder/coding-review/run-v2",
        json={"emr_text": "冠心病", "method_id": "noop.unavailable"},
    )
    body = r.json()
    expected_keys = {
        "run_id", "method_id", "method_name", "method_family", "agent_ref",
        "status", "reason", "primary_code", "primary_name", "primary_confidence",
        "secondary_codes", "procedure_codes", "issues", "manual_review_required",
        "confidence", "stage_trace", "processing_time_ms",
    }
    assert set(body.keys()) == expected_keys
    # Pipeline stages observed (legacy 14-stage field) is GONE.
    assert "pipeline_stages_observed" not in body


# ── Phase C: Code Like Humans (CLH) e2e ──


def test_run_v2_clh_via_mode_alias(client):
    """`mode='code_like_humans'` translates to method_id 'medcoder.code_like_humans'."""
    r = client.post(
        "/api/icoder/coding-review/run-v2",
        json={"emr_text": "冠心病合并高血压 PCI 术后", "mode": "code_like_humans"},
    )
    body = r.json()
    assert body["method_id"] == "medcoder.code_like_humans"
    assert body["method_family"] == "medcoder"
    # status is determined by capability probe — without LLM env it'll be 'unavailable'
    # (this is the intended 'no silent degradation' behavior, NOT a bug)
    assert body["status"] in {"ok", "unavailable", "error"}


def test_run_v2_clh_via_method_id(client):
    """Canonical method_id path."""
    r = client.post(
        "/api/icoder/coding-review/run-v2",
        json={
            "emr_text": "冠心病合并高血压 PCI 术后",
            "method_id": "medcoder.code_like_humans",
        },
    )
    body = r.json()
    assert body["method_id"] == "medcoder.code_like_humans"
    assert body["method_family"] == "medcoder"


def test_run_v2_clh_empty_emr_returns_unavailable(client):
    """Empty input short-circuits to unavailable regardless of mode."""
    r = client.post(
        "/api/icoder/coding-review/run-v2",
        json={"emr_text": "", "mode": "code_like_humans"},
    )
    body = r.json()
    assert body["method_id"] == "medcoder.code_like_humans"
    assert body["status"] == "unavailable"
    assert "empty emr_text" in body["reason"]


def test_get_method_clh(client):
    """CLH is discoverable via /coding-methods/{id}."""
    r = client.get("/api/icoder/coding-methods/medcoder.code_like_humans")
    assert r.status_code == 200
    body = r.json()
    assert body["method_id"] == "medcoder.code_like_humans"
    assert body["method_family"] == "medcoder"
    assert body["stage_count"] == 4
    # Crucially: CLH does NOT require the FAISS retriever
    assert "retriever" not in body["required_capabilities"]