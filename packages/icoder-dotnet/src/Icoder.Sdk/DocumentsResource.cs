using System.Net;
using System.Text.Json.Serialization;

namespace Icoder.Sdk;

public static class DocumentationModes
{
    public const string GlobalSequential = "global_sequential";
    public const string RoutedParallel = "routed_parallel";
}

public sealed record DocumentFact
{
    [JsonPropertyName("text")]
    public required string Text { get; init; }

    [JsonPropertyName("group")]
    public string? Group { get; init; }

    [JsonPropertyName("source")]
    public string? Source { get; init; }
}

public sealed record DocumentTranscriptData
{
    [JsonPropertyName("text")]
    public required string Text { get; init; }

    [JsonPropertyName("channel")]
    public int? Channel { get; init; }

    [JsonPropertyName("participant")]
    public int? Participant { get; init; }

    [JsonPropertyName("speakerId")]
    public int? SpeakerId { get; init; }

    [JsonPropertyName("start")]
    public double? Start { get; init; }

    [JsonPropertyName("end")]
    public double? End { get; init; }
}

public sealed record DocumentContext
{
    [JsonPropertyName("type")]
    public required string Type { get; init; }

    [JsonPropertyName("data")]
    public required object Data { get; init; }

    public static DocumentContext Facts(IReadOnlyList<DocumentFact> facts)
        => new() { Type = "facts", Data = facts };

    public static DocumentContext Transcript(DocumentTranscriptData transcript)
        => new() { Type = "transcript", Data = transcript };

    public static DocumentContext String(string text)
        => new() { Type = "string", Data = text };
}

public sealed record DocumentSectionOverride
{
    [JsonPropertyName("key")]
    public required string Key { get; init; }

    [JsonPropertyName("nameOverride")]
    public string? NameOverride { get; init; }

    [JsonPropertyName("writingStyleOverride")]
    public string? WritingStyleOverride { get; init; }

    [JsonPropertyName("formatRuleOverride")]
    public string? FormatRuleOverride { get; init; }

    [JsonPropertyName("additionalInstructionsOverride")]
    public string? AdditionalInstructionsOverride { get; init; }

    [JsonPropertyName("contentOverride")]
    public string? ContentOverride { get; init; }
}

public sealed record DocumentTemplate
{
    [JsonPropertyName("sections")]
    public IReadOnlyList<DocumentSectionOverride>? Sections { get; init; }

    [JsonPropertyName("sectionKeys")]
    public IReadOnlyList<string>? SectionKeys { get; init; }

    [JsonPropertyName("description")]
    public string? Description { get; init; }

    [JsonPropertyName("documentName")]
    public string? DocumentName { get; init; }

    [JsonPropertyName("additionalInstructionsOverride")]
    public string? AdditionalInstructionsOverride { get; init; }

    [JsonPropertyName("additionalInstructions")]
    public string? AdditionalInstructions { get; init; }
}

public sealed record DocumentCreateRequest
{
    [JsonPropertyName("context")]
    public required IReadOnlyList<DocumentContext> Context { get; init; }

    [JsonPropertyName("name")]
    public string? Name { get; init; }

    [JsonPropertyName("outputLanguage")]
    public required string OutputLanguage { get; init; }

    [JsonPropertyName("disableGuardrails")]
    public bool? DisableGuardrails { get; init; }

    [JsonPropertyName("documentationMode")]
    public string? DocumentationMode { get; init; }

    [JsonPropertyName("templateKey")]
    public string? TemplateKey { get; init; }

    [JsonPropertyName("template")]
    public DocumentTemplate? Template { get; init; }
}

public sealed record DocumentSection
{
    [JsonPropertyName("key")]
    public required string Key { get; init; }

    [JsonPropertyName("name")]
    public required string Name { get; init; }

    [JsonPropertyName("text")]
    public required string Text { get; init; }

    [JsonPropertyName("sort")]
    public int Sort { get; init; }

    [JsonPropertyName("createdAt")]
    public string CreatedAt { get; init; } = "";

    [JsonPropertyName("updatedAt")]
    public string UpdatedAt { get; init; } = "";
}

public sealed record DocumentUsageInfo
{
    [JsonPropertyName("creditsConsumed")]
    public double CreditsConsumed { get; init; }
}

public sealed record ClassicDocument
{
    [JsonPropertyName("id")]
    public required string Id { get; init; }

    [JsonPropertyName("name")]
    public string Name { get; init; } = "";

    [JsonPropertyName("templateRef")]
    public string TemplateRef { get; init; } = "";

    [JsonPropertyName("isStream")]
    public bool IsStream { get; init; }

    [JsonPropertyName("sections")]
    public IReadOnlyList<DocumentSection> Sections { get; init; } = [];

    [JsonPropertyName("createdAt")]
    public string CreatedAt { get; init; } = "";

    [JsonPropertyName("updatedAt")]
    public string UpdatedAt { get; init; } = "";

    [JsonPropertyName("outputLanguage")]
    public string OutputLanguage { get; init; } = "";

    [JsonPropertyName("usageInfo")]
    public DocumentUsageInfo UsageInfo { get; init; } = new();
}

public sealed record DocumentsListResponse
{
    [JsonPropertyName("data")]
    public IReadOnlyList<ClassicDocument> Data { get; init; } = [];
}

public sealed record DocumentUpdateSection
{
    [JsonPropertyName("key")]
    public required string Key { get; init; }

    [JsonPropertyName("name")]
    public required string Name { get; init; }

    [JsonPropertyName("text")]
    public required string Text { get; init; }

    [JsonPropertyName("sort")]
    public int Sort { get; init; }
}

public sealed record DocumentUpdateRequest
{
    [JsonPropertyName("name")]
    public string? Name { get; init; }

    [JsonPropertyName("sections")]
    public IReadOnlyList<DocumentUpdateSection>? Sections { get; init; }
}

public sealed record DocumentCreateResult(
    ClassicDocument Document,
    HttpStatusCode StatusCode,
    bool RetentionAcknowledged);

public sealed class DocumentsResource(ICoDerClient client)
{
    public async Task<DocumentCreateResult> CreateAsync(
        string interactionId,
        DocumentCreateRequest request,
        string? retentionPolicy = null,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        ValidateId(interactionId, nameof(interactionId));
        ValidateRequest(request);
        if (retentionPolicy is not null && retentionPolicy != "none")
        {
            throw new ArgumentException(
                "Retention policy supports only null or 'none'.",
                nameof(retentionPolicy));
        }
        IReadOnlyDictionary<string, string>? headers = retentionPolicy == "none"
            ? new Dictionary<string, string> { ["X-Corti-Retention-Policy"] = "none" }
            : null;
        var response = await client.SendWithMetadataAsync<ClassicDocument>(
            HttpMethod.Post,
            $"{Base(interactionId)}/",
            request,
            headers,
            cancellationToken,
            requestOptions).ConfigureAwait(false);
        return new DocumentCreateResult(
            response.Value,
            response.StatusCode,
            string.Equals(
                response.GetHeader("X-Corti-Retention-Policy"),
                "acknowledged",
                StringComparison.OrdinalIgnoreCase));
    }

    public async Task<ClassicDocument> PreviewAsync(
        string interactionId,
        DocumentCreateRequest request,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        var result = await CreateAsync(
            interactionId,
            request,
            "none",
            cancellationToken,
            requestOptions).ConfigureAwait(false);
        if (!result.RetentionAcknowledged)
        {
            throw new InvalidOperationException(
                "Server did not acknowledge the zero-retention policy.");
        }
        return result.Document;
    }

    public async Task<IReadOnlyList<ClassicDocument>> ListAsync(
        string interactionId,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        ValidateId(interactionId, nameof(interactionId));
        var response = await client.SendAsync<DocumentsListResponse>(
            HttpMethod.Get,
            $"{Base(interactionId)}/",
            cancellationToken: cancellationToken,
            requestOptions: requestOptions).ConfigureAwait(false);
        return response.Data;
    }

    public Task<ClassicDocument> GetAsync(
        string interactionId,
        string documentId,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        ValidateId(interactionId, nameof(interactionId));
        ValidateId(documentId, nameof(documentId));
        return client.SendAsync<ClassicDocument>(
            HttpMethod.Get,
            $"{Base(interactionId)}/{Escape(documentId)}",
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task<ClassicDocument> UpdateAsync(
        string interactionId,
        string documentId,
        DocumentUpdateRequest request,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        ValidateId(interactionId, nameof(interactionId));
        ValidateId(documentId, nameof(documentId));
        Guard.NotNull(request, nameof(request));
        return client.SendAsync<ClassicDocument>(
            Compatibility.Patch,
            $"{Base(interactionId)}/{Escape(documentId)}",
            request,
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task DeleteAsync(
        string interactionId,
        string documentId,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        ValidateId(interactionId, nameof(interactionId));
        ValidateId(documentId, nameof(documentId));
        return client.SendNoContentAsync(
            HttpMethod.Delete,
            $"{Base(interactionId)}/{Escape(documentId)}",
            cancellationToken,
            requestOptions: requestOptions);
    }

    private static void ValidateRequest(DocumentCreateRequest request)
    {
        Guard.NotNull(request, nameof(request));
        if (request.Context is null || request.Context.Count == 0)
        {
            throw new ArgumentException("At least one context item is required.", nameof(request));
        }
        Guard.NotNullOrWhiteSpace(request.OutputLanguage, nameof(request.OutputLanguage));
        var hasTemplateKey = !string.IsNullOrWhiteSpace(request.TemplateKey);
        if (hasTemplateKey == (request.Template is not null))
        {
            throw new ArgumentException(
                "Exactly one of TemplateKey or Template is required.",
                nameof(request));
        }
        if (request.Template is not null)
        {
            var hasSections = request.Template.Sections is { Count: > 0 };
            var hasSectionKeys = request.Template.SectionKeys is { Count: > 0 };
            if (hasSections == hasSectionKeys)
            {
                throw new ArgumentException(
                    "A dynamic template requires exactly one of Sections or SectionKeys.",
                    nameof(request));
            }
        }
        if (request.DocumentationMode is not null &&
            request.DocumentationMode != DocumentationModes.GlobalSequential &&
            request.DocumentationMode != DocumentationModes.RoutedParallel)
        {
            throw new ArgumentException("Unsupported documentation mode.", nameof(request));
        }
        if (request.DocumentationMode == DocumentationModes.RoutedParallel &&
            request.Context.Any(item => item.Type != "facts"))
        {
            throw new ArgumentException(
                "Routed-parallel generation supports facts context only.",
                nameof(request));
        }
    }

    private static string Base(string interactionId)
        => $"/api/v2/tools/interactions/{Escape(interactionId)}/documents";

    private static string Escape(string value) => Uri.EscapeDataString(value);

    private static void ValidateId(string value, string parameterName)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            throw new ArgumentException("Identifier cannot be empty.", parameterName);
        }
    }
}
