using System.Text.Json;
using Icoder.Sdk;

var baseUrl = Environment.GetEnvironmentVariable("ICODER_E2E_BASE_URL");
var sseBaseUrl = Environment.GetEnvironmentVariable("ICODER_E2E_SSE_BASE_URL") ?? baseUrl;
var accessToken = Environment.GetEnvironmentVariable("ICODER_E2E_ACCESS_TOKEN");
if (string.IsNullOrWhiteSpace(baseUrl) || string.IsNullOrWhiteSpace(accessToken))
{
    Console.Error.WriteLine("ICODER_E2E_BASE_URL and ICODER_E2E_ACCESS_TOKEN are required.");
    return 2;
}

using var client = new ICoDerClient(new ICoDerClientOptions
{
    BaseUri = new Uri(baseUrl),
    AccessToken = accessToken,
});

var longSseVerified = "skipped";
var longSseRunId = Environment.GetEnvironmentVariable("ICODER_E2E_SSE_RUN_ID");
var longSseToken = Environment.GetEnvironmentVariable("ICODER_E2E_SSE_TRACE_TOKEN");
if (!string.IsNullOrWhiteSpace(longSseRunId) && !string.IsNullOrWhiteSpace(longSseToken))
{
    var startedAt = System.Diagnostics.Stopwatch.StartNew();
    using var resilientClient = new ICoDerClient(new ICoDerClientOptions
    {
        BaseUri = new Uri(sseBaseUrl!),
        AccessToken = accessToken,
    });
    var longEvents = new List<RunStreamEvent>();
    await foreach (var item in resilientClient.AgentRuns.StreamEventsResilientAsync(
        longSseRunId,
        longSseToken,
        new RunStreamRetryOptions
        {
            MaxAttempts = 4,
            InitialDelay = TimeSpan.FromMilliseconds(10),
            MaxDelay = TimeSpan.FromMilliseconds(50),
            JitterRatio = 0,
        }))
    {
        longEvents.Add(item);
    }
    var names = longEvents.Select(item =>
        JsonDocument.Parse(item.Data).RootElement.GetProperty("name").GetString()).ToArray();
    if (!names.SequenceEqual(new[] { "run.ingest", "run.completion", "stream.completed" }))
    {
        throw new InvalidOperationException(
            $"Long SSE tail contract failed: {string.Join(',', names)}");
    }
    using var terminalDocument = JsonDocument.Parse(longEvents[^1].Data);
    var terminalPayload = terminalDocument.RootElement.GetProperty("payload");
    if (terminalPayload.GetProperty("status").GetString() != "COMPLETED" ||
        terminalPayload.GetProperty("event_count").GetInt32() != 2 ||
        startedAt.Elapsed < TimeSpan.FromMilliseconds(300))
    {
        throw new InvalidOperationException("Long SSE terminal contract is incomplete.");
    }
    longSseVerified = "expired-token-renewed-two-disconnects-resumed-terminal";
}

var oauthClientCredentials = "skipped";
ICoDerClient? partnerClient = null;
var runClient = client;
var oauthClientId = Environment.GetEnvironmentVariable("ICODER_E2E_CLIENT_ID");
var oauthClientSecret = Environment.GetEnvironmentVariable("ICODER_E2E_CLIENT_SECRET");
if (!string.IsNullOrWhiteSpace(oauthClientId) && !string.IsNullOrWhiteSpace(oauthClientSecret))
{
    using var authClient = new ICoDerClient(new ICoDerClientOptions
    {
        BaseUri = new Uri(baseUrl),
    });
    var token = await authClient.AuthenticateClientCredentialsAsync(
        oauthClientId, oauthClientSecret);
    if (string.IsNullOrWhiteSpace(token.AccessToken) || token.RefreshToken is not null ||
        token.User is not null)
    {
        throw new InvalidOperationException("Client-credentials token shape is invalid.");
    }
    partnerClient = new ICoDerClient(new ICoDerClientOptions
    {
        BaseUri = new Uri(baseUrl),
        AccessToken = token.AccessToken,
    });
    var oauthHub = await partnerClient.AgentHub.ListAsync();
    if (oauthHub.Total != 26)
    {
        throw new InvalidOperationException("OAuth token could not access Agent Hub.");
    }
    oauthClientCredentials = "form-token-hub";
    runClient = partnerClient;
}

var hub = await client.AgentHub.ListAsync();
if (hub.Total != 26 || hub.Agents.Count != 26 ||
    hub.Agents.Any(agent => !agent.Runnable || !agent.LaunchCandidateReady))
{
    throw new InvalidOperationException(
        $"Agent Hub release-candidate contract failed: total={hub.Total}.");
}

var factsFailedClosed = false;
try
{
    await client.Facts.ExtractAsync(new FactExtractionRequest
    {
        Context = [new FactExtractionContext
        {
            Text = "Synthetic SDK Facts contract smoke only.",
        }],
        OutputLanguage = "zh-CN",
    });
}
catch (ICoDerApiException exception) when (exception.StatusCodeValue == System.Net.HttpStatusCode.ServiceUnavailable)
{
    factsFailedClosed = true;
}
if (!factsFailedClosed)
{
    throw new InvalidOperationException("Credential-free Facts extraction did not fail closed.");
}

var codingFilterReachedServer = false;
try
{
    var coding = await client.MedicalCoding.PredictAsync(new CodingPredictRequest
    {
        Text = "Synthetic coding-filter transport smoke only.",
        CodingSystems = ["icd10cn", "icd9cm3"],
        Filter = new CodingCodeFilter
        {
            Include = ["E11"],
            Exclude = ["E11.9"],
            Expand = true,
        },
    });
    codingFilterReachedServer = coding.Error;
}
catch (ICoDerApiException exception) when (exception.StatusCodeValue == System.Net.HttpStatusCode.ServiceUnavailable)
{
    codingFilterReachedServer = true;
}
if (!codingFilterReachedServer)
{
    throw new InvalidOperationException("Credential-free Coding did not fail closed.");
}

var run = await runClient.AgentRuns.RunTextAsync(
    "note-completeness-agent",
    "SDK contract smoke only; no patient or clinical data.",
    idempotencyKey: $"dotnet-smoke-{Guid.NewGuid():N}",
    purposeOfUse: "treatment");
if (run.AgentId != "note-completeness-agent" || string.IsNullOrWhiteSpace(run.RunId))
{
    throw new InvalidOperationException("Unified Agent Run envelope is incomplete.");
}
if (run.Error)
{
    throw new InvalidOperationException(
        "Deterministic local Note Completeness Agent Run failed unexpectedly.");
}
if (run.Result.ValueKind != JsonValueKind.Object ||
    !run.Result.TryGetProperty("review_conclusion", out var reviewConclusion) ||
    reviewConclusion.ValueKind != JsonValueKind.String ||
    !run.Result.TryGetProperty("completeness_score", out var completenessScore) ||
    completenessScore.ValueKind != JsonValueKind.Number)
{
    throw new InvalidOperationException(
        "Deterministic local Note Completeness result contract is incomplete.");
}
var runStatus = await runClient.AgentRuns.GetAsync(run.RunId);
if (!runStatus.Terminal || runStatus.RunId != run.RunId)
{
    throw new InvalidOperationException(
        "Agent Run status polling did not return the terminal run.");
}
var runCancellation = await runClient.AgentRuns.CancelAsync(
    run.RunId,
    "SDK lifecycle smoke after terminal completion");
if (runCancellation.Outcome != "ALREADY_COMPLETE")
{
    throw new InvalidOperationException(
        $"Unexpected terminal cancellation outcome: {runCancellation.Outcome}.");
}
var traceQueryOffset = run.TraceUrl.IndexOf('?', StringComparison.Ordinal);
var traceToken = (traceQueryOffset >= 0 ? run.TraceUrl[(traceQueryOffset + 1)..] : "")
    .Split('&', StringSplitOptions.RemoveEmptyEntries)
    .Select(item => item.Split('=', 2))
    .Where(item => item.Length == 2 && item[0] == "token")
    .Select(item => System.Net.WebUtility.UrlDecode(item[1]))
    .FirstOrDefault();
if (string.IsNullOrWhiteSpace(traceToken))
{
    throw new InvalidOperationException("Agent Run trace URL has no signed token.");
}
var runEvents = new List<RunStreamEvent>();
await foreach (var item in runClient.AgentRuns.StreamEventsAsync(run.RunId, traceToken))
{
    runEvents.Add(item);
}
if (!runEvents.Any(item => item.Data.Contains("stream.completed", StringComparison.Ordinal)))
{
    throw new InvalidOperationException("Agent Run lifecycle stream did not complete.");
}

var firstTurn = await client.A2A.MessageSendTextAsync(
    "note-completeness-agent",
    "Synthetic SDK context turn one; test phone 13800138000 only.");
var secondTurn = await client.A2A.MessageSendTextAsync(
    "note-completeness-agent",
    "Synthetic SDK context turn two; verify continuation only.",
    firstTurn.ContextId);
if (secondTurn.ContextId != firstTurn.ContextId)
{
    throw new InvalidOperationException("A2A continuation returned a different contextId.");
}
var context = await client.A2A.GetContextAsync(
    "note-completeness-agent", firstTurn.ContextId);
if (context.Id != firstTurn.ContextId || context.Items.Count != 4)
{
    throw new InvalidOperationException(
        $"A2A Context history is incomplete: items={context.Items.Count}.");
}
var serializedContext = JsonSerializer.Serialize(context);
var hasPhoneRedactionMarker =
    serializedContext.Contains("<REDACTED:PHONE>", StringComparison.Ordinal) ||
    serializedContext.Contains("\\u003CREDACTED:PHONE\\u003E", StringComparison.OrdinalIgnoreCase);
if (serializedContext.Contains("13800138000", StringComparison.Ordinal) ||
    !hasPhoneRedactionMarker)
{
    throw new InvalidOperationException("A2A Context did not persist the PHI-redacted view.");
}
var deletedContext = await client.A2A.DeleteContextAsync(firstTurn.ContextId);
if (!deletedContext.Deleted)
{
    throw new InvalidOperationException("A2A Context delete did not confirm deletion.");
}

var interactionId = $"dotnet-sdk-{Guid.NewGuid():N}";
var payload = new byte[] { 0x52, 0x49, 0x46, 0x46, 0x00, 0x00, 0x00, 0x00 };
var recording = await client.SpeechToText.UploadRecordingAsync(
    interactionId,
    payload,
    "audio/wav");
var recordings = await client.SpeechToText.ListRecordingsAsync(interactionId);
if (!recordings.Recordings.Contains(recording.RecordingId))
{
    throw new InvalidOperationException("Uploaded recording was not listed.");
}
var downloaded = await client.SpeechToText.DownloadRecordingAsync(
    interactionId,
    recording.RecordingId);
if (!payload.SequenceEqual(downloaded))
{
    throw new InvalidOperationException("Downloaded recording differs from uploaded bytes.");
}
await client.SpeechToText.DeleteRecordingAsync(interactionId, recording.RecordingId);
var afterDelete = await client.SpeechToText.ListRecordingsAsync(interactionId);
if (afterDelete.Recordings.Contains(recording.RecordingId))
{
    throw new InvalidOperationException("Deleted recording is still listed.");
}

await using (var realtime = await client.SpeechToText.CreateRealtimeSessionAsync())
{
    var ready = realtime.Ready;
    if (ready is null || ready.Type != "ready" ||
        ready.MaxSessionBytes != RealtimeSttSession.MaximumSessionBytes)
    {
        throw new InvalidOperationException("Real-time STT did not acknowledge ready limits.");
    }
    await realtime.CloseAsync();
}

Console.WriteLine(JsonSerializer.Serialize(new
{
    status = "passed",
    hub_total = hub.Total,
    run_error = run.Error,
    run_has_trace = !string.IsNullOrWhiteSpace(run.TraceId),
    run_lifecycle = "status-terminal,cancel-already-complete,sse-completed",
    long_sse = longSseVerified,
    context_roundtrip = "send-continue-get-delete",
    recording_lifecycle = "upload-list-download-delete",
    realtime_stt = "authenticated-start-ready-close",
    oauth_client_credentials = oauthClientCredentials,
    facts_without_real_llm = "failed_closed",
    coding_multi_system_filter_transport = "accepted_and_degraded_without_llm",
}));
partnerClient?.Dispose();
return 0;
