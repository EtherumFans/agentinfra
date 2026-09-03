import httpx

from icoder_sdk import iCoDerClient, iCoDerConfig


def test_models_resource_reads_secret_free_catalog():
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path))
        return httpx.Response(200, json={
            "active_provider": "mock",
            "active_model": "mock/1.0",
            "operator_default_provider": "mock",
            "operator_default_model": "mock/1.0",
            "effective_deployment_id": "mock",
            "tenant_selection": {"mode": "inherit", "deployment_id": None, "version": 0},
            "registered_deployments": [],
            "selection_editable": True,
            "tenant_region": "cn",
            "egress_policy": "strict",
            "external_llm_allowed": False,
            "models": [],
            "readiness_scope": "configuration_and_policy_only",
            "live_health_verified": False,
            "disclaimer": "configuration only",
        })

    client = iCoDerClient(
        iCoDerConfig(base_url="https://api.cn.icoder.cloud", access_token="token")
    )
    client.http.close()
    client.http = httpx.Client(
        base_url=client.base_url,
        headers={"Authorization": "Bearer token"},
        transport=httpx.MockTransport(handler),
    )
    try:
        result = client.models.get_catalog()
    finally:
        client.close()

    assert calls == [("GET", "/api/v1/model-catalog")]
    assert result["live_health_verified"] is False
    assert result["readiness_scope"] == "configuration_and_policy_only"


def test_models_resource_updates_versioned_tenant_selection():
    captured = {}

    def handler(request):
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["json"] = __import__("json").loads(request.content)
        return httpx.Response(200, json={
            "mode": "pinned", "deployment_id": "qwen-cn-a", "version": 2,
        })

    client = iCoDerClient(
        iCoDerConfig(base_url="https://api.cn.icoder.cloud", access_token="token")
    )
    client.http.close()
    client.http = httpx.Client(
        base_url=client.base_url,
        headers={"Authorization": "Bearer token"},
        transport=httpx.MockTransport(handler),
    )
    try:
        result = client.models.update_selection(
            mode="pinned", deployment_id="qwen-cn-a", expected_version=1,
        )
    finally:
        client.close()

    assert captured == {
        "method": "PUT",
        "path": "/api/v1/model-catalog/selection",
        "json": {
            "mode": "pinned",
            "deployment_id": "qwen-cn-a",
            "expected_version": 1,
        },
    }
    assert result["version"] == 2


def test_models_resource_runs_configuration_health_probe():
    captured = {}

    def handler(request):
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["json"] = __import__("json").loads(request.content)
        return httpx.Response(200, json={
            "deployment_id": "hospital-local",
            "provider_id": "local",
            "model": "hospital-model-v1",
            "status": "healthy",
            "probe_mode": "configuration",
            "egress_decision": "allow",
            "credential_configured": False,
            "circuit_open": False,
            "checked_at": "2026-08-21T00:00:00Z",
        })

    client = iCoDerClient(
        iCoDerConfig(base_url="https://api.cn.icoder.cloud", access_token="token")
    )
    client.http.close()
    client.http = httpx.Client(
        base_url=client.base_url,
        headers={"Authorization": "Bearer token"},
        transport=httpx.MockTransport(handler),
    )
    try:
        result = client.models.health_probe("hospital-local")
    finally:
        client.close()

    assert captured == {
        "method": "POST",
        "path": "/api/v1/model-catalog/health-probe",
        "json": {"deployment_id": "hospital-local"},
    }
    assert result["probe_mode"] == "configuration"


def test_models_resource_sends_fixed_explicit_live_canary_contract():
    captured = {}

    def handler(request):
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["json"] = __import__("json").loads(request.content)
        return httpx.Response(200, json={
            "deployment_id": "deepseek", "provider_id": "deepseek",
            "model": "deepseek-chat", "status": "reachable", "reason_code": "ok",
            "probe_mode": "external_connectivity_canary", "egress_decision": "allow",
            "synthetic_payload": True, "patient_data_sent": False,
            "expected_token_matched": True, "latency_ms": 25,
            "usage": {"input_tokens": 31, "output_tokens": 4},
            "cost": {"amount": 0.000006, "currency": "CNY",
                     "billing_authoritative": False,
                     "source": "provider_usage_pricing_estimate"},
            "request_cost_cap_cny": 0.01, "estimated_max_cost_cny": 0.000146,
            "checked_at": "2026-08-21T00:00:00Z",
        })

    client = iCoDerClient(
        iCoDerConfig(base_url="https://api.cn.icoder.cloud", access_token="token")
    )
    client.http.close()
    client.http = httpx.Client(
        base_url=client.base_url,
        headers={"Authorization": "Bearer token"},
        transport=httpx.MockTransport(handler),
    )
    try:
        result = client.models.live_canary("deepseek", max_cost_cny=0.01)
    finally:
        client.close()

    assert captured == {
        "method": "POST", "path": "/api/v1/model-catalog/live-canary",
        "json": {
            "deployment_id": "deepseek", "acknowledge_external_call": True,
            "purpose": "connectivity_only_no_patient_data", "max_cost_cny": 0.01,
        },
    }
    assert result["patient_data_sent"] is False
    assert result["cost"]["billing_authoritative"] is False


def test_models_resource_activates_metadata_only_clinical_package():
    captured = {}

    def handler(request):
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["json"] = __import__("json").loads(request.content)
        return httpx.Response(200, json={
            "id": "activation-1",
            "use_case": "clinical_coding_decision_support",
            "package_id": "11111111-1111-4111-8111-111111111111",
            "previous_package_id": None,
            "deployment_mode": "hospital_private",
            "record_version": 1,
            "activated_by_user_id": "user-1",
            "created_at": "2026-08-27T00:00:00Z",
            "updated_at": "2026-08-27T00:00:00Z",
            "activation_blockers": [],
            "runtime_loading_enabled": False,
        })

    client = iCoDerClient(
        iCoDerConfig(base_url="https://api.cn.icoder.cloud", access_token="token")
    )
    client.http.close()
    client.http = httpx.Client(
        base_url=client.base_url,
        headers={"Authorization": "Bearer token"},
        transport=httpx.MockTransport(handler),
    )
    try:
        result = client.models.activate_clinical_package(
            "clinical_coding_decision_support",
            package_id="11111111-1111-4111-8111-111111111111",
            deployment_mode="hospital_private",
            expected_version=0,
        )
    finally:
        client.close()

    assert captured == {
        "method": "PUT",
        "path": "/api/v1/clinical-model-packages/activations/clinical_coding_decision_support",
        "json": {
            "package_id": "11111111-1111-4111-8111-111111111111",
            "deployment_mode": "hospital_private",
            "expected_version": 0,
            "acknowledge_clinical_governance": True,
        },
    }
    assert result["runtime_loading_enabled"] is False


def test_models_resource_exposes_signed_synthetic_shadow_contract():
    calls = []

    def handler(request):
        calls.append({
            "method": request.method,
            "path": request.url.path,
            "json": __import__("json").loads(request.content) if request.content else None,
            "idempotency_key": request.headers.get("Idempotency-Key"),
        })
        if len(calls) == 1:
            payload = {"items": [], "count": 0, "metadata_only": True}
        elif len(calls) == 2:
            payload = {
                "id": "att-1", "bundle_stored": False,
                "patient_data_stored": False, "production_inference_enabled": False,
            }
        elif len(calls) <= 4:
            payload = {
                "id": "binding-1", "mode": "shadow_only",
                "patient_data_allowed": False, "runtime_inference_enabled": False,
                "predictions_emitted": False,
            }
        elif len(calls) == 5:
            payload = {"items": [], "count": 0, "aggregate_only": True}
        elif len(calls) == 6:
            payload = {
                "id": "evaluation-1", "result": "stopped",
                "rollback_performed": True, "aggregate_only": True,
                "patient_data_used": False, "predictions_emitted": False,
                "production_inference_enabled": False,
            }
        elif len(calls) == 8:
            payload = {
                "items": [{"id": "job-1", "status": "passed"}], "count": 1,
                "aggregate_only": True, "patient_data_used": False,
            }
        elif len(calls) == 12:
            payload = {
                "status": "healthy", "status_counts": {"queued": 0},
                "due_queued_count": 0, "active_lease_count": 0,
                "expired_lease_count": 0, "exhausted_count": 0,
                "dead_letter_count": 0,
                "oldest_due_age_seconds": 0, "alert_codes": [],
                "evaluated_at": "2026-08-27T00:00:00Z", "aggregate_only": True,
                "patient_data_used": False, "identifiers_emitted": False,
            }
        elif len(calls) == 13:
            payload = {
                "finalized_exhausted_count": 0, "aggregate_only": True,
                "organizations_evaluated": 1, "alerts_fired": 0,
                "alerts_resolved": 0,
                "patient_data_used": False, "identifiers_emitted": False,
            }
        elif len(calls) == 14:
            payload = {
                "items": [{"id": "dead-1", "status": "available",
                           "patient_data_used": False}],
                "count": 1, "aggregate_only": True,
            }
        elif len(calls) == 16:
            payload = {
                "items": [{"alert_code": "dead_letter_backlog",
                           "state": "resolved", "occurrence_count": 1}],
                "count": 1, "aggregate_only": True,
                "patient_data_used": False, "identifiers_emitted": False,
            }
        else:
            payload = {
                "id": "job-1",
                "status": (
                    "passed" if len(calls) == 10
                    else "cancelled" if len(calls) == 11 else "queued"
                ),
                "lease_active": False, "aggregate_only": True,
                "patient_data_used": False, "predictions_emitted": False,
                "production_inference_enabled": False,
            }
        return httpx.Response(200, json=payload)

    client = iCoDerClient(
        iCoDerConfig(base_url="https://api.cn.icoder.cloud", access_token="token")
    )
    client.http.close()
    client.http = httpx.Client(
        base_url=client.base_url,
        headers={"Authorization": "Bearer token"},
        transport=httpx.MockTransport(handler),
    )
    try:
        client.models.list_clinical_artifact_attestations("package-1")
        attestation = client.models.probe_synthetic_clinical_artifact(
            "package-1", bundle_base64="e30=", expected_package_record_version=3,
        )
        binding = client.models.bind_clinical_shadow_attestation(
            "clinical_coding_decision_support",
            attestation_id="att-1", expected_version=0,
        )
        client.models.rollback_clinical_shadow_binding(
            "clinical_coding_decision_support",
            attestation_id="att-1", expected_version=1,
        )
        client.models.list_clinical_shadow_evaluations(
            "clinical_coding_decision_support",
        )
        evaluation = client.models.evaluate_synthetic_clinical_shadow(
            "clinical_coding_decision_support",
            expected_binding_version=2,
            fault_mode="worker_timeout",
            acknowledge_fault_injection=True,
        )
        job = client.models.create_clinical_shadow_evaluation_job(
            "clinical_coding_decision_support",
            expected_binding_version=3,
            idempotency_key="shadow-job-0001",
        )
        client.models.list_clinical_shadow_evaluation_jobs(
            "clinical_coding_decision_support",
        )
        client.models.get_clinical_shadow_evaluation_job("job-1")
        executed = client.models.execute_clinical_shadow_evaluation_job_simulation(
            "job-1",
        )
        cancelled = client.models.cancel_clinical_shadow_evaluation_job(
            "job-1", reason="safety_stop",
        )
        health = client.models.get_clinical_shadow_evaluation_job_health()
        maintenance = (
            client.models.maintain_clinical_shadow_evaluation_jobs_simulation()
        )
        dead_letters = client.models.list_clinical_shadow_dead_letters()
        replay = client.models.replay_clinical_shadow_dead_letter(
            "dead-1", idempotency_key="shadow-replay-0001",
        )
        alert_states = client.models.list_clinical_shadow_alert_states()
    finally:
        client.close()

    assert calls[0]["path"].endswith("/package-1/artifact-attestations")
    assert calls[1]["path"].endswith("/package-1/synthetic-artifact-probe")
    assert calls[1]["json"] == {
        "bundle_base64": "e30=", "expected_package_record_version": 3,
    }
    assert calls[2]["method"] == "PUT"
    assert calls[2]["json"]["acknowledge_shadow_only"] is True
    assert calls[3]["method"] == "POST"
    assert calls[4]["path"].endswith("/evaluations")
    assert calls[5]["path"].endswith("/synthetic-evaluation")
    assert calls[5]["json"]["acknowledge_fault_injection"] is True
    assert calls[6]["path"].endswith("/evaluation-jobs")
    assert calls[6]["idempotency_key"] == "shadow-job-0001"
    assert calls[6]["json"]["acknowledge_synthetic_only"] is True
    assert calls[7]["method"] == "GET"
    assert calls[8]["path"].endswith("/shadow-evaluation-jobs/job-1")
    assert calls[9]["path"].endswith("/shadow-evaluation-jobs/job-1/execute")
    assert calls[10]["path"].endswith("/shadow-evaluation-jobs/job-1/cancel")
    assert calls[10]["json"] == {"reason": "safety_stop"}
    assert calls[11]["path"].endswith("/shadow-evaluation-jobs/health/summary")
    assert calls[12]["path"].endswith("/shadow-evaluation-jobs/maintenance/run")
    assert calls[13]["path"].endswith("/shadow-evaluation-jobs/dead-letters/list")
    assert calls[14]["path"].endswith(
        "/shadow-evaluation-jobs/dead-letters/dead-1/replay"
    )
    assert calls[14]["idempotency_key"] == "shadow-replay-0001"
    assert calls[15]["path"].endswith("/shadow-evaluation-jobs/alerts/states")
    assert attestation["production_inference_enabled"] is False
    assert binding["runtime_inference_enabled"] is False
    assert evaluation["rollback_performed"] is True
    assert job["status"] == "queued"
    assert executed["status"] == "passed"
    assert cancelled["status"] == "cancelled"
    assert health["status"] == "healthy"
    assert maintenance["finalized_exhausted_count"] == 0
    assert dead_letters["count"] == 1
    assert replay["status"] == "queued"
    assert alert_states["items"][0]["state"] == "resolved"
