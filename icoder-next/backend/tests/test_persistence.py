"""Persistence + audit tests — the sqlite RunStore and the history/audit endpoints.

Two layers: RunStore unit round-trips (incl. restart survival on a real file) and the
HTTP surface (list history, audit trail, human-review persistence, report-view audit).
The autouse conftest fixture forces the DeterministicProvider, so runs need no model.
"""
import time

import pytest
from fastapi.testclient import TestClient

from conftest import AUTH
from sample_data import SAMPLE_TEXT

from icoder.api.app import create_app
from icoder.runtime.store import RunStore
from icoder.runtime.types import (
    CodeResult,
    ComplianceGate,
    DrgRoute,
    Evidence,
    RunResult,
    Versions,
    new_id,
)

RUN_URL = "/api/coding-review/run"


def _sample_run(run_id: str | None = None, created_at: float | None = None,
                primary: str = "I50.900", human_review: dict | None = None) -> RunResult:
    """A full, realistic RunResult (drg_route + compliance + Chinese text) for store tests."""
    return RunResult(
        run_id=run_id or new_id("run"),
        agent_id="icoder/homepage-coding-review-agent",
        agent_version="1.0.0",
        coding_system="ICD-10-CN",
        created_at=created_at if created_at is not None else time.time(),
        redaction={"redacted": True, "spans": 3, "text": "主要诊断：慢性心力衰竭。"},
        codes=[CodeResult(
            system="ICD-10-CN", code=primary, display="慢性心力衰竭",
            code_type="diagnosis", status="code", confidence=0.95,
            is_primary=True, high_risk=False,
            evidences=[Evidence(start=0, end=6, text="慢性心力衰竭")],
        )],
        candidates=[],
        compliance=ComplianceGate(
            rule_set="medical_coding", passed=True, human_review_required=False, hits=[],
        ),
        drg_route=DrgRoute(
            adrg="FT2", drg="FT25", group_name="心力衰竭",
            mdc="MDCF", mdc_name="循环系统", surgical=False, cc_mcc=None,
            dip_code="DIP-I50.900", dip_name="心力衰竭", dip_score=285.0,
            rationale=["MDCF → FT2 → FT25"], note="",
        ),
        stages=[],
        usage={"tool_calls": 0, "llm_calls": 0, "provider": "test", "stages_observed": 0},
        versions=Versions(
            runtime_version="rt-test", agent_version="1.0.0",
            ruleset_version="medical_coding@0.1.0", catalog_version="cat-test",
            model_version="deterministic",
        ),
        human_review=human_review,
    )


@pytest.fixture
def store(tmp_path):
    s = RunStore(str(tmp_path / "s.db"))
    yield s
    s.close()


# ---- RunStore unit ----

def test_round_trip_full(store):
    run = _sample_run()
    store.save_run(run)
    got = store.get_run(run.run_id)
    assert got is not None
    assert got.codes[0].code == "I50.900"
    assert got.codes[0].evidences[0].text == "慢性心力衰竭"      # Chinese survives JSON
    assert got.drg_route.drg == "FT25"
    assert got.drg_route.dip_code == "DIP-I50.900"
    assert got.compliance.passed is True
    assert got.versions.model_version == "deterministic"
    assert got == run                                          # whole graph round-trips


def test_round_trip_human_review(store):
    run = _sample_run(human_review={"reviewer_role": "coder", "decision": "accept",
                                    "code": "I50.900"})
    store.save_run(run)
    assert store.get_run(run.run_id).human_review["decision"] == "accept"
    [summary] = store.list_runs()
    assert summary["reviewed"] == 1


def test_round_trip_no_drg_route(store):
    run = _sample_run()
    run.drg_route = None
    store.save_run(run)
    assert store.get_run(run.run_id).drg_route is None
    [summary] = store.list_runs()
    assert summary["drg"] is None and summary["dip_code"] is None


def test_get_missing_returns_none(store):
    assert store.get_run("run_does_not_exist") is None


def test_get_audit_missing_returns_empty(store):
    assert store.get_audit("nope") == []


def test_list_runs_newest_first(store):
    t = time.time()
    store.save_run(_sample_run(run_id="run_a", created_at=t))
    store.save_run(_sample_run(run_id="run_b", created_at=t + 1))
    store.save_run(_sample_run(run_id="run_c", created_at=t + 2))
    assert [r["run_id"] for r in store.list_runs()] == ["run_c", "run_b", "run_a"]


def test_list_runs_pagination(store):
    base = time.time()
    for i in range(5):
        store.save_run(_sample_run(run_id=f"run_{i}", created_at=base + i))
    assert [r["run_id"] for r in store.list_runs(limit=2, offset=0)] == ["run_4", "run_3"]
    assert [r["run_id"] for r in store.list_runs(limit=2, offset=2)] == ["run_2", "run_1"]
    assert len(store.list_runs(limit=2, offset=4)) == 1


def test_list_runs_filter_by_agent(store):
    base = time.time()
    a = _sample_run(run_id="run_a", created_at=base)
    a.agent_id = "icoder/homepage-coding-review-agent"
    b = _sample_run(run_id="run_b", created_at=base + 1)
    b.agent_id = "icoder/drg-grouping-review-agent"
    store.save_run(a)
    store.save_run(b)
    assert [r["run_id"] for r in store.list_runs()] == ["run_b", "run_a"]
    only_a = store.list_runs(agent_id="icoder/homepage-coding-review-agent")
    assert [r["run_id"] for r in only_a] == ["run_a"]
    assert store.list_runs(agent_id="icoder/nope") == []


def test_list_summary_has_no_blob(store):
    store.save_run(_sample_run())
    [summary] = store.list_runs()
    assert "blob" not in summary
    for col in ("run_id", "agent_id", "created_at", "passed", "human_review_required",
                "primary_code", "drg", "dip_code", "reviewed"):
        assert col in summary
    assert summary["primary_code"] == "I50.900"


def test_audit_round_trip(store):
    actor = {"role": "coder", "token": "demo:coder"}
    store.append_audit("run_x", actor, "run.created", {"n_codes": 2})
    store.append_audit("run_x", actor, "human_review", {"decision": "accept"})
    events = store.get_audit("run_x")
    assert [e["action"] for e in events] == ["run.created", "human_review"]   # id ASC
    assert events[0]["actor_role"] == "coder"
    assert events[0]["detail"] == {"n_codes": 2}                              # parsed to dict


def test_store_restart_survival(tmp_path):
    path = str(tmp_path / "rs.db")
    s1 = RunStore(path)
    s1.save_run(_sample_run(run_id="run_persist"))
    s1.append_audit("run_persist", {"role": "coder", "token": "demo:coder"}, "run.created", {})
    s1.close()                                          # "restart"
    s2 = RunStore(path)
    try:
        got = s2.get_run("run_persist")
        assert got is not None and got.codes[0].code == "I50.900"
        assert len(s2.get_audit("run_persist")) == 1
    finally:
        s2.close()


# ---- HTTP surface ----

def _run(client) -> str:
    return client.post(RUN_URL, json={"text": SAMPLE_TEXT}, headers=AUTH).json()["run_id"]


def test_run_persists_and_lists(client):
    run_id = _run(client)
    body = client.get("/api/coding-review/runs", headers=AUTH).json()
    assert body["limit"] == 50 and body["offset"] == 0
    summary = next(r for r in body["runs"] if r["run_id"] == run_id)
    assert summary["primary_code"] == "I50.900"
    assert summary["drg"] == "FT23"                    # homepage agent: CC tier
    assert summary["dip_code"] == "DIP-I50.900"


def test_list_empty(client):
    assert client.get("/api/coding-review/runs", headers=AUTH).json() == {
        "runs": [], "limit": 50, "offset": 0, "agent_id": None,
    }


def test_list_pagination_params(client):
    for _ in range(3):
        _run(client)
    assert len(client.get("/api/coding-review/runs?limit=2", headers=AUTH).json()["runs"]) == 2
    assert len(client.get("/api/coding-review/runs?limit=100", headers=AUTH).json()["runs"]) == 3


def test_list_filter_by_agent_param(client):
    run_id = _run(client)  # homepage agent
    body = client.get(
        "/api/coding-review/runs?agent_id=icoder/homepage-coding-review-agent",
        headers=AUTH,
    ).json()
    assert body["agent_id"] == "icoder/homepage-coding-review-agent"
    assert any(r["run_id"] == run_id for r in body["runs"])
    other = client.get("/api/coding-review/runs?agent_id=icoder/nonexistent", headers=AUTH).json()
    assert other["runs"] == []


def test_audit_endpoint_has_run_created(client):
    run_id = _run(client)
    events = client.get(f"/api/coding-review/{run_id}/audit", headers=AUTH).json()["events"]
    created = [e for e in events if e["action"] == "run.created"]
    assert len(created) == 1
    assert created[0]["actor_role"] == "coder"          # actor from token, not body
    assert created[0]["detail"]["agent_id"] == "icoder/homepage-coding-review-agent"


def test_human_review_persists_and_audits(client):
    run_id = _run(client)
    client.post(f"/api/coding-review/{run_id}/human-review",
                json={"decision": "accept", "code": "I50.900"}, headers=AUTH)
    run = client.get(f"/api/coding-review/{run_id}", headers=AUTH).json()
    assert run["human_review"]["decision"] == "accept"
    assert run["human_review"]["reviewer_role"] == "coder"
    actions = [e["action"] for e in
               client.get(f"/api/coding-review/{run_id}/audit", headers=AUTH).json()["events"]]
    assert "run.created" in actions and "human_review" in actions


def test_report_view_audited(client):
    run_id = _run(client)
    client.get(f"/api/coding-review/{run_id}/report", headers=AUTH)
    client.get(f"/api/coding-review/{run_id}/report?format=html", headers=AUTH)
    events = client.get(f"/api/coding-review/{run_id}/audit", headers=AUTH).json()["events"]
    viewed = [e for e in events if e["action"] == "report.viewed"]
    assert len(viewed) == 2
    assert {e["detail"]["format"] for e in viewed} == {"json", "html"}


def test_audit_unknown_run_404(client):
    assert client.get("/api/coding-review/run_missing/audit", headers=AUTH).status_code == 404


def test_app_restart_survival(tmp_path):
    db = str(tmp_path / "app.db")
    with TestClient(create_app(db_path=db)) as c1:
        run_id = _run(c1)
        c1.post(f"/api/coding-review/{run_id}/human-review",
                json={"decision": "accept", "code": "I50.900"}, headers=AUTH)
    # a fresh app on the same db file == server restart
    with TestClient(create_app(db_path=db)) as c2:
        r = c2.get(f"/api/coding-review/{run_id}", headers=AUTH)
        assert r.status_code == 200
        body = r.json()
        assert body["codes"][0]["code"] == "I50.900"
        assert body["human_review"]["decision"] == "accept"
        events = c2.get(f"/api/coding-review/{run_id}/audit", headers=AUTH).json()["events"]
        assert {e["action"] for e in events} >= {"run.created", "human_review"}
