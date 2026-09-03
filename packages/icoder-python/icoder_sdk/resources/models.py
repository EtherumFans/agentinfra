"""Secret-free model configuration and regional egress readiness."""

from __future__ import annotations

import re
from typing import Literal, TypedDict, cast

from ..client import iCoDerClient
from ..request_options import RequestOptions


class ModelCatalogItem(TypedDict):
    id: str
    display_name: str
    default_model: str
    model: str
    deployment_kind: str
    selected: bool
    credential_required: bool
    credential_configured: bool | None
    adapter_capabilities: list[str]
    china_scenario: str
    provider_region: Literal["cn", "eu", "us"]
    tenant_region: Literal["cn", "eu", "us"]
    egress_decision: Literal["allow", "deny"]
    status: Literal[
        "available_to_configure",
        "configured_not_live_verified",
        "development_only",
        "blocked",
    ]
    blocking_reasons: list[str]
    health_status: str
    health_checked_at: str | None
    canary_status: str
    canary_checked_at: str | None
    canary_scope: Literal["connectivity_only_no_patient_data"]


class ModelLiveCanaryPolicy(TypedDict):
    purpose: Literal["connectivity_only_no_patient_data"]
    fixed_synthetic_payload: Literal[True]
    patient_data_allowed: Literal[False]
    requires_owner_admin: Literal[True]
    requires_explicit_acknowledgement: Literal[True]
    max_cost_cny: float
    max_output_tokens: int
    timeout_seconds: float
    cooldown_seconds: int


class ModelCatalog(TypedDict):
    active_provider: str
    active_model: str
    operator_default_provider: str
    operator_default_model: str
    effective_deployment_id: str
    tenant_selection: "TenantModelSelection"
    registered_deployments: list["ModelDeployment"]
    selection_editable: bool
    live_canary_available: bool
    live_canary_policy: ModelLiveCanaryPolicy
    tenant_region: Literal["cn", "eu", "us"]
    egress_policy: Literal["strict", "best_effort", "off"]
    external_llm_allowed: bool
    models: list[ModelCatalogItem]
    readiness_scope: Literal["configuration_and_policy_only"]
    live_health_verified: Literal[False]
    disclaimer: str


class TenantModelSelection(TypedDict):
    mode: Literal["inherit", "pinned"]
    deployment_id: str | None
    version: int


class ModelDeployment(TypedDict):
    id: str
    provider_id: str
    model: str
    is_default: bool
    tenant_selectable: bool
    credential_configured: bool
    canary_status: str
    canary_checked_at: str | None


class ModelHealthProbe(TypedDict):
    deployment_id: str
    provider_id: str
    model: str
    status: str
    probe_mode: Literal["configuration"]
    egress_decision: Literal["allow", "deny"]
    credential_configured: bool
    circuit_open: bool
    checked_at: str


class ModelLiveCanaryUsage(TypedDict):
    input_tokens: int
    output_tokens: int


class ModelLiveCanaryCost(TypedDict):
    amount: float
    currency: Literal["CNY"]
    billing_authoritative: Literal[False]
    source: Literal["provider_usage_pricing_estimate"]


class ModelLiveCanaryResponse(TypedDict):
    deployment_id: str
    provider_id: str
    model: str
    status: Literal[
        "reachable", "provider_unavailable", "unexpected_response", "budget_exceeded"
    ]
    reason_code: Literal[
        "ok",
        "provider_degraded",
        "provider_timeout",
        "provider_exception",
        "unexpected_response",
        "reported_cost_exceeded_cap",
    ]
    probe_mode: Literal["external_connectivity_canary"]
    egress_decision: Literal["allow"]
    synthetic_payload: Literal[True]
    patient_data_sent: Literal[False]
    expected_token_matched: bool
    latency_ms: int
    usage: ModelLiveCanaryUsage
    cost: ModelLiveCanaryCost
    request_cost_cap_cny: float
    estimated_max_cost_cny: float
    checked_at: str


class ClinicalModelPackageManifest(TypedDict, total=False):
    package_key: str
    package_version: str
    package_sha256: str
    use_case: Literal[
        "clinical_coding_decision_support",
        "clinical_documentation_improvement",
    ]
    model_kind: str
    runtime_contract: str
    jurisdiction: Literal["CN"]
    training_data_scope: Literal["aggregate_manifest_only"]
    training_dataset_sha256: str
    training_case_count: int
    evaluation_evidence_sha256: str
    license_status: Literal[
        "unknown", "external_review_required", "verified", "restricted"
    ]
    redistribution_authorized: bool
    cloud_use_authorized: bool
    hospital_use_authorized: bool
    independent_gold_validated: bool
    independent_reviewer_approved: bool


class ClinicalModelPackage(ClinicalModelPackageManifest):
    id: str
    status: Literal["draft", "submitted", "approved", "active", "retired", "rejected"]
    record_version: int
    created_by_user_id: str
    submitted_by_user_id: str | None
    reviewed_by_user_id: str | None
    review_reference_sha256: str | None
    decision_reason_code: str | None
    created_at: str
    updated_at: str
    submitted_at: str | None
    reviewed_at: str | None
    binary_stored: Literal[False]
    patient_data_stored: Literal[False]


class ClinicalModelPackageList(TypedDict):
    items: list[ClinicalModelPackage]
    count: int
    governance_scope: Literal["metadata_and_evidence_digests_only"]
    runtime_loading_enabled: Literal[False]


class ClinicalModelActivation(TypedDict):
    id: str
    use_case: str
    package_id: str
    previous_package_id: str | None
    deployment_mode: Literal["development", "hospital_private", "cloud"]
    record_version: int
    activated_by_user_id: str
    created_at: str
    updated_at: str
    activation_blockers: list[str]
    runtime_loading_enabled: Literal[False]


class ClinicalModelArtifactAttestation(TypedDict):
    id: str
    package_id: str
    bundle_content_sha256: str
    manifest_sha256: str
    verification_report_sha256: str
    trust_key_id: str
    trust_store_sha256: str
    sbom_sha256: str
    model_sha256: str
    artifact_class: Literal["development_synthetic"]
    model_format: Literal["icoder.synthetic-json/v1"]
    runtime_contract: str
    verifier_version: str
    content_scan_status: Literal["clean_development_scanner"]
    probe_status: Literal["passed"]
    test_vector_count: int
    verified_by_user_id: str
    created_at: str
    bundle_stored: Literal[False]
    patient_data_stored: Literal[False]
    production_inference_enabled: Literal[False]


class ClinicalModelArtifactAttestationList(TypedDict):
    items: list[ClinicalModelArtifactAttestation]
    count: int
    metadata_only: Literal[True]


class ClinicalModelShadowBinding(TypedDict):
    id: str
    use_case: str
    package_id: str
    attestation_id: str
    previous_package_id: str | None
    previous_attestation_id: str | None
    mode: Literal["shadow_only"]
    record_version: int
    bound_by_user_id: str
    created_at: str
    updated_at: str
    evaluation_gate_status: Literal["not_evaluated", "passed", "stopped"]
    last_evaluation_id: str | None
    last_evaluated_at: str | None
    patient_data_allowed: Literal[False]
    runtime_inference_enabled: Literal[False]
    predictions_emitted: Literal[False]


class ClinicalModelShadowEvaluation(TypedDict):
    id: str
    binding_id: str
    use_case: str
    package_id: str
    attestation_id: str
    source: Literal["repository_synthetic", "synthetic_fault_injection"]
    suite_id: str
    suite_sha256: str
    artifact_sha256: str
    observation_report_sha256: str
    result: Literal["passed", "stopped"]
    reason_code: str
    fault_mode: Literal["none", "worker_timeout", "malformed_response", "model_hash_mismatch"]
    run_count: int
    vector_observation_count: int
    success_count: int
    mismatch_count: int
    error_count: int
    latency_p50_ms: int
    latency_p95_ms: int
    artifact_reverified: bool
    rollback_performed: bool
    binding_version_before: int
    binding_version_after: int
    evaluated_by_user_id: str
    created_at: str
    aggregate_only: Literal[True]
    patient_data_used: Literal[False]
    raw_input_stored: Literal[False]
    predictions_emitted: Literal[False]
    network_used: Literal[False]
    production_inference_enabled: Literal[False]


class ClinicalModelShadowEvaluationList(TypedDict):
    items: list[ClinicalModelShadowEvaluation]
    count: int
    aggregate_only: Literal[True]


class ClinicalModelShadowJob(TypedDict):
    id: str
    binding_id: str
    use_case: str
    package_id: str
    attestation_id: str
    binding_record_version: int
    request_sha256: str
    fault_mode: Literal["none", "worker_timeout", "malformed_response", "model_hash_mismatch"]
    status: Literal["queued", "running", "passed", "stopped", "failed", "cancelled"]
    attempt_count: int
    max_attempts: int
    evaluation_id: str | None
    error_code: str | None
    rollback_performed: bool
    created_by_user_id: str
    started_at: str | None
    completed_at: str | None
    cancellation_reason: Literal["operator_request", "maintenance", "safety_stop"] | None
    cancelled_at: str | None
    cancelled_by_user_id: str | None
    created_at: str
    updated_at: str
    lease_active: bool
    artifact_source: Literal["repository_synthetic_fixture"]
    aggregate_only: Literal[True]
    patient_data_used: Literal[False]
    raw_input_stored: Literal[False]
    predictions_emitted: Literal[False]
    network_used: Literal[False]
    production_inference_enabled: Literal[False]


class ClinicalModelShadowJobList(TypedDict):
    items: list[ClinicalModelShadowJob]
    count: int
    aggregate_only: Literal[True]


class ClinicalModelShadowJobHealth(TypedDict):
    status: Literal["healthy", "degraded"]
    status_counts: dict[str, int]
    due_queued_count: int
    active_lease_count: int
    expired_lease_count: int
    exhausted_count: int
    dead_letter_count: int
    oldest_due_age_seconds: int
    alert_codes: list[Literal[
        "queue_backlog", "queue_age_exceeded", "expired_leases", "exhausted_jobs",
        "dead_letter_backlog",
    ]]
    evaluated_at: str
    aggregate_only: Literal[True]
    patient_data_used: Literal[False]
    identifiers_emitted: Literal[False]


class ClinicalModelShadowJobMaintenance(TypedDict):
    finalized_exhausted_count: int
    organizations_evaluated: int
    alerts_fired: int
    alerts_resolved: int
    aggregate_only: Literal[True]
    patient_data_used: Literal[False]
    identifiers_emitted: Literal[False]


class ClinicalModelShadowDeadLetter(TypedDict):
    id: str
    source_job_id: str
    binding_id: str
    use_case: str
    package_id: str
    attestation_id: str
    binding_record_version: int
    error_code: str
    attempt_count: int
    max_attempts: int
    status: Literal["available", "replayed", "discarded"]
    replayed_job_id: str | None
    replayed_at: str | None
    replayed_by_user_id: str | None
    created_at: str
    updated_at: str
    aggregate_only: Literal[True]
    patient_data_used: Literal[False]
    raw_input_stored: Literal[False]


class ClinicalModelShadowDeadLetterList(TypedDict):
    items: list[ClinicalModelShadowDeadLetter]
    count: int
    aggregate_only: Literal[True]


class ClinicalModelShadowAlertState(TypedDict):
    alert_code: Literal[
        "queue_backlog", "queue_age_exceeded", "expired_leases",
        "exhausted_jobs", "dead_letter_backlog",
    ]
    state: Literal["firing", "resolved"]
    occurrence_count: int
    opened_at: str
    last_evaluated_at: str
    last_transition_at: str
    resolved_at: str | None


class ClinicalModelShadowAlertStateList(TypedDict):
    items: list[ClinicalModelShadowAlertState]
    count: int
    aggregate_only: Literal[True]
    patient_data_used: Literal[False]
    identifiers_emitted: Literal[False]


class ModelsResource:
    def __init__(self, client: iCoDerClient):
        self._client = client

    def get_catalog(
        self, request_options: RequestOptions | None = None,
    ) -> ModelCatalog:
        response = self._client.get(
            "/api/v1/model-catalog", request_options=request_options,
        )
        response.raise_for_status()
        return cast(ModelCatalog, response.json())

    def update_selection(
        self,
        *,
        mode: Literal["inherit", "pinned"],
        expected_version: int,
        deployment_id: str | None = None,
        request_options: RequestOptions | None = None,
    ) -> TenantModelSelection:
        payload: dict[str, object] = {
            "mode": mode,
            "expected_version": expected_version,
        }
        if deployment_id is not None:
            payload["deployment_id"] = deployment_id
        response = self._client.put(
            "/api/v1/model-catalog/selection",
            json=payload,
            request_options=request_options,
        )
        response.raise_for_status()
        return cast(TenantModelSelection, response.json())

    def health_probe(
        self,
        deployment_id: str,
        request_options: RequestOptions | None = None,
    ) -> ModelHealthProbe:
        """Run a no-network, configuration-only deployment health probe."""
        response = self._client.post(
            "/api/v1/model-catalog/health-probe",
            json={"deployment_id": deployment_id},
            request_options=request_options,
        )
        response.raise_for_status()
        return cast(ModelHealthProbe, response.json())

    def live_canary(
        self,
        deployment_id: str,
        *,
        max_cost_cny: float,
        request_options: RequestOptions | None = None,
    ) -> ModelLiveCanaryResponse:
        """Run one fixed-payload, explicitly acknowledged external call."""
        if not isinstance(deployment_id, str) or not deployment_id.strip() or len(deployment_id) > 64:
            raise ValueError("deployment_id must contain between 1 and 64 characters")
        if (
            isinstance(max_cost_cny, bool)
            or not isinstance(max_cost_cny, (int, float))
            or max_cost_cny <= 0
            or max_cost_cny > 1
        ):
            raise ValueError("max_cost_cny must be greater than 0 and at most 1")
        response = self._client.post(
            "/api/v1/model-catalog/live-canary",
            json={
                "deployment_id": deployment_id,
                "acknowledge_external_call": True,
                "purpose": "connectivity_only_no_patient_data",
                "max_cost_cny": float(max_cost_cny),
            },
            request_options=request_options,
        )
        response.raise_for_status()
        return cast(ModelLiveCanaryResponse, response.json())

    def list_clinical_packages(
        self, request_options: RequestOptions | None = None,
    ) -> ClinicalModelPackageList:
        response = self._client.get(
            "/api/v1/clinical-model-packages", request_options=request_options,
        )
        response.raise_for_status()
        return cast(ClinicalModelPackageList, response.json())

    def create_clinical_package(
        self,
        manifest: ClinicalModelPackageManifest,
        request_options: RequestOptions | None = None,
    ) -> ClinicalModelPackage:
        response = self._client.post(
            "/api/v1/clinical-model-packages",
            json=dict(manifest),
            request_options=request_options,
        )
        response.raise_for_status()
        return cast(ClinicalModelPackage, response.json())

    def submit_clinical_package(
        self,
        package_id: str,
        *,
        expected_version: int,
        request_options: RequestOptions | None = None,
    ) -> ClinicalModelPackage:
        response = self._client.post(
            f"/api/v1/clinical-model-packages/{package_id}/submit",
            json={"expected_version": expected_version},
            request_options=request_options,
        )
        response.raise_for_status()
        return cast(ClinicalModelPackage, response.json())

    def decide_clinical_package(
        self,
        package_id: str,
        *,
        expected_version: int,
        decision: Literal["approve", "reject"],
        review_reference_sha256: str,
        reason_code: str,
        request_options: RequestOptions | None = None,
    ) -> ClinicalModelPackage:
        response = self._client.post(
            f"/api/v1/clinical-model-packages/{package_id}/decision",
            json={
                "expected_version": expected_version,
                "decision": decision,
                "review_reference_sha256": review_reference_sha256,
                "reason_code": reason_code,
            },
            request_options=request_options,
        )
        response.raise_for_status()
        return cast(ClinicalModelPackage, response.json())

    def get_clinical_activation(
        self,
        use_case: str,
        request_options: RequestOptions | None = None,
    ) -> ClinicalModelActivation:
        response = self._client.get(
            f"/api/v1/clinical-model-packages/activations/{use_case}",
            request_options=request_options,
        )
        response.raise_for_status()
        return cast(ClinicalModelActivation, response.json())

    def activate_clinical_package(
        self,
        use_case: str,
        *,
        package_id: str,
        deployment_mode: Literal["development", "hospital_private", "cloud"],
        expected_version: int,
        request_options: RequestOptions | None = None,
    ) -> ClinicalModelActivation:
        response = self._client.put(
            f"/api/v1/clinical-model-packages/activations/{use_case}",
            json={
                "package_id": package_id,
                "deployment_mode": deployment_mode,
                "expected_version": expected_version,
                "acknowledge_clinical_governance": True,
            },
            request_options=request_options,
        )
        response.raise_for_status()
        return cast(ClinicalModelActivation, response.json())

    def rollback_clinical_package(
        self,
        use_case: str,
        *,
        package_id: str,
        deployment_mode: Literal["development", "hospital_private", "cloud"],
        expected_version: int,
        request_options: RequestOptions | None = None,
    ) -> ClinicalModelActivation:
        response = self._client.post(
            f"/api/v1/clinical-model-packages/activations/{use_case}/rollback",
            json={
                "package_id": package_id,
                "deployment_mode": deployment_mode,
                "expected_version": expected_version,
                "acknowledge_clinical_governance": True,
            },
            request_options=request_options,
        )
        response.raise_for_status()
        return cast(ClinicalModelActivation, response.json())

    def list_clinical_artifact_attestations(
        self,
        package_id: str,
        request_options: RequestOptions | None = None,
    ) -> ClinicalModelArtifactAttestationList:
        response = self._client.get(
            f"/api/v1/clinical-model-packages/{package_id}/artifact-attestations",
            request_options=request_options,
        )
        response.raise_for_status()
        return cast(ClinicalModelArtifactAttestationList, response.json())

    def probe_synthetic_clinical_artifact(
        self,
        package_id: str,
        *,
        bundle_base64: str,
        expected_package_record_version: int,
        request_options: RequestOptions | None = None,
    ) -> ClinicalModelArtifactAttestation:
        response = self._client.post(
            f"/api/v1/clinical-model-packages/{package_id}/synthetic-artifact-probe",
            json={
                "bundle_base64": bundle_base64,
                "expected_package_record_version": expected_package_record_version,
            },
            request_options=request_options,
        )
        response.raise_for_status()
        return cast(ClinicalModelArtifactAttestation, response.json())

    def get_clinical_shadow_binding(
        self,
        use_case: str,
        request_options: RequestOptions | None = None,
    ) -> ClinicalModelShadowBinding:
        response = self._client.get(
            f"/api/v1/clinical-model-packages/shadow-bindings/{use_case}",
            request_options=request_options,
        )
        response.raise_for_status()
        return cast(ClinicalModelShadowBinding, response.json())

    def bind_clinical_shadow_attestation(
        self,
        use_case: str,
        *,
        attestation_id: str,
        expected_version: int,
        request_options: RequestOptions | None = None,
    ) -> ClinicalModelShadowBinding:
        response = self._client.put(
            f"/api/v1/clinical-model-packages/shadow-bindings/{use_case}",
            json={
                "attestation_id": attestation_id,
                "expected_version": expected_version,
                "acknowledge_shadow_only": True,
            },
            request_options=request_options,
        )
        response.raise_for_status()
        return cast(ClinicalModelShadowBinding, response.json())

    def rollback_clinical_shadow_binding(
        self,
        use_case: str,
        *,
        attestation_id: str,
        expected_version: int,
        request_options: RequestOptions | None = None,
    ) -> ClinicalModelShadowBinding:
        response = self._client.post(
            f"/api/v1/clinical-model-packages/shadow-bindings/{use_case}/rollback",
            json={
                "attestation_id": attestation_id,
                "expected_version": expected_version,
                "acknowledge_shadow_only": True,
            },
            request_options=request_options,
        )
        response.raise_for_status()
        return cast(ClinicalModelShadowBinding, response.json())

    def list_clinical_shadow_evaluations(
        self,
        use_case: str,
        request_options: RequestOptions | None = None,
    ) -> ClinicalModelShadowEvaluationList:
        response = self._client.get(
            f"/api/v1/clinical-model-packages/shadow-bindings/{use_case}/evaluations",
            request_options=request_options,
        )
        response.raise_for_status()
        return cast(ClinicalModelShadowEvaluationList, response.json())

    def evaluate_synthetic_clinical_shadow(
        self,
        use_case: str,
        *,
        expected_binding_version: int,
        bundle_base64: str | None = None,
        fault_mode: Literal[
            "none", "worker_timeout", "malformed_response", "model_hash_mismatch"
        ] = "none",
        acknowledge_fault_injection: bool = False,
        request_options: RequestOptions | None = None,
    ) -> ClinicalModelShadowEvaluation:
        payload: dict[str, object] = {
            "expected_binding_version": expected_binding_version,
            "fault_mode": fault_mode,
            "acknowledge_synthetic_only": True,
            "acknowledge_fault_injection": acknowledge_fault_injection,
        }
        if bundle_base64 is not None:
            payload["bundle_base64"] = bundle_base64
        response = self._client.post(
            f"/api/v1/clinical-model-packages/shadow-bindings/{use_case}/synthetic-evaluation",
            json=payload,
            request_options=request_options,
        )
        response.raise_for_status()
        return cast(ClinicalModelShadowEvaluation, response.json())

    def create_clinical_shadow_evaluation_job(
        self,
        use_case: str,
        *,
        expected_binding_version: int,
        idempotency_key: str,
        fault_mode: Literal[
            "none", "worker_timeout", "malformed_response", "model_hash_mismatch"
        ] = "none",
        acknowledge_fault_injection: bool = False,
        request_options: RequestOptions | None = None,
    ) -> ClinicalModelShadowJob:
        response = self._client.post(
            f"/api/v1/clinical-model-packages/shadow-bindings/{use_case}/evaluation-jobs",
            json={
                "expected_binding_version": expected_binding_version,
                "fault_mode": fault_mode,
                "acknowledge_synthetic_only": True,
                "acknowledge_fault_injection": acknowledge_fault_injection,
            },
            headers={"Idempotency-Key": idempotency_key},
            request_options=request_options,
        )
        response.raise_for_status()
        return cast(ClinicalModelShadowJob, response.json())

    def list_clinical_shadow_evaluation_jobs(
        self,
        use_case: str,
        request_options: RequestOptions | None = None,
    ) -> ClinicalModelShadowJobList:
        response = self._client.get(
            f"/api/v1/clinical-model-packages/shadow-bindings/{use_case}/evaluation-jobs",
            request_options=request_options,
        )
        response.raise_for_status()
        return cast(ClinicalModelShadowJobList, response.json())

    def get_clinical_shadow_evaluation_job(
        self,
        job_id: str,
        request_options: RequestOptions | None = None,
    ) -> ClinicalModelShadowJob:
        response = self._client.get(
            f"/api/v1/clinical-model-packages/shadow-evaluation-jobs/{job_id}",
            request_options=request_options,
        )
        response.raise_for_status()
        return cast(ClinicalModelShadowJob, response.json())

    def execute_clinical_shadow_evaluation_job_simulation(
        self,
        job_id: str,
        request_options: RequestOptions | None = None,
    ) -> ClinicalModelShadowJob:
        response = self._client.post(
            f"/api/v1/clinical-model-packages/shadow-evaluation-jobs/{job_id}/execute",
            json={},
            request_options=request_options,
        )
        response.raise_for_status()
        return cast(ClinicalModelShadowJob, response.json())

    def cancel_clinical_shadow_evaluation_job(
        self,
        job_id: str,
        *,
        reason: Literal["operator_request", "maintenance", "safety_stop"],
        request_options: RequestOptions | None = None,
    ) -> ClinicalModelShadowJob:
        response = self._client.post(
            f"/api/v1/clinical-model-packages/shadow-evaluation-jobs/{job_id}/cancel",
            json={"reason": reason},
            request_options=request_options,
        )
        response.raise_for_status()
        return cast(ClinicalModelShadowJob, response.json())

    def get_clinical_shadow_evaluation_job_health(
        self,
        request_options: RequestOptions | None = None,
    ) -> ClinicalModelShadowJobHealth:
        response = self._client.get(
            "/api/v1/clinical-model-packages/shadow-evaluation-jobs/health/summary",
            request_options=request_options,
        )
        response.raise_for_status()
        return cast(ClinicalModelShadowJobHealth, response.json())

    def maintain_clinical_shadow_evaluation_jobs_simulation(
        self,
        request_options: RequestOptions | None = None,
    ) -> ClinicalModelShadowJobMaintenance:
        response = self._client.post(
            "/api/v1/clinical-model-packages/shadow-evaluation-jobs/maintenance/run",
            json={},
            request_options=request_options,
        )
        response.raise_for_status()
        return cast(ClinicalModelShadowJobMaintenance, response.json())

    def list_clinical_shadow_dead_letters(
        self, request_options: RequestOptions | None = None,
    ) -> ClinicalModelShadowDeadLetterList:
        response = self._client.get(
            "/api/v1/clinical-model-packages/shadow-evaluation-jobs/dead-letters/list",
            request_options=request_options,
        )
        response.raise_for_status()
        return cast(ClinicalModelShadowDeadLetterList, response.json())

    def replay_clinical_shadow_dead_letter(
        self,
        dead_letter_id: str,
        *,
        idempotency_key: str,
        request_options: RequestOptions | None = None,
    ) -> ClinicalModelShadowJob:
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{7,127}", idempotency_key) is None:
            raise ValueError("idempotency_key must contain 8 to 128 safe characters")
        response = self._client.post(
            f"/api/v1/clinical-model-packages/shadow-evaluation-jobs/dead-letters/{dead_letter_id}/replay",
            json={},
            headers={"Idempotency-Key": idempotency_key},
            request_options=request_options,
        )
        response.raise_for_status()
        return cast(ClinicalModelShadowJob, response.json())

    def list_clinical_shadow_alert_states(
        self, request_options: RequestOptions | None = None,
    ) -> ClinicalModelShadowAlertStateList:
        response = self._client.get(
            "/api/v1/clinical-model-packages/shadow-evaluation-jobs/alerts/states",
            request_options=request_options,
        )
        response.raise_for_status()
        return cast(ClinicalModelShadowAlertStateList, response.json())
