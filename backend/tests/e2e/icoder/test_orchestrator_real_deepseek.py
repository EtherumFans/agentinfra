"""Authenticated live HTTP proof for the canonical Medical Coding A2A route.

Run explicitly in the isolated live job with --noconftest. No TestClient,
mock lifespan, authentication bypass, legacy route or degraded success.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import uuid

import pytest
import requests

from scripts.corti_parity.agent_hub_live_evidence import (
    capture_trace_artifact, result_attestation_evidence,
)
from scripts.corti_parity.run_agent_hub_examples_e2e import _login

AGENT_ID = "medical-coding-agent"
ENDPOINT = f"/api/icoder/agents/{AGENT_ID}/v1/message:send"
BACKEND = Path(__file__).resolve().parents[3]


def validate_result(body: dict, pack: dict) -> tuple[dict, dict]:
    assert body.get("jsonrpc") == "2.0" and "error" not in body
    message = body.get("result") or {}
    assert message.get("kind") == "message" and message.get("role") == "agent"
    assert message.get("messageId") and message.get("contextId")
    metadata = message.get("metadata") or {}
    assert metadata.get("agent_id") == AGENT_ID and metadata.get("run_id")
    # Dedicated coding exposes review_required in the signed domain result;
    # generic providers additionally repeat it in message metadata.
    assert metadata.get("manual_review_required") in (None, True)
    assert metadata.get("production_writeback_blocked") is True
    assert not metadata.get("degraded") and not metadata.get("error")
    schema = pack["output_contract"]["schema_ref"]
    parts = [part for part in message.get("parts", [])
             if part.get("kind") == "data" and
             (part.get("metadata") or {}).get("schema_ref") == schema]
    assert len(parts) == 1, "canonical schema-labelled DataPart required"
    result = parts[0].get("data") or {}
    assert set(pack["output_contract"]["required_fields"]).issubset(result)
    assert result.get("contract_output_suppressed") is not True
    assert (result.get("human_review") or {}).get("review_required") is True
    normalized = {
        "run_id": metadata["run_id"], "result": result,
        "result_attestation": (parts[0].get("metadata") or {}).get("result_attestation"),
    }
    proof = result_attestation_evidence(
        normalized, agent_id=AGENT_ID, output_schema_ref=schema,
    )
    assert proof["claims_bound"] and proof["signature_verified"], "result proof invalid"
    return normalized, proof


@pytest.mark.skipif(
    os.environ.get("ICODER_RUN_LIVE_AGENT_E2E") != "1",
    reason="real HTTP E2E runs explicitly in the isolated Agent Hub live job",
)
def test_orchestrator_real_deepseek_end_to_end():
    assert os.environ.get("ICODER_CREDENTIAL_LLM", "").strip(), "live credential missing"
    assert os.environ.get("ICODER_DISABLE_AUTH_FOR_TESTS") == "0"
    assert os.environ.get("ICODER_ALLOW_DEGRADED_NO_KEY") == "0"
    assert os.environ.get("ICODER_ALLOW_EXTERNAL_LLM") == "true"
    base = os.environ["ICODER_BACKEND"].rstrip("/")
    output = Path(os.environ["ICODER_LIVE_EVIDENCE_DIR"])
    output.mkdir(parents=True, exist_ok=True)
    pack = json.loads((BACKEND / "official_agents/medical_coding/agent_pack.json").read_text(encoding="utf-8"))
    token = _login(base, allow_self_register=True)
    headers = {"Authorization": f"Bearer {token}", "A2A-Protocol-Version": "0.3"}
    case = json.loads((BACKEND / "tests/fixtures/orchestrator_e2e_case.json").read_text(encoding="utf-8"))
    request_id = uuid.uuid4().hex
    response = requests.post(base + ENDPOINT, headers=headers, timeout=150, json={
        "jsonrpc": "2.0", "id": request_id, "method": "message/send",
        "params": {"message": {"role": "user", "messageId": uuid.uuid4().hex,
                                  "parts": [{"kind": "text", "text": case["text"]}]}},
    })
    # Preserve diagnostics in the isolated artifact, not the assertion/log body.
    body = response.json()
    (output / "response.json").write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
    assert response.status_code == 200, f"canonical A2A HTTP {response.status_code}"
    assert response.headers.get("A2A-Protocol-Version") == "0.3"
    assert body.get("id") == request_id
    trace = capture_trace_artifact(
        base_url=base, headers=headers,
        response={"run_id": ((body.get("result") or {}).get("metadata") or {}).get("run_id", "")},
        trace_path=output / "trace.json", timeout=30,
    )
    normalized, proof = validate_result(body, pack)
    assert trace["http_status"] == 200 and trace["run_id_matches"]
    assert trace["trace_attestation_signature_verified"]
    assert trace["model_call_observed"] and "deepseek" in trace["model_providers"]
    assert not trace["mock_detected"] and not trace["degraded_detected"]
    parts = body["result"]["parts"]
    domain_part = next(p for p in parts if p.get("kind") == "data")
    cost = ((domain_part.get("metadata") or {}).get("runtime") or {}).get("cost") or {}
    usage = cost.get("token_usage") or {}
    assert cost.get("source") == "provider_token_usage"
    assert usage.get("input_tokens", 0) > 0 and usage.get("output_tokens", 0) > 0
    primary = (normalized["result"].get("code_assignment") or {}).get("primary_diagnosis") or {}
    assert str(primary.get("code") or "").startswith(case["expected_principal_diagnosis"][:3])
    (output / "evidence.json").write_text(json.dumps({
        "source_revision": os.environ.get("GITHUB_SHA", ""),
        "agent_id": AGENT_ID, "passed": True, "result_proof": proof, "trace": trace,
        "clinical_quality_proven": False,
    }, indent=2), encoding="utf-8")
