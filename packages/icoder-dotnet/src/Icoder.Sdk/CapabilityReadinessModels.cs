using System.Text.Json.Serialization;

namespace Icoder.Sdk;

public sealed record SttReadiness
{
    [JsonPropertyName("configuration_status")]
    public required string ConfigurationStatus { get; init; }
    [JsonPropertyName("verified_languages")]
    public IReadOnlyList<string> VerifiedLanguages { get; init; } = [];
    [JsonPropertyName("local_engine_enabled")]
    public bool LocalEngineEnabled { get; init; }
    [JsonPropertyName("whisper_fallback_configured")]
    public bool WhisperFallbackConfigured { get; init; }
    [JsonPropertyName("batch_provider_priority")]
    public IReadOnlyList<string> BatchProviderPriority { get; init; } = [];
    [JsonPropertyName("recording_storage_backend")]
    public required string RecordingStorageBackend { get; init; }
    [JsonPropertyName("external_object_storage_configured")]
    public bool ExternalObjectStorageConfigured { get; init; }
    [JsonPropertyName("at_rest_encryption_enabled")]
    public bool AtRestEncryptionEnabled { get; init; }
    [JsonPropertyName("durable_job_state")]
    public bool DurableJobState { get; init; }
    [JsonPropertyName("restart_recovery")]
    public bool RestartRecovery { get; init; }
    [JsonPropertyName("queue_backend")]
    public required string QueueBackend { get; init; }
    [JsonPropertyName("horizontally_scalable_queue")]
    public bool HorizontallyScalableQueue { get; init; }
    [JsonPropertyName("pending_transcript_count")]
    public int PendingTranscriptCount { get; init; }
    [JsonPropertyName("live_health_verified")]
    public bool LiveHealthVerified { get; init; }
    [JsonPropertyName("maximum_recording_bytes")]
    public int MaximumRecordingBytes { get; init; }
    [JsonPropertyName("production_ready")]
    public bool ProductionReady { get; init; }
}

public sealed record ExpertCapabilityReadiness
{
    [JsonPropertyName("expert_count")]
    public int ExpertCount { get; init; }
    [JsonPropertyName("published_expert_count")]
    public int PublishedExpertCount { get; init; }
    [JsonPropertyName("mcp_server_count")]
    public int McpServerCount { get; init; }
    [JsonPropertyName("active_mcp_server_count")]
    public int ActiveMcpServerCount { get; init; }
    [JsonPropertyName("mcp_authorization_type_counts")]
    public IReadOnlyDictionary<string, int> McpAuthorizationTypeCounts { get; init; }
        = new Dictionary<string, int>();
    [JsonPropertyName("built_in_mcp_tool_count")]
    public int BuiltInMcpToolCount { get; init; }
    [JsonPropertyName("tenant_scope_enforced")]
    public bool TenantScopeEnforced { get; init; }
    [JsonPropertyName("credentials_exposed")]
    public bool CredentialsExposed { get; init; }
    [JsonPropertyName("external_mcp_live_verified")]
    public bool ExternalMcpLiveVerified { get; init; }
    [JsonPropertyName("aggregate_only")]
    public bool AggregateOnly { get; init; }
    [JsonPropertyName("production_ready")]
    public bool ProductionReady { get; init; }
}
