"""HTTP regression: do not seed RunHistory to make the A2A trace pass."""
from fastapi.testclient import TestClient
import pytest

from app.coding_runtime.base import CodingResult
from app.icoder.agent_runtime import a2a_facade
from official_agents.medical_coding.schema import MedicalCodingOutputSchema


@pytest.mark.parametrize("error", [False, True])
def test_medical_a2a_creates_its_own_trace_authority(monkeypatch, error):
    from app.main import app

    async def dispatch(**kwargs):
        result = CodingResult(
            codes=[], run_id=kwargs["run_id"], trace_id=kwargs["trace_id"],
            llm_provider="mock", error=error,
            error_reason="provider_failure" if error else "",
            raw_schema=MedicalCodingOutputSchema(
                review_conclusion="WARNING", manual_review_required=True,
                confidence=0.0, provider="mock", model="mock",
            ).to_dict(),
            trace_events=[{"step": "llm_call", "status": "failed" if error else "ok"}],
        )
        return result, result.run_id, result.trace_id

    monkeypatch.setattr(a2a_facade, "dispatch_medical_coding_fast", dispatch)
    with TestClient(app) as client:
        response = client.post(
            "/api/icoder/agents/medical-coding-agent/v1/message:send",
            headers={"A2A-Protocol-Version": "0.3"},
            json={
                "jsonrpc": "2.0", "id": "audit-regression", "method": "message/send",
                "params": {"message": {
                    "role": "user", "messageId": "audit-request",
                    "parts": [{"kind": "text", "text": "synthetic evidence"}],
                }},
            },
        )
        assert response.status_code == (503 if error else 200), response.text
        payload = response.json()
        if error:
            metadata = payload["error"]["data"]
        else:
            metadata = payload["result"]["metadata"]
        trace = client.get(f"/api/runtime/runs/{metadata['run_id']}/trace?format=raw")
        assert trace.status_code == 200, trace.text
        assert trace.json()["trace_attestation"]
        assert any(event["step"] == "llm_call" for event in trace.json()["events"])
