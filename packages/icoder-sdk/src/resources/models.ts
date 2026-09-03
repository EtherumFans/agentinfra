import type { AxiosInstance } from 'axios';
import { requestConfig, type iCoDerRequestOptions } from '../request-options.js';

export type ModelCatalogStatus =
  | 'available_to_configure'
  | 'configured_not_live_verified'
  | 'development_only'
  | 'blocked';

export interface ModelCatalogItem {
  id: string;
  display_name: string;
  default_model: string;
  model: string;
  deployment_kind: string;
  selected: boolean;
  credential_required: boolean;
  credential_configured: boolean | null;
  adapter_capabilities: string[];
  china_scenario: string;
  provider_region: 'cn' | 'eu' | 'us';
  tenant_region: 'cn' | 'eu' | 'us';
  egress_decision: 'allow' | 'deny';
  status: ModelCatalogStatus;
  blocking_reasons: string[];
  health_status?: string;
  health_checked_at?: string | null;
  canary_status?: string;
  canary_checked_at?: string | null;
  canary_scope?: 'connectivity_only_no_patient_data';
}

export interface ModelLiveCanaryPolicy {
  purpose: 'connectivity_only_no_patient_data';
  fixed_synthetic_payload: true;
  patient_data_allowed: false;
  requires_owner_admin: true;
  requires_explicit_acknowledgement: true;
  max_cost_cny: number;
  max_output_tokens: number;
  timeout_seconds: number;
  cooldown_seconds: number;
}

export interface ModelCatalog {
  active_provider: string;
  active_model: string;
  operator_default_provider: string;
  operator_default_model: string;
  effective_deployment_id: string;
  tenant_selection: TenantModelSelection;
  registered_deployments: ModelDeployment[];
  selection_editable: boolean;
  live_canary_available: boolean;
  live_canary_policy: ModelLiveCanaryPolicy;
  tenant_region: 'cn' | 'eu' | 'us';
  egress_policy: 'strict' | 'best_effort' | 'off';
  external_llm_allowed: boolean;
  models: ModelCatalogItem[];
  readiness_scope: 'configuration_and_policy_only';
  live_health_verified: false;
  disclaimer: string;
}

export interface TenantModelSelection {
  mode: 'inherit' | 'pinned';
  deployment_id: string | null;
  version: number;
}

export interface ModelDeployment {
  id: string;
  provider_id: string;
  model: string;
  is_default: boolean;
  tenant_selectable: boolean;
  credential_configured: boolean;
  canary_status?: string;
  canary_checked_at?: string | null;
}

export interface ModelHealthProbe {
  deployment_id: string;
  provider_id: string;
  model: string;
  status: string;
  probe_mode: 'configuration';
  egress_decision: 'allow' | 'deny';
  credential_configured: boolean;
  circuit_open: boolean;
  checked_at: string;
}

export interface ModelLiveCanaryResponse {
  deployment_id: string;
  provider_id: string;
  model: string;
  status: 'reachable' | 'provider_unavailable' | 'unexpected_response' | 'budget_exceeded';
  reason_code:
    | 'ok'
    | 'provider_degraded'
    | 'provider_timeout'
    | 'provider_exception'
    | 'unexpected_response'
    | 'reported_cost_exceeded_cap';
  probe_mode: 'external_connectivity_canary';
  egress_decision: 'allow';
  synthetic_payload: true;
  patient_data_sent: false;
  expected_token_matched: boolean;
  latency_ms: number;
  usage: { input_tokens: number; output_tokens: number };
  cost: {
    amount: number;
    currency: 'CNY';
    billing_authoritative: false;
    source: 'provider_usage_pricing_estimate';
  };
  request_cost_cap_cny: number;
  estimated_max_cost_cny: number;
  checked_at: string;
}

export type ClinicalModelUseCase =
  | 'clinical_coding_decision_support'
  | 'clinical_documentation_improvement';
export type ClinicalModelDeploymentMode = 'development' | 'hospital_private' | 'cloud';
export type ClinicalModelPackageStatus =
  | 'draft' | 'submitted' | 'approved' | 'active' | 'retired' | 'rejected';

export interface ClinicalModelPackageManifest {
  package_key: string;
  package_version: string;
  package_sha256: string;
  use_case: ClinicalModelUseCase;
  model_kind: string;
  runtime_contract: string;
  jurisdiction?: 'CN';
  training_data_scope?: 'aggregate_manifest_only';
  training_dataset_sha256: string;
  training_case_count: number;
  evaluation_evidence_sha256: string;
  license_status?: 'unknown' | 'external_review_required' | 'verified' | 'restricted';
  redistribution_authorized?: boolean;
  cloud_use_authorized?: boolean;
  hospital_use_authorized?: boolean;
  independent_gold_validated?: boolean;
  independent_reviewer_approved?: boolean;
}

export interface ClinicalModelPackage extends Required<ClinicalModelPackageManifest> {
  id: string;
  status: ClinicalModelPackageStatus;
  record_version: number;
  created_by_user_id: string;
  submitted_by_user_id: string | null;
  reviewed_by_user_id: string | null;
  review_reference_sha256: string | null;
  decision_reason_code: string | null;
  created_at: string;
  updated_at: string;
  submitted_at: string | null;
  reviewed_at: string | null;
  binary_stored: false;
  patient_data_stored: false;
}

export interface ClinicalModelPackageList {
  items: ClinicalModelPackage[];
  count: number;
  governance_scope: 'metadata_and_evidence_digests_only';
  runtime_loading_enabled: false;
}

export interface ClinicalModelActivation {
  id: string;
  use_case: ClinicalModelUseCase;
  package_id: string;
  previous_package_id: string | null;
  deployment_mode: ClinicalModelDeploymentMode;
  record_version: number;
  activated_by_user_id: string;
  created_at: string;
  updated_at: string;
  activation_blockers: string[];
  runtime_loading_enabled: false;
}

export interface ClinicalModelActivationInput {
  package_id: string;
  deployment_mode: ClinicalModelDeploymentMode;
  expected_version: number;
  acknowledge_clinical_governance: true;
}

export interface ClinicalModelArtifactAttestation {
  id: string;
  package_id: string;
  bundle_content_sha256: string;
  manifest_sha256: string;
  verification_report_sha256: string;
  trust_key_id: string;
  trust_store_sha256: string;
  sbom_sha256: string;
  model_sha256: string;
  artifact_class: 'development_synthetic';
  model_format: 'icoder.synthetic-json/v1';
  runtime_contract: string;
  verifier_version: string;
  content_scan_status: 'clean_development_scanner';
  probe_status: 'passed';
  test_vector_count: number;
  verified_by_user_id: string;
  created_at: string;
  bundle_stored: false;
  patient_data_stored: false;
  production_inference_enabled: false;
}

export interface ClinicalModelArtifactAttestationList {
  items: ClinicalModelArtifactAttestation[];
  count: number;
  metadata_only: true;
}

export interface ClinicalModelShadowBinding {
  id: string;
  use_case: ClinicalModelUseCase;
  package_id: string;
  attestation_id: string;
  previous_package_id: string | null;
  previous_attestation_id: string | null;
  mode: 'shadow_only';
  record_version: number;
  bound_by_user_id: string;
  created_at: string;
  updated_at: string;
  evaluation_gate_status: 'not_evaluated' | 'passed' | 'stopped';
  last_evaluation_id: string | null;
  last_evaluated_at: string | null;
  patient_data_allowed: false;
  runtime_inference_enabled: false;
  predictions_emitted: false;
}

export interface ClinicalModelShadowBindingInput {
  attestation_id: string;
  expected_version: number;
  acknowledge_shadow_only: true;
}

export type ClinicalModelShadowFaultMode =
  | 'none' | 'worker_timeout' | 'malformed_response' | 'model_hash_mismatch';

export interface ClinicalModelShadowEvaluationInput {
  expected_binding_version: number;
  bundle_base64?: string;
  fault_mode?: ClinicalModelShadowFaultMode;
  acknowledge_synthetic_only: true;
  acknowledge_fault_injection?: boolean;
}

export interface ClinicalModelShadowEvaluation {
  id: string;
  binding_id: string;
  use_case: ClinicalModelUseCase;
  package_id: string;
  attestation_id: string;
  source: 'repository_synthetic' | 'synthetic_fault_injection';
  suite_id: string;
  suite_sha256: string;
  artifact_sha256: string;
  observation_report_sha256: string;
  result: 'passed' | 'stopped';
  reason_code: string;
  fault_mode: ClinicalModelShadowFaultMode;
  run_count: number;
  vector_observation_count: number;
  success_count: number;
  mismatch_count: number;
  error_count: number;
  latency_p50_ms: number;
  latency_p95_ms: number;
  artifact_reverified: boolean;
  rollback_performed: boolean;
  binding_version_before: number;
  binding_version_after: number;
  evaluated_by_user_id: string;
  created_at: string;
  aggregate_only: true;
  patient_data_used: false;
  raw_input_stored: false;
  predictions_emitted: false;
  network_used: false;
  production_inference_enabled: false;
}

export interface ClinicalModelShadowEvaluationList {
  items: ClinicalModelShadowEvaluation[];
  count: number;
  aggregate_only: true;
}

export interface ClinicalModelShadowJobInput {
  expected_binding_version: number;
  fault_mode?: ClinicalModelShadowFaultMode;
  acknowledge_synthetic_only: true;
  acknowledge_fault_injection?: boolean;
}

export interface ClinicalModelShadowJob {
  id: string;
  binding_id: string;
  use_case: ClinicalModelUseCase;
  package_id: string;
  attestation_id: string;
  binding_record_version: number;
  request_sha256: string;
  fault_mode: ClinicalModelShadowFaultMode;
  status: 'queued' | 'running' | 'passed' | 'stopped' | 'failed' | 'cancelled';
  attempt_count: number;
  max_attempts: number;
  evaluation_id: string | null;
  error_code: string | null;
  rollback_performed: boolean;
  created_by_user_id: string;
  started_at: string | null;
  completed_at: string | null;
  cancellation_reason: 'operator_request' | 'maintenance' | 'safety_stop' | null;
  cancelled_at: string | null;
  cancelled_by_user_id: string | null;
  created_at: string;
  updated_at: string;
  lease_active: boolean;
  artifact_source: 'repository_synthetic_fixture';
  aggregate_only: true;
  patient_data_used: false;
  raw_input_stored: false;
  predictions_emitted: false;
  network_used: false;
  production_inference_enabled: false;
}

export interface ClinicalModelShadowJobList {
  items: ClinicalModelShadowJob[];
  count: number;
  aggregate_only: true;
}

export interface ClinicalModelShadowJobHealth {
  status: 'healthy' | 'degraded';
  status_counts: Record<ClinicalModelShadowJob['status'], number>;
  due_queued_count: number;
  active_lease_count: number;
  expired_lease_count: number;
  exhausted_count: number;
  dead_letter_count: number;
  oldest_due_age_seconds: number;
  alert_codes: Array<
    'queue_backlog' | 'queue_age_exceeded' | 'expired_leases' | 'exhausted_jobs'
    | 'dead_letter_backlog'
  >;
  evaluated_at: string;
  aggregate_only: true;
  patient_data_used: false;
  identifiers_emitted: false;
}

export interface ClinicalModelShadowJobMaintenance {
  finalized_exhausted_count: number;
  organizations_evaluated: number;
  alerts_fired: number;
  alerts_resolved: number;
  aggregate_only: true;
  patient_data_used: false;
  identifiers_emitted: false;
}

export interface ClinicalModelShadowDeadLetter {
  id: string;
  source_job_id: string;
  binding_id: string;
  use_case: ClinicalModelUseCase;
  package_id: string;
  attestation_id: string;
  binding_record_version: number;
  error_code: string;
  attempt_count: number;
  max_attempts: number;
  status: 'available' | 'replayed' | 'discarded';
  replayed_job_id: string | null;
  replayed_at: string | null;
  replayed_by_user_id: string | null;
  created_at: string;
  updated_at: string;
  aggregate_only: true;
  patient_data_used: false;
  raw_input_stored: false;
}

export interface ClinicalModelShadowDeadLetterList {
  items: ClinicalModelShadowDeadLetter[];
  count: number;
  aggregate_only: true;
}

export interface ClinicalModelShadowAlertState {
  alert_code: 'queue_backlog' | 'queue_age_exceeded' | 'expired_leases'
    | 'exhausted_jobs' | 'dead_letter_backlog';
  state: 'firing' | 'resolved';
  occurrence_count: number;
  opened_at: string;
  last_evaluated_at: string;
  last_transition_at: string;
  resolved_at: string | null;
}

export interface ClinicalModelShadowAlertStateList {
  items: ClinicalModelShadowAlertState[];
  count: number;
  aggregate_only: true;
  patient_data_used: false;
  identifiers_emitted: false;
}

export class ModelsResource {
  constructor(private readonly http: AxiosInstance) {}

  async getCatalog(options?: iCoDerRequestOptions): Promise<ModelCatalog> {
    const { data } = await this.http.get<ModelCatalog>(
      '/api/v1/model-catalog', requestConfig(options),
    );
    return data;
  }

  async updateSelection(input: {
    mode: 'inherit' | 'pinned';
    deployment_id?: string;
    expected_version: number;
  }, options?: iCoDerRequestOptions): Promise<TenantModelSelection> {
    const { data } = await this.http.put<TenantModelSelection>(
      '/api/v1/model-catalog/selection',
      input,
      requestConfig(options),
    );
    return data;
  }

  /** Run a no-network, configuration-only health probe for a deployment. */
  async healthProbe(
    deploymentId: string,
    options?: iCoDerRequestOptions,
  ): Promise<ModelHealthProbe> {
    const { data } = await this.http.post<ModelHealthProbe>(
      '/api/v1/model-catalog/health-probe',
      { deployment_id: deploymentId },
      requestConfig(options),
    );
    return data;
  }

  /**
   * Run one explicitly acknowledged fixed-payload external connectivity call.
   * No caller text is accepted and the completion text is never returned.
   */
  async liveCanary(
    deploymentId: string,
    maxCostCny: number,
    options?: iCoDerRequestOptions,
  ): Promise<ModelLiveCanaryResponse> {
    if (!deploymentId.trim() || deploymentId.length > 64) {
      throw new RangeError('deploymentId must contain between 1 and 64 characters');
    }
    if (!Number.isFinite(maxCostCny) || maxCostCny <= 0 || maxCostCny > 1) {
      throw new RangeError('maxCostCny must be greater than 0 and at most 1');
    }
    const { data } = await this.http.post<ModelLiveCanaryResponse>(
      '/api/v1/model-catalog/live-canary',
      {
        deployment_id: deploymentId,
        acknowledge_external_call: true,
        purpose: 'connectivity_only_no_patient_data',
        max_cost_cny: maxCostCny,
      },
      requestConfig(options),
    );
    return data;
  }

  async listClinicalPackages(
    options?: iCoDerRequestOptions,
  ): Promise<ClinicalModelPackageList> {
    const { data } = await this.http.get<ClinicalModelPackageList>(
      '/api/v1/clinical-model-packages', requestConfig(options),
    );
    return data;
  }

  async createClinicalPackage(
    manifest: ClinicalModelPackageManifest,
    options?: iCoDerRequestOptions,
  ): Promise<ClinicalModelPackage> {
    const { data } = await this.http.post<ClinicalModelPackage>(
      '/api/v1/clinical-model-packages', manifest, requestConfig(options),
    );
    return data;
  }

  async submitClinicalPackage(
    packageId: string,
    expectedVersion: number,
    options?: iCoDerRequestOptions,
  ): Promise<ClinicalModelPackage> {
    const { data } = await this.http.post<ClinicalModelPackage>(
      `/api/v1/clinical-model-packages/${encodeURIComponent(packageId)}/submit`,
      { expected_version: expectedVersion },
      requestConfig(options),
    );
    return data;
  }

  async decideClinicalPackage(
    packageId: string,
    input: {
      expected_version: number;
      decision: 'approve' | 'reject';
      review_reference_sha256: string;
      reason_code: 'evidence_verified' | 'evidence_incomplete' | 'license_unverified'
        | 'clinical_validation_failed' | 'security_review_failed';
    },
    options?: iCoDerRequestOptions,
  ): Promise<ClinicalModelPackage> {
    const { data } = await this.http.post<ClinicalModelPackage>(
      `/api/v1/clinical-model-packages/${encodeURIComponent(packageId)}/decision`,
      input,
      requestConfig(options),
    );
    return data;
  }

  async getClinicalActivation(
    useCase: ClinicalModelUseCase,
    options?: iCoDerRequestOptions,
  ): Promise<ClinicalModelActivation> {
    const { data } = await this.http.get<ClinicalModelActivation>(
      `/api/v1/clinical-model-packages/activations/${useCase}`,
      requestConfig(options),
    );
    return data;
  }

  async activateClinicalPackage(
    useCase: ClinicalModelUseCase,
    input: ClinicalModelActivationInput,
    options?: iCoDerRequestOptions,
  ): Promise<ClinicalModelActivation> {
    const { data } = await this.http.put<ClinicalModelActivation>(
      `/api/v1/clinical-model-packages/activations/${useCase}`,
      input,
      requestConfig(options),
    );
    return data;
  }

  async rollbackClinicalPackage(
    useCase: ClinicalModelUseCase,
    input: ClinicalModelActivationInput,
    options?: iCoDerRequestOptions,
  ): Promise<ClinicalModelActivation> {
    const { data } = await this.http.post<ClinicalModelActivation>(
      `/api/v1/clinical-model-packages/activations/${useCase}/rollback`,
      input,
      requestConfig(options),
    );
    return data;
  }

  async listClinicalArtifactAttestations(
    packageId: string,
    options?: iCoDerRequestOptions,
  ): Promise<ClinicalModelArtifactAttestationList> {
    const { data } = await this.http.get<ClinicalModelArtifactAttestationList>(
      `/api/v1/clinical-model-packages/${encodeURIComponent(packageId)}/artifact-attestations`,
      requestConfig(options),
    );
    return data;
  }

  async probeSyntheticClinicalArtifact(
    packageId: string,
    bundleBase64: string,
    expectedPackageRecordVersion: number,
    options?: iCoDerRequestOptions,
  ): Promise<ClinicalModelArtifactAttestation> {
    const { data } = await this.http.post<ClinicalModelArtifactAttestation>(
      `/api/v1/clinical-model-packages/${encodeURIComponent(packageId)}/synthetic-artifact-probe`,
      {
        bundle_base64: bundleBase64,
        expected_package_record_version: expectedPackageRecordVersion,
      },
      requestConfig(options),
    );
    return data;
  }

  async getClinicalShadowBinding(
    useCase: ClinicalModelUseCase,
    options?: iCoDerRequestOptions,
  ): Promise<ClinicalModelShadowBinding> {
    const { data } = await this.http.get<ClinicalModelShadowBinding>(
      `/api/v1/clinical-model-packages/shadow-bindings/${useCase}`,
      requestConfig(options),
    );
    return data;
  }

  async bindClinicalShadowAttestation(
    useCase: ClinicalModelUseCase,
    input: ClinicalModelShadowBindingInput,
    options?: iCoDerRequestOptions,
  ): Promise<ClinicalModelShadowBinding> {
    const { data } = await this.http.put<ClinicalModelShadowBinding>(
      `/api/v1/clinical-model-packages/shadow-bindings/${useCase}`,
      input,
      requestConfig(options),
    );
    return data;
  }

  async rollbackClinicalShadowBinding(
    useCase: ClinicalModelUseCase,
    input: ClinicalModelShadowBindingInput,
    options?: iCoDerRequestOptions,
  ): Promise<ClinicalModelShadowBinding> {
    const { data } = await this.http.post<ClinicalModelShadowBinding>(
      `/api/v1/clinical-model-packages/shadow-bindings/${useCase}/rollback`,
      input,
      requestConfig(options),
    );
    return data;
  }

  async listClinicalShadowEvaluations(
    useCase: ClinicalModelUseCase,
    options?: iCoDerRequestOptions,
  ): Promise<ClinicalModelShadowEvaluationList> {
    const { data } = await this.http.get<ClinicalModelShadowEvaluationList>(
      `/api/v1/clinical-model-packages/shadow-bindings/${useCase}/evaluations`,
      requestConfig(options),
    );
    return data;
  }

  async evaluateSyntheticClinicalShadow(
    useCase: ClinicalModelUseCase,
    input: ClinicalModelShadowEvaluationInput,
    options?: iCoDerRequestOptions,
  ): Promise<ClinicalModelShadowEvaluation> {
    const { data } = await this.http.post<ClinicalModelShadowEvaluation>(
      `/api/v1/clinical-model-packages/shadow-bindings/${useCase}/synthetic-evaluation`,
      input,
      requestConfig(options),
    );
    return data;
  }

  async createClinicalShadowEvaluationJob(
    useCase: ClinicalModelUseCase,
    input: ClinicalModelShadowJobInput,
    idempotencyKey: string,
    options?: iCoDerRequestOptions,
  ): Promise<ClinicalModelShadowJob> {
    if (!/^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$/.test(idempotencyKey)) {
      throw new TypeError('idempotencyKey must contain 8 to 128 safe characters');
    }
    const { data } = await this.http.post<ClinicalModelShadowJob>(
      `/api/v1/clinical-model-packages/shadow-bindings/${useCase}/evaluation-jobs`,
      input,
      requestConfig(options, {}, { 'Idempotency-Key': idempotencyKey }),
    );
    return data;
  }

  async listClinicalShadowEvaluationJobs(
    useCase: ClinicalModelUseCase,
    options?: iCoDerRequestOptions,
  ): Promise<ClinicalModelShadowJobList> {
    const { data } = await this.http.get<ClinicalModelShadowJobList>(
      `/api/v1/clinical-model-packages/shadow-bindings/${useCase}/evaluation-jobs`,
      requestConfig(options),
    );
    return data;
  }

  async getClinicalShadowEvaluationJob(
    jobId: string,
    options?: iCoDerRequestOptions,
  ): Promise<ClinicalModelShadowJob> {
    const { data } = await this.http.get<ClinicalModelShadowJob>(
      `/api/v1/clinical-model-packages/shadow-evaluation-jobs/${encodeURIComponent(jobId)}`,
      requestConfig(options),
    );
    return data;
  }

  async executeClinicalShadowEvaluationJobSimulation(
    jobId: string,
    options?: iCoDerRequestOptions,
  ): Promise<ClinicalModelShadowJob> {
    const { data } = await this.http.post<ClinicalModelShadowJob>(
      `/api/v1/clinical-model-packages/shadow-evaluation-jobs/${encodeURIComponent(jobId)}/execute`,
      {},
      requestConfig(options),
    );
    return data;
  }

  async cancelClinicalShadowEvaluationJob(
    jobId: string,
    reason: 'operator_request' | 'maintenance' | 'safety_stop',
    options?: iCoDerRequestOptions,
  ): Promise<ClinicalModelShadowJob> {
    const { data } = await this.http.post<ClinicalModelShadowJob>(
      `/api/v1/clinical-model-packages/shadow-evaluation-jobs/${encodeURIComponent(jobId)}/cancel`,
      { reason },
      requestConfig(options),
    );
    return data;
  }

  async getClinicalShadowEvaluationJobHealth(
    options?: iCoDerRequestOptions,
  ): Promise<ClinicalModelShadowJobHealth> {
    const { data } = await this.http.get<ClinicalModelShadowJobHealth>(
      '/api/v1/clinical-model-packages/shadow-evaluation-jobs/health/summary',
      requestConfig(options),
    );
    return data;
  }

  async maintainClinicalShadowEvaluationJobsSimulation(
    options?: iCoDerRequestOptions,
  ): Promise<ClinicalModelShadowJobMaintenance> {
    const { data } = await this.http.post<ClinicalModelShadowJobMaintenance>(
      '/api/v1/clinical-model-packages/shadow-evaluation-jobs/maintenance/run',
      {},
      requestConfig(options),
    );
    return data;
  }

  async listClinicalShadowDeadLetters(
    options?: iCoDerRequestOptions,
  ): Promise<ClinicalModelShadowDeadLetterList> {
    const { data } = await this.http.get<ClinicalModelShadowDeadLetterList>(
      '/api/v1/clinical-model-packages/shadow-evaluation-jobs/dead-letters/list',
      requestConfig(options),
    );
    return data;
  }

  async replayClinicalShadowDeadLetter(
    deadLetterId: string,
    idempotencyKey: string,
    options?: iCoDerRequestOptions,
  ): Promise<ClinicalModelShadowJob> {
    if (!/^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$/.test(idempotencyKey)) {
      throw new TypeError('idempotencyKey must contain 8 to 128 safe characters');
    }
    const { data } = await this.http.post<ClinicalModelShadowJob>(
      `/api/v1/clinical-model-packages/shadow-evaluation-jobs/dead-letters/${encodeURIComponent(deadLetterId)}/replay`,
      {},
      requestConfig(options, {}, { 'Idempotency-Key': idempotencyKey }),
    );
    return data;
  }

  async listClinicalShadowAlertStates(
    options?: iCoDerRequestOptions,
  ): Promise<ClinicalModelShadowAlertStateList> {
    const { data } = await this.http.get<ClinicalModelShadowAlertStateList>(
      '/api/v1/clinical-model-packages/shadow-evaluation-jobs/alerts/states',
      requestConfig(options),
    );
    return data;
  }
}
