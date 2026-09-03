using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Runtime.CompilerServices;
using System.Text.Json;

namespace Icoder.Sdk;

public sealed class AgentRunsResource(ICoDerClient client)
{
    public Task<AgentRunResponse> RunAsync(
        string agentId,
        AgentRunRequest request,
        string? idempotencyKey = null,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(agentId, nameof(agentId));
        Guard.NotNull(request, nameof(request));
        IReadOnlyDictionary<string, string>? headers = string.IsNullOrWhiteSpace(idempotencyKey)
            ? null
            : new Dictionary<string, string> { ["Idempotency-Key"] = idempotencyKey! };
        return client.SendAsync<AgentRunResponse>(
            HttpMethod.Post,
            $"/api/v1/agents/{Uri.EscapeDataString(agentId)}/run",
            request,
            headers,
            cancellationToken,
            requestOptions);
    }

    public Task<AgentRunResponse> RunTextAsync(
        string agentId,
        string text,
        string? runtimeMode = null,
        string? idempotencyKey = null,
        string? purposeOfUse = null,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
        => RunAsync(
            agentId,
            new AgentRunRequest
            {
                Input = new AgentRunInput { Text = text },
                RuntimeMode = runtimeMode,
                PurposeOfUse = purposeOfUse,
            },
            idempotencyKey,
            cancellationToken,
            requestOptions);

    public Task<RunStatusResponse> GetAsync(
        string runId,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(runId, nameof(runId));
        return client.SendAsync<RunStatusResponse>(
            HttpMethod.Get,
            $"/api/v1/runs/{Uri.EscapeDataString(runId)}",
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task<RunCancelResponse> CancelAsync(
        string runId,
        string reason = "",
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(runId, nameof(runId));
        return client.SendAsync<RunCancelResponse>(
            HttpMethod.Post,
            $"/api/v1/runs/{Uri.EscapeDataString(runId)}/cancel",
            new { reason },
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task<RunTraceTokenRenewResponse> RenewTraceTokenAsync(
        string runId,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(runId, nameof(runId));
        return client.SendAsync<RunTraceTokenRenewResponse>(
            HttpMethod.Post,
            $"/api/v1/runs/{Uri.EscapeDataString(runId)}/trace-token",
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public IAsyncEnumerable<RunStreamEvent> StreamEventsAsync(
        string runId,
        string traceToken,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(runId, nameof(runId));
        Guard.NotNullOrWhiteSpace(traceToken, nameof(traceToken));
        return client.SendRunEventsAsync(
            $"/api/v1/runs/{Uri.EscapeDataString(runId)}/events" +
            $"?token={Uri.EscapeDataString(traceToken)}",
            null,
            cancellationToken,
            requestOptions);
    }

    public IAsyncEnumerable<RunStreamEvent> StreamEventsAsync(
        string runId,
        string traceToken,
        string lastEventId,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(runId, nameof(runId));
        Guard.NotNullOrWhiteSpace(traceToken, nameof(traceToken));
        Guard.NotNullOrWhiteSpace(lastEventId, nameof(lastEventId));
        if (lastEventId.Length > 128 || lastEventId.IndexOfAny(['\r', '\n', '\0']) >= 0)
        {
            throw new ArgumentException("Last event ID is malformed.", nameof(lastEventId));
        }
        return client.SendRunEventsAsync(
            $"/api/v1/runs/{Uri.EscapeDataString(runId)}/events" +
            $"?token={Uri.EscapeDataString(traceToken)}",
            lastEventId,
            cancellationToken,
            requestOptions);
    }

    public async IAsyncEnumerable<RunStreamEvent> StreamEventsResilientAsync(
        string runId,
        string traceToken,
        RunStreamRetryOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(runId, nameof(runId));
        Guard.NotNullOrWhiteSpace(traceToken, nameof(traceToken));
        options ??= new RunStreamRetryOptions();
        ValidateRetryOptions(options);

        var currentToken = traceToken;
        var lastEventId = options.LastEventId;
        for (var attempt = 0; attempt < options.MaxAttempts; attempt++)
        {
            cancellationToken.ThrowIfCancellationRequested();
            Exception? failure = null;
            var completed = false;
            await using (var enumerator = client.SendRunEventsAsync(
                $"/api/v1/runs/{Uri.EscapeDataString(runId)}/events" +
                $"?token={Uri.EscapeDataString(currentToken)}",
                lastEventId,
                cancellationToken,
                requestOptions).GetAsyncEnumerator(cancellationToken))
            {
                while (true)
                {
                    RunStreamEvent? current = null;
                    try
                    {
                        if (!await enumerator.MoveNextAsync().ConfigureAwait(false))
                        {
                            break;
                        }
                        current = enumerator.Current;
                        completed = IsTerminalRunEvent(current);
                        if (!string.IsNullOrWhiteSpace(current.Id))
                        {
                            lastEventId = current.Id;
                        }
                    }
                    catch (Exception error)
                    {
                        failure = error;
                        break;
                    }

                    yield return current;
                }
            }

            if (failure is null && completed)
            {
                yield break;
            }
            failure ??= new IOException(
                "iCoDer run event stream ended before completion.");

            var canRenew = failure is ICoDerApiException apiError &&
                apiError.StatusCodeValue == HttpStatusCode.Unauthorized;
            var retryableTransport = failure is IOException ||
                (failure is HttpRequestException && failure is not ICoDerApiException) ||
                (failure is TaskCanceledException && !cancellationToken.IsCancellationRequested);
            if ((!canRenew && !retryableTransport) || attempt + 1 >= options.MaxAttempts)
            {
                throw failure;
            }
            if (canRenew)
            {
                currentToken = (await RenewTraceTokenAsync(
                    runId, cancellationToken, requestOptions).ConfigureAwait(false)).TraceToken;
            }

            var delay = RetryDelay(options, attempt);
            if (delay > TimeSpan.Zero)
            {
                await Task.Delay(delay, cancellationToken).ConfigureAwait(false);
            }
        }
    }

    private static void ValidateRetryOptions(RunStreamRetryOptions options)
    {
        if (options.MaxAttempts < 1)
        {
            throw new ArgumentOutOfRangeException(
                nameof(options), "MaxAttempts must be positive.");
        }
        if (options.InitialDelay < TimeSpan.Zero ||
            options.MaxDelay < options.InitialDelay)
        {
            throw new ArgumentOutOfRangeException(
                nameof(options), "Retry delays are invalid.");
        }
        if (options.JitterRatio is < 0 or > 1)
        {
            throw new ArgumentOutOfRangeException(
                nameof(options), "JitterRatio must be between 0 and 1.");
        }
        if (!string.IsNullOrWhiteSpace(options.LastEventId) &&
            (options.LastEventId!.Length > 128 ||
             options.LastEventId.IndexOfAny(['\r', '\n', '\0']) >= 0))
        {
            throw new ArgumentException("Last event ID is malformed.", nameof(options));
        }
    }

    private static TimeSpan RetryDelay(RunStreamRetryOptions options, int attempt)
    {
        var baseMilliseconds = Math.Min(
            options.MaxDelay.TotalMilliseconds,
            options.InitialDelay.TotalMilliseconds * Math.Pow(2, attempt));
        var jitter = 1 + ((Compatibility.NextDouble() * 2 - 1) * options.JitterRatio);
        return TimeSpan.FromMilliseconds(Compatibility.Clamp(
            baseMilliseconds * jitter, 0, options.MaxDelay.TotalMilliseconds));
    }

    private static bool IsTerminalRunEvent(RunStreamEvent current)
    {
        using var document = JsonDocument.Parse(current.Data);
        if (document.RootElement.ValueKind != JsonValueKind.Object)
        {
            throw new JsonException("Run SSE data must be a JSON object.");
        }
        return string.Equals(current.Event, "stream.completed", StringComparison.Ordinal) ||
            (document.RootElement.TryGetProperty("name", out var name) &&
             string.Equals(name.GetString(), "stream.completed", StringComparison.Ordinal));
    }
}

public sealed class AgentHubResource(ICoDerClient client)
{
    public async Task<AgentHubResponse> ListAsync(
        string? useCase = null,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        var path = string.IsNullOrWhiteSpace(useCase)
            ? "/api/icoder/agents/hub"
            : $"/api/icoder/agents/hub?use_case={Uri.EscapeDataString(useCase)}";
        var response = await client.SendAsync<AgentHubResponse>(
            HttpMethod.Get, path, cancellationToken: cancellationToken,
            requestOptions: requestOptions).ConfigureAwait(false);
        ValidateReadiness(response);
        return response;
    }

    public async Task<AgentHubTenantReadinessResponse> GetReadinessAsync(
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        var response = await client.SendAsync<AgentHubTenantReadinessResponse>(
            HttpMethod.Get,
            "/api/icoder/agents/hub/readiness",
            cancellationToken: cancellationToken,
            requestOptions: requestOptions).ConfigureAwait(false);
        ValidateTenantReadiness(response);
        return response;
    }

    public Task<A2ALegacyAgentCard> GetCardAsync(
        string agentId,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(agentId, nameof(agentId));
        return client.SendAsync<A2ALegacyAgentCard>(
            HttpMethod.Get,
            $"/api/icoder/agents/{Uri.EscapeDataString(agentId)}/card",
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    /// <summary>Clone a governed Hub Agent into the active tenant project.</summary>
    public async Task<AgentCloneResponse> CloneAsync(
        string agentId,
        AgentCloneRequest? request = null,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(agentId, nameof(agentId));
        var response = await client.SendAsync<AgentCloneResponse>(
            HttpMethod.Post,
            $"/api/icoder/agents/{Uri.EscapeDataString(agentId)}/clone",
            request ?? new AgentCloneRequest(),
            cancellationToken: cancellationToken,
            requestOptions: requestOptions).ConfigureAwait(false);
        ValidateCloneResponse(response);
        return response;
    }

    private static void ValidateCloneResponse(AgentCloneResponse response)
    {
        if (string.IsNullOrWhiteSpace(response.ProjectAgentId) ||
            string.IsNullOrWhiteSpace(response.RuntimeAgentId) ||
            string.IsNullOrWhiteSpace(response.SourceRuntimeAgentId) ||
            string.IsNullOrWhiteSpace(response.SourceAgentRef) ||
            string.IsNullOrWhiteSpace(response.ChatUrl) ||
            string.IsNullOrWhiteSpace(response.CustomizeUrl) ||
            string.IsNullOrWhiteSpace(response.RunUrl))
        {
            throw new InvalidDataException(
                "Agent clone response is missing a required identity or URL.");
        }
        if (!string.Equals(
            response.RuntimeAgentId, response.ProjectAgentId, StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                "Agent clone response would bypass the project runtime identity.");
        }
    }

    private static void ValidateReadiness(AgentHubResponse response)
    {
        if (!string.Equals(response.SchemaVersion, "1.3", StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                "Unsupported or malformed Agent Hub response; schema_version 1.3 is required.");
        }
        var configurationStatuses = new HashSet<string>(StringComparer.Ordinal)
        {
            "not_checked", "local_ready", "configured_not_live_verified", "unavailable",
        };
        foreach (var card in response.Agents)
        {
            var readiness = card.RuntimeReadiness ?? throw new InvalidDataException(
                "Agent Hub schema 1.3 card is missing runtime_readiness.");
            if ((readiness.StructuralStatus != "ready" && readiness.StructuralStatus != "blocked") ||
                !configurationStatuses.Contains(readiness.ConfigurationStatus) ||
                (readiness.SemanticValidationStatus != "verified" &&
                 readiness.SemanticValidationStatus != "not_verified") ||
                (readiness.ProductionApprovalStatus != "approved" &&
                 readiness.ProductionApprovalStatus != "not_approved"))
            {
                throw new InvalidDataException(
                    "Agent Hub runtime_readiness failed schema 1.3 validation.");
            }
            if (readiness.RunActionEnabled &&
                (readiness.StructuralStatus != "ready" ||
                 readiness.ConfigurationStatus is "not_checked" or "unavailable"))
            {
                throw new InvalidDataException(
                    "Agent Hub runtime_readiness enables an unavailable Agent.");
            }
            if ((readiness.ConfigurationStatus == "local_ready" &&
                 readiness.ExternalLlmRequired) ||
                (readiness.ConfigurationStatus == "configured_not_live_verified" &&
                 !readiness.ExternalLlmRequired))
            {
                throw new InvalidDataException(
                    "Agent Hub runtime_readiness dependency classification is inconsistent.");
            }
        }
    }

    private static void ValidateTenantReadiness(
        AgentHubTenantReadinessResponse response)
    {
        if (!string.Equals(response.SchemaVersion, "1.0", StringComparison.Ordinal) ||
            response.Agents is null ||
            response.Total != response.Agents.Count ||
            string.IsNullOrWhiteSpace(response.GeneratedAt))
        {
            throw new InvalidDataException(
                "Unsupported or malformed tenant Agent Hub readiness response; " +
                "schema_version 1.0 is required.");
        }
        var configurationStatuses = new HashSet<string>(StringComparer.Ordinal)
        {
            "local_ready", "configured", "unavailable",
        };
        var connectivityStatuses = new HashSet<string>(StringComparer.Ordinal)
        {
            "not_applicable", "not_run", "verified", "expired", "failed",
        };
        var seen = new HashSet<string>(StringComparer.Ordinal);
        foreach (var item in response.Agents)
        {
            if (item is null)
            {
                throw new InvalidDataException(
                    "Tenant Agent Hub readiness contains a null Agent item.");
            }
            var readiness = item.RuntimeReadiness ?? throw new InvalidDataException(
                "Tenant Agent Hub readiness is missing runtime_readiness.");
            var evidence = item.Evidence ?? throw new InvalidDataException(
                "Tenant Agent Hub readiness is missing evidence.");
            if (string.IsNullOrWhiteSpace(item.AgentId) ||
                string.IsNullOrWhiteSpace(item.ExecutionTarget) ||
                !seen.Add(item.AgentId) ||
                (readiness.StructuralStatus != "ready" &&
                 readiness.StructuralStatus != "blocked") ||
                !configurationStatuses.Contains(readiness.ConfigurationStatus) ||
                !connectivityStatuses.Contains(readiness.ConnectivityStatus) ||
                string.IsNullOrWhiteSpace(readiness.Reason) ||
                readiness.RuntimeDependencies is null ||
                (readiness.SemanticValidationStatus != "verified" &&
                 readiness.SemanticValidationStatus != "not_verified") ||
                (readiness.ProductionApprovalStatus != "approved" &&
                 readiness.ProductionApprovalStatus != "not_approved") ||
                evidence.Scope != "tenant_configuration_and_connectivity" ||
                (evidence.SelectionMode != "inherit" && evidence.SelectionMode != "pinned") ||
                evidence.SelectionVersion < 0 ||
                string.IsNullOrWhiteSpace(evidence.ConfigurationProbeStatus))
            {
                throw new InvalidDataException(
                    "Tenant Agent Hub runtime readiness failed schema 1.0 validation.");
            }
            if (readiness.LiveHealthVerified && readiness.ConnectivityStatus != "verified")
            {
                throw new InvalidDataException(
                    "Tenant Agent Hub readiness claims live health without verified connectivity.");
            }
            if (readiness.RunActionEnabled &&
                (readiness.StructuralStatus != "ready" ||
                 readiness.ConfigurationStatus == "unavailable" ||
                 readiness.ConnectivityStatus == "failed"))
            {
                throw new InvalidDataException(
                    "Tenant Agent Hub readiness enables an unavailable Agent.");
            }
            if ((readiness.ConfigurationStatus == "local_ready" && readiness.LlmRequired) ||
                (readiness.ConfigurationStatus == "configured" && !readiness.LlmRequired))
            {
                throw new InvalidDataException(
                    "Tenant Agent Hub readiness dependency classification is inconsistent.");
            }
        }
    }
}

public sealed class MedicalCodingResource(ICoDerClient client)
{
    public Task<CodingPricingEstimateResponse> EstimateCostAsync(
        int inputChars,
        string mode = "corti_like_fast",
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        if (inputChars is < 0 or > 16000)
        {
            throw new ArgumentOutOfRangeException(
                nameof(inputChars), "inputChars must be between 0 and 16000.");
        }
        if (mode != "corti_like_fast" && mode != "medcoder_deep")
        {
            throw new ArgumentException("Unsupported coding mode.", nameof(mode));
        }
        return client.SendAsync<CodingPricingEstimateResponse>(
            HttpMethod.Get,
            $"/api/v1/coding/pricing?input_chars={inputChars}" +
            $"&mode={Uri.EscapeDataString(mode)}",
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task<CodingPredictResponse> PredictAsync(
        CodingPredictRequest request,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNull(request, nameof(request));
        if (string.IsNullOrWhiteSpace(request.Text) || request.Text.Length > 16000)
        {
            throw new ArgumentException(
                "Text must contain between 1 and 16000 characters.", nameof(request));
        }
        if (request.Mode != "corti_like_fast" && request.Mode != "medcoder_deep")
        {
            throw new ArgumentException("Unsupported coding mode.", nameof(request));
        }
        var codingSystems = NormalizeCodingSystems(request);
        var normalizedRequest = request with
        {
            CodingSystem = null,
            CodingSystems = codingSystems,
            Filter = request.Filter is null ? null : NormalizeFilter(request.Filter),
        };
        return client.SendAsync<CodingPredictResponse>(
            HttpMethod.Post,
            "/api/v1/coding/predict",
            normalizedRequest,
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    private static IReadOnlyList<string> NormalizeCodingSystems(
        CodingPredictRequest request)
    {
        if (!string.IsNullOrWhiteSpace(request.CodingSystem) &&
            request.CodingSystems is not null)
        {
            throw new ArgumentException(
                "Use CodingSystem or CodingSystems, not both.", nameof(request));
        }
        List<string> systems = request.CodingSystems is not null
            ? request.CodingSystems.ToList()
            : [request.CodingSystem ?? "icd10cn"];
        if (systems.Count is < 1 or > 2)
        {
            throw new ArgumentException(
                "CodingSystems must contain one or two systems.", nameof(request));
        }
        if (systems.Any(system => system is not ("icd10cn" or "icd9cm3")))
        {
            throw new ArgumentException(
                "Unsupported Chinese coding system.", nameof(request));
        }
        if (systems.Distinct(StringComparer.Ordinal).Count() != systems.Count)
        {
            throw new ArgumentException(
                "CodingSystems must not contain duplicates.", nameof(request));
        }
        return systems;
    }

    private static CodingCodeFilter NormalizeFilter(CodingCodeFilter filter)
    {
        var include = NormalizeTerms(filter.Include);
        var exclude = NormalizeTerms(filter.Exclude);
        if (include.Count + exclude.Count > 100)
        {
            throw new ArgumentException(
                "Filter include and exclude may contain at most 100 entries combined.",
                nameof(filter));
        }
        return filter with { Include = include, Exclude = exclude };
    }

    private static IReadOnlyList<string> NormalizeTerms(IReadOnlyList<string> values)
    {
        var normalized = new List<string>();
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var raw in values)
        {
            var value = raw?.Trim() ?? "";
            if (value.Length is < 1 or > 64 || value.Any(char.IsControl))
            {
                throw new ArgumentException(
                    "Code filter entries must contain between 1 and 64 printable characters.",
                    nameof(values));
            }
            if (seen.Add(value))
            {
                normalized.Add(value);
            }
        }
        return normalized;
    }
}
