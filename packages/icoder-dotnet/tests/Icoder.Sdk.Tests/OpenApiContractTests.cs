using System.Text.Json;
using Xunit;

namespace Icoder.Sdk.Tests;

public sealed class OpenApiContractTests
{
    [Fact]
    public void EverySdkOperationExistsInExportedOpenApi()
    {
        using var schema = JsonDocument.Parse(File.ReadAllText(FindOpenApiSchema()));
        var paths = schema.RootElement.GetProperty("paths");
        var expected = new (string Path, string Method)[]
        {
            ("/api/v1/agents/{agent_id}/run", "post"),
            ("/api/icoder/agents/hub", "get"),
            ("/api/icoder/agents/{agent_id}/card", "get"),
            ("/.well-known/agent-card.json", "get"),
            ("/api/v2/agentic/agents/{agent_id}/.well-known/agent-card.json", "get"),
            ("/api/v1/coding/predict", "post"),
            ("/api/v1/model-catalog", "get"),
            ("/api/v1/model-catalog/health-probe", "post"),
            ("/api/v1/model-catalog/live-canary", "post"),
            ("/api/v1/model-catalog/selection", "put"),
            ("/api/v1/clinical-model-packages", "get"),
            ("/api/v1/clinical-model-packages", "post"),
            ("/api/v1/clinical-model-packages/{package_id}", "get"),
            ("/api/v1/clinical-model-packages/{package_id}/submit", "post"),
            ("/api/v1/clinical-model-packages/{package_id}/decision", "post"),
            ("/api/v1/clinical-model-packages/{package_id}/artifact-attestations", "get"),
            ("/api/v1/clinical-model-packages/{package_id}/synthetic-artifact-probe", "post"),
            ("/api/v1/clinical-model-packages/activations/{use_case}", "get"),
            ("/api/v1/clinical-model-packages/activations/{use_case}", "put"),
            ("/api/v1/clinical-model-packages/activations/{use_case}/rollback", "post"),
            ("/api/v1/clinical-model-packages/shadow-bindings/{use_case}", "get"),
            ("/api/v1/clinical-model-packages/shadow-bindings/{use_case}", "put"),
            ("/api/v1/clinical-model-packages/shadow-bindings/{use_case}/rollback", "post"),
            ("/api/v1/clinical-model-packages/shadow-bindings/{use_case}/evaluations", "get"),
            ("/api/v1/clinical-model-packages/shadow-bindings/{use_case}/synthetic-evaluation", "post"),
            ("/api/v1/clinical-model-packages/shadow-bindings/{use_case}/evaluation-jobs", "post"),
            ("/api/v1/clinical-model-packages/shadow-bindings/{use_case}/evaluation-jobs", "get"),
            ("/api/v1/clinical-model-packages/shadow-evaluation-jobs/{job_id}", "get"),
            ("/api/v1/clinical-model-packages/shadow-evaluation-jobs/{job_id}/execute", "post"),
            ("/api/v1/clinical-model-packages/shadow-evaluation-jobs/{job_id}/cancel", "post"),
            ("/api/v1/clinical-model-packages/shadow-evaluation-jobs/health/summary", "get"),
            ("/api/v1/clinical-model-packages/shadow-evaluation-jobs/maintenance/run", "post"),
            ("/api/drg/analyze", "post"),
            ("/api/drg/rules", "get"),
            ("/api/drg/governance", "get"),
            ("/api/v2/tools/interactions/{interaction_id}/recordings", "get"),
            ("/api/v2/tools/interactions/{interaction_id}/recordings", "post"),
            ("/api/v2/tools/interactions/{interaction_id}/recordings/{recording_id}", "get"),
            ("/api/v2/tools/interactions/{interaction_id}/recordings/{recording_id}", "delete"),
            ("/api/v2/tools/interactions/{interaction_id}/transcripts", "get"),
            ("/api/v2/tools/interactions/{interaction_id}/transcripts", "post"),
            ("/api/v2/tools/interactions/{interaction_id}/transcripts/{transcript_id}", "get"),
            ("/api/v2/tools/interactions/{interaction_id}/transcripts/{transcript_id}", "delete"),
            ("/api/v2/tools/interactions/{interaction_id}/transcripts/{transcript_id}/status", "get"),
            ("/api/v2/tools/interactions/{interaction_id}/facts", "get"),
            ("/api/v2/tools/interactions/{interaction_id}/facts", "post"),
            ("/api/v2/tools/interactions/{interaction_id}/facts", "patch"),
            ("/api/v2/tools/interactions/{interaction_id}/facts/{fact_id}", "patch"),
            ("/api/v2/tools/interactions/{interaction_id}/documents/", "get"),
            ("/api/v2/tools/interactions/{interaction_id}/documents/", "post"),
            ("/api/v2/tools/interactions/{interaction_id}/documents/{document_id}", "get"),
            ("/api/v2/tools/interactions/{interaction_id}/documents/{document_id}", "patch"),
            ("/api/v2/tools/interactions/{interaction_id}/documents/{document_id}", "delete"),
            ("/api/v2/tools/templates/", "get"),
            ("/api/v2/tools/templates/{template_id}", "get"),
            ("/api/v2/tools/sections/", "get"),
            ("/api/v2/tools/sections/", "post"),
            ("/api/v2/tools/sections/{section_id}", "get"),
            ("/api/v2/tools/sections/{section_id}", "patch"),
            ("/api/v2/tools/sections/{section_id}", "delete"),
        };

        foreach (var operation in expected)
        {
            Assert.True(paths.TryGetProperty(operation.Path, out var path),
                $"OpenAPI is missing {operation.Path}");
            Assert.True(path.TryGetProperty(operation.Method, out _),
                $"OpenAPI is missing {operation.Method.ToUpperInvariant()} {operation.Path}");
        }
    }

    [Fact]
    public void AsyncTranscriptResponseDocumentsAcceptedAndLocationContract()
    {
        using var schema = JsonDocument.Parse(File.ReadAllText(FindOpenApiSchema()));
        var operation = schema.RootElement
            .GetProperty("paths")
            .GetProperty("/api/v2/tools/interactions/{interaction_id}/transcripts")
            .GetProperty("post");
        Assert.True(operation.GetProperty("responses").TryGetProperty("202", out _));

        var requestSchema = schema.RootElement
            .GetProperty("components")
            .GetProperty("schemas")
            .GetProperty("TranscriptsCreateRequest")
            .GetProperty("properties");
        Assert.True(requestSchema.TryGetProperty("async", out _));
        Assert.True(requestSchema.TryGetProperty("recordingId", out _));
        Assert.True(requestSchema.TryGetProperty("primaryLanguage", out _));
    }

    [Fact]
    public void AgentHubOpenApiPublishesSchema13RuntimeReadiness()
    {
        using var schema = JsonDocument.Parse(File.ReadAllText(FindOpenApiSchema()));
        var response = schema.RootElement
            .GetProperty("paths")
            .GetProperty("/api/icoder/agents/hub")
            .GetProperty("get")
            .GetProperty("responses")
            .GetProperty("200")
            .GetProperty("content")
            .GetProperty("application/json")
            .GetProperty("schema");
        Assert.Equal(
            "#/components/schemas/AgentHubListResponse",
            response.GetProperty("$ref").GetString());

        var readiness = schema.RootElement
            .GetProperty("components")
            .GetProperty("schemas")
            .GetProperty("AgentHubRuntimeReadiness");
        Assert.False(readiness.GetProperty("additionalProperties").GetBoolean());
        var properties = readiness.GetProperty("properties");
        Assert.True(properties.TryGetProperty("run_action_enabled", out _));
        Assert.True(properties.TryGetProperty("live_health_verified", out _));
        Assert.True(properties.TryGetProperty("semantic_validation_status", out _));
        Assert.True(properties.TryGetProperty("production_approval_status", out _));

        var tenantResponse = schema.RootElement
            .GetProperty("paths")
            .GetProperty("/api/icoder/agents/hub/readiness")
            .GetProperty("get")
            .GetProperty("responses")
            .GetProperty("200")
            .GetProperty("content")
            .GetProperty("application/json")
            .GetProperty("schema");
        Assert.Equal(
            "#/components/schemas/AgentHubTenantReadinessResponse",
            tenantResponse.GetProperty("$ref").GetString());
        var tenantReadiness = schema.RootElement
            .GetProperty("components")
            .GetProperty("schemas")
            .GetProperty("AgentHubTenantRuntimeReadiness");
        Assert.False(tenantReadiness.GetProperty("additionalProperties").GetBoolean());
        var tenantProperties = tenantReadiness.GetProperty("properties");
        Assert.True(tenantProperties.TryGetProperty("llm_required", out _));
        Assert.True(tenantProperties.TryGetProperty("connectivity_status", out _));
    }

    private static string FindOpenApiSchema()
    {
        var current = new DirectoryInfo(AppContext.BaseDirectory);
        while (current is not null)
        {
            var candidate = Path.Combine(current.FullName, "docs", "openapi", "openapi.json");
            if (File.Exists(candidate))
            {
                return candidate;
            }
            current = current.Parent;
        }
        throw new FileNotFoundException("Could not locate docs/openapi/openapi.json from test output.");
    }
}
