"""Every medical coding entry uses the server binding, including Deep A2A."""
import pytest
from fastapi.testclient import TestClient

from app.coding_runtime.base import CodingResult
from app.coding_runtime.engines import EngineManifest
from official_agents.medical_coding.schema import MedicalCodingOutputSchema


@pytest.fixture
def engine_client(monkeypatch):
    from app.main import app
    from app.coding_runtime import dispatcher as module

    class Engine:
        manifest = EngineManifest("test.hospital", "1.0")
        requests = []

        async def predict(self, request):
            self.requests.append(request)
            return CodingResult(codes=[], run_id=request.run_id, llm_provider="test",
                raw_schema=MedicalCodingOutputSchema(review_conclusion="WARNING",
                    manual_review_required=True, confidence=0, provider="test", model="test").to_dict())

    engine = Engine()
    monkeypatch.setattr(app.state, "coding_engine_factory", lambda app: (engine,), raising=False)
    monkeypatch.setenv("ICODER_CODING_ENGINE_BINDINGS", '{"legacy_default":false,"tenants":{"org_default1":{"engine_id":"test.hospital","engine_version":"1.0","revision":"r1"}}}')
    monkeypatch.delenv("ICODER_CREDENTIAL_LLM", raising=False)
    monkeypatch.delenv("ICODER_ALLOW_DEGRADED_NO_KEY", raising=False)
    with TestClient(app) as client:
        # Auth bypass supplies an org object, not a persisted organization.
        # Keep real FK/audit enforcement enabled; create that prerequisite row.
        async def ensure_organization():
            from app import database
            from app.models.organization import Organization
            async with database.AsyncSessionLocal() as db:
                if await db.get(Organization, "org_default1") is None:
                    db.add(Organization(id="org_default1", name="Engine integration test", slug="engine-test-org"))
                    await db.commit()
        client.portal.call(ensure_organization)
        yield client, engine, module.get_dispatcher()


def test_predict_and_capability_use_authenticated_tenant(engine_client):
    client, engine, bound = engine_client
    response = client.get("/api/v1/coding/engine-capabilities")
    assert response.status_code == 200, response.text
    assert response.json()["manifest"]["engine_id"] == "test.hospital"
    assert client.get("/api/v1/coding/pricing?input_chars=100").status_code == 409
    for mode in ("corti_like_fast", "medcoder_deep"):
        response = client.post("/api/v1/coding/predict", json={"text": "synthetic record", "mode": mode})
        assert response.status_code == 200, response.text
        data = response.json()
        assert not data["error"] and data["manual_review_required"] and data["production_writeback_blocked"]
        assert data["engine"]["engine_id"] == "test.hospital"
        assert engine.requests[-1].tenant_id == "org_default1"
    assert bound._fast is None and bound._deep is None
    response = client.post("/api/v1/coding/predict", json={"text": "record", "tenant_id": "other", "engine_id": "icoder.legacy"})
    assert response.status_code == 422
    assert len(engine.requests) == 2


def test_agent_run_uses_engine_and_preserves_identity(engine_client):
    client, engine, bound = engine_client
    response = client.post("/api/v1/agents/medical-coding-agent/run",
        json={"input": {"text": "synthetic record"}, "runtime_mode": "medcoder_deep"})
    assert response.status_code == 200, response.text
    assert len(engine.requests) == 1, response.text
    assert not response.json()["error"], response.text
    assert response.json()["result"]["trace_refs"]["engine"]["engine_id"] == "test.hospital"
    assert response.json()["manual_review_required"]
    assert bound._deep is None


def test_deep_a2a_cannot_bypass_binding(engine_client):
    client, engine, bound = engine_client
    response = client.post("/api/icoder/agents/medical-coding-agent/v1/message:send",
        headers={"A2A-Protocol-Version": "0.3"}, json={
            "jsonrpc": "2.0", "id": "engine-test", "method": "message/send",
            "params": {"message": {"role": "user", "messageId": "engine-test",
                "parts": [{"kind": "text", "text": "synthetic record"}],
                "metadata": {"runtime_mode": "medcoder_deep"}}},
        })
    assert response.status_code == 200, response.text
    assert len(engine.requests) == 1
    assert engine.requests[0].mode.value == "medcoder_deep"
    assert engine.requests[0].tenant_id == "org_default1"
    assert bound._deep is None
    assert response.json()["result"]["parts"][0]["data"]["trace_refs"]["engine"]["engine_id"] == "test.hospital"


def test_legacy_v2_calls_replacement_without_legacy_credential(engine_client):
    client, engine, bound = engine_client
    response = client.post("/api/v2/tools/coding/icoder", json={
        "context": [{"type": "text", "text": "synthetic record"}], "system": ["icd10cn-inpatient"]})
    # Existing v2 rejects empty suggestions; the selected engine still owns execution.
    assert response.status_code == 502, response.text
    assert response.json()["detail"]["error"] == "empty_extracted_diagnoses"
    assert len(engine.requests) == 1 and engine.requests[0].tenant_id == "org_default1"
    assert bound._deep is None
