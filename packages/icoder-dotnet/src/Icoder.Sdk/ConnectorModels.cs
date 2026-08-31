using System.Text.Json;
using System.Text.Json.Serialization;

namespace Icoder.Sdk;

public sealed record AgentConnectorCredentialMetadata
{
    public bool Present { get; init; }
    public string? Provider { get; init; }
    [JsonPropertyName("secret_type")]
    public string? SecretType { get; init; }
    public string? Fingerprint { get; init; }
    public string? Status { get; init; }
    public int? Version { get; init; }
    [JsonPropertyName("rotated_at")]
    public DateTimeOffset? RotatedAt { get; init; }
}

public sealed record AgentConnector
{
    public required string Id { get; init; }
    [JsonPropertyName("agent_id")]
    public required string AgentId { get; init; }
    public required string Type { get; init; }
    public required string Name { get; init; }
    public string Description { get; init; } = "";
    public bool Enabled { get; init; }
    public JsonElement Config { get; init; }
    [JsonPropertyName("target_agent_id")]
    public string? TargetAgentId { get; init; }
    [JsonPropertyName("normalized_url")]
    public string? NormalizedUrl { get; init; }
    [JsonPropertyName("schema_ref")]
    public string? SchemaRef { get; init; }
    [JsonPropertyName("schema_digest")]
    public string? SchemaDigest { get; init; }
    public int Version { get; init; }
    public AgentConnectorCredentialMetadata Credential { get; init; } = new();
    [JsonPropertyName("created_by")]
    public string CreatedBy { get; init; } = "";
    [JsonPropertyName("created_at")]
    public DateTimeOffset CreatedAt { get; init; }
    [JsonPropertyName("updated_at")]
    public DateTimeOffset UpdatedAt { get; init; }
}

public sealed record AgentConnectorList
{
    public IReadOnlyList<AgentConnector> Connectors { get; init; } = [];
    public int Total { get; init; }
}

public sealed record AgentConnectorCreateRequest
{
    public required string Type { get; init; }
    public required string Name { get; init; }
    public string Description { get; init; } = "";
    public bool Enabled { get; init; }
    public required object Config { get; init; }
}

public sealed record AgentConnectorUpdateRequest
{
    [JsonPropertyName("expected_version")]
    public required int ExpectedVersion { get; init; }
    public string? Name { get; init; }
    public string? Description { get; init; }
    public bool? Enabled { get; init; }
    public object? Config { get; init; }
}

public sealed record ConnectorCredentialBindRequest
{
    public required string Provider { get; init; }
    [JsonPropertyName("secret_ref")]
    public required string SecretRef { get; init; }
    [JsonPropertyName("secret_type")]
    public required string SecretType { get; init; }
    [JsonPropertyName("expected_version")]
    public int? ExpectedVersion { get; init; }
}

public sealed record ConnectorGraphCondition
{
    [JsonPropertyName("input_key")]
    public required string InputKey { get; init; }
    public required string Operator { get; init; }
    public object? Value { get; init; }
}

public sealed record ConnectorGraphNode
{
    public required string Id { get; init; }
    [JsonPropertyName("connector_id")]
    public required string ConnectorId { get; init; }
    public required string Operation { get; init; }
    public bool Required { get; init; } = true;
    public bool Idempotent { get; init; }
    [JsonPropertyName("include_text")]
    public bool IncludeText { get; init; }
    [JsonPropertyName("input_keys")]
    public IReadOnlyList<string> InputKeys { get; init; } = [];
    [JsonPropertyName("depends_on")]
    public IReadOnlyList<string> DependsOn { get; init; } = [];
    public ConnectorGraphCondition? When { get; init; }
    [JsonPropertyName("data_classification")]
    public string DataClassification { get; init; } = "deidentified";
    [JsonPropertyName("purpose_of_use")]
    public string PurposeOfUse { get; init; } = "treatment";
}

public sealed record ConnectorGraph
{
    public string Version { get; init; } = "1.0";
    public bool Enabled { get; init; }
    [JsonPropertyName("execution_mode")]
    public string ExecutionMode { get; init; } = "sequential";
    [JsonPropertyName("max_concurrency")]
    public int MaxConcurrency { get; init; } = 4;
    public IReadOnlyList<ConnectorGraphNode> Nodes { get; init; } = [];
    public int Revision { get; init; }
}

public sealed record ConnectorGraphPutRequest
{
    public string Version { get; init; } = "1.0";
    public bool Enabled { get; init; }
    [JsonPropertyName("execution_mode")]
    public string ExecutionMode { get; init; } = "sequential";
    [JsonPropertyName("max_concurrency")]
    public int MaxConcurrency { get; init; } = 4;
    public IReadOnlyList<ConnectorGraphNode> Nodes { get; init; } = [];
    [JsonPropertyName("expected_revision")]
    public required int ExpectedRevision { get; init; }
}

public sealed record MemoryConsent
{
    public required string Id { get; init; }
    [JsonPropertyName("agent_id")]
    public required string AgentId { get; init; }
    [JsonPropertyName("user_id")]
    public required string UserId { get; init; }
    [JsonPropertyName("purpose_of_use")]
    public required string PurposeOfUse { get; init; }
    [JsonPropertyName("legal_basis")]
    public string LegalBasis { get; init; } = "user-consent";
    [JsonPropertyName("authority_class")]
    public string AuthorityClass { get; init; } = "authenticated_user_self_service";
    [JsonPropertyName("patient_authority_verified")]
    public bool PatientAuthorityVerified { get; init; }
    [JsonPropertyName("phi_storage_allowed")]
    public bool PhiStorageAllowed { get; init; }
    [JsonPropertyName("retention_days")]
    public int RetentionDays { get; init; }
    public required string Status { get; init; }
    [JsonPropertyName("expires_at")]
    public DateTimeOffset ExpiresAt { get; init; }
    [JsonPropertyName("revoked_at")]
    public DateTimeOffset? RevokedAt { get; init; }
    [JsonPropertyName("created_at")]
    public DateTimeOffset CreatedAt { get; init; }
    [JsonPropertyName("updated_at")]
    public DateTimeOffset UpdatedAt { get; init; }
}

public sealed record MemoryConsentGrantRequest
{
    [JsonPropertyName("purpose_of_use")]
    public string PurposeOfUse { get; init; } = "treatment";
    [JsonPropertyName("retention_days")]
    public int RetentionDays { get; init; } = 30;
    [JsonPropertyName("expires_in_days")]
    public int ExpiresInDays { get; init; } = 30;
    public required bool Acknowledgement { get; init; }
}

public sealed record MemoryReadiness
{
    [JsonPropertyName("agent_id")]
    public required string AgentId { get; init; }
    [JsonPropertyName("purpose_of_use")]
    public required string PurposeOfUse { get; init; }
    [JsonPropertyName("consent_status")]
    public required string ConsentStatus { get; init; }
    [JsonPropertyName("persisted_memory_count")]
    public int PersistedMemoryCount { get; init; }
    [JsonPropertyName("retention_days")]
    public int? RetentionDays { get; init; }
    [JsonPropertyName("expires_at")]
    public DateTimeOffset? ExpiresAt { get; init; }
    [JsonPropertyName("encryption_enabled")]
    public bool EncryptionEnabled { get; init; }
    [JsonPropertyName("semantic_required")]
    public bool SemanticRequired { get; init; }
    [JsonPropertyName("semantic_provider")]
    public IReadOnlyDictionary<string, object?> SemanticProvider { get; init; }
        = new Dictionary<string, object?>();
    [JsonPropertyName("lexical_fallback_available")]
    public bool LexicalFallbackAvailable { get; init; }
    [JsonPropertyName("native_ml_in_api_process")]
    public bool NativeMlInApiProcess { get; init; }
    [JsonPropertyName("patient_authority_verified")]
    public bool PatientAuthorityVerified { get; init; }
    [JsonPropertyName("phi_storage_allowed")]
    public bool PhiStorageAllowed { get; init; }
    [JsonPropertyName("operationally_configured")]
    public bool OperationallyConfigured { get; init; }
}
