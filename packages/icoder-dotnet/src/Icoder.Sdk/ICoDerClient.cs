using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Net.WebSockets;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Icoder.Sdk;

/// <summary>Typed entry point for the iCoDer HTTP APIs.</summary>
public sealed class ICoDerClient : IDisposable
{
    private static readonly HashSet<string> ProtectedHeaders = new(
        new[]
        {
            "authorization", "proxy-authorization", "cookie", "host",
            "content-length", "content-type", "transfer-encoding", "connection",
            "te", "trailer", "upgrade", "tenant-name",
            "x-icoder-organization-id", "x-organization-id",
        },
        StringComparer.OrdinalIgnoreCase);

    private readonly HttpClient _http;
    private readonly bool _ownsHttpClient;
    private readonly SemaphoreSlim _refreshLock = new(1, 1);
    private readonly Func<Uri, CancellationToken, Task<WebSocket>> _webSocketConnector;
    private bool _disposed;

    internal JsonSerializerOptions JsonOptions { get; } = new(JsonSerializerDefaults.Web)
    {
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
    };

    public ICoDerClientOptions Options { get; }
    public AgentRunsResource AgentRuns { get; }
    public AgentHubResource AgentHub { get; }
    public AgentConnectorsResource AgentConnectors { get; }
    public ExpertsResource Experts { get; }
    public A2AResource A2A { get; }
    public MedicalCodingResource MedicalCoding { get; }
    public SpeechToTextResource SpeechToText { get; }
    public StreamsResource Streams { get; }
    public FactsResource Facts { get; }
    public DocumentsResource Documents { get; }
    public TemplatesResource Templates { get; }
    public PlatformResource Platform { get; }
    public ModelsResource Models { get; }
    public BillingResource Billing { get; }
    public DrgDipRiskReviewResource DrgDipRiskReview { get; }

    public ICoDerClient(
        ICoDerClientOptions options,
        HttpClient? httpClient = null,
        Func<Uri, CancellationToken, Task<WebSocket>>? webSocketConnector = null)
    {
        Options = options ?? throw new ArgumentNullException(nameof(options));
        ValidateBaseUri(options);
        _ownsHttpClient = httpClient is null;
        _http = httpClient ?? new HttpClient();
        _webSocketConnector = webSocketConnector ?? ConnectDefaultWebSocketAsync;
        _http.BaseAddress = options.BaseUri;
        _http.Timeout = Timeout.InfiniteTimeSpan;
        ValidateTransportOptions(options.Timeout, options.MaxRetries);
        ValidateAdditionalHeaders(options.AdditionalHeaders, null, "client option");

        AgentRuns = new AgentRunsResource(this);
        AgentHub = new AgentHubResource(this);
        AgentConnectors = new AgentConnectorsResource(this);
        Experts = new ExpertsResource(this);
        A2A = new A2AResource(this);
        MedicalCoding = new MedicalCodingResource(this);
        SpeechToText = new SpeechToTextResource(this);
        Streams = new StreamsResource(this);
        Facts = new FactsResource(this);
        Documents = new DocumentsResource(this);
        Templates = new TemplatesResource(this);
        Platform = new PlatformResource(this);
        Models = new ModelsResource(this);
        Billing = new BillingResource(this);
        DrgDipRiskReview = new DrgDipRiskReviewResource(this);
    }

    internal async Task<WebSocket> ConnectWebSocketAsync(
        Uri uri,
        CancellationToken cancellationToken)
    {
        ThrowIfDisposed();
        return await _webSocketConnector(uri, cancellationToken).ConfigureAwait(false)
            ?? throw new InvalidOperationException("The WebSocket connector returned null.");
    }

    private static async Task<WebSocket> ConnectDefaultWebSocketAsync(
        Uri uri,
        CancellationToken cancellationToken)
    {
        var socket = new ClientWebSocket();
        try
        {
            await socket.ConnectAsync(uri, cancellationToken).ConfigureAwait(false);
            return socket;
        }
        catch
        {
            socket.Dispose();
            throw;
        }
    }

    /// <summary>Authenticate a machine client without changing the current token.</summary>
    public Task<TokenResponse> AuthenticateClientCredentialsAsync(
        string clientId,
        string clientSecret,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(clientId, nameof(clientId));
        Guard.NotNullOrWhiteSpace(clientSecret, nameof(clientSecret));
        return SendAnonymousFormAsync<TokenResponse>(
            HttpMethod.Post,
            "/api/oauth/token",
            new Dictionary<string, string>
            {
                ["grant_type"] = "client_credentials",
                ["client_id"] = clientId,
                ["client_secret"] = clientSecret,
                ["scope"] = "api:read api:write",
            },
            cancellationToken,
            requestOptions);
    }

    internal async Task<T> SendAsync<T>(
        HttpMethod method,
        string path,
        object? body = null,
        IReadOnlyDictionary<string, string>? headers = null,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
        => (await SendWithMetadataAsync<T>(
                method, path, body, headers, cancellationToken, requestOptions))
            .Value;

    internal async Task<T> SendA2AAsync<T>(
        HttpMethod method,
        string path,
        object? body = null,
        IReadOnlyDictionary<string, string>? headers = null,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
        where T : class
    {
        ThrowIfDisposed();
        var maxRetries = ResolveMaxRetries(requestOptions);
        var retryAttempt = 0;
        var refreshAttempted = false;
        while (true)
        {
            using var timeout = CreateRequestTimeout(requestOptions, cancellationToken);
            using var request = CreateRequest(method, path, body, headers, requestOptions);
            using var response = await _http.SendAsync(request, timeout.Token)
                .ConfigureAwait(false);
            if (response.StatusCode == HttpStatusCode.Unauthorized && !refreshAttempted &&
                await TryRefreshTokenAsync(timeout.Token).ConfigureAwait(false))
            {
                refreshAttempted = true;
                continue;
            }
            if (IsRetryable(response.StatusCode) && retryAttempt < maxRetries)
            {
                retryAttempt++;
                await DelayBeforeRetryAsync(response, retryAttempt, cancellationToken)
                    .ConfigureAwait(false);
                continue;
            }

            A2AJsonRpcEnvelope<T>? envelope;
            try
            {
                envelope = await response.Content
                    .ReadFromJsonAsync<A2AJsonRpcEnvelope<T>>(JsonOptions, timeout.Token)
                    .ConfigureAwait(false);
            }
            catch (JsonException)
            {
                throw new ICoDerApiException(
                    response.StatusCode,
                    "iCoDer returned an invalid A2A JSON response.");
            }
            if (envelope?.Error is not null)
            {
                throw new A2AProtocolException(
                    envelope.Error.Code,
                    envelope.Error.Data?.A2AErrorCode,
                    response.StatusCode);
            }
            if (!response.IsSuccessStatusCode)
            {
                throw new ICoDerApiException(
                    response.StatusCode,
                    "iCoDer A2A request failed without a protocol error envelope.");
            }
            if (envelope?.Result is null)
            {
                throw new ICoDerApiException(
                    response.StatusCode,
                    "iCoDer returned an incomplete A2A response.");
            }
            return envelope.Result;
        }
    }

    internal async Task<T> SendA2AV1Async<T>(
        HttpMethod method,
        string path,
        object? body = null,
        IReadOnlyDictionary<string, string>? headers = null,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
        where T : class
    {
        ThrowIfDisposed();
        var maxRetries = ResolveMaxRetries(requestOptions);
        var retryAttempt = 0;
        var refreshAttempted = false;
        while (true)
        {
            using var timeout = CreateRequestTimeout(requestOptions, cancellationToken);
            using var request = CreateRequest(method, path, body, headers, requestOptions);
            using var response = await _http.SendAsync(request, timeout.Token)
                .ConfigureAwait(false);
            if (response.StatusCode == HttpStatusCode.Unauthorized && !refreshAttempted &&
                await TryRefreshTokenAsync(timeout.Token).ConfigureAwait(false))
            {
                refreshAttempted = true;
                continue;
            }
            if (IsRetryable(response.StatusCode) && retryAttempt < maxRetries)
            {
                retryAttempt++;
                await DelayBeforeRetryAsync(response, retryAttempt, cancellationToken)
                    .ConfigureAwait(false);
                continue;
            }
            await ThrowIfA2AV1FailedAsync(response, timeout.Token).ConfigureAwait(false);
            try
            {
                return await response.Content.ReadFromJsonAsync<T>(JsonOptions, timeout.Token)
                    .ConfigureAwait(false)
                    ?? throw new ICoDerApiException(
                        response.StatusCode,
                        "iCoDer returned an incomplete A2A v1 response.");
            }
            catch (JsonException)
            {
                throw new ICoDerApiException(
                    response.StatusCode,
                    "iCoDer returned an invalid A2A v1 JSON response.");
            }
        }
    }

    internal async IAsyncEnumerable<A2AStreamEvent> SendA2AStreamAsync(
        string path,
        object body,
        IReadOnlyDictionary<string, string>? headers = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        ThrowIfDisposed();
        var streamHeaders = headers is null
            ? new Dictionary<string, string>()
            : headers.ToDictionary(
                item => item.Key, item => item.Value, StringComparer.OrdinalIgnoreCase);
        streamHeaders["Accept"] = "text/event-stream";
        var maxRetries = ResolveMaxRetries(requestOptions);
        var retryAttempt = 0;
        var refreshAttempted = false;
        while (true)
        {
            using var timeout = CreateRequestTimeout(requestOptions, cancellationToken);
            using var request = CreateRequest(
                HttpMethod.Post, path, body, streamHeaders, requestOptions);
            using var response = await _http.SendAsync(
                request,
                HttpCompletionOption.ResponseHeadersRead,
                timeout.Token).ConfigureAwait(false);
            if (response.StatusCode == HttpStatusCode.Unauthorized && !refreshAttempted &&
                await TryRefreshTokenAsync(timeout.Token).ConfigureAwait(false))
            {
                refreshAttempted = true;
                continue;
            }
            if (IsRetryable(response.StatusCode) && retryAttempt < maxRetries)
            {
                retryAttempt++;
                await DelayBeforeRetryAsync(response, retryAttempt, cancellationToken)
                    .ConfigureAwait(false);
                continue;
            }
            if (headers?.ContainsKey("A2A-Version") == true)
            {
                await ThrowIfA2AV1FailedAsync(response, timeout.Token)
                    .ConfigureAwait(false);
            }
            else
            {
                await ThrowIfFailedAsync(response, timeout.Token)
                    .ConfigureAwait(false);
            }
            if (!string.Equals(
                    response.Content.Headers.ContentType?.MediaType,
                    "text/event-stream",
                    StringComparison.OrdinalIgnoreCase))
            {
                throw new ICoDerApiException(
                    response.StatusCode,
                    "iCoDer returned a non-SSE A2A stream response.");
            }

            // Timeout governs the HTTP handshake. Once headers establish a
            // valid SSE stream, only caller cancellation limits its lifetime.
            timeout.CancelAfter(Timeout.InfiniteTimeSpan);

            using var stream = await Compatibility
                .ReadAsStreamAsync(response.Content, timeout.Token).ConfigureAwait(false);
            using var reader = new StreamReader(stream);
            var eventName = "message";
            string? eventId = null;
            var dataLines = new List<string>();
            while (await Compatibility.ReadLineAsync(reader, timeout.Token)
                       .ConfigureAwait(false) is { } line)
            {
                if (line.Length == 0)
                {
                    if (dataLines.Count > 0)
                    {
                        yield return new A2AStreamEvent
                        {
                            Event = eventName,
                            Data = string.Join("\n", dataLines),
                            Id = eventId,
                        };
                    }
                    eventName = "message";
                    eventId = null;
                    dataLines.Clear();
                    continue;
                }
                if (line.StartsWith("event:", StringComparison.Ordinal))
                {
                    eventName = line.Substring(6).TrimStart();
                }
                else if (line.StartsWith("data:", StringComparison.Ordinal))
                {
                    dataLines.Add(line.Substring(5).TrimStart());
                }
                else if (line.StartsWith("id:", StringComparison.Ordinal))
                {
                    eventId = line.Substring(3).TrimStart();
                }
            }
            if (dataLines.Count > 0)
            {
                yield return new A2AStreamEvent
                {
                    Event = eventName,
                    Data = string.Join("\n", dataLines),
                    Id = eventId,
                };
            }
            yield break;
        }
    }

    internal async IAsyncEnumerable<A2AStreamEvent> SendA2AV1TaskEventsAsync(
        string path,
        IReadOnlyDictionary<string, string>? headers = null,
        string? lastEventId = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        ThrowIfDisposed();
        var streamHeaders = headers is null
            ? new Dictionary<string, string>()
            : headers.ToDictionary(
                item => item.Key, item => item.Value, StringComparer.OrdinalIgnoreCase);
        streamHeaders["Accept"] = "text/event-stream";
        if (!string.IsNullOrWhiteSpace(lastEventId))
        {
            streamHeaders["Last-Event-ID"] = lastEventId!;
        }
        var maxRetries = ResolveMaxRetries(requestOptions);
        var retryAttempt = 0;
        var refreshAttempted = false;
        while (true)
        {
            using var timeout = CreateRequestTimeout(requestOptions, cancellationToken);
            using var request = CreateRequest(
                HttpMethod.Get, path, null, streamHeaders, requestOptions);
            using var response = await _http.SendAsync(
                request,
                HttpCompletionOption.ResponseHeadersRead,
                timeout.Token).ConfigureAwait(false);
            if (response.StatusCode == HttpStatusCode.Unauthorized && !refreshAttempted &&
                await TryRefreshTokenAsync(timeout.Token).ConfigureAwait(false))
            {
                refreshAttempted = true;
                continue;
            }
            if (IsRetryable(response.StatusCode) && retryAttempt < maxRetries)
            {
                retryAttempt++;
                await DelayBeforeRetryAsync(response, retryAttempt, cancellationToken)
                    .ConfigureAwait(false);
                continue;
            }
            await ThrowIfA2AV1FailedAsync(response, timeout.Token).ConfigureAwait(false);
            if (!string.Equals(
                    response.Content.Headers.ContentType?.MediaType,
                    "text/event-stream",
                    StringComparison.OrdinalIgnoreCase))
            {
                throw new ICoDerApiException(
                    response.StatusCode,
                    "iCoDer returned a non-SSE A2A v1 Task subscription.");
            }

            // Keep long-lived subscriptions alive after the bounded handshake.
            timeout.CancelAfter(Timeout.InfiniteTimeSpan);

            using var stream = await Compatibility
                .ReadAsStreamAsync(response.Content, timeout.Token).ConfigureAwait(false);
            using var reader = new StreamReader(stream);
            var eventName = "message";
            string? eventId = null;
            var dataLines = new List<string>();
            while (await Compatibility.ReadLineAsync(reader, timeout.Token)
                       .ConfigureAwait(false) is { } line)
            {
                if (line.Length == 0)
                {
                    if (dataLines.Count > 0)
                    {
                        yield return new A2AStreamEvent
                        {
                            Event = eventName,
                            Data = string.Join("\n", dataLines),
                            Id = eventId,
                        };
                    }
                    eventName = "message";
                    eventId = null;
                    dataLines.Clear();
                }
                else if (line.StartsWith("event:", StringComparison.Ordinal))
                {
                    eventName = line.Substring(6).TrimStart();
                }
                else if (line.StartsWith("data:", StringComparison.Ordinal))
                {
                    dataLines.Add(line.Substring(5).TrimStart());
                }
                else if (line.StartsWith("id:", StringComparison.Ordinal))
                {
                    eventId = line.Substring(3).TrimStart();
                }
            }
            if (dataLines.Count > 0)
            {
                yield return new A2AStreamEvent
                {
                    Event = eventName,
                    Data = string.Join("\n", dataLines),
                    Id = eventId,
                };
            }
            yield break;
        }
    }

    internal async IAsyncEnumerable<RunStreamEvent> SendRunEventsAsync(
        string path,
        string? lastEventId = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        ThrowIfDisposed();
        var headers = new Dictionary<string, string>
        {
            ["Accept"] = "text/event-stream",
        };
        if (!string.IsNullOrWhiteSpace(lastEventId))
        {
            headers["Last-Event-ID"] = lastEventId!;
        }
        var maxRetries = ResolveMaxRetries(requestOptions);
        var retryAttempt = 0;
        HttpResponseMessage? openedResponse = null;
        while (true)
        {
            using var timeout = CreateRequestTimeout(requestOptions, cancellationToken);
            using var request = CreateRequest(
                HttpMethod.Get, path, null, headers, requestOptions);
            var candidate = await _http.SendAsync(
                request,
                HttpCompletionOption.ResponseHeadersRead,
                timeout.Token).ConfigureAwait(false);
            if (IsRetryable(candidate.StatusCode) && retryAttempt < maxRetries)
            {
                retryAttempt++;
                await DelayBeforeRetryAsync(candidate, retryAttempt, cancellationToken)
                    .ConfigureAwait(false);
                candidate.Dispose();
                continue;
            }
            openedResponse = candidate;
            break;
        }
        using var response = openedResponse;
        // This endpoint authenticates with a signed trace token in the query.
        // A 401 therefore means the trace token is invalid; refreshing the
        // bearer token would hide the real failure and needlessly replay it.
        await ThrowIfFailedAsync(response, cancellationToken).ConfigureAwait(false);
        if (!string.Equals(
                response.Content.Headers.ContentType?.MediaType,
                "text/event-stream",
                StringComparison.OrdinalIgnoreCase))
        {
            throw new ICoDerApiException(
                response.StatusCode,
                "iCoDer returned a non-SSE run event response.");
        }

        using var stream = await Compatibility
            .ReadAsStreamAsync(response.Content, cancellationToken).ConfigureAwait(false);
        using var reader = new StreamReader(stream);
        var eventName = "message";
        string? eventId = null;
        var dataLines = new List<string>();
        while (await Compatibility.ReadLineAsync(reader, cancellationToken)
                   .ConfigureAwait(false) is { } line)
        {
            if (line.Length == 0)
            {
                if (dataLines.Count > 0)
                {
                    yield return new RunStreamEvent
                    {
                        Event = eventName,
                        Data = string.Join("\n", dataLines),
                        Id = eventId,
                    };
                }
                eventName = "message";
                eventId = null;
                dataLines.Clear();
                continue;
            }
            if (line.StartsWith("event:", StringComparison.Ordinal))
            {
                eventName = line.Substring(6).TrimStart();
            }
            else if (line.StartsWith("data:", StringComparison.Ordinal))
            {
                dataLines.Add(line.Substring(5).TrimStart());
            }
            else if (line.StartsWith("id:", StringComparison.Ordinal))
            {
                eventId = line.Substring(3).TrimStart();
            }
        }
        if (dataLines.Count > 0)
        {
            yield return new RunStreamEvent
            {
                Event = eventName,
                Data = string.Join("\n", dataLines),
                Id = eventId,
            };
        }
    }

    internal async Task<ICoDerResponse<T>> SendWithMetadataAsync<T>(
        HttpMethod method,
        string path,
        object? body = null,
        IReadOnlyDictionary<string, string>? headers = null,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        ThrowIfDisposed();
        var maxRetries = ResolveMaxRetries(requestOptions);
        var retryAttempt = 0;
        var refreshAttempted = false;
        while (true)
        {
            using var timeout = CreateRequestTimeout(requestOptions, cancellationToken);
            using var request = CreateRequest(method, path, body, headers, requestOptions);
            using var response = await _http.SendAsync(request, timeout.Token)
                .ConfigureAwait(false);
            if (response.StatusCode == HttpStatusCode.Unauthorized && !refreshAttempted &&
                await TryRefreshTokenAsync(timeout.Token).ConfigureAwait(false))
            {
                refreshAttempted = true;
                continue;
            }
            if (IsRetryable(response.StatusCode) && retryAttempt < maxRetries)
            {
                retryAttempt++;
                await DelayBeforeRetryAsync(response, retryAttempt, cancellationToken)
                    .ConfigureAwait(false);
                continue;
            }

            await ThrowIfFailedAsync(response, timeout.Token).ConfigureAwait(false);
            var value = await response.Content.ReadFromJsonAsync<T>(JsonOptions, timeout.Token)
                .ConfigureAwait(false);
            if (value is null)
            {
                throw new ICoDerApiException(
                    response.StatusCode,
                    "iCoDer returned an empty JSON response.");
            }
            return new ICoDerResponse<T>(value, response.StatusCode, response.Headers.Location)
            {
                Headers = SnapshotHeaders(response),
            };
        }
    }

    internal async Task<T> SendContentAsync<T>(
        HttpMethod method,
        string path,
        Func<HttpContent> contentFactory,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        ThrowIfDisposed();
        Guard.NotNull(contentFactory, nameof(contentFactory));
        var maxRetries = ResolveMaxRetries(requestOptions);
        var retryAttempt = 0;
        var refreshAttempted = false;
        while (true)
        {
            using var timeout = CreateRequestTimeout(requestOptions, cancellationToken);
            using var request = new HttpRequestMessage(
                method,
                MergeAdditionalQueryParameters(path, requestOptions?.AdditionalQueryParameters));
            AttachAuthorization(request);
            ApplyAdditionalHeaders(
                request, Options.AdditionalHeaders, null, "client option");
            ApplyAdditionalHeaders(
                request, requestOptions?.AdditionalHeaders, null, "request option");
            request.Content = contentFactory();
            using var response = await _http.SendAsync(request, timeout.Token)
                .ConfigureAwait(false);
            if (response.StatusCode == HttpStatusCode.Unauthorized && !refreshAttempted &&
                await TryRefreshTokenAsync(timeout.Token).ConfigureAwait(false))
            {
                refreshAttempted = true;
                continue;
            }
            if (IsRetryable(response.StatusCode) && retryAttempt < maxRetries)
            {
                retryAttempt++;
                await DelayBeforeRetryAsync(response, retryAttempt, cancellationToken)
                    .ConfigureAwait(false);
                continue;
            }
            await ThrowIfFailedAsync(response, timeout.Token).ConfigureAwait(false);
            var value = await response.Content.ReadFromJsonAsync<T>(JsonOptions, timeout.Token)
                .ConfigureAwait(false);
            return value ?? throw new ICoDerApiException(
                response.StatusCode,
                "iCoDer returned an empty JSON response.");
        }
    }

    internal async Task<byte[]> SendBytesAsync(
        HttpMethod method,
        string path,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null,
        bool allowRetries = true)
    {
        ThrowIfDisposed();
        var maxRetries = allowRetries ? ResolveMaxRetries(requestOptions) : 0;
        var retryAttempt = 0;
        var refreshAttempted = false;
        while (true)
        {
            using var timeout = CreateRequestTimeout(requestOptions, cancellationToken);
            using var request = CreateRequest(method, path, null, null, requestOptions);
            using var response = await _http.SendAsync(request, timeout.Token)
                .ConfigureAwait(false);
            if (response.StatusCode == HttpStatusCode.Unauthorized && !refreshAttempted &&
                await TryRefreshTokenAsync(timeout.Token).ConfigureAwait(false))
            {
                refreshAttempted = true;
                continue;
            }
            if (IsRetryable(response.StatusCode) && retryAttempt < maxRetries)
            {
                retryAttempt++;
                await DelayBeforeRetryAsync(response, retryAttempt, cancellationToken)
                    .ConfigureAwait(false);
                continue;
            }
            await ThrowIfFailedAsync(response, timeout.Token).ConfigureAwait(false);
            return await Compatibility.ReadAsByteArrayAsync(response.Content, timeout.Token)
                .ConfigureAwait(false);
        }
    }

    internal async Task SendNoContentAsync(
        HttpMethod method,
        string path,
        CancellationToken cancellationToken = default,
        IReadOnlyDictionary<string, string>? headers = null,
        ICoDerRequestOptions? requestOptions = null)
    {
        ThrowIfDisposed();
        var maxRetries = ResolveMaxRetries(requestOptions);
        var retryAttempt = 0;
        var refreshAttempted = false;
        while (true)
        {
            using var timeout = CreateRequestTimeout(requestOptions, cancellationToken);
            using var request = CreateRequest(method, path, null, headers, requestOptions);
            using var response = await _http.SendAsync(request, timeout.Token).ConfigureAwait(false);
            if (response.StatusCode == HttpStatusCode.Unauthorized && !refreshAttempted &&
                await TryRefreshTokenAsync(timeout.Token).ConfigureAwait(false))
            {
                refreshAttempted = true;
                continue;
            }
            if (IsRetryable(response.StatusCode) && retryAttempt < maxRetries)
            {
                retryAttempt++;
                await DelayBeforeRetryAsync(response, retryAttempt, cancellationToken)
                    .ConfigureAwait(false);
                continue;
            }
            await ThrowIfFailedAsync(response, timeout.Token).ConfigureAwait(false);
            return;
        }
    }

    private HttpRequestMessage CreateRequest(
        HttpMethod method,
        string path,
        object? body,
        IReadOnlyDictionary<string, string>? headers,
        ICoDerRequestOptions? requestOptions = null)
    {
        ValidateRequestOptions(requestOptions);
        var request = new HttpRequestMessage(
            method,
            MergeAdditionalQueryParameters(path, requestOptions?.AdditionalQueryParameters));
        AttachAuthorization(request);
        if (body is not null)
        {
            request.Content = JsonContent.Create(body, options: JsonOptions);
        }
        ApplyAdditionalHeaders(request, Options.AdditionalHeaders, headers, "client option");
        ApplyAdditionalHeaders(
            request, requestOptions?.AdditionalHeaders, headers, "request option");
        if (headers is not null)
        {
            foreach (var item in headers)
            {
                if (!request.Headers.TryAddWithoutValidation(item.Key, item.Value))
                {
                    throw new ArgumentException(
                        $"Resource header {item.Key} is invalid.", nameof(headers));
                }
            }
        }
        return request;
    }

    private static void ValidateTransportOptions(TimeSpan timeout, int maxRetries)
    {
        if (timeout <= TimeSpan.Zero || timeout > TimeSpan.FromHours(1))
        {
            throw new ArgumentOutOfRangeException(
                nameof(timeout), "Timeout must be greater than zero and at most one hour.");
        }
        if (maxRetries < 0 || maxRetries > 10)
        {
            throw new ArgumentOutOfRangeException(
                nameof(maxRetries), "MaxRetries must be between 0 and 10.");
        }
    }

    private void ValidateRequestOptions(ICoDerRequestOptions? requestOptions)
    {
        if (requestOptions is null)
        {
            return;
        }
        ValidateTransportOptions(
            requestOptions.Timeout ?? Options.Timeout,
            requestOptions.MaxRetries ?? Options.MaxRetries);
        ValidateAdditionalHeaders(
            requestOptions.AdditionalHeaders, null, "request option");
        ValidateAdditionalQueryParameters(requestOptions.AdditionalQueryParameters);
    }

    private int ResolveMaxRetries(ICoDerRequestOptions? requestOptions)
    {
        ValidateRequestOptions(requestOptions);
        return requestOptions?.MaxRetries ?? Options.MaxRetries;
    }

    private CancellationTokenSource CreateRequestTimeout(
        ICoDerRequestOptions? requestOptions,
        CancellationToken cancellationToken)
    {
        var timeout = requestOptions?.Timeout ?? Options.Timeout;
        ValidateTransportOptions(timeout, requestOptions?.MaxRetries ?? Options.MaxRetries);
        var source = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        source.CancelAfter(timeout);
        return source;
    }

    private static bool IsRetryable(HttpStatusCode statusCode)
        => statusCode == HttpStatusCode.RequestTimeout ||
           (int)statusCode == 429 ||
           (int)statusCode >= 500;

    private static async Task DelayBeforeRetryAsync(
        HttpResponseMessage response,
        int retryAttempt,
        CancellationToken cancellationToken)
    {
        var delay = response.Headers.RetryAfter?.Delta;
        if (delay is null && response.Headers.RetryAfter?.Date is { } retryAt)
        {
            delay = retryAt - DateTimeOffset.UtcNow;
        }
        if (delay is null || delay < TimeSpan.Zero)
        {
            delay = TimeSpan.FromMilliseconds(
                Math.Min(2_000, 250 * Math.Pow(2, retryAttempt - 1)));
        }
        if (delay > TimeSpan.FromSeconds(30))
        {
            delay = TimeSpan.FromSeconds(30);
        }
        await Task.Delay(delay.Value, cancellationToken).ConfigureAwait(false);
    }

    private string MergeAdditionalQueryParameters(
        string path,
        IReadOnlyDictionary<string, string>? additional)
    {
        if (string.IsNullOrWhiteSpace(path) || path.Contains('#'))
        {
            throw new ArgumentException(
                "SDK request paths must be same-origin paths without fragments.",
                nameof(path));
        }
        if (Uri.TryCreate(path, UriKind.Absolute, out var absolute))
        {
            if (!string.Equals(absolute.Scheme, Options.BaseUri.Scheme, StringComparison.OrdinalIgnoreCase) ||
                !string.Equals(absolute.Host, Options.BaseUri.Host, StringComparison.OrdinalIgnoreCase) ||
                absolute.Port != Options.BaseUri.Port ||
                !string.IsNullOrEmpty(absolute.UserInfo))
            {
                throw new ArgumentException(
                    "SDK request URLs must use the configured API origin.", nameof(path));
            }
        }
        else if (!path.StartsWith("/", StringComparison.Ordinal) ||
                 path.StartsWith("//", StringComparison.Ordinal))
        {
            throw new ArgumentException(
                "SDK request paths must be same-origin absolute paths.", nameof(path));
        }
        if (additional is null || additional.Count == 0)
        {
            return path;
        }
        ValidateAdditionalQueryParameters(additional);
        var separator = path.IndexOf('?');
        var existingQuery = separator >= 0 ? path.Substring(separator + 1) : string.Empty;
        var existingNames = new HashSet<string>(StringComparer.Ordinal);
        foreach (var pair in existingQuery.Split(
                     new[] { '&' }, StringSplitOptions.RemoveEmptyEntries))
        {
            var equal = pair.IndexOf('=');
            var encodedName = equal >= 0 ? pair.Substring(0, equal) : pair;
            existingNames.Add(Uri.UnescapeDataString(encodedName.Replace("+", "%20")));
        }
        foreach (var item in additional)
        {
            if (existingNames.Contains(item.Key))
            {
                throw new ArgumentException(
                    $"Request option query parameter {item.Key} conflicts with a resource parameter.",
                    nameof(additional));
            }
        }
        var suffix = string.Join("&", additional.Select(item =>
            $"{Uri.EscapeDataString(item.Key)}={Uri.EscapeDataString(item.Value)}"));
        return path + (separator >= 0 ? "&" : "?") + suffix;
    }

    private static void ValidateAdditionalQueryParameters(
        IReadOnlyDictionary<string, string>? values)
    {
        if (values is null)
        {
            return;
        }
        foreach (var item in values)
        {
            if (string.IsNullOrWhiteSpace(item.Key) || item.Key.Length > 128 ||
                item.Key.Any(character => char.IsControl(character)))
            {
                throw new ArgumentException(
                    "Request option query parameters contain an invalid name.",
                    nameof(values));
            }
            if (item.Value is null || item.Value.Length > 8192)
            {
                throw new ArgumentException(
                    $"Request option query parameter {item.Key} has an invalid value.",
                    nameof(values));
            }
        }
    }

    private static void ApplyAdditionalHeaders(
        HttpRequestMessage request,
        IReadOnlyDictionary<string, string?>? values,
        IReadOnlyDictionary<string, string>? resourceHeaders,
        string source)
    {
        ValidateAdditionalHeaders(values, resourceHeaders, source);
        if (values is null)
        {
            return;
        }
        foreach (var item in values)
        {
            request.Headers.Remove(item.Key);
            if (!request.Headers.TryAddWithoutValidation(item.Key, item.Value))
            {
                throw new ArgumentException(
                    $"{source} header {item.Key} is invalid.", nameof(values));
            }
        }
    }

    private static void ValidateAdditionalHeaders(
        IReadOnlyDictionary<string, string?>? values,
        IReadOnlyDictionary<string, string>? resourceHeaders,
        string source)
    {
        if (values is null)
        {
            return;
        }
        var domainNames = resourceHeaders is null
            ? new HashSet<string>(StringComparer.OrdinalIgnoreCase)
            : new HashSet<string>(resourceHeaders.Keys, StringComparer.OrdinalIgnoreCase);
        foreach (var item in values)
        {
            var name = item.Key?.Trim() ?? string.Empty;
            if (!IsValidHeaderName(name))
            {
                throw new ArgumentException(
                    $"{source} headers contain an invalid name.", nameof(values));
            }
            if (ProtectedHeaders.Contains(name))
            {
                throw new ArgumentException(
                    $"{source} header {name} is controlled by the SDK.", nameof(values));
            }
            if (domainNames.Contains(name))
            {
                throw new ArgumentException(
                    $"{source} header {name} conflicts with a resource header.", nameof(values));
            }
            if (item.Value is null || item.Value.Length > 4096 ||
                item.Value.Contains('\r') || item.Value.Contains('\n'))
            {
                throw new ArgumentException(
                    $"{source} header {name} has an invalid value.", nameof(values));
            }
        }
    }

    private static bool IsValidHeaderName(string name)
    {
        if (name.Length == 0 || name.Length > 128)
        {
            return false;
        }
        const string punctuation = "!#$%&'*+-.^_`|~";
        return name.All(character =>
            Compatibility.IsAsciiLetterOrDigit(character) || punctuation.Contains(character));
    }

    private void AttachAuthorization(HttpRequestMessage request)
    {
        if (!string.IsNullOrWhiteSpace(Options.AccessToken))
        {
            request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", Options.AccessToken);
        }
    }

    private async Task<T> SendAnonymousAsync<T>(
        HttpMethod method,
        string path,
        object body,
        CancellationToken cancellationToken,
        ICoDerRequestOptions? requestOptions = null)
    {
        var maxRetries = ResolveMaxRetries(requestOptions);
        for (var attempt = 0; ; attempt++)
        {
            using var timeout = CreateRequestTimeout(requestOptions, cancellationToken);
            using var request = new HttpRequestMessage(
                method,
                MergeAdditionalQueryParameters(path, requestOptions?.AdditionalQueryParameters))
            {
                Content = JsonContent.Create(body, options: JsonOptions),
            };
            ApplyAdditionalHeaders(
                request, Options.AdditionalHeaders, null, "client option");
            ApplyAdditionalHeaders(
                request, requestOptions?.AdditionalHeaders, null, "request option");
            using var response = await _http.SendAsync(request, timeout.Token).ConfigureAwait(false);
            if (IsRetryable(response.StatusCode) && attempt < maxRetries)
            {
                await DelayBeforeRetryAsync(response, attempt + 1, cancellationToken)
                    .ConfigureAwait(false);
                continue;
            }
            await ThrowIfFailedAsync(response, timeout.Token).ConfigureAwait(false);
            return await response.Content.ReadFromJsonAsync<T>(JsonOptions, timeout.Token)
                .ConfigureAwait(false)
                ?? throw new ICoDerApiException(
                    response.StatusCode, "iCoDer returned an empty JSON response.");
        }
    }

    private async Task<T> SendAnonymousFormAsync<T>(
        HttpMethod method,
        string path,
        IReadOnlyDictionary<string, string> fields,
        CancellationToken cancellationToken,
        ICoDerRequestOptions? requestOptions = null)
    {
        var maxRetries = ResolveMaxRetries(requestOptions);
        for (var attempt = 0; ; attempt++)
        {
            using var timeout = CreateRequestTimeout(requestOptions, cancellationToken);
            using var request = new HttpRequestMessage(
                method,
                MergeAdditionalQueryParameters(path, requestOptions?.AdditionalQueryParameters))
            {
                Content = new FormUrlEncodedContent(fields),
            };
            ApplyAdditionalHeaders(
                request, Options.AdditionalHeaders, null, "client option");
            ApplyAdditionalHeaders(
                request, requestOptions?.AdditionalHeaders, null, "request option");
            using var response = await _http.SendAsync(request, timeout.Token).ConfigureAwait(false);
            if (IsRetryable(response.StatusCode) && attempt < maxRetries)
            {
                await DelayBeforeRetryAsync(response, attempt + 1, cancellationToken)
                    .ConfigureAwait(false);
                continue;
            }
            await ThrowIfFailedAsync(response, timeout.Token).ConfigureAwait(false);
            return await response.Content.ReadFromJsonAsync<T>(JsonOptions, timeout.Token)
                .ConfigureAwait(false)
                ?? throw new ICoDerApiException(
                    response.StatusCode, "iCoDer returned an empty JSON response.");
        }
    }

    private async Task<bool> TryRefreshTokenAsync(CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(Options.RefreshToken))
        {
            return false;
        }
        var tokenBeforeWait = Options.AccessToken;
        await _refreshLock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            if (!string.Equals(tokenBeforeWait, Options.AccessToken, StringComparison.Ordinal))
            {
                return true;
            }
            try
            {
                var tokens = await SendAnonymousAsync<TokenResponse>(
                    HttpMethod.Post,
                    "/api/auth/refresh",
                    new { refresh_token = Options.RefreshToken },
                    cancellationToken).ConfigureAwait(false);
                Options.AccessToken = tokens.AccessToken;
                Options.RefreshToken = tokens.RefreshToken ?? Options.RefreshToken;
                Options.OnTokenRefreshed?.Invoke(tokens);
                return true;
            }
            catch (ICoDerApiException)
            {
                return false;
            }
        }
        finally
        {
            _refreshLock.Release();
        }
    }

    private static async Task ThrowIfFailedAsync(
        HttpResponseMessage response,
        CancellationToken cancellationToken)
    {
        if (response.IsSuccessStatusCode)
        {
            return;
        }

        var detail = response.ReasonPhrase ?? "iCoDer request failed.";
        string? code = null;
        string? requestId = null;
        int? retentionDays = null;
        try
        {
            using var stream = await Compatibility
                .ReadAsStreamAsync(response.Content, cancellationToken).ConfigureAwait(false);
            using var document = await JsonDocument.ParseAsync(stream, cancellationToken: cancellationToken)
                .ConfigureAwait(false);
            var root = document.RootElement;
            if (root.TryGetProperty("detail", out var detailNode))
            {
                if (detailNode.ValueKind == JsonValueKind.String)
                {
                    detail = detailNode.GetString() ?? detail;
                }
                else if (detailNode.ValueKind == JsonValueKind.Object)
                {
                    detail = ReadString(detailNode, "detail") ?? detail;
                    code = ReadString(detailNode, "type") ?? ReadString(detailNode, "code");
                    requestId = ReadString(detailNode, "requestid") ?? ReadString(detailNode, "request_id");
                    retentionDays = ReadPositiveInt(detailNode, "retention_days");
                }
            }
            code ??= ReadString(root, "type") ?? ReadString(root, "code");
            requestId ??= ReadString(root, "requestid") ?? ReadString(root, "request_id");
        }
        catch (JsonException)
        {
            // Do not retain or expose a non-JSON response body; it may contain PHI.
        }

        if (detail.Length > 512)
        {
            detail = detail.Substring(0, 512);
        }
        if (response.StatusCode == HttpStatusCode.Gone && code is
            "SSE_CURSOR_EXPIRED" or "SSE_TRACE_EXPIRED" or "TRACE_EXPIRED")
        {
            throw new RunEventRetentionException(code, retentionDays, requestId);
        }
        throw new ICoDerApiException(response.StatusCode, detail, code, requestId);
    }

    private static async Task ThrowIfA2AV1FailedAsync(
        HttpResponseMessage response,
        CancellationToken cancellationToken)
    {
        if (response.IsSuccessStatusCode) return;
        try
        {
            using var stream = await Compatibility
                .ReadAsStreamAsync(response.Content, cancellationToken).ConfigureAwait(false);
            using var document = await JsonDocument.ParseAsync(
                stream,
                cancellationToken: cancellationToken).ConfigureAwait(false);
            if (document.RootElement.TryGetProperty("error", out var error) &&
                error.ValueKind == JsonValueKind.Object)
            {
                var code = error.TryGetProperty("code", out var codeNode) &&
                           codeNode.TryGetInt32(out var parsedCode)
                    ? parsedCode
                    : (int)response.StatusCode;
                var reason = ReadA2AV1Reason(error);
                throw new A2AProtocolException(code, reason, response.StatusCode);
            }
        }
        catch (JsonException)
        {
            // Never retain an invalid/raw response body; it may contain PHI.
        }
        throw new ICoDerApiException(
            response.StatusCode,
            "iCoDer A2A v1 request failed without a protocol error envelope.");
    }

    private static string? ReadA2AV1Reason(JsonElement error)
    {
        if (error.TryGetProperty("data", out var data) && data.ValueKind == JsonValueKind.Object)
        {
            var legacy = ReadString(data, "a2a_error_code");
            if (!string.IsNullOrWhiteSpace(legacy)) return legacy;
        }
        foreach (var property in new[] { "data", "details" })
        {
            if (!error.TryGetProperty(property, out var details) ||
                details.ValueKind != JsonValueKind.Array)
            {
                continue;
            }
            foreach (var detail in details.EnumerateArray())
            {
                if (detail.ValueKind != JsonValueKind.Object) continue;
                var reason = ReadString(detail, "reason");
                if (!string.IsNullOrWhiteSpace(reason)) return reason;
            }
        }
        return null;
    }

    private static string? ReadString(JsonElement element, string property)
        => element.TryGetProperty(property, out var value) && value.ValueKind == JsonValueKind.String
            ? value.GetString()
            : null;

    private static int? ReadPositiveInt(JsonElement element, string property)
        => element.TryGetProperty(property, out var value) &&
           value.ValueKind == JsonValueKind.Number &&
           value.TryGetInt32(out var number) && number > 0
            ? number
            : null;

    private static IReadOnlyDictionary<string, IReadOnlyList<string>> SnapshotHeaders(
        HttpResponseMessage response)
    {
        var headers = new Dictionary<string, IReadOnlyList<string>>(
            StringComparer.OrdinalIgnoreCase);
        foreach (var header in response.Headers)
        {
            headers[header.Key] = header.Value.ToArray();
        }
        foreach (var header in response.Content.Headers)
        {
            headers[header.Key] = header.Value.ToArray();
        }
        return headers;
    }

    private static void ValidateBaseUri(ICoDerClientOptions options)
    {
        if (!options.BaseUri.IsAbsoluteUri ||
            (options.BaseUri.Scheme != Uri.UriSchemeHttps && options.BaseUri.Scheme != Uri.UriSchemeHttp))
        {
            throw new ArgumentException("BaseUri must be an absolute HTTP(S) URI.", nameof(options));
        }
        if (options.BaseUri.Scheme == Uri.UriSchemeHttp &&
            !options.AllowInsecureHttp &&
            !options.BaseUri.IsLoopback)
        {
            throw new ArgumentException(
                "Non-loopback HTTP requires AllowInsecureHttp=true; use HTTPS for PHI traffic.",
                nameof(options));
        }
    }

    private void ThrowIfDisposed()
    {
        Guard.NotDisposed(_disposed, this);
    }

    public void Dispose()
    {
        if (_disposed)
        {
            return;
        }
        _disposed = true;
        _refreshLock.Dispose();
        if (_ownsHttpClient)
        {
            _http.Dispose();
        }
    }
}
