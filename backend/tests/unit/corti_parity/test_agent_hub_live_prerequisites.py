from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest

from scripts.corti_parity import verify_agent_hub_live_prerequisites as gate


@pytest.fixture
def configured(monkeypatch):
    for name, value in {
        "ICODER_CREDENTIAL_LLM": "test-value-not-output",
        "ICODER_ALLOW_DEGRADED_NO_KEY": "0", "ICODER_DISABLE_AUTH_FOR_TESTS": "0",
        "ICODER_ALLOW_EXTERNAL_LLM": "true", "LLM_PROVIDER": "deepseek",
        "ICODER_REGION": "cn", "ICODER_EGRESS_POLICY": "strict",
        "DATABASE_URL": "postgresql+asyncpg://test@localhost/test",
    }.items():
        monkeypatch.setenv(name, value)


def test_live_configuration_passes(configured):
    assert gate.configuration_errors() == []


@pytest.mark.parametrize("name,value", [
    ("ICODER_CREDENTIAL_LLM", ""), ("ICODER_ALLOW_DEGRADED_NO_KEY", "1"),
    ("ICODER_DISABLE_AUTH_FOR_TESTS", "1"), ("ICODER_ALLOW_EXTERNAL_LLM", "false"),
    ("LLM_PROVIDER", "mock"), ("DATABASE_URL", "sqlite+aiosqlite:///:memory:"),
])
def test_unsafe_configuration_fails_closed(configured, monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    assert gate.configuration_errors()
    assert "test-value-not-output" not in str(gate.configuration_errors())


def test_incomplete_or_failed_registry_is_not_ready():
    good = {"started": True, "registry_sync": {
        "last_status": "success", "agents_failed": 0,
        "total_in_registry": 26, "total_in_db": 26,
    }}
    assert gate.runtime_errors(good) == []
    for key, value in [("last_status", "never_run"), ("last_status", "failed"),
                       ("agents_failed", 1), ("total_in_db", 25), ("total_in_registry", 0)]:
        bad = copy.deepcopy(good)
        bad["registry_sync"][key] = value
        assert gate.runtime_errors(bad)
    assert gate.runtime_errors({})


def test_bad_configuration_does_not_access_database_or_http(configured, monkeypatch, tmp_path):
    monkeypatch.setenv("ICODER_ALLOW_EXTERNAL_LLM", "false")
    monkeypatch.setattr(gate.requests, "get", lambda *a, **k: pytest.fail("network called"))
    assert gate.main(["--output", str(tmp_path / "proof.json")]) == 1
    assert "test-value-not-output" not in (tmp_path / "proof.json").read_text()


def test_canonical_a2a_rejects_errors_and_degraded_results(monkeypatch):
    path = Path(__file__).resolve().parents[2] / "e2e/icoder/test_orchestrator_real_deepseek.py"
    spec = importlib.util.spec_from_file_location("live_a2a_contract", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.ENDPOINT == "/api/icoder/agents/medical-coding-agent/v1/message:send"
    for result in ({"error": {"code": -32601}}, {}, {"result": {"kind": "task"}}):
        with pytest.raises(AssertionError):
            module.validate_result(result, {})
    pack = {"output_contract": {"schema_ref": "test/v1", "required_fields": ["value"]}}
    good = {"jsonrpc": "2.0", "result": {
        "kind": "message", "role": "agent", "messageId": "m", "contextId": "c",
        "metadata": {"agent_id": module.AGENT_ID, "run_id": "r",
                     "manual_review_required": True, "production_writeback_blocked": True},
        "parts": [{"kind": "data", "data": {"value": "x", "human_review": {"review_required": True}},
                   "metadata": {"schema_ref": "test/v1", "result_attestation": "test-proof"}}],
    }}
    monkeypatch.setattr(module, "result_attestation_evidence", lambda *a, **k: {
        "claims_bound": True, "signature_verified": True,
    })
    assert module.validate_result(good, pack)[0]["result"]["value"] == "x"
    nested_only = copy.deepcopy(good)
    del nested_only["result"]["metadata"]["manual_review_required"]
    module.validate_result(nested_only, pack)
    nested_only["result"]["parts"][0]["data"]["human_review"]["review_required"] = False
    with pytest.raises(AssertionError):
        module.validate_result(nested_only, pack)
    for field, value in [("degraded", True), ("error", True),
                         ("manual_review_required", False), ("production_writeback_blocked", False),
                         ("agent_id", "medcoder-coding-review")]:
        bad = copy.deepcopy(good)
        bad["result"]["metadata"][field] = value
        with pytest.raises(AssertionError):
            module.validate_result(bad, pack)
    monkeypatch.setattr(module, "result_attestation_evidence", lambda *a, **k: {
        "claims_bound": True, "signature_verified": False,
    })
    with pytest.raises(AssertionError, match="result proof invalid"):
        module.validate_result(good, pack)
