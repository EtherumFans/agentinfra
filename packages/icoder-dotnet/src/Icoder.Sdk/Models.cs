using System.Net;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Icoder.Sdk;

public sealed record A2AV1AgentInterface
{
    [JsonPropertyName("url")]
    public required string Url { get; init; }

    [JsonPropertyName("protocolBinding")]
    public required string ProtocolBinding { get; init; }

    [JsonPropertyName("protocolVersion")]
    public required string ProtocolVersion { get; init; }

    [JsonPropertyName("tenant")]
    public string? Tenant { get; init; }
}

public sealed record A2AV1AgentCardCapabilities
{
    [JsonPropertyName("streaming")]
    public bool Streaming { get; init; }

    [JsonPropertyName("pushNotifications")]
    public bool PushNotifications { get; init; }

    [JsonPropertyName("extendedAgentCard")]
    public bool ExtendedAgentCard { get; init; }
}

public sealed record A2AV1AgentSkill
{
    [JsonPropertyName("id")]
    public required string Id { get; init; }

    [JsonPropertyName("name")]
    public required string Name { get; init; }

    [JsonPropertyName("description")]
    public required string Description { get; init; }

    [JsonPropertyName("tags")]
    public IReadOnlyList<string> Tags { get; init; } = [];

    [JsonPropertyName("examples")]
    public IReadOnlyList<string> Examples { get; init; } = [];

    [JsonPropertyName("inputModes")]
    public IReadOnlyList<string> InputModes { get; init; } = [];

    [JsonPropertyName("outputModes")]
    public IReadOnlyList<string> OutputModes { get; init; } = [];
}

public sealed record A2AV1AgentCard
{
    [JsonPropertyName("name")]
    public required string Name { get; init; }

    [JsonPropertyName("description")]
    public required string Description { get; init; }

    [JsonPropertyName("supportedInterfaces")]
    public IReadOnlyList<A2AV1AgentInterface> SupportedInterfaces { get; init; } = [];

    [JsonPropertyName("version")]
    public required string Version { get; init; }

    [JsonPropertyName("documentationUrl")]
    public string? DocumentationUrl { get; init; }

    [JsonPropertyName("capabilities")]
    public required A2AV1AgentCardCapabilities Capabilities { get; init; }

    [JsonPropertyName("defaultInputModes")]
    public IReadOnlyList<string> DefaultInputModes { get; init; } = [];

    [JsonPropertyName("defaultOutputModes")]
    public IReadOnlyList<string> DefaultOutputModes { get; init; } = [];

    [JsonPropertyName("skills")]
    public IReadOnlyList<A2AV1AgentSkill> Skills { get; init; } = [];

    [JsonPropertyName("securitySchemes")]
    public IReadOnlyDictionary<string, JsonElement> SecuritySchemes { get; init; } =
        new Dictionary<string, JsonElement>();

    [JsonPropertyName("securityRequirements")]
    public IReadOnlyList<JsonElement> SecurityRequirements { get; init; } = [];
}

public sealed record A2ALegacyAgentCardCapabilities
{
    [JsonPropertyName("streaming")]
    public bool Streaming { get; init; }

    [JsonPropertyName("pushNotifications")]
    public bool PushNotifications { get; init; }

    [JsonPropertyName("stateTransitionHistory")]
    public bool StateTransitionHistory { get; init; }
}

public sealed record A2ALegacyAgentSkill
{
    [JsonPropertyName("id")]
    public required string Id { get; init; }

    [JsonPropertyName("name")]
    public required string Name { get; init; }

    [JsonPropertyName("description")]
    public required string Description { get; init; }

    [JsonPropertyName("inputSchema")]
    public IReadOnlyDictionary<string, JsonElement> InputSchema { get; init; }
        = new Dictionary<string, JsonElement>();

    [JsonPropertyName("outputSchema")]
    public IReadOnlyDictionary<string, JsonElement> OutputSchema { get; init; }
        = new Dictionary<string, JsonElement>();
}

/// <summary>A2A v0.3 discovery card returned by /api/icoder/agents/{id}/card.</summary>
public sealed record A2ALegacyAgentCard
{
    [JsonPropertyName("name")]
    public required string Name { get; init; }

    [JsonPropertyName("description")]
    public required string Description { get; init; }

    [JsonPropertyName("url")]
    public required string Url { get; init; }

    [JsonPropertyName("version")]
    public required string Version { get; init; }

    [JsonPropertyName("provider")]
    public required string Provider { get; init; }

    [JsonPropertyName("capabilities")]
    public required A2ALegacyAgentCardCapabilities Capabilities { get; init; }

    [JsonPropertyName("skills")]
    public IReadOnlyList<A2ALegacyAgentSkill> Skills { get; init; } = [];

    [JsonPropertyName("defaultInputModes")]
    public IReadOnlyList<string> DefaultInputModes { get; init; } = [];

    [JsonPropertyName("defaultOutputModes")]
    public IReadOnlyList<string> DefaultOutputModes { get; init; } = [];

    [JsonPropertyName("securitySchemes")]
    public IReadOnlyDictionary<string, JsonElement> SecuritySchemes { get; init; }
        = new Dictionary<string, JsonElement>();
}

public sealed record AgenticTraceDescriptor
{
    [JsonPropertyName("id")]
    public required string Id { get; init; }

    [JsonPropertyName("name")]
    public required string Name { get; init; }

    [JsonPropertyName("start_time")]
    public required DateTimeOffset StartTime { get; init; }

    [JsonPropertyName("thread_id")]
    public required string ThreadId { get; init; }
}

public sealed record AgenticTraceSpan
{
    [JsonPropertyName("name")]
    public required string Name { get; init; }

    [JsonPropertyName("span_id")]
    public required string SpanId { get; init; }

    [JsonPropertyName("parent_span_id")]
    public string? ParentSpanId { get; init; }

    [JsonPropertyName("start_time")]
    public required DateTimeOffset StartTime { get; init; }

    [JsonPropertyName("attributes")]
    public IReadOnlyDictionary<string, JsonElement> Attributes { get; init; } =
        new Dictionary<string, JsonElement>();
}

public sealed record AgenticTrace
{
    [JsonPropertyName("trace")]
    public required AgenticTraceDescriptor Trace { get; init; }

    [JsonPropertyName("spans")]
    public IReadOnlyList<AgenticTraceSpan> Spans { get; init; } = [];
}

public sealed record AgenticTracePage
{
    [JsonPropertyName("traces")]
    public IReadOnlyList<AgenticTrace> Traces { get; init; } = [];

    [JsonPropertyName("nextPageToken")]
    public string? NextPageToken { get; init; }

    [JsonPropertyName("totalSize")]
    public int? TotalSize { get; init; }
}

public sealed record AgenticContextSummary
{
    [JsonPropertyName("id")]
    public required string Id { get; init; }

    [JsonPropertyName("agentId")]
    public required string AgentId { get; init; }

    [JsonPropertyName("taskCount")]
    public int TaskCount { get; init; }

    [JsonPropertyName("createdAt")]
    public DateTimeOffset CreatedAt { get; init; }

    [JsonPropertyName("updatedAt")]
    public DateTimeOffset UpdatedAt { get; init; }

    [JsonPropertyName("expiresAt")]
    public DateTimeOffset? ExpiresAt { get; init; }
}

public sealed record AgenticContextResource
{
    [JsonPropertyName("id")]
    public required string Id { get; init; }

    [JsonPropertyName("agentId")]
    public required string AgentId { get; init; }

    [JsonPropertyName("taskCount")]
    public int TaskCount { get; init; }

    [JsonPropertyName("createdAt")]
    public DateTimeOffset CreatedAt { get; init; }

    [JsonPropertyName("updatedAt")]
    public DateTimeOffset UpdatedAt { get; init; }

    [JsonPropertyName("expiresAt")]
    public DateTimeOffset? ExpiresAt { get; init; }

    [JsonPropertyName("tasks")]
    public IReadOnlyList<A2AV1Task> Tasks { get; init; } = [];
}

public sealed record AgenticContextPage
{
    [JsonPropertyName("contexts")]
    public IReadOnlyList<AgenticContextSummary> Contexts { get; init; } = [];

    [JsonPropertyName("nextPageToken")]
    public string? NextPageToken { get; init; }

    [JsonPropertyName("totalSize")]
    public int TotalSize { get; init; }
}

public sealed record AgenticContextTaskPage
{
    [JsonPropertyName("tasks")]
    public IReadOnlyList<A2AV1Task> Tasks { get; init; } = [];

    [JsonPropertyName("nextPageToken")]
    public string? NextPageToken { get; init; }

    [JsonPropertyName("totalSize")]
    public int TotalSize { get; init; }
}

public sealed record AgenticArtifact
{
    [JsonPropertyName("artifactId")]
    public required string ArtifactId { get; init; }

    [JsonPropertyName("name")]
    public string? Name { get; init; }

    [JsonPropertyName("description")]
    public string? Description { get; init; }

    [JsonPropertyName("parts")]
    public IReadOnlyList<JsonElement> Parts { get; init; } = [];

    [JsonPropertyName("metadata")]
    public IReadOnlyDictionary<string, JsonElement> Metadata { get; init; }
        = new Dictionary<string, JsonElement>();

    [JsonPropertyName("extensions")]
    public IReadOnlyList<string> Extensions { get; init; } = [];
}

public sealed record AgenticArtifactObject
{
    [JsonPropertyName("objectId")]
    public required string ObjectId { get; init; }

    [JsonPropertyName("artifactId")]
    public required string ArtifactId { get; init; }

    [JsonPropertyName("filename")]
    public required string Filename { get; init; }

    [JsonPropertyName("mediaType")]
    public required string MediaType { get; init; }

    [JsonPropertyName("sizeBytes")]
    public int SizeBytes { get; init; }

    [JsonPropertyName("sha256")]
    public required string Sha256 { get; init; }

    [JsonPropertyName("status")]
    public string Status { get; init; } = "";

    [JsonPropertyName("malwareScanStatus")]
    public required string MalwareScanStatus { get; init; }

    [JsonPropertyName("dlpScanStatus")]
    public required string DlpScanStatus { get; init; }

    [JsonPropertyName("dataClassification")]
    public required string DataClassification { get; init; }

    [JsonPropertyName("rejectionCode")]
    public string? RejectionCode { get; init; }

    [JsonPropertyName("scanEngine")]
    public required string ScanEngine { get; init; }

    [JsonPropertyName("createdAt")]
    public DateTimeOffset CreatedAt { get; init; }

    [JsonPropertyName("scannedAt")]
    public DateTimeOffset? ScannedAt { get; init; }
}

public sealed record AgenticArtifactObjectPage
{
    [JsonPropertyName("objects")]
    public IReadOnlyList<AgenticArtifactObject> Objects { get; init; } = [];

    [JsonPropertyName("totalSize")]
    public int TotalSize { get; init; }
}

public sealed record AgenticArtifactDownloadPart
{
    [JsonPropertyName("url")]
    public required string Url { get; init; }

    [JsonPropertyName("filename")]
    public string? Filename { get; init; }

    [JsonPropertyName("mediaType")]
    public string? MediaType { get; init; }

    [JsonPropertyName("metadata")]
    public IReadOnlyDictionary<string, JsonElement> Metadata { get; init; }
        = new Dictionary<string, JsonElement>();
}

public sealed record AgenticArtifactDownloadAuthorization
{
    [JsonPropertyName("objectId")]
    public required string ObjectId { get; init; }

    [JsonPropertyName("expiresAt")]
    public DateTimeOffset ExpiresAt { get; init; }

    [JsonPropertyName("singleUse")]
    public bool SingleUse { get; init; }

    [JsonPropertyName("purposeOfUse")]
    public required string PurposeOfUse { get; init; }

    [JsonPropertyName("part")]
    public required AgenticArtifactDownloadPart Part { get; init; }
}

public sealed record AgenticUsageTotals
{
    [JsonPropertyName("invocations")]
    public int Invocations { get; init; }

    [JsonPropertyName("uniqueContexts")]
    public int UniqueContexts { get; init; }
}

public sealed record AgenticUsageBucket
{
    [JsonPropertyName("periodStart")]
    public DateTimeOffset PeriodStart { get; init; }

    [JsonPropertyName("periodEnd")]
    public DateTimeOffset PeriodEnd { get; init; }

    [JsonPropertyName("invocations")]
    public int Invocations { get; init; }

    [JsonPropertyName("uniqueContexts")]
    public int UniqueContexts { get; init; }
}

public sealed record AgenticAgentUsage
{
    [JsonPropertyName("granularity")]
    public required string Granularity { get; init; }

    [JsonPropertyName("from")]
    public DateTimeOffset From { get; init; }

    [JsonPropertyName("to")]
    public DateTimeOffset To { get; init; }

    [JsonPropertyName("totals")]
    public required AgenticUsageTotals Totals { get; init; }

    [JsonPropertyName("buckets")]
    public IReadOnlyList<AgenticUsageBucket> Buckets { get; init; } = [];
}

public sealed record AgenticBinaryRating
{
    [JsonPropertyName("scale")]
    public string Scale { get; init; } = "binary";

    [JsonPropertyName("value")]
    public required int Value { get; init; }
}

public sealed record AgenticFeedbackTarget
{
    [JsonPropertyName("messageId")]
    public required string MessageId { get; init; }
}

public sealed record AgenticFeedbackActorMetadata
{
    [JsonPropertyName("externalId")]
    public required string ExternalId { get; init; }
}

public sealed record AgenticFeedbackMetadata
{
    [JsonPropertyName("collectionMethod")]
    public string? CollectionMethod { get; init; }

    [JsonPropertyName("clientReference")]
    public string? ClientReference { get; init; }

    [JsonPropertyName("actor")]
    public AgenticFeedbackActorMetadata? Actor { get; init; }
}

public sealed record AgenticFeedbackInput
{
    [JsonPropertyName("rating")]
    public required AgenticBinaryRating Rating { get; init; }

    [JsonPropertyName("labels")]
    public IReadOnlyList<string> Labels { get; init; } = [];

    [JsonPropertyName("reason")]
    public string? Reason { get; init; }

    [JsonPropertyName("target")]
    public AgenticFeedbackTarget? Target { get; init; }

    [JsonPropertyName("metadata")]
    public AgenticFeedbackMetadata? Metadata { get; init; }
}

public sealed record AgenticFeedback
{
    [JsonPropertyName("id")]
    public required string Id { get; init; }

    [JsonPropertyName("taskId")]
    public required string TaskId { get; init; }

    [JsonPropertyName("rating")]
    public required AgenticBinaryRating Rating { get; init; }

    [JsonPropertyName("normalizedScore")]
    public double NormalizedScore { get; init; }

    [JsonPropertyName("labels")]
    public IReadOnlyList<string> Labels { get; init; } = [];

    [JsonPropertyName("reason")]
    public string? Reason { get; init; }

    [JsonPropertyName("createdAt")]
    public DateTimeOffset CreatedAt { get; init; }

    [JsonPropertyName("target")]
    public AgenticFeedbackTarget? Target { get; init; }
}

public sealed record AgenticFeedbackList
{
    [JsonPropertyName("feedbacks")]
    public IReadOnlyList<AgenticFeedback> Feedbacks { get; init; } = [];
}

public sealed record FeedbackTrainingAuthorizationInput
{
    [JsonPropertyName("purposeOfUse")]
    public string PurposeOfUse { get; init; } = "quality_improvement";

    [JsonPropertyName("dataScope")]
    public string DataScope { get; init; } = "feedback_metadata_only";

    [JsonPropertyName("expiresAt")]
    public required DateTimeOffset ExpiresAt { get; init; }

    [JsonPropertyName("approvalReference")]
    public required string ApprovalReference { get; init; }

    [JsonPropertyName("acknowledgement")]
    public bool Acknowledgement { get; init; } = true;
}

public sealed record FeedbackTrainingAuthorization
{
    [JsonPropertyName("id")]
    public required string Id { get; init; }

    [JsonPropertyName("feedbackId")]
    public required string FeedbackId { get; init; }

    [JsonPropertyName("taskId")]
    public required string TaskId { get; init; }

    [JsonPropertyName("trainingAuthorized")]
    public bool TrainingAuthorized { get; init; }

    [JsonPropertyName("authorizationStatus")]
    public required string AuthorizationStatus { get; init; }

    [JsonPropertyName("purposeOfUse")]
    public required string PurposeOfUse { get; init; }

    [JsonPropertyName("dataScope")]
    public required string DataScope { get; init; }

    [JsonPropertyName("expiresAt")]
    public DateTimeOffset ExpiresAt { get; init; }

    [JsonPropertyName("createdAt")]
    public DateTimeOffset CreatedAt { get; init; }

    [JsonPropertyName("updatedAt")]
    public DateTimeOffset UpdatedAt { get; init; }

    [JsonPropertyName("revokedAt")]
    public DateTimeOffset? RevokedAt { get; init; }

    [JsonPropertyName("version")]
    public int Version { get; init; }
}

public sealed record TokenResponse
{
    [JsonPropertyName("access_token")]
    public required string AccessToken { get; init; }

    [JsonPropertyName("refresh_token")]
    public string? RefreshToken { get; init; }

    [JsonPropertyName("token_type")]
    public string TokenType { get; init; } = "bearer";

    [JsonPropertyName("expires_in")]
    public int? ExpiresIn { get; init; }

    [JsonPropertyName("user")]
    public JsonElement? User { get; init; }
}

public sealed record ICoDerResponse<T>(T Value, HttpStatusCode StatusCode, Uri? Location)
{
    public IReadOnlyDictionary<string, IReadOnlyList<string>> Headers { get; init; }
        = new Dictionary<string, IReadOnlyList<string>>(StringComparer.OrdinalIgnoreCase);

    public string? GetHeader(string name)
        => Headers.TryGetValue(name, out var values) ? values.FirstOrDefault() : null;
}

public sealed record EnvironmentPlanRequest
{
    [JsonPropertyName("environment_code")]
    public required string EnvironmentCode { get; init; }

    [JsonPropertyName("region_code")]
    public required string RegionCode { get; init; }

    [JsonPropertyName("tenant_id")]
    public string? TenantId { get; init; }

    [JsonPropertyName("dry_run")]
    public bool DryRun { get; init; } = true;
}

public sealed record PlatformCatalog
{
    [JsonPropertyName("deployment_mode")]
    public string DeploymentMode { get; init; } = "local";

    [JsonPropertyName("environments")]
    public IReadOnlyList<JsonElement> Environments { get; init; } = [];
}

public sealed record RegionCatalog
{
    [JsonPropertyName("regions")]
    public IReadOnlyList<JsonElement> Regions { get; init; } = [];
}

public sealed record EnvironmentDeploymentPlan
{
    [JsonPropertyName("dry_run")]
    public bool DryRun { get; init; }

    [JsonPropertyName("provisioned")]
    public bool Provisioned { get; init; }

    [JsonPropertyName("external_approval_required")]
    public bool ExternalApprovalRequired { get; init; }
}

public sealed record TenantView
{
    [JsonPropertyName("id")]
    public required string Id { get; init; }

    [JsonPropertyName("country")]
    public string Country { get; init; } = "CN";

    [JsonPropertyName("environment_assignments")]
    public IReadOnlyList<string> EnvironmentAssignments { get; init; } = [];
}

public sealed record TenantEnvironmentAssignments
{
    [JsonPropertyName("tenant_id")]
    public required string TenantId { get; init; }

    [JsonPropertyName("environment_assignments")]
    public IReadOnlyList<string> EnvironmentAssignments { get; init; } = [];

    [JsonPropertyName("environment_provisioned")]
    public bool EnvironmentProvisioned { get; init; }
}

public sealed record AgentRunInput
{
    [JsonPropertyName("text")]
    public required string Text { get; init; }

    [JsonPropertyName("extra")]
    public IReadOnlyDictionary<string, object?> Extra { get; init; }
        = new Dictionary<string, object?>();

    [JsonPropertyName("documents")]
    public IReadOnlyList<AgentRunSourceDocument> Documents { get; init; } = [];

    [JsonPropertyName("upstream_results")]
    public IReadOnlyList<AgentRunUpstreamResult> UpstreamResults { get; init; } = [];
}

public sealed record AgentRunSourceDocument
{
    [JsonPropertyName("document_id")]
    public required string DocumentId { get; init; }

    [JsonPropertyName("text")]
    public required string Text { get; init; }

    [JsonPropertyName("document_version")]
    public string DocumentVersion { get; init; } = "";

    [JsonPropertyName("document_type")]
    public string DocumentType { get; init; } = "";

    [JsonPropertyName("normalization")]
    public string Normalization { get; init; } = "NFC";
}

public sealed record AgentRunUpstreamResult
{
    [JsonPropertyName("agent_id")]
    public required string AgentId { get; init; }

    [JsonPropertyName("result")]
    public IReadOnlyDictionary<string, object?> Result { get; init; }
        = new Dictionary<string, object?>();

    [JsonPropertyName("run_id")]
    public required string RunId { get; init; }

    [JsonPropertyName("schema_ref")]
    public required string SchemaRef { get; init; }

    [JsonPropertyName("attestation")]
    public required string Attestation { get; init; }
}

public sealed record AgentRunRequest
{
    [JsonPropertyName("input")]
    public required AgentRunInput Input { get; init; }

    [JsonPropertyName("runtime_mode")]
    public string? RuntimeMode { get; init; }

    [JsonPropertyName("purpose_of_use")]
    public string? PurposeOfUse { get; init; }

    [JsonPropertyName("include_trace")]
    public bool IncludeTrace { get; init; } = true;

    [JsonPropertyName("include_evidence")]
    public bool IncludeEvidence { get; init; } = true;
}

public sealed record AgentRunResponse
{
    [JsonPropertyName("agent_id")]
    public required string AgentId { get; init; }

    [JsonPropertyName("run_id")]
    public required string RunId { get; init; }

    [JsonPropertyName("trace_id")]
    public string TraceId { get; init; } = "";

    [JsonPropertyName("trace_url")]
    public string TraceUrl { get; init; } = "";

    [JsonPropertyName("runtime_mode")]
    public string RuntimeMode { get; init; } = "";

    [JsonPropertyName("latency_ms")]
    public int LatencyMs { get; init; }

    [JsonPropertyName("cost")]
    public JsonElement Cost { get; init; }

    [JsonPropertyName("billing")]
    public AgentRunBilling? Billing { get; init; }

    [JsonPropertyName("summary")]
    public string Summary { get; init; } = "";

    [JsonPropertyName("result")]
    public JsonElement Result { get; init; }

    [JsonPropertyName("schema_ref")]
    public string SchemaRef { get; init; } = "";

    [JsonPropertyName("result_attestation")]
    public string ResultAttestation { get; init; } = "";

    [JsonPropertyName("evidence")]
    public IReadOnlyList<JsonElement> Evidence { get; init; } = [];

    [JsonPropertyName("warnings")]
    public IReadOnlyList<string> Warnings { get; init; } = [];

    [JsonPropertyName("manual_review_required")]
    public bool ManualReviewRequired { get; init; }

    [JsonPropertyName("trace_events")]
    public IReadOnlyList<JsonElement> TraceEvents { get; init; } = [];

    [JsonPropertyName("error")]
    public bool Error { get; init; }

    [JsonPropertyName("error_reason")]
    public string ErrorReason { get; init; } = "";
}

public sealed record AgentRunBilling
{
    [JsonPropertyName("simulation")]
    public bool Simulation { get; init; }

    [JsonPropertyName("status")]
    public string Status { get; init; } = "";

    [JsonPropertyName("reserved_amount")]
    public decimal ReservedAmount { get; init; }

    [JsonPropertyName("settled_amount")]
    public decimal SettledAmount { get; init; }

    [JsonPropertyName("balance_after")]
    public decimal BalanceAfter { get; init; }

    [JsonPropertyName("currency")]
    public string Currency { get; init; } = "CNY";

    [JsonPropertyName("error_code")]
    public string? ErrorCode { get; init; }
}

public sealed record RunStatusResponse
{
    [JsonPropertyName("run_id")]
    public required string RunId { get; init; }

    [JsonPropertyName("status")]
    public required string Status { get; init; }

    [JsonPropertyName("terminal")]
    public bool Terminal { get; init; }

    [JsonPropertyName("agent_id")]
    public string AgentId { get; init; } = "";

    [JsonPropertyName("trace_id")]
    public string TraceId { get; init; } = "";

    [JsonPropertyName("runtime_mode")]
    public string RuntimeMode { get; init; } = "";

    [JsonPropertyName("latency_ms")]
    public int LatencyMs { get; init; }

    [JsonPropertyName("cost_amount")]
    public decimal CostAmount { get; init; }

    [JsonPropertyName("cost_currency")]
    public string CostCurrency { get; init; } = "CNY";

    [JsonPropertyName("error")]
    public bool Error { get; init; }

    [JsonPropertyName("error_reason")]
    public string? ErrorReason { get; init; }

    [JsonPropertyName("cancel_reason")]
    public string? CancelReason { get; init; }

    [JsonPropertyName("cancelled_at")]
    public string? CancelledAt { get; init; }

    [JsonPropertyName("cancelled_by_user_id")]
    public string? CancelledByUserId { get; init; }

    [JsonPropertyName("created_at")]
    public string? CreatedAt { get; init; }

    [JsonPropertyName("trace_retention_days")]
    public int TraceRetentionDays { get; init; }

    [JsonPropertyName("trace_events_purged_at")]
    public string? TraceEventsPurgedAt { get; init; }

    [JsonPropertyName("trace_events_purged_count")]
    public int TraceEventsPurgedCount { get; init; }
}

public sealed record RunCancelResponse
{
    [JsonPropertyName("run_id")]
    public required string RunId { get; init; }

    [JsonPropertyName("outcome")]
    public required string Outcome { get; init; }

    [JsonPropertyName("status")]
    public required string Status { get; init; }

    [JsonPropertyName("message")]
    public string Message { get; init; } = "";

    [JsonPropertyName("cancel_reason")]
    public string? CancelReason { get; init; }

    [JsonPropertyName("cancelled_at")]
    public string? CancelledAt { get; init; }
}

public sealed record RunTraceTokenRenewResponse
{
    [JsonPropertyName("run_id")]
    public required string RunId { get; init; }

    [JsonPropertyName("trace_token")]
    public required string TraceToken { get; init; }

    [JsonPropertyName("expires_at")]
    public long ExpiresAt { get; init; }

    [JsonPropertyName("events_url")]
    public required string EventsUrl { get; init; }

    [JsonPropertyName("trace_url")]
    public required string TraceUrl { get; init; }

    [JsonPropertyName("trace_retention_days")]
    public int TraceRetentionDays { get; init; }
}

public sealed record RunStreamRetryOptions
{
    /// <summary>Total connection attempts, including the first.</summary>
    public int MaxAttempts { get; init; } = 4;

    public TimeSpan InitialDelay { get; init; } = TimeSpan.FromMilliseconds(250);

    public TimeSpan MaxDelay { get; init; } = TimeSpan.FromSeconds(4);

    /// <summary>Symmetric delay jitter in the inclusive range 0..1.</summary>
    public double JitterRatio { get; init; } = 0.2;

    public string? LastEventId { get; init; }
}

public sealed record RunStreamEvent
{
    public string Event { get; init; } = "message";
    public string Data { get; init; } = "";
    public string? Id { get; init; }
}

public sealed record AgentCloneRequest
{
    [JsonPropertyName("name")]
    public string? Name { get; init; }

    [JsonPropertyName("description")]
    public string? Description { get; init; }

    [JsonPropertyName("project_id")]
    public string? ProjectId { get; init; }

    [JsonPropertyName("open_after_clone")]
    public bool OpenAfterClone { get; init; } = true;
}

public sealed record AgentCloneResponse
{
    [JsonPropertyName("project_agent_id")]
    public required string ProjectAgentId { get; init; }

    [JsonPropertyName("runtime_agent_id")]
    public required string RuntimeAgentId { get; init; }

    [JsonPropertyName("source_runtime_agent_id")]
    public required string SourceRuntimeAgentId { get; init; }

    [JsonPropertyName("source_agent_ref")]
    public required string SourceAgentRef { get; init; }

    [JsonPropertyName("chat_url")]
    public required string ChatUrl { get; init; }

    [JsonPropertyName("customize_url")]
    public required string CustomizeUrl { get; init; }

    [JsonPropertyName("run_url")]
    public required string RunUrl { get; init; }

    [JsonPropertyName("cloned")]
    public bool Cloned { get; init; }
}

public sealed record AgentHubResponse
{
    [JsonPropertyName("agents")]
    public IReadOnlyList<AgentHubCard> Agents { get; init; } = [];

    [JsonPropertyName("total")]
    public int Total { get; init; }

    [JsonPropertyName("source")]
    public string Source { get; init; } = "";

    [JsonPropertyName("schema_version")]
    public string SchemaVersion { get; init; } = "";
}

public sealed record AgentHubTenantReadinessResponse
{
    [JsonPropertyName("agents")]
    public IReadOnlyList<AgentHubTenantReadinessItem> Agents { get; init; } = [];

    [JsonPropertyName("total")]
    public int Total { get; init; }

    [JsonPropertyName("generated_at")]
    public required string GeneratedAt { get; init; }

    [JsonPropertyName("schema_version")]
    public required string SchemaVersion { get; init; }
}

public sealed record AgentHubTenantReadinessItem
{
    [JsonPropertyName("agent_id")]
    public required string AgentId { get; init; }

    [JsonPropertyName("execution_target")]
    public required string ExecutionTarget { get; init; }

    [JsonPropertyName("runtime_readiness")]
    public required AgentHubTenantRuntimeReadiness RuntimeReadiness { get; init; }

    [JsonPropertyName("evidence")]
    public required AgentHubTenantReadinessEvidence Evidence { get; init; }
}

public sealed record AgentHubTenantRuntimeReadiness
{
    [JsonPropertyName("structural_status")]
    public required string StructuralStatus { get; init; }

    [JsonPropertyName("configuration_status")]
    public required string ConfigurationStatus { get; init; }

    [JsonPropertyName("run_action_enabled")]
    public bool RunActionEnabled { get; init; }

    [JsonPropertyName("reason")]
    public required string Reason { get; init; }

    [JsonPropertyName("runtime_dependencies")]
    public IReadOnlyList<string> RuntimeDependencies { get; init; } = [];

    [JsonPropertyName("llm_required")]
    public bool LlmRequired { get; init; }

    [JsonPropertyName("live_health_verified")]
    public bool LiveHealthVerified { get; init; }

    [JsonPropertyName("connectivity_status")]
    public required string ConnectivityStatus { get; init; }

    [JsonPropertyName("semantic_validation_status")]
    public required string SemanticValidationStatus { get; init; }

    [JsonPropertyName("production_approval_status")]
    public required string ProductionApprovalStatus { get; init; }
}

public sealed record AgentHubTenantReadinessEvidence
{
    [JsonPropertyName("scope")]
    public required string Scope { get; init; }

    [JsonPropertyName("selection_mode")]
    public required string SelectionMode { get; init; }

    [JsonPropertyName("selection_version")]
    public int SelectionVersion { get; init; }

    [JsonPropertyName("deployment_id")]
    public string? DeploymentId { get; init; }

    [JsonPropertyName("provider_id")]
    public string? ProviderId { get; init; }

    [JsonPropertyName("configuration_probe_status")]
    public required string ConfigurationProbeStatus { get; init; }

    [JsonPropertyName("canary_checked_at")]
    public string? CanaryCheckedAt { get; init; }

    [JsonPropertyName("canary_expires_at")]
    public string? CanaryExpiresAt { get; init; }
}

public sealed record AgentHubCard
{
    [JsonPropertyName("agent_id")]
    public required string AgentId { get; init; }

    [JsonPropertyName("agent_ref")]
    public required string AgentRef { get; init; }

    [JsonPropertyName("name")]
    public required string Name { get; init; }

    [JsonPropertyName("description")]
    public string Description { get; init; } = "";

    [JsonPropertyName("category")]
    public string Category { get; init; } = "";

    [JsonPropertyName("use_case")]
    public string UseCase { get; init; } = "";

    [JsonPropertyName("runnable")]
    public bool Runnable { get; init; }

    [JsonPropertyName("launch_candidate_ready")]
    public bool LaunchCandidateReady { get; init; }

    [JsonPropertyName("production_ready")]
    public bool ProductionReady { get; init; }

    [JsonPropertyName("manual_review_required")]
    public bool ManualReviewRequired { get; init; }

    [JsonPropertyName("human_review")]
    public string HumanReview { get; init; } = "";

    [JsonPropertyName("execution_path")]
    public string ExecutionPath { get; init; } = "";

    [JsonPropertyName("execution_target")]
    public string ExecutionTarget { get; init; } = "";

    [JsonPropertyName("runtime_readiness")]
    public AgentHubRuntimeReadiness? RuntimeReadiness { get; init; }

    [JsonPropertyName("output_contract")]
    public AgentHubOutputContract OutputContract { get; init; } = new();

    [JsonExtensionData]
    public IDictionary<string, JsonElement>? AdditionalProperties { get; init; }
}

public sealed record AgentHubRuntimeReadiness
{
    [JsonPropertyName("structural_status")]
    public required string StructuralStatus { get; init; }

    [JsonPropertyName("configuration_status")]
    public required string ConfigurationStatus { get; init; }

    [JsonPropertyName("run_action_enabled")]
    public bool RunActionEnabled { get; init; }

    [JsonPropertyName("reason")]
    public required string Reason { get; init; }

    [JsonPropertyName("runtime_dependencies")]
    public IReadOnlyList<string> RuntimeDependencies { get; init; } = [];

    [JsonPropertyName("external_llm_required")]
    public bool ExternalLlmRequired { get; init; }

    [JsonPropertyName("live_health_verified")]
    public bool LiveHealthVerified { get; init; }

    [JsonPropertyName("semantic_validation_status")]
    public required string SemanticValidationStatus { get; init; }

    [JsonPropertyName("production_approval_status")]
    public required string ProductionApprovalStatus { get; init; }
}

public sealed record AgentHubOutputContract
{
    [JsonPropertyName("schema_ref")]
    public string? SchemaRef { get; init; }

    [JsonPropertyName("required_fields")]
    public IReadOnlyList<string> RequiredFields { get; init; } = [];

    [JsonPropertyName("optional_fields")]
    public IReadOnlyList<string> OptionalFields { get; init; } = [];

    [JsonPropertyName("field_types")]
    public IReadOnlyDictionary<string, string> FieldTypes { get; init; }
        = new Dictionary<string, string>();

    [JsonPropertyName("field_schemas")]
    public IReadOnlyDictionary<string, AgentOutputFieldSchema> FieldSchemas { get; init; }
        = new Dictionary<string, AgentOutputFieldSchema>();

    [JsonPropertyName("field_relations")]
    public IReadOnlyList<AgentOutputFieldRelation> FieldRelations { get; init; } = [];

    [JsonPropertyName("evidence_bindings")]
    public IReadOnlyList<AgentOutputEvidenceBinding> EvidenceBindings { get; init; } = [];

    [JsonPropertyName("cross_agent_relations")]
    public IReadOnlyList<AgentOutputCrossAgentRelation> CrossAgentRelations { get; init; } = [];
}

public sealed record AgentOutputFieldRelation
{
    [JsonPropertyName("id")]
    public string Id { get; init; } = "";

    [JsonPropertyName("for_each")]
    public string? ForEach { get; init; }

    [JsonPropertyName("when")]
    public IReadOnlyList<AgentOutputFieldPredicate> When { get; init; } = [];

    [JsonPropertyName("must")]
    public IReadOnlyList<AgentOutputFieldPredicate> Must { get; init; } = [];
}

public sealed record AgentOutputFieldPredicate
{
    [JsonPropertyName("path")]
    public string Path { get; init; } = "";

    [JsonPropertyName("operator")]
    public string Operator { get; init; } = "";

    [JsonPropertyName("value")]
    public JsonElement? Value { get; init; }

    [JsonPropertyName("other_path")]
    public string? OtherPath { get; init; }

    [JsonPropertyName("where")]
    public IReadOnlyList<AgentOutputFieldPredicate>? Where { get; init; }

    [JsonPropertyName("item_path")]
    public string? ItemPath { get; init; }

    [JsonPropertyName("other_item_path")]
    public string? OtherItemPath { get; init; }
}

public sealed record AgentOutputEvidenceBinding
{
    [JsonPropertyName("id")]
    public string Id { get; init; } = "";

    [JsonPropertyName("for_each")]
    public string ForEach { get; init; } = "";

    [JsonPropertyName("text_path")]
    public string TextPath { get; init; } = "";

    [JsonPropertyName("span_path")]
    public string? SpanPath { get; init; }

    [JsonPropertyName("start_path")]
    public string? StartPath { get; init; }

    [JsonPropertyName("end_path")]
    public string? EndPath { get; init; }

    [JsonPropertyName("document_id_path")]
    public string? DocumentIdPath { get; init; }

    [JsonPropertyName("document_version_path")]
    public string? DocumentVersionPath { get; init; }
}

public sealed record AgentOutputCrossAgentRelation
{
    [JsonPropertyName("id")]
    public string Id { get; init; } = "";

    [JsonPropertyName("local_path")]
    public string LocalPath { get; init; } = "";

    [JsonPropertyName("local_item_path")]
    public string? LocalItemPath { get; init; }

    [JsonPropertyName("upstream_agent_id")]
    public string UpstreamAgentId { get; init; } = "";

    [JsonPropertyName("upstream_path")]
    public string UpstreamPath { get; init; } = "";

    [JsonPropertyName("upstream_item_path")]
    public string UpstreamItemPath { get; init; } = "";

    [JsonPropertyName("operator")]
    public string Operator { get; init; } = "";

    [JsonPropertyName("normalization")]
    public string Normalization { get; init; } = "none";

    [JsonPropertyName("required")]
    public bool Required { get; init; }
}

public sealed record AgentOutputFieldSchema
{
    [JsonPropertyName("type")]
    public string Type { get; init; } = "";

    [JsonPropertyName("properties")]
    public IReadOnlyDictionary<string, AgentOutputFieldSchema>? Properties { get; init; }

    [JsonPropertyName("required")]
    public IReadOnlyList<string>? Required { get; init; }

    [JsonPropertyName("additionalProperties")]
    public JsonElement? AdditionalProperties { get; init; }

    [JsonPropertyName("items")]
    public AgentOutputFieldSchema? Items { get; init; }

    [JsonPropertyName("enum")]
    public IReadOnlyList<JsonElement>? Enum { get; init; }

    [JsonPropertyName("const")]
    public JsonElement? Const { get; init; }

    [JsonPropertyName("minimum")]
    public double? Minimum { get; init; }

    [JsonPropertyName("maximum")]
    public double? Maximum { get; init; }

    [JsonPropertyName("minLength")]
    public int? MinLength { get; init; }

    [JsonPropertyName("maxLength")]
    public int? MaxLength { get; init; }

    [JsonPropertyName("pattern")]
    public string? Pattern { get; init; }

    [JsonPropertyName("minItems")]
    public int? MinItems { get; init; }

    [JsonPropertyName("maxItems")]
    public int? MaxItems { get; init; }

    [JsonPropertyName("uniqueItems")]
    public bool? UniqueItems { get; init; }

    [JsonPropertyName("x-order")]
    public string? XOrder { get; init; }
}

public sealed record A2APart
{
    [JsonPropertyName("kind")]
    public required string Kind { get; init; }

    [JsonPropertyName("text")]
    public string? Text { get; init; }

    [JsonPropertyName("data")]
    public object? Data { get; init; }
}

public sealed record A2AMessageRequest
{
    [JsonPropertyName("role")]
    public string Role { get; init; } = "user";

    [JsonPropertyName("parts")]
    public required IReadOnlyList<A2APart> Parts { get; init; }

    [JsonPropertyName("messageId")]
    public string MessageId { get; init; } = $"msg-{Guid.NewGuid()}";

    [JsonPropertyName("contextId")]
    public string? ContextId { get; init; }

    [JsonPropertyName("metadata")]
    public IReadOnlyDictionary<string, object?>? Metadata { get; init; }
}

public sealed record A2AMessage
{
    [JsonPropertyName("kind")]
    public required string Kind { get; init; }

    [JsonPropertyName("role")]
    public required string Role { get; init; }

    [JsonPropertyName("messageId")]
    public required string MessageId { get; init; }

    [JsonPropertyName("contextId")]
    public required string ContextId { get; init; }

    [JsonPropertyName("parts")]
    public IReadOnlyList<JsonElement> Parts { get; init; } = [];

    [JsonPropertyName("metadata")]
    public IReadOnlyDictionary<string, JsonElement> Metadata { get; init; }
        = new Dictionary<string, JsonElement>();
}

public sealed record A2AContextResponse
{
    [JsonPropertyName("id")]
    public required string Id { get; init; }

    [JsonPropertyName("items")]
    public IReadOnlyList<JsonElement> Items { get; init; } = [];
}

public sealed record A2AContextDeleted
{
    [JsonPropertyName("kind")]
    public required string Kind { get; init; }

    [JsonPropertyName("contextId")]
    public required string ContextId { get; init; }

    [JsonPropertyName("deleted")]
    public bool Deleted { get; init; }

    [JsonPropertyName("reason")]
    public string Reason { get; init; } = "";
}

public sealed record A2AStreamEvent
{
    public string Event { get; init; } = "message";
    public string Data { get; init; } = "";
    public string? Id { get; init; }
}

public sealed record A2AV1Part
{
    [JsonPropertyName("text")]
    public string? Text { get; init; }

    [JsonPropertyName("data")]
    public JsonElement? Data { get; init; }

    [JsonPropertyName("raw")]
    public string? Raw { get; init; }

    [JsonPropertyName("url")]
    public string? Url { get; init; }

    [JsonPropertyName("filename")]
    public string? Filename { get; init; }

    [JsonPropertyName("mediaType")]
    public string? MediaType { get; init; }

    [JsonPropertyName("metadata")]
    public IReadOnlyDictionary<string, object?>? Metadata { get; init; }
}

public sealed record A2AV1MessageRequest
{
    [JsonPropertyName("role")]
    public string Role { get; init; } = "ROLE_USER";

    [JsonPropertyName("parts")]
    public required IReadOnlyList<A2AV1Part> Parts { get; init; }

    [JsonPropertyName("messageId")]
    public string MessageId { get; init; } = $"msg-{Guid.NewGuid()}";

    [JsonPropertyName("contextId")]
    public string? ContextId { get; init; }

    [JsonPropertyName("taskId")]
    public string? TaskId { get; init; }

    [JsonPropertyName("metadata")]
    public IReadOnlyDictionary<string, object?>? Metadata { get; init; }
}

public sealed record A2AV1Message
{
    [JsonPropertyName("role")]
    public required string Role { get; init; }

    [JsonPropertyName("messageId")]
    public required string MessageId { get; init; }

    [JsonPropertyName("contextId")]
    public required string ContextId { get; init; }

    [JsonPropertyName("taskId")]
    public string? TaskId { get; init; }

    [JsonPropertyName("parts")]
    public IReadOnlyList<JsonElement> Parts { get; init; } = [];

    [JsonPropertyName("metadata")]
    public IReadOnlyDictionary<string, JsonElement> Metadata { get; init; }
        = new Dictionary<string, JsonElement>();
}

public sealed record A2AV1TaskStatus
{
    [JsonPropertyName("state")]
    public required string State { get; init; }

    [JsonPropertyName("timestamp")]
    public string? Timestamp { get; init; }

    [JsonPropertyName("message")]
    public A2AV1Message? Message { get; init; }
}

public sealed record A2AV1Artifact
{
    [JsonPropertyName("artifactId")]
    public required string ArtifactId { get; init; }

    [JsonPropertyName("name")]
    public string? Name { get; init; }

    [JsonPropertyName("description")]
    public string? Description { get; init; }

    [JsonPropertyName("parts")]
    public IReadOnlyList<A2AV1Part> Parts { get; init; } = [];

    [JsonPropertyName("metadata")]
    public IReadOnlyDictionary<string, JsonElement> Metadata { get; init; }
        = new Dictionary<string, JsonElement>();

    [JsonPropertyName("extensions")]
    public IReadOnlyList<string> Extensions { get; init; } = [];
}

public sealed record A2AV1TaskStatusUpdateEvent
{
    [JsonPropertyName("taskId")]
    public required string TaskId { get; init; }

    [JsonPropertyName("contextId")]
    public required string ContextId { get; init; }

    [JsonPropertyName("status")]
    public required A2AV1TaskStatus Status { get; init; }

    [JsonPropertyName("metadata")]
    public IReadOnlyDictionary<string, JsonElement> Metadata { get; init; }
        = new Dictionary<string, JsonElement>();
}

public sealed record A2AV1TaskArtifactUpdateEvent
{
    [JsonPropertyName("taskId")]
    public required string TaskId { get; init; }

    [JsonPropertyName("contextId")]
    public required string ContextId { get; init; }

    [JsonPropertyName("artifact")]
    public required A2AV1Artifact Artifact { get; init; }

    [JsonPropertyName("append")]
    public bool Append { get; init; }

    [JsonPropertyName("lastChunk")]
    public bool LastChunk { get; init; }

    [JsonPropertyName("metadata")]
    public IReadOnlyDictionary<string, JsonElement> Metadata { get; init; }
        = new Dictionary<string, JsonElement>();
}

public sealed record A2AV1StreamResponse
{
    [JsonPropertyName("task")]
    public A2AV1Task? Task { get; init; }

    [JsonPropertyName("message")]
    public A2AV1Message? Message { get; init; }

    [JsonPropertyName("statusUpdate")]
    public A2AV1TaskStatusUpdateEvent? StatusUpdate { get; init; }

    [JsonPropertyName("artifactUpdate")]
    public A2AV1TaskArtifactUpdateEvent? ArtifactUpdate { get; init; }
}

public sealed record A2AV1Task
{
    [JsonPropertyName("id")]
    public required string Id { get; init; }

    [JsonPropertyName("contextId")]
    public required string ContextId { get; init; }

    [JsonPropertyName("status")]
    public required A2AV1TaskStatus Status { get; init; }

    [JsonPropertyName("artifacts")]
    public IReadOnlyList<A2AV1Artifact> Artifacts { get; init; } = [];

    [JsonPropertyName("history")]
    public IReadOnlyList<A2AV1Message> History { get; init; } = [];

    [JsonPropertyName("metadata")]
    public IReadOnlyDictionary<string, JsonElement> Metadata { get; init; }
        = new Dictionary<string, JsonElement>();
}

public sealed record A2AV1SendResponse
{
    [JsonPropertyName("message")]
    public A2AV1Message? Message { get; init; }

    [JsonPropertyName("task")]
    public A2AV1Task? Task { get; init; }
}

public sealed record A2AV1TaskList
{
    [JsonPropertyName("tasks")]
    public IReadOnlyList<A2AV1Task> Tasks { get; init; } = [];

    [JsonPropertyName("nextPageToken")]
    public string NextPageToken { get; init; } = "";

    [JsonPropertyName("pageSize")]
    public int PageSize { get; init; }

    [JsonPropertyName("totalSize")]
    public int TotalSize { get; init; }
}

internal sealed record A2AJsonRpcEnvelope<T>
{
    [JsonPropertyName("result")]
    public T? Result { get; init; }

    [JsonPropertyName("error")]
    public A2AJsonRpcError? Error { get; init; }
}

internal sealed record A2AJsonRpcError
{
    [JsonPropertyName("code")]
    public int Code { get; init; }

    [JsonPropertyName("data")]
    public A2AJsonRpcErrorData? Data { get; init; }
}

internal sealed record A2AJsonRpcErrorData
{
    [JsonPropertyName("a2a_error_code")]
    public string? A2AErrorCode { get; init; }
}

public sealed record CodingPredictRequest
{
    [JsonPropertyName("text")]
    public required string Text { get; init; }

    [JsonPropertyName("mode")]
    public string Mode { get; init; } = "corti_like_fast";

    [JsonPropertyName("coding_system")]
    public string? CodingSystem { get; init; }

    [JsonPropertyName("coding_systems")]
    public IReadOnlyList<string>? CodingSystems { get; init; }

    [JsonPropertyName("include_evidence")]
    public bool IncludeEvidence { get; init; } = true;

    [JsonPropertyName("include_trace")]
    public bool IncludeTrace { get; init; } = true;

    [JsonPropertyName("filter")]
    public CodingCodeFilter? Filter { get; init; }
}

public sealed record CodingCodeFilter
{
    [JsonPropertyName("include")]
    public IReadOnlyList<string> Include { get; init; } = [];

    [JsonPropertyName("exclude")]
    public IReadOnlyList<string> Exclude { get; init; } = [];

    [JsonPropertyName("expand")]
    public bool Expand { get; init; } = true;
}

public sealed record CodingPredictResponse
{
    [JsonPropertyName("codes")]
    public IReadOnlyList<JsonElement> Codes { get; init; } = [];

    [JsonPropertyName("summary")]
    public string Summary { get; init; } = "";

    [JsonPropertyName("runtime_mode")]
    public string RuntimeMode { get; init; } = "";

    [JsonPropertyName("latency_ms")]
    public int LatencyMs { get; init; }

    [JsonPropertyName("trace_id")]
    public string TraceId { get; init; } = "";

    [JsonPropertyName("run_id")]
    public string RunId { get; init; } = "";

    [JsonPropertyName("cost")]
    public JsonElement Cost { get; init; }

    [JsonPropertyName("error")]
    public bool Error { get; init; }

    [JsonPropertyName("error_reason")]
    public string ErrorReason { get; init; } = "";

    [JsonPropertyName("filter_applied")]
    public CodingCodeFilter? FilterApplied { get; init; }

    [JsonPropertyName("coding_systems_applied")]
    public IReadOnlyList<string> CodingSystemsApplied { get; init; } = [];
}

public sealed record CodingPricingEstimateResponse
{
    [JsonPropertyName("input_chars")]
    public int InputChars { get; init; }

    [JsonPropertyName("runtime_mode")]
    public string RuntimeMode { get; init; } = "corti_like_fast";

    [JsonPropertyName("currency")]
    public string Currency { get; init; } = "CNY";

    [JsonPropertyName("estimated_cost_min")]
    public double EstimatedCostMin { get; init; }

    [JsonPropertyName("estimated_cost_max")]
    public double EstimatedCostMax { get; init; }

    [JsonPropertyName("estimated_model_calls_min")]
    public int EstimatedModelCallsMin { get; init; }

    [JsonPropertyName("estimated_model_calls_max")]
    public int EstimatedModelCallsMax { get; init; }

    [JsonPropertyName("price_source")]
    public string PriceSource { get; init; } = "server_configuration";

    [JsonPropertyName("billing_authoritative")]
    public bool BillingAuthoritative { get; init; }

    [JsonPropertyName("disclaimer")]
    public string Disclaimer { get; init; } = "";

    [JsonExtensionData]
    public IDictionary<string, JsonElement>? AdditionalProperties { get; init; }
}

public sealed record RecordingCreatedResponse
{
    [JsonPropertyName("recordingId")]
    public required string RecordingId { get; init; }
}

public sealed record RecordingsListResponse
{
    [JsonPropertyName("recordings")]
    public IReadOnlyList<string> Recordings { get; init; } = [];
}

public sealed record TranscriptParticipant
{
    [JsonPropertyName("channel")]
    public required int Channel { get; init; }

    [JsonPropertyName("role")]
    public required string Role { get; init; }
}

public sealed record TranscriptReplacement
{
    [JsonPropertyName("find")]
    public required string Find { get; init; }

    [JsonPropertyName("replace")]
    public required string Replace { get; init; }
}

public sealed record TranscriptKeyterm
{
    [JsonPropertyName("term")]
    public required string Term { get; init; }
}

public sealed record TranscriptKeyterms
{
    [JsonPropertyName("terms")]
    public IReadOnlyList<TranscriptKeyterm> Terms { get; init; } = [];
}

public sealed record TranscriptCreateRequest
{
    [JsonPropertyName("recordingId")]
    public required string RecordingId { get; init; }

    [JsonPropertyName("primaryLanguage")]
    public string PrimaryLanguage { get; init; } = "zh-CN";

    [JsonPropertyName("spokenPunctuation")]
    public bool? SpokenPunctuation { get; init; }

    [JsonPropertyName("automaticPunctuation")]
    public bool? AutomaticPunctuation { get; init; } = true;

    [JsonPropertyName("isDictation")]
    public bool? IsDictation { get; init; }

    [JsonPropertyName("isMultichannel")]
    public bool? IsMultichannel { get; init; }

    [JsonPropertyName("diarize")]
    public bool? Diarize { get; init; }

    [JsonPropertyName("participants")]
    public IReadOnlyList<TranscriptParticipant>? Participants { get; init; }

    [JsonPropertyName("async")]
    public bool? Async { get; init; }

    [JsonPropertyName("replacements")]
    public IReadOnlyList<TranscriptReplacement>? Replacements { get; init; }

    [JsonPropertyName("keyterms")]
    public TranscriptKeyterms? Keyterms { get; init; }
}

public sealed record TranscriptResponse
{
    [JsonPropertyName("id")]
    public required string Id { get; init; }

    [JsonPropertyName("recordingId")]
    public string? RecordingId { get; init; }

    [JsonPropertyName("status")]
    public string? Status { get; init; }

    [JsonPropertyName("metadata")]
    public JsonElement? Metadata { get; init; }

    [JsonPropertyName("transcripts")]
    public IReadOnlyList<JsonElement>? Transcripts { get; init; }

    [JsonPropertyName("usageInfo")]
    public JsonElement? UsageInfo { get; init; }
}

public sealed record TranscriptsListResponse
{
    [JsonPropertyName("transcripts")]
    public IReadOnlyList<JsonElement>? Transcripts { get; init; }
}

public sealed record TranscriptStatusResponse
{
    [JsonPropertyName("status")]
    public required string Status { get; init; }
}

public sealed record FactsEnvelope
{
    [JsonPropertyName("facts")]
    public IReadOnlyList<FactRecord> Facts { get; init; } = [];
}

public sealed record FactExtractionRequest
{
    [JsonPropertyName("context")]
    public required IReadOnlyList<FactExtractionContext> Context { get; init; }

    [JsonPropertyName("outputLanguage")]
    public string OutputLanguage { get; init; } = "zh-CN";
}

public sealed record FactExtractionContext
{
    [JsonPropertyName("type")]
    public string Type { get; init; } = "text";

    [JsonPropertyName("text")]
    public required string Text { get; init; }
}

public sealed record FactExtractionResponse
{
    [JsonPropertyName("facts")]
    public IReadOnlyList<FactExtractionItem> Facts { get; init; } = [];

    [JsonPropertyName("outputLanguage")]
    public required string OutputLanguage { get; init; }

    [JsonPropertyName("usageInfo")]
    public required FactExtractionUsageInfo UsageInfo { get; init; }
}

public sealed record FactExtractionItem
{
    [JsonPropertyName("group")]
    public required string Group { get; init; }

    [JsonPropertyName("text")]
    public required string Text { get; init; }

    [JsonPropertyName("value")]
    public string Value { get; init; } = "";
}

public sealed record FactExtractionUsageInfo
{
    [JsonPropertyName("creditsConsumed")]
    public double CreditsConsumed { get; init; }
}

public sealed record FactRecord
{
    [JsonPropertyName("id")]
    public required string Id { get; init; }

    [JsonPropertyName("text")]
    public required string Text { get; init; }

    [JsonPropertyName("group")]
    public required string Group { get; init; }

    [JsonPropertyName("groupId")]
    public required string GroupId { get; init; }

    [JsonPropertyName("source")]
    public required string Source { get; init; }

    [JsonPropertyName("isDiscarded")]
    public bool IsDiscarded { get; init; }

    [JsonPropertyName("createdAt")]
    public string? CreatedAt { get; init; }

    [JsonPropertyName("updatedAt")]
    public required string UpdatedAt { get; init; }
}

public sealed record FactCreateInput
{
    [JsonPropertyName("text")]
    public required string Text { get; init; }

    [JsonPropertyName("group")]
    public required string Group { get; init; }

    [JsonPropertyName("source")]
    public string? Source { get; init; }
}

public sealed record FactUpdateInput
{
    [JsonPropertyName("factId")]
    public required string FactId { get; init; }

    [JsonPropertyName("text")]
    public string? Text { get; init; }

    [JsonPropertyName("group")]
    public string? Group { get; init; }

    [JsonPropertyName("source")]
    public string? Source { get; init; }

    [JsonPropertyName("isDiscarded")]
    public bool? IsDiscarded { get; init; }
}
