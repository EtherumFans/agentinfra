from __future__ import annotations

import httpx
import pytest

from icoder_sdk import RequestOptions, iCoDerClient, iCoDerConfig


def configured_client(handler) -> iCoDerClient:
    client = iCoDerClient(iCoDerConfig(
        base_url="https://api.cn.icoder.test",
        access_token="fixed-token",
        max_retries=0,
    ))
    client.http.close()
    client.http = httpx.Client(
        base_url=client.base_url,
        transport=httpx.MockTransport(handler),
        headers={"Authorization": "Bearer fixed-token"},
    )
    return client


def test_compliance_resource_maps_real_rule_engine_routes_and_request_options():
    observed: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append(request)
        return httpx.Response(200, json={"ok": True})

    client = configured_client(handler)
    try:
        assert client.compliance.rule_engine_status()["ok"] is True
        assert client.compliance.rule_engine_rules(
            "medical_coding",
            RequestOptions(headers={"X-Trace-Mode": "safe"}),
        )["ok"] is True
        assert client.compliance.validate(
            "medical_coding",
            {"diagnoses": []},
            {"region": "CN"},
        )["ok"] is True
        assert [request.url.path for request in observed] == [
            "/api/compliance/rule-engine/status",
            "/api/compliance/rule-engine/rules",
            "/api/compliance/rule-engine/validate",
        ]
        assert observed[1].url.params["rule_set"] == "medical_coding"
        assert observed[1].headers["X-Trace-Mode"] == "safe"
        with pytest.raises(ValueError, match="conflicts with a resource parameter"):
            client.compliance.rule_engine_rules(
                request_options=RequestOptions(query_params={"rule_set": "attacker"}),
            )
    finally:
        client.close()


def test_runtime_resource_maps_only_current_openapi_routes_and_bounds_controls():
    observed: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append(request)
        return httpx.Response(200, json={"ok": True})

    client = configured_client(handler)
    try:
        calls = [
            lambda: client.runtime.status(),
            lambda: client.runtime.data_policy(),
            lambda: client.runtime.list_agents("official"),
            lambda: client.runtime.install_agent("Agent", "1.0"),
            lambda: client.runtime.run_agent("agent/1", "safe synthetic input"),
            lambda: client.runtime.agent_lifecycle("agent/1", "disable"),
            lambda: client.runtime.list_runs("agent/1", 25),
            lambda: client.runtime.get_run("run/1"),
            lambda: client.runtime.fallback_stats(24),
            lambda: client.runtime.shadow_stats(24),
            lambda: client.runtime.audit_log("run", 25),
            lambda: client.runtime.medical_coding_status(),
            lambda: client.runtime.test_medical_coding("safe synthetic input"),
            lambda: client.runtime.rule_engine_status(),
            lambda: client.runtime.rule_engine_rules(),
            lambda: client.runtime.validate_rules("medical_coding", {}),
            lambda: client.runtime.registry_health(),
            lambda: client.runtime.registry_repair(),
        ]
        for call in calls:
            assert call()["ok"] is True
        assert len(observed) == 18
        assert observed[4].url.raw_path.startswith(b"/api/runtime/agents/agent%2F1/run")
        assert observed[7].url.raw_path.startswith(b"/api/runtime/runs/run%2F1")
        with pytest.raises(ValueError, match="limit must be an integer"):
            client.runtime.list_runs(limit=0)
        with pytest.raises(ValueError, match="limit must be an integer"):
            client.runtime.list_runs(limit=201)
        with pytest.raises(ValueError, match="hours must be an integer"):
            client.runtime.fallback_stats(169)
        with pytest.raises(ValueError, match="limit must be an integer"):
            client.runtime.audit_log(limit=501)
        with pytest.raises(ValueError, match="action must be"):
            client.runtime.agent_lifecycle("agent-1", "publish")  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="conflicts with a resource parameter"):
            client.runtime.list_runs(
                request_options=RequestOptions(query_params={"limit": "999"}),
            )
    finally:
        client.close()


def test_patient_context_resource_is_idempotent_same_origin_and_bounded():
    observed: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append(request)
        if request.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(200, json={"id": "context-1"})

    body = {
        "tenant_id": "tenant-1",
        "source_system": "HIS",
        "patient_id": "patient-token",
        "visit_type": "inpatient",
        "department_id": "dept-1",
        "clinician_id": "clinician-1",
        "purpose_of_use": "treatment",
        "consent_legal_basis": "treatment-necessity",
    }
    client = configured_client(handler)
    try:
        assert client.patient_context.create(
            body,  # type: ignore[arg-type]
            idempotency_key="idem-1",
        )["id"] == "context-1"
        assert client.patient_context.get("context/1")["id"] == "context-1"
        client.patient_context.delete("context/1")
        assert client.patient_context.extend("context/1", 60)["id"] == "context-1"
        assert observed[0].headers["Idempotency-Key"] == "idem-1"
        assert observed[1].url.raw_path == b"/api/v1/patient-context/context%2F1"
        assert observed[3].url.raw_path == b"/api/v1/patient-context/context%2F1/extend"
        with pytest.raises(ValueError, match="extend_seconds"):
            client.patient_context.extend("context-1", 59)
        with pytest.raises(ValueError, match="conflicts with a resource header"):
            client.patient_context.create(
                body,  # type: ignore[arg-type]
                idempotency_key="idem-1",
                request_options=RequestOptions(headers={"Idempotency-Key": "attacker"}),
            )
    finally:
        client.close()
