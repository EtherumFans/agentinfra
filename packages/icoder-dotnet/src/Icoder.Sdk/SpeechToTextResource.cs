using System.Net.Http.Headers;

namespace Icoder.Sdk;

public sealed class SpeechToTextResource(ICoDerClient client)
{
    public const int MaximumRecordingBytes = 150 * 1024 * 1024;
    private static readonly HashSet<string> SupportedRecordingMediaTypes = new(StringComparer.OrdinalIgnoreCase)
    {
        "application/octet-stream", "audio/wav", "audio/x-wav", "audio/webm",
        "audio/mpeg", "audio/mp3", "audio/mpeg3", "audio/mp4", "audio/m4a",
        "audio/ogg", "audio/opus", "audio/vorbis", "audio/flac",
    };
    private static readonly HashSet<string> SupportedRealtimeMediaTypes = new(StringComparer.OrdinalIgnoreCase)
    {
        "audio/webm", "audio/wav", "audio/x-wav", "audio/mpeg", "audio/ogg", "audio/mp4",
    };

    public Task<SttReadiness> GetReadinessAsync(
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
        => client.SendAsync<SttReadiness>(
            HttpMethod.Get,
            "/api/v2/tools/stt/readiness",
            cancellationToken: cancellationToken,
            requestOptions: requestOptions);

    public async Task<RealtimeSttSession> CreateRealtimeSessionAsync(
        RealtimeSttSessionOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        options ??= new RealtimeSttSessionOptions();
        ValidateRealtimeOptions(options);
        var token = client.Options.AccessToken;
        if (string.IsNullOrWhiteSpace(token))
        {
            throw new InvalidOperationException(
                "An access token is required for real-time STT.");
        }

        var baseUri = client.Options.BaseUri;
        var builder = new UriBuilder(baseUri)
        {
            Scheme = baseUri.Scheme == Uri.UriSchemeHttps ? "wss" : "ws",
            Path = "/ws/speech-to-text",
            Query = $"token={Uri.EscapeDataString(token)}",
        };
        async Task<System.Net.WebSockets.WebSocket> ConnectSanitizedAsync(
            CancellationToken connectCancellationToken)
        {
            try
            {
                return await client.ConnectWebSocketAsync(
                    builder.Uri, connectCancellationToken).ConfigureAwait(false);
            }
            catch (OperationCanceledException) when (connectCancellationToken.IsCancellationRequested)
            {
                throw;
            }
            catch
            {
                // Connector errors may contain the token-bearing query URI.
                throw new RealtimeSttSessionException("connection_failed", retryable: true);
            }
        }
        System.Net.WebSockets.WebSocket socket;
        using var connectionTimeout = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken);
        connectionTimeout.CancelAfter(client.Options.Timeout);
        try
        {
            socket = await ConnectSanitizedAsync(connectionTimeout.Token).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch
        {
            // Connector errors can include the full query URI. Do not retain
            // the tenant access token in the public exception or InnerException.
            throw new InvalidOperationException(
                "Unable to establish the real-time STT WebSocket connection.");
        }
        var session = new RealtimeSttSession(
            socket,
            client.JsonOptions,
            options,
            ConnectSanitizedAsync,
            client.Options.Timeout);
        try
        {
            await session.InitializeAsync(connectionTimeout.Token).ConfigureAwait(false);
            return session;
        }
        catch
        {
            await session.DisposeAsync().ConfigureAwait(false);
            throw;
        }
    }

    public Task<RecordingCreatedResponse> UploadRecordingAsync(
        string interactionId,
        ReadOnlyMemory<byte> audio,
        string mediaType = "application/octet-stream",
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        ValidateId(interactionId, nameof(interactionId));
        if (audio.IsEmpty)
        {
            throw new ArgumentException("Audio cannot be empty.", nameof(audio));
        }
        if (audio.Length > MaximumRecordingBytes)
        {
            throw new ArgumentOutOfRangeException(
                nameof(audio),
                $"Audio exceeds the {MaximumRecordingBytes}-byte server limit.");
        }
        if (!MediaTypeHeaderValue.TryParse(mediaType, out var parsedMediaType))
        {
            throw new ArgumentException("Invalid media type.", nameof(mediaType));
        }
        if (parsedMediaType.MediaType is null || !SupportedRecordingMediaTypes.Contains(parsedMediaType.MediaType))
        {
            throw new ArgumentException("Unsupported recording media type.", nameof(mediaType));
        }
        var bytes = audio.ToArray();
        return client.SendContentAsync<RecordingCreatedResponse>(
            HttpMethod.Post,
            $"/api/v2/tools/interactions/{Escape(interactionId)}/recordings",
            () =>
            {
                var content = new ByteArrayContent(bytes);
                content.Headers.ContentType = parsedMediaType;
                return content;
            },
            cancellationToken,
            requestOptions);
    }

    public Task<RecordingsListResponse> ListRecordingsAsync(
        string interactionId,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        ValidateId(interactionId, nameof(interactionId));
        return client.SendAsync<RecordingsListResponse>(
            HttpMethod.Get,
            $"/api/v2/tools/interactions/{Escape(interactionId)}/recordings",
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task<byte[]> DownloadRecordingAsync(
        string interactionId,
        string recordingId,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        ValidateId(interactionId, nameof(interactionId));
        ValidateId(recordingId, nameof(recordingId));
        return client.SendBytesAsync(
            HttpMethod.Get,
            $"/api/v2/tools/interactions/{Escape(interactionId)}/recordings/{Escape(recordingId)}",
            cancellationToken,
            requestOptions);
    }

    public Task DeleteRecordingAsync(
        string interactionId,
        string recordingId,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        ValidateId(interactionId, nameof(interactionId));
        ValidateId(recordingId, nameof(recordingId));
        return client.SendNoContentAsync(
            HttpMethod.Delete,
            $"/api/v2/tools/interactions/{Escape(interactionId)}/recordings/{Escape(recordingId)}",
            cancellationToken,
            requestOptions: requestOptions);
    }

    public Task<ICoDerResponse<TranscriptResponse>> CreateTranscriptAsync(
        string interactionId,
        TranscriptCreateRequest request,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        ValidateId(interactionId, nameof(interactionId));
        Guard.NotNull(request, nameof(request));
        ValidateTranscriptRequest(request);
        return client.SendWithMetadataAsync<TranscriptResponse>(
            HttpMethod.Post,
            $"/api/v2/tools/interactions/{Escape(interactionId)}/transcripts",
            request,
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task<TranscriptsListResponse> ListTranscriptsAsync(
        string interactionId,
        bool full = false,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        ValidateId(interactionId, nameof(interactionId));
        return client.SendAsync<TranscriptsListResponse>(
            HttpMethod.Get,
            $"/api/v2/tools/interactions/{Escape(interactionId)}/transcripts?full={full.ToString().ToLowerInvariant()}",
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task<TranscriptResponse> GetTranscriptAsync(
        string interactionId,
        string transcriptId,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        ValidateId(interactionId, nameof(interactionId));
        ValidateId(transcriptId, nameof(transcriptId));
        return client.SendAsync<TranscriptResponse>(
            HttpMethod.Get,
            $"/api/v2/tools/interactions/{Escape(interactionId)}/transcripts/{Escape(transcriptId)}",
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task<TranscriptStatusResponse> GetTranscriptStatusAsync(
        string interactionId,
        string transcriptId,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        ValidateId(interactionId, nameof(interactionId));
        ValidateId(transcriptId, nameof(transcriptId));
        return client.SendAsync<TranscriptStatusResponse>(
            HttpMethod.Get,
            $"/api/v2/tools/interactions/{Escape(interactionId)}/transcripts/{Escape(transcriptId)}/status",
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task DeleteTranscriptAsync(
        string interactionId,
        string transcriptId,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        ValidateId(interactionId, nameof(interactionId));
        ValidateId(transcriptId, nameof(transcriptId));
        return client.SendNoContentAsync(
            HttpMethod.Delete,
            $"/api/v2/tools/interactions/{Escape(interactionId)}/transcripts/{Escape(transcriptId)}",
            cancellationToken,
            requestOptions: requestOptions);
    }

    private static string Escape(string value) => Uri.EscapeDataString(value);

    private static void ValidateTranscriptRequest(TranscriptCreateRequest request)
    {
        if (!request.PrimaryLanguage.StartsWith("zh", StringComparison.OrdinalIgnoreCase))
        {
            throw new ArgumentException(
                "The verified STT runtime currently supports Chinese audio only.",
                nameof(request));
        }
        var unsupported = new List<string>();
        if (request.AutomaticPunctuation is false && request.SpokenPunctuation is not true)
        {
            unsupported.Add("AutomaticPunctuation=false");
        }
        if (request.Diarize is true) unsupported.Add("Diarize");
        var participants = request.Participants ?? [];
        if (participants.Any(item => item is null ||
                item.Role is not ("doctor" or "patient" or "multiple")))
        {
            throw new ArgumentException(
                "Participants require an integer channel and a supported role.",
                nameof(request));
        }
        if (request.IsMultichannel is true)
        {
            var channels = participants.Select(item => item.Channel).OrderBy(item => item).ToArray();
            if (participants.Count != 2 || !channels.SequenceEqual(new[] { 0, 1 }))
            {
                throw new ArgumentException(
                    "Multichannel transcription requires participants for channels 0 and 1.",
                    nameof(request));
            }
        }
        else if (participants.Count > 1)
        {
            unsupported.Add("Participants>1");
        }
        if (unsupported.Count > 0)
        {
            throw new ArgumentException(
                $"Unsupported STT features: {string.Join(", ", unsupported)}.",
                nameof(request));
        }
        if (request.Replacements?.Count > 1000)
        {
            throw new ArgumentException("Replacements cannot exceed 1000 items.", nameof(request));
        }
        var keyterms = request.Keyterms?.Terms;
        if (request.Keyterms is not null && keyterms is null)
        {
            throw new ArgumentException("Keyterms must contain a terms list.", nameof(request));
        }
        if (keyterms?.Count > 1000)
        {
            throw new ArgumentException("Keyterms cannot exceed 1000 items.", nameof(request));
        }
        if (keyterms?.Any(item =>
                item is null || string.IsNullOrEmpty(item.Term) || item.Term.Length > 50) is true)
        {
            throw new ArgumentException(
                "Each keyterm must contain 1 to 50 characters.",
                nameof(request));
        }
    }

    private static void ValidateRealtimeOptions(RealtimeSttSessionOptions options)
    {
        if (string.IsNullOrWhiteSpace(options.Language) || options.Language.Length > 35 ||
            !options.Language.StartsWith("zh", StringComparison.OrdinalIgnoreCase))
        {
            throw new ArgumentException(
                "The verified real-time STT runtime currently supports zh-CN only.",
                nameof(options));
        }
        if (!string.Equals(options.Punctuation, "auto", StringComparison.OrdinalIgnoreCase))
        {
            throw new ArgumentException(
                "Spoken or disabled punctuation is not supported by the verified real-time STT runtime.",
                nameof(options));
        }
        if (string.IsNullOrWhiteSpace(options.MediaType) || options.MediaType.Length > 128 ||
            !MediaTypeHeaderValue.TryParse(options.MediaType, out var parsedMediaType) ||
            parsedMediaType.MediaType is null ||
            !SupportedRealtimeMediaTypes.Contains(parsedMediaType.MediaType))
        {
            throw new ArgumentException(
                "Unsupported real-time STT media type.",
                nameof(options));
        }
        if (options.ReconnectAttempts is < 0 or > 20)
        {
            throw new ArgumentException(
                "ReconnectAttempts must be between 0 and 20.", nameof(options));
        }
        if (options.ReconnectInitialDelay < TimeSpan.Zero ||
            options.ReconnectMaxDelay < options.ReconnectInitialDelay ||
            options.ReconnectMaxDelay > TimeSpan.FromMinutes(1))
        {
            throw new ArgumentException(
                "Real-time STT reconnect delays are invalid.", nameof(options));
        }
    }

    private static void ValidateId(string value, string parameterName)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            throw new ArgumentException("Identifier cannot be empty.", parameterName);
        }
    }
}
