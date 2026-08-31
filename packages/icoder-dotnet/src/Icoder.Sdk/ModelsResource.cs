using System.Text.Json.Serialization;

namespace Icoder.Sdk;

public sealed class ModelsResource(ICoDerClient client)
{
    public Task<ModelCatalog> GetCatalogAsync(
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
        => client.SendAsync<ModelCatalog>(
            HttpMethod.Get, "/api/v1/model-catalog", cancellationToken: cancellationToken,
            requestOptions: requestOptions);

    public Task<TenantModelSelection> UpdateSelectionAsync(
        UpdateModelSelectionRequest request,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
        => client.SendAsync<TenantModelSelection>(
            HttpMethod.Put,
            "/api/v1/model-catalog/selection",
            request,
            cancellationToken: cancellationToken, requestOptions: requestOptions);

    public Task<ModelLiveCanaryResponse> LiveCanaryAsync(
        string deploymentId,
        decimal maxCostCny,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(deploymentId, nameof(deploymentId));
        if (deploymentId.Length > 64)
        {
            throw new ArgumentOutOfRangeException(nameof(deploymentId));
        }
        if (maxCostCny is <= 0 or > 1)
        {
            throw new ArgumentOutOfRangeException(
                nameof(maxCostCny), "maxCostCny must be greater than 0 and at most 1.");
        }
        return client.SendAsync<ModelLiveCanaryResponse>(
            HttpMethod.Post,
            "/api/v1/model-catalog/live-canary",
            new
            {
                deployment_id = deploymentId,
                acknowledge_external_call = true,
                purpose = "connectivity_only_no_patient_data",
                max_cost_cny = maxCostCny,
            },
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task<ClinicalModelPackageList> ListClinicalPackagesAsync(
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
        => client.SendAsync<ClinicalModelPackageList>(
            HttpMethod.Get, "/api/v1/clinical-model-packages",
            cancellationToken: cancellationToken, requestOptions: requestOptions);

    public Task<ClinicalModelPackage> CreateClinicalPackageAsync(
        ClinicalModelPackageManifest manifest,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
        => client.SendAsync<ClinicalModelPackage>(
            HttpMethod.Post, "/api/v1/clinical-model-packages", manifest,
            cancellationToken: cancellationToken, requestOptions: requestOptions);

    public Task<ClinicalModelPackage> SubmitClinicalPackageAsync(
        string packageId,
        int expectedVersion,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(packageId, nameof(packageId));
        return client.SendAsync<ClinicalModelPackage>(
            HttpMethod.Post,
            $"/api/v1/clinical-model-packages/{Uri.EscapeDataString(packageId)}/submit",
            new { expected_version = expectedVersion },
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task<ClinicalModelPackage> DecideClinicalPackageAsync(
        string packageId,
        ClinicalModelPackageDecision request,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(packageId, nameof(packageId));
        return client.SendAsync<ClinicalModelPackage>(
            HttpMethod.Post,
            $"/api/v1/clinical-model-packages/{Uri.EscapeDataString(packageId)}/decision",
            request,
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task<ClinicalModelActivation> GetClinicalActivationAsync(
        string useCase,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(useCase, nameof(useCase));
        return client.SendAsync<ClinicalModelActivation>(
            HttpMethod.Get,
            $"/api/v1/clinical-model-packages/activations/{Uri.EscapeDataString(useCase)}",
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task<ClinicalModelActivation> ActivateClinicalPackageAsync(
        string useCase,
        ClinicalModelActivationRequest request,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(useCase, nameof(useCase));
        return client.SendAsync<ClinicalModelActivation>(
            HttpMethod.Put,
            $"/api/v1/clinical-model-packages/activations/{Uri.EscapeDataString(useCase)}",
            request,
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task<ClinicalModelActivation> RollbackClinicalPackageAsync(
        string useCase,
        ClinicalModelActivationRequest request,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(useCase, nameof(useCase));
        return client.SendAsync<ClinicalModelActivation>(
            HttpMethod.Post,
            $"/api/v1/clinical-model-packages/activations/{Uri.EscapeDataString(useCase)}/rollback",
            request,
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task<ClinicalModelArtifactAttestationList> ListClinicalArtifactAttestationsAsync(
        string packageId,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(packageId, nameof(packageId));
        return client.SendAsync<ClinicalModelArtifactAttestationList>(
            HttpMethod.Get,
            $"/api/v1/clinical-model-packages/{Uri.EscapeDataString(packageId)}/artifact-attestations",
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task<ClinicalModelArtifactAttestation> ProbeSyntheticClinicalArtifactAsync(
        string packageId,
        ClinicalModelSyntheticArtifactProbeRequest request,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(packageId, nameof(packageId));
        return client.SendAsync<ClinicalModelArtifactAttestation>(
            HttpMethod.Post,
            $"/api/v1/clinical-model-packages/{Uri.EscapeDataString(packageId)}/synthetic-artifact-probe",
            request,
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task<ClinicalModelShadowBinding> GetClinicalShadowBindingAsync(
        string useCase,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(useCase, nameof(useCase));
        return client.SendAsync<ClinicalModelShadowBinding>(
            HttpMethod.Get,
            $"/api/v1/clinical-model-packages/shadow-bindings/{Uri.EscapeDataString(useCase)}",
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task<ClinicalModelShadowBinding> BindClinicalShadowAttestationAsync(
        string useCase,
        ClinicalModelShadowBindingRequest request,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(useCase, nameof(useCase));
        return client.SendAsync<ClinicalModelShadowBinding>(
            HttpMethod.Put,
            $"/api/v1/clinical-model-packages/shadow-bindings/{Uri.EscapeDataString(useCase)}",
            request,
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task<ClinicalModelShadowBinding> RollbackClinicalShadowBindingAsync(
        string useCase,
        ClinicalModelShadowBindingRequest request,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(useCase, nameof(useCase));
        return client.SendAsync<ClinicalModelShadowBinding>(
            HttpMethod.Post,
            $"/api/v1/clinical-model-packages/shadow-bindings/{Uri.EscapeDataString(useCase)}/rollback",
            request,
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task<ClinicalModelShadowEvaluationList> ListClinicalShadowEvaluationsAsync(
        string useCase,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(useCase, nameof(useCase));
        return client.SendAsync<ClinicalModelShadowEvaluationList>(
            HttpMethod.Get,
            $"/api/v1/clinical-model-packages/shadow-bindings/{Uri.EscapeDataString(useCase)}/evaluations",
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task<ClinicalModelShadowEvaluation> EvaluateSyntheticClinicalShadowAsync(
        string useCase,
        ClinicalModelShadowEvaluationRequest request,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(useCase, nameof(useCase));
        return client.SendAsync<ClinicalModelShadowEvaluation>(
            HttpMethod.Post,
            $"/api/v1/clinical-model-packages/shadow-bindings/{Uri.EscapeDataString(useCase)}/synthetic-evaluation",
            request,
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task<ClinicalModelShadowJob> CreateClinicalShadowEvaluationJobAsync(
        string useCase,
        ClinicalModelShadowJobRequest request,
        string idempotencyKey,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(useCase, nameof(useCase));
        Guard.NotNullOrWhiteSpace(idempotencyKey, nameof(idempotencyKey));
        IReadOnlyDictionary<string, string> headers =
            new Dictionary<string, string> { ["Idempotency-Key"] = idempotencyKey };
        return client.SendAsync<ClinicalModelShadowJob>(
            HttpMethod.Post,
            $"/api/v1/clinical-model-packages/shadow-bindings/{Uri.EscapeDataString(useCase)}/evaluation-jobs",
            request,
            headers,
            cancellationToken,
            requestOptions);
    }

    public Task<ClinicalModelShadowJobList> ListClinicalShadowEvaluationJobsAsync(
        string useCase,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(useCase, nameof(useCase));
        return client.SendAsync<ClinicalModelShadowJobList>(
            HttpMethod.Get,
            $"/api/v1/clinical-model-packages/shadow-bindings/{Uri.EscapeDataString(useCase)}/evaluation-jobs",
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task<ClinicalModelShadowJob> GetClinicalShadowEvaluationJobAsync(
        string jobId,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(jobId, nameof(jobId));
        return client.SendAsync<ClinicalModelShadowJob>(
            HttpMethod.Get,
            $"/api/v1/clinical-model-packages/shadow-evaluation-jobs/{Uri.EscapeDataString(jobId)}",
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task<ClinicalModelShadowJob> ExecuteClinicalShadowEvaluationJobSimulationAsync(
        string jobId,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(jobId, nameof(jobId));
        return client.SendAsync<ClinicalModelShadowJob>(
            HttpMethod.Post,
            $"/api/v1/clinical-model-packages/shadow-evaluation-jobs/{Uri.EscapeDataString(jobId)}/execute",
            new { },
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task<ClinicalModelShadowJob> CancelClinicalShadowEvaluationJobAsync(
        string jobId,
        string reason,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(jobId, nameof(jobId));
        Guard.NotNullOrWhiteSpace(reason, nameof(reason));
        return client.SendAsync<ClinicalModelShadowJob>(
            HttpMethod.Post,
            $"/api/v1/clinical-model-packages/shadow-evaluation-jobs/{Uri.EscapeDataString(jobId)}/cancel",
            new ClinicalModelShadowJobCancelRequest(reason),
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task<ClinicalModelShadowJobHealth> GetClinicalShadowEvaluationJobHealthAsync(
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        return client.SendAsync<ClinicalModelShadowJobHealth>(
            HttpMethod.Get,
            "/api/v1/clinical-model-packages/shadow-evaluation-jobs/health/summary",
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task<ClinicalModelShadowJobMaintenance> MaintainClinicalShadowEvaluationJobsSimulationAsync(
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        return client.SendAsync<ClinicalModelShadowJobMaintenance>(
            HttpMethod.Post,
            "/api/v1/clinical-model-packages/shadow-evaluation-jobs/maintenance/run",
            new { },
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task<ClinicalModelShadowDeadLetterList> ListClinicalShadowDeadLettersAsync(
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
        => client.SendAsync<ClinicalModelShadowDeadLetterList>(
            HttpMethod.Get,
            "/api/v1/clinical-model-packages/shadow-evaluation-jobs/dead-letters/list",
            cancellationToken: cancellationToken, requestOptions: requestOptions);

    public Task<ClinicalModelShadowJob> ReplayClinicalShadowDeadLetterAsync(
        string deadLetterId,
        string idempotencyKey,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(deadLetterId, nameof(deadLetterId));
        Guard.NotNullOrWhiteSpace(idempotencyKey, nameof(idempotencyKey));
        IReadOnlyDictionary<string, string> headers =
            new Dictionary<string, string> { ["Idempotency-Key"] = idempotencyKey };
        return client.SendAsync<ClinicalModelShadowJob>(
            HttpMethod.Post,
            $"/api/v1/clinical-model-packages/shadow-evaluation-jobs/dead-letters/{Uri.EscapeDataString(deadLetterId)}/replay",
            new { },
            headers,
            cancellationToken,
            requestOptions);
    }

    public Task<ClinicalModelShadowAlertStateList> ListClinicalShadowAlertStatesAsync(
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
        => client.SendAsync<ClinicalModelShadowAlertStateList>(
            HttpMethod.Get,
            "/api/v1/clinical-model-packages/shadow-evaluation-jobs/alerts/states",
            cancellationToken: cancellationToken, requestOptions: requestOptions);
}

public record ClinicalModelPackageManifest
{
    [JsonPropertyName("package_key")]
    public required string PackageKey { get; init; }

    [JsonPropertyName("package_version")]
    public required string PackageVersion { get; init; }

    [JsonPropertyName("package_sha256")]
    public required string PackageSha256 { get; init; }

    [JsonPropertyName("use_case")]
    public required string UseCase { get; init; }

    [JsonPropertyName("model_kind")]
    public required string ModelKind { get; init; }

    [JsonPropertyName("runtime_contract")]
    public required string RuntimeContract { get; init; }

    [JsonPropertyName("jurisdiction")]
    public string Jurisdiction { get; init; } = "CN";

    [JsonPropertyName("training_data_scope")]
    public string TrainingDataScope { get; init; } = "aggregate_manifest_only";

    [JsonPropertyName("training_dataset_sha256")]
    public required string TrainingDatasetSha256 { get; init; }

    [JsonPropertyName("training_case_count")]
    public int TrainingCaseCount { get; init; }

    [JsonPropertyName("evaluation_evidence_sha256")]
    public required string EvaluationEvidenceSha256 { get; init; }

    [JsonPropertyName("license_status")]
    public string LicenseStatus { get; init; } = "external_review_required";

    [JsonPropertyName("redistribution_authorized")]
    public bool RedistributionAuthorized { get; init; }

    [JsonPropertyName("cloud_use_authorized")]
    public bool CloudUseAuthorized { get; init; }

    [JsonPropertyName("hospital_use_authorized")]
    public bool HospitalUseAuthorized { get; init; }

    [JsonPropertyName("independent_gold_validated")]
    public bool IndependentGoldValidated { get; init; }

    [JsonPropertyName("independent_reviewer_approved")]
    public bool IndependentReviewerApproved { get; init; }
}

public sealed record ClinicalModelPackageDecision(
    [property: JsonPropertyName("expected_version")] int ExpectedVersion,
    [property: JsonPropertyName("decision")] string Decision,
    [property: JsonPropertyName("review_reference_sha256")] string ReviewReferenceSha256,
    [property: JsonPropertyName("reason_code")] string ReasonCode);

public sealed record ClinicalModelActivationRequest(
    [property: JsonPropertyName("package_id")] string PackageId,
    [property: JsonPropertyName("deployment_mode")] string DeploymentMode,
    [property: JsonPropertyName("expected_version")] int ExpectedVersion,
    [property: JsonPropertyName("acknowledge_clinical_governance")] bool AcknowledgeClinicalGovernance = true);

public sealed record ClinicalModelSyntheticArtifactProbeRequest(
    [property: JsonPropertyName("bundle_base64")] string BundleBase64,
    [property: JsonPropertyName("expected_package_record_version")] int ExpectedPackageRecordVersion);

public sealed record ClinicalModelShadowBindingRequest(
    [property: JsonPropertyName("attestation_id")] string AttestationId,
    [property: JsonPropertyName("expected_version")] int ExpectedVersion,
    [property: JsonPropertyName("acknowledge_shadow_only")] bool AcknowledgeShadowOnly = true);

public sealed record ClinicalModelShadowEvaluationRequest(
    [property: JsonPropertyName("expected_binding_version")] int ExpectedBindingVersion,
    [property: JsonPropertyName("bundle_base64")] string? BundleBase64 = null,
    [property: JsonPropertyName("fault_mode")] string FaultMode = "none",
    [property: JsonPropertyName("acknowledge_synthetic_only")] bool AcknowledgeSyntheticOnly = true,
    [property: JsonPropertyName("acknowledge_fault_injection")] bool AcknowledgeFaultInjection = false);

public sealed record ClinicalModelShadowJobRequest(
    [property: JsonPropertyName("expected_binding_version")] int ExpectedBindingVersion,
    [property: JsonPropertyName("fault_mode")] string FaultMode = "none",
    [property: JsonPropertyName("acknowledge_synthetic_only")] bool AcknowledgeSyntheticOnly = true,
    [property: JsonPropertyName("acknowledge_fault_injection")] bool AcknowledgeFaultInjection = false);

public sealed record ClinicalModelShadowJobCancelRequest(
    [property: JsonPropertyName("reason")] string Reason);

public sealed record ClinicalModelPackage : ClinicalModelPackageManifest
{
    [JsonPropertyName("id")]
    public required string Id { get; init; }

    [JsonPropertyName("status")]
    public required string Status { get; init; }

    [JsonPropertyName("record_version")]
    public int RecordVersion { get; init; }

    [JsonPropertyName("created_by_user_id")]
    public required string CreatedByUserId { get; init; }

    [JsonPropertyName("submitted_by_user_id")]
    public string? SubmittedByUserId { get; init; }

    [JsonPropertyName("reviewed_by_user_id")]
    public string? ReviewedByUserId { get; init; }

    [JsonPropertyName("review_reference_sha256")]
    public string? ReviewReferenceSha256 { get; init; }

    [JsonPropertyName("decision_reason_code")]
    public string? DecisionReasonCode { get; init; }

    [JsonPropertyName("created_at")]
    public required string CreatedAt { get; init; }

    [JsonPropertyName("updated_at")]
    public required string UpdatedAt { get; init; }

    [JsonPropertyName("submitted_at")]
    public string? SubmittedAt { get; init; }

    [JsonPropertyName("reviewed_at")]
    public string? ReviewedAt { get; init; }

    [JsonPropertyName("binary_stored")]
    public bool BinaryStored { get; init; }

    [JsonPropertyName("patient_data_stored")]
    public bool PatientDataStored { get; init; }
}

public sealed record ClinicalModelPackageList
{
    [JsonPropertyName("items")]
    public IReadOnlyList<ClinicalModelPackage> Items { get; init; } = [];

    [JsonPropertyName("count")]
    public int Count { get; init; }

    [JsonPropertyName("governance_scope")]
    public required string GovernanceScope { get; init; }

    [JsonPropertyName("runtime_loading_enabled")]
    public bool RuntimeLoadingEnabled { get; init; }
}

public sealed record ClinicalModelActivation
{
    [JsonPropertyName("id")]
    public required string Id { get; init; }

    [JsonPropertyName("use_case")]
    public required string UseCase { get; init; }

    [JsonPropertyName("package_id")]
    public required string PackageId { get; init; }

    [JsonPropertyName("previous_package_id")]
    public string? PreviousPackageId { get; init; }

    [JsonPropertyName("deployment_mode")]
    public required string DeploymentMode { get; init; }

    [JsonPropertyName("record_version")]
    public int RecordVersion { get; init; }

    [JsonPropertyName("activated_by_user_id")]
    public required string ActivatedByUserId { get; init; }

    [JsonPropertyName("created_at")]
    public required string CreatedAt { get; init; }

    [JsonPropertyName("updated_at")]
    public required string UpdatedAt { get; init; }

    [JsonPropertyName("activation_blockers")]
    public IReadOnlyList<string> ActivationBlockers { get; init; } = [];

    [JsonPropertyName("runtime_loading_enabled")]
    public bool RuntimeLoadingEnabled { get; init; }
}

public sealed record ClinicalModelArtifactAttestation
{
    [JsonPropertyName("id")] public required string Id { get; init; }
    [JsonPropertyName("package_id")] public required string PackageId { get; init; }
    [JsonPropertyName("bundle_content_sha256")] public required string BundleContentSha256 { get; init; }
    [JsonPropertyName("manifest_sha256")] public required string ManifestSha256 { get; init; }
    [JsonPropertyName("verification_report_sha256")] public required string VerificationReportSha256 { get; init; }
    [JsonPropertyName("trust_key_id")] public required string TrustKeyId { get; init; }
    [JsonPropertyName("trust_store_sha256")] public required string TrustStoreSha256 { get; init; }
    [JsonPropertyName("sbom_sha256")] public required string SbomSha256 { get; init; }
    [JsonPropertyName("model_sha256")] public required string ModelSha256 { get; init; }
    [JsonPropertyName("artifact_class")] public required string ArtifactClass { get; init; }
    [JsonPropertyName("model_format")] public required string ModelFormat { get; init; }
    [JsonPropertyName("runtime_contract")] public required string RuntimeContract { get; init; }
    [JsonPropertyName("verifier_version")] public required string VerifierVersion { get; init; }
    [JsonPropertyName("content_scan_status")] public required string ContentScanStatus { get; init; }
    [JsonPropertyName("probe_status")] public required string ProbeStatus { get; init; }
    [JsonPropertyName("test_vector_count")] public int TestVectorCount { get; init; }
    [JsonPropertyName("verified_by_user_id")] public required string VerifiedByUserId { get; init; }
    [JsonPropertyName("created_at")] public required string CreatedAt { get; init; }
    [JsonPropertyName("bundle_stored")] public bool BundleStored { get; init; }
    [JsonPropertyName("patient_data_stored")] public bool PatientDataStored { get; init; }
    [JsonPropertyName("production_inference_enabled")] public bool ProductionInferenceEnabled { get; init; }
}

public sealed record ClinicalModelArtifactAttestationList
{
    [JsonPropertyName("items")]
    public IReadOnlyList<ClinicalModelArtifactAttestation> Items { get; init; } = [];
    [JsonPropertyName("count")] public int Count { get; init; }
    [JsonPropertyName("metadata_only")] public bool MetadataOnly { get; init; }
}

public sealed record ClinicalModelShadowBinding
{
    [JsonPropertyName("id")] public required string Id { get; init; }
    [JsonPropertyName("use_case")] public required string UseCase { get; init; }
    [JsonPropertyName("package_id")] public required string PackageId { get; init; }
    [JsonPropertyName("attestation_id")] public required string AttestationId { get; init; }
    [JsonPropertyName("previous_package_id")] public string? PreviousPackageId { get; init; }
    [JsonPropertyName("previous_attestation_id")] public string? PreviousAttestationId { get; init; }
    [JsonPropertyName("mode")] public required string Mode { get; init; }
    [JsonPropertyName("record_version")] public int RecordVersion { get; init; }
    [JsonPropertyName("bound_by_user_id")] public required string BoundByUserId { get; init; }
    [JsonPropertyName("created_at")] public required string CreatedAt { get; init; }
    [JsonPropertyName("updated_at")] public required string UpdatedAt { get; init; }
    [JsonPropertyName("evaluation_gate_status")] public required string EvaluationGateStatus { get; init; }
    [JsonPropertyName("last_evaluation_id")] public string? LastEvaluationId { get; init; }
    [JsonPropertyName("last_evaluated_at")] public string? LastEvaluatedAt { get; init; }
    [JsonPropertyName("patient_data_allowed")] public bool PatientDataAllowed { get; init; }
    [JsonPropertyName("runtime_inference_enabled")] public bool RuntimeInferenceEnabled { get; init; }
    [JsonPropertyName("predictions_emitted")] public bool PredictionsEmitted { get; init; }
}

public sealed record ClinicalModelShadowEvaluation
{
    [JsonPropertyName("id")] public required string Id { get; init; }
    [JsonPropertyName("binding_id")] public required string BindingId { get; init; }
    [JsonPropertyName("use_case")] public required string UseCase { get; init; }
    [JsonPropertyName("package_id")] public required string PackageId { get; init; }
    [JsonPropertyName("attestation_id")] public required string AttestationId { get; init; }
    [JsonPropertyName("source")] public required string Source { get; init; }
    [JsonPropertyName("suite_id")] public required string SuiteId { get; init; }
    [JsonPropertyName("suite_sha256")] public required string SuiteSha256 { get; init; }
    [JsonPropertyName("artifact_sha256")] public required string ArtifactSha256 { get; init; }
    [JsonPropertyName("observation_report_sha256")] public required string ObservationReportSha256 { get; init; }
    [JsonPropertyName("result")] public required string Result { get; init; }
    [JsonPropertyName("reason_code")] public required string ReasonCode { get; init; }
    [JsonPropertyName("fault_mode")] public required string FaultMode { get; init; }
    [JsonPropertyName("run_count")] public int RunCount { get; init; }
    [JsonPropertyName("vector_observation_count")] public int VectorObservationCount { get; init; }
    [JsonPropertyName("success_count")] public int SuccessCount { get; init; }
    [JsonPropertyName("mismatch_count")] public int MismatchCount { get; init; }
    [JsonPropertyName("error_count")] public int ErrorCount { get; init; }
    [JsonPropertyName("latency_p50_ms")] public int LatencyP50Ms { get; init; }
    [JsonPropertyName("latency_p95_ms")] public int LatencyP95Ms { get; init; }
    [JsonPropertyName("artifact_reverified")] public bool ArtifactReverified { get; init; }
    [JsonPropertyName("rollback_performed")] public bool RollbackPerformed { get; init; }
    [JsonPropertyName("binding_version_before")] public int BindingVersionBefore { get; init; }
    [JsonPropertyName("binding_version_after")] public int BindingVersionAfter { get; init; }
    [JsonPropertyName("evaluated_by_user_id")] public required string EvaluatedByUserId { get; init; }
    [JsonPropertyName("created_at")] public required string CreatedAt { get; init; }
    [JsonPropertyName("aggregate_only")] public bool AggregateOnly { get; init; }
    [JsonPropertyName("patient_data_used")] public bool PatientDataUsed { get; init; }
    [JsonPropertyName("raw_input_stored")] public bool RawInputStored { get; init; }
    [JsonPropertyName("predictions_emitted")] public bool PredictionsEmitted { get; init; }
    [JsonPropertyName("network_used")] public bool NetworkUsed { get; init; }
    [JsonPropertyName("production_inference_enabled")] public bool ProductionInferenceEnabled { get; init; }
}

public sealed record ClinicalModelShadowEvaluationList
{
    [JsonPropertyName("items")]
    public IReadOnlyList<ClinicalModelShadowEvaluation> Items { get; init; } = [];
    [JsonPropertyName("count")] public int Count { get; init; }
    [JsonPropertyName("aggregate_only")] public bool AggregateOnly { get; init; }
}

public sealed record ClinicalModelShadowJob
{
    [JsonPropertyName("id")] public required string Id { get; init; }
    [JsonPropertyName("binding_id")] public required string BindingId { get; init; }
    [JsonPropertyName("use_case")] public required string UseCase { get; init; }
    [JsonPropertyName("package_id")] public required string PackageId { get; init; }
    [JsonPropertyName("attestation_id")] public required string AttestationId { get; init; }
    [JsonPropertyName("binding_record_version")] public int BindingRecordVersion { get; init; }
    [JsonPropertyName("request_sha256")] public required string RequestSha256 { get; init; }
    [JsonPropertyName("fault_mode")] public required string FaultMode { get; init; }
    [JsonPropertyName("status")] public required string Status { get; init; }
    [JsonPropertyName("attempt_count")] public int AttemptCount { get; init; }
    [JsonPropertyName("max_attempts")] public int MaxAttempts { get; init; }
    [JsonPropertyName("evaluation_id")] public string? EvaluationId { get; init; }
    [JsonPropertyName("error_code")] public string? ErrorCode { get; init; }
    [JsonPropertyName("rollback_performed")] public bool RollbackPerformed { get; init; }
    [JsonPropertyName("created_by_user_id")] public required string CreatedByUserId { get; init; }
    [JsonPropertyName("started_at")] public string? StartedAt { get; init; }
    [JsonPropertyName("completed_at")] public string? CompletedAt { get; init; }
    [JsonPropertyName("cancellation_reason")] public string? CancellationReason { get; init; }
    [JsonPropertyName("cancelled_at")] public string? CancelledAt { get; init; }
    [JsonPropertyName("cancelled_by_user_id")] public string? CancelledByUserId { get; init; }
    [JsonPropertyName("created_at")] public required string CreatedAt { get; init; }
    [JsonPropertyName("updated_at")] public required string UpdatedAt { get; init; }
    [JsonPropertyName("lease_active")] public bool LeaseActive { get; init; }
    [JsonPropertyName("artifact_source")] public required string ArtifactSource { get; init; }
    [JsonPropertyName("aggregate_only")] public bool AggregateOnly { get; init; }
    [JsonPropertyName("patient_data_used")] public bool PatientDataUsed { get; init; }
    [JsonPropertyName("raw_input_stored")] public bool RawInputStored { get; init; }
    [JsonPropertyName("predictions_emitted")] public bool PredictionsEmitted { get; init; }
    [JsonPropertyName("network_used")] public bool NetworkUsed { get; init; }
    [JsonPropertyName("production_inference_enabled")] public bool ProductionInferenceEnabled { get; init; }
}

public sealed record ClinicalModelShadowJobList
{
    [JsonPropertyName("items")]
    public IReadOnlyList<ClinicalModelShadowJob> Items { get; init; } = [];
    [JsonPropertyName("count")] public int Count { get; init; }
    [JsonPropertyName("aggregate_only")] public bool AggregateOnly { get; init; }
}

public sealed record ClinicalModelShadowJobHealth
{
    [JsonPropertyName("status")] public required string Status { get; init; }
    [JsonPropertyName("status_counts")]
    public IReadOnlyDictionary<string, int> StatusCounts { get; init; }
        = new Dictionary<string, int>();
    [JsonPropertyName("due_queued_count")] public int DueQueuedCount { get; init; }
    [JsonPropertyName("active_lease_count")] public int ActiveLeaseCount { get; init; }
    [JsonPropertyName("expired_lease_count")] public int ExpiredLeaseCount { get; init; }
    [JsonPropertyName("exhausted_count")] public int ExhaustedCount { get; init; }
    [JsonPropertyName("dead_letter_count")] public int DeadLetterCount { get; init; }
    [JsonPropertyName("oldest_due_age_seconds")] public int OldestDueAgeSeconds { get; init; }
    [JsonPropertyName("alert_codes")]
    public IReadOnlyList<string> AlertCodes { get; init; } = [];
    [JsonPropertyName("evaluated_at")] public required string EvaluatedAt { get; init; }
    [JsonPropertyName("aggregate_only")] public bool AggregateOnly { get; init; }
    [JsonPropertyName("patient_data_used")] public bool PatientDataUsed { get; init; }
    [JsonPropertyName("identifiers_emitted")] public bool IdentifiersEmitted { get; init; }
}

public sealed record ClinicalModelShadowJobMaintenance
{
    [JsonPropertyName("finalized_exhausted_count")]
    public int FinalizedExhaustedCount { get; init; }
    [JsonPropertyName("organizations_evaluated")] public int OrganizationsEvaluated { get; init; }
    [JsonPropertyName("alerts_fired")] public int AlertsFired { get; init; }
    [JsonPropertyName("alerts_resolved")] public int AlertsResolved { get; init; }
    [JsonPropertyName("aggregate_only")] public bool AggregateOnly { get; init; }
    [JsonPropertyName("patient_data_used")] public bool PatientDataUsed { get; init; }
    [JsonPropertyName("identifiers_emitted")] public bool IdentifiersEmitted { get; init; }
}

public sealed record ClinicalModelShadowDeadLetter
{
    [JsonPropertyName("id")] public required string Id { get; init; }
    [JsonPropertyName("source_job_id")] public required string SourceJobId { get; init; }
    [JsonPropertyName("binding_id")] public required string BindingId { get; init; }
    [JsonPropertyName("use_case")] public required string UseCase { get; init; }
    [JsonPropertyName("package_id")] public required string PackageId { get; init; }
    [JsonPropertyName("attestation_id")] public required string AttestationId { get; init; }
    [JsonPropertyName("binding_record_version")] public int BindingRecordVersion { get; init; }
    [JsonPropertyName("error_code")] public required string ErrorCode { get; init; }
    [JsonPropertyName("attempt_count")] public int AttemptCount { get; init; }
    [JsonPropertyName("max_attempts")] public int MaxAttempts { get; init; }
    [JsonPropertyName("status")] public required string Status { get; init; }
    [JsonPropertyName("replayed_job_id")] public string? ReplayedJobId { get; init; }
    [JsonPropertyName("replayed_at")] public string? ReplayedAt { get; init; }
    [JsonPropertyName("replayed_by_user_id")] public string? ReplayedByUserId { get; init; }
    [JsonPropertyName("created_at")] public required string CreatedAt { get; init; }
    [JsonPropertyName("updated_at")] public required string UpdatedAt { get; init; }
    [JsonPropertyName("aggregate_only")] public bool AggregateOnly { get; init; }
    [JsonPropertyName("patient_data_used")] public bool PatientDataUsed { get; init; }
    [JsonPropertyName("raw_input_stored")] public bool RawInputStored { get; init; }
}

public sealed record ClinicalModelShadowDeadLetterList
{
    [JsonPropertyName("items")]
    public IReadOnlyList<ClinicalModelShadowDeadLetter> Items { get; init; } = [];
    [JsonPropertyName("count")] public int Count { get; init; }
    [JsonPropertyName("aggregate_only")] public bool AggregateOnly { get; init; }
}

public sealed record ClinicalModelShadowAlertState
{
    [JsonPropertyName("alert_code")] public required string AlertCode { get; init; }
    [JsonPropertyName("state")] public required string State { get; init; }
    [JsonPropertyName("occurrence_count")] public int OccurrenceCount { get; init; }
    [JsonPropertyName("opened_at")] public required string OpenedAt { get; init; }
    [JsonPropertyName("last_evaluated_at")] public required string LastEvaluatedAt { get; init; }
    [JsonPropertyName("last_transition_at")] public required string LastTransitionAt { get; init; }
    [JsonPropertyName("resolved_at")] public string? ResolvedAt { get; init; }
}

public sealed record ClinicalModelShadowAlertStateList
{
    [JsonPropertyName("items")]
    public IReadOnlyList<ClinicalModelShadowAlertState> Items { get; init; } = [];
    [JsonPropertyName("count")] public int Count { get; init; }
    [JsonPropertyName("aggregate_only")] public bool AggregateOnly { get; init; }
    [JsonPropertyName("patient_data_used")] public bool PatientDataUsed { get; init; }
    [JsonPropertyName("identifiers_emitted")] public bool IdentifiersEmitted { get; init; }
}

public sealed record UpdateModelSelectionRequest(
    [property: JsonPropertyName("mode")] string Mode,
    [property: JsonPropertyName("expected_version")] int ExpectedVersion,
    [property: JsonPropertyName("deployment_id")] string? DeploymentId = null);

public sealed record TenantModelSelection
{
    [JsonPropertyName("mode")]
    public required string Mode { get; init; }

    [JsonPropertyName("deployment_id")]
    public string? DeploymentId { get; init; }

    [JsonPropertyName("version")]
    public int Version { get; init; }
}

public sealed record ModelCatalog
{
    [JsonPropertyName("active_provider")]
    public required string ActiveProvider { get; init; }

    [JsonPropertyName("active_model")]
    public required string ActiveModel { get; init; }

    [JsonPropertyName("operator_default_provider")]
    public required string OperatorDefaultProvider { get; init; }

    [JsonPropertyName("operator_default_model")]
    public required string OperatorDefaultModel { get; init; }

    [JsonPropertyName("effective_deployment_id")]
    public required string EffectiveDeploymentId { get; init; }

    [JsonPropertyName("tenant_selection")]
    public required TenantModelSelection TenantSelection { get; init; }

    [JsonPropertyName("registered_deployments")]
    public IReadOnlyList<ModelDeployment> RegisteredDeployments { get; init; } = [];

    [JsonPropertyName("selection_editable")]
    public bool SelectionEditable { get; init; }

    [JsonPropertyName("live_canary_available")]
    public bool LiveCanaryAvailable { get; init; }

    [JsonPropertyName("live_canary_policy")]
    public required ModelLiveCanaryPolicy LiveCanaryPolicy { get; init; }

    [JsonPropertyName("tenant_region")]
    public required string TenantRegion { get; init; }

    [JsonPropertyName("egress_policy")]
    public required string EgressPolicy { get; init; }

    [JsonPropertyName("external_llm_allowed")]
    public bool ExternalLlmAllowed { get; init; }

    [JsonPropertyName("models")]
    public IReadOnlyList<ModelCatalogItem> Models { get; init; } = [];

    [JsonPropertyName("readiness_scope")]
    public required string ReadinessScope { get; init; }

    [JsonPropertyName("live_health_verified")]
    public bool LiveHealthVerified { get; init; }

    [JsonPropertyName("disclaimer")]
    public required string Disclaimer { get; init; }
}

public sealed record ModelDeployment
{
    [JsonPropertyName("id")]
    public required string Id { get; init; }

    [JsonPropertyName("provider_id")]
    public required string ProviderId { get; init; }

    [JsonPropertyName("model")]
    public required string Model { get; init; }

    [JsonPropertyName("is_default")]
    public bool IsDefault { get; init; }

    [JsonPropertyName("tenant_selectable")]
    public bool TenantSelectable { get; init; }

    [JsonPropertyName("credential_configured")]
    public bool CredentialConfigured { get; init; }

    [JsonPropertyName("canary_status")]
    public string CanaryStatus { get; init; } = "not_run";

    [JsonPropertyName("canary_checked_at")]
    public string? CanaryCheckedAt { get; init; }
}

public sealed record ModelCatalogItem
{
    [JsonPropertyName("id")]
    public required string Id { get; init; }

    [JsonPropertyName("display_name")]
    public required string DisplayName { get; init; }

    [JsonPropertyName("model")]
    public required string Model { get; init; }

    [JsonPropertyName("selected")]
    public bool Selected { get; init; }

    [JsonPropertyName("status")]
    public required string Status { get; init; }

    [JsonPropertyName("provider_region")]
    public required string ProviderRegion { get; init; }

    [JsonPropertyName("tenant_region")]
    public required string TenantRegion { get; init; }

    [JsonPropertyName("egress_decision")]
    public required string EgressDecision { get; init; }

    [JsonPropertyName("blocking_reasons")]
    public IReadOnlyList<string> BlockingReasons { get; init; } = [];

    [JsonPropertyName("canary_status")]
    public string CanaryStatus { get; init; } = "not_run";

    [JsonPropertyName("canary_checked_at")]
    public string? CanaryCheckedAt { get; init; }

    [JsonPropertyName("canary_scope")]
    public string CanaryScope { get; init; } = "connectivity_only_no_patient_data";
}

public sealed record ModelLiveCanaryPolicy
{
    [JsonPropertyName("purpose")]
    public required string Purpose { get; init; }

    [JsonPropertyName("fixed_synthetic_payload")]
    public bool FixedSyntheticPayload { get; init; }

    [JsonPropertyName("patient_data_allowed")]
    public bool PatientDataAllowed { get; init; }

    [JsonPropertyName("requires_owner_admin")]
    public bool RequiresOwnerAdmin { get; init; }

    [JsonPropertyName("requires_explicit_acknowledgement")]
    public bool RequiresExplicitAcknowledgement { get; init; }

    [JsonPropertyName("max_cost_cny")]
    public decimal MaxCostCny { get; init; }

    [JsonPropertyName("max_output_tokens")]
    public int MaxOutputTokens { get; init; }

    [JsonPropertyName("timeout_seconds")]
    public double TimeoutSeconds { get; init; }

    [JsonPropertyName("cooldown_seconds")]
    public int CooldownSeconds { get; init; }
}

public sealed record ModelLiveCanaryResponse
{
    [JsonPropertyName("deployment_id")]
    public required string DeploymentId { get; init; }

    [JsonPropertyName("provider_id")]
    public required string ProviderId { get; init; }

    [JsonPropertyName("model")]
    public required string Model { get; init; }

    [JsonPropertyName("status")]
    public required string Status { get; init; }

    [JsonPropertyName("reason_code")]
    public required string ReasonCode { get; init; }

    [JsonPropertyName("probe_mode")]
    public required string ProbeMode { get; init; }

    [JsonPropertyName("egress_decision")]
    public required string EgressDecision { get; init; }

    [JsonPropertyName("synthetic_payload")]
    public bool SyntheticPayload { get; init; }

    [JsonPropertyName("patient_data_sent")]
    public bool PatientDataSent { get; init; }

    [JsonPropertyName("expected_token_matched")]
    public bool ExpectedTokenMatched { get; init; }

    [JsonPropertyName("latency_ms")]
    public int LatencyMs { get; init; }

    [JsonPropertyName("usage")]
    public required ModelLiveCanaryUsage Usage { get; init; }

    [JsonPropertyName("cost")]
    public required ModelLiveCanaryCost Cost { get; init; }

    [JsonPropertyName("request_cost_cap_cny")]
    public decimal RequestCostCapCny { get; init; }

    [JsonPropertyName("estimated_max_cost_cny")]
    public decimal EstimatedMaxCostCny { get; init; }

    [JsonPropertyName("checked_at")]
    public required string CheckedAt { get; init; }
}

public sealed record ModelLiveCanaryUsage
{
    [JsonPropertyName("input_tokens")]
    public int InputTokens { get; init; }

    [JsonPropertyName("output_tokens")]
    public int OutputTokens { get; init; }
}

public sealed record ModelLiveCanaryCost
{
    [JsonPropertyName("amount")]
    public decimal Amount { get; init; }

    [JsonPropertyName("currency")]
    public required string Currency { get; init; }

    [JsonPropertyName("billing_authoritative")]
    public bool BillingAuthoritative { get; init; }

    [JsonPropertyName("source")]
    public required string Source { get; init; }
}
