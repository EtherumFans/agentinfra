using System.Net.WebSockets;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Icoder.Sdk;

public sealed record StreamsParticipant
{
    [JsonPropertyName("channel")]
    public required int Channel { get; init; }

    [JsonPropertyName("role")]
    public required string Role { get; init; }
}

public sealed record StreamsTranscriptionConfiguration
{
    [JsonPropertyName("primaryLanguage")]
    public required string PrimaryLanguage { get; init; }

    [JsonPropertyName("diarize")]
    public bool Diarize { get; init; }

    [JsonPropertyName("isMultichannel")]
    public bool IsMultichannel { get; init; }

    [JsonPropertyName("participants")]
    public IReadOnlyList<StreamsParticipant> Participants { get; init; } = [];
}

public sealed record StreamsModeConfiguration
{
    [JsonPropertyName("type")]
    public required string Type { get; init; }

    [JsonPropertyName("outputLocale")]
    public string? OutputLocale { get; init; }

    [JsonPropertyName("factGenerationInterval")]
    public string? FactGenerationInterval { get; init; }
}

public sealed record StreamsReplacement
{
    [JsonPropertyName("find")]
    public required string Find { get; init; }

    [JsonPropertyName("replace")]
    public required string Replace { get; init; }
}

public sealed record StreamsConfiguration
{
    [JsonPropertyName("transcription")]
    public required StreamsTranscriptionConfiguration Transcription { get; init; }

    [JsonPropertyName("mode")]
    public required StreamsModeConfiguration Mode { get; init; }

    [JsonPropertyName("retentionPolicy")]
    public string RetentionPolicy { get; init; } = "retain";

    [JsonPropertyName("audioFormat")]
    public string? AudioFormat { get; init; }

    [JsonPropertyName("audioEvents")]
    public StreamsAudioEventsConfiguration AudioEvents { get; init; } = new();

    [JsonPropertyName("replacements")]
    public IReadOnlyList<StreamsReplacement> Replacements { get; init; } = [];

    [JsonPropertyName("keyterms")]
    public StreamsKeytermsConfiguration Keyterms { get; init; } = new();
}

public sealed record StreamsAudioEventsConfiguration
{
    [JsonPropertyName("enabled")]
    public bool Enabled { get; init; }
}

public sealed record StreamsKeytermsConfiguration
{
    [JsonPropertyName("terms")]
    public IReadOnlyList<StreamsKeyterm> Terms { get; init; } = [];
}

public sealed record StreamsKeyterm
{
    [JsonPropertyName("term")]
    public required string Term { get; init; }
}

public sealed record StreamsSessionOptions
{
    public required Guid InteractionId { get; init; }
    public required string TenantName { get; init; }
    public string Environment { get; init; } = "cn";
    public required StreamsConfiguration Configuration { get; init; }
    public bool RequireCheckpointResume { get; init; }
}

public sealed record StreamsEvent
{
    public required string Type { get; init; }
    public string? SessionId { get; init; }
    public JsonElement? Configuration { get; init; }
    public bool Resumed { get; init; }
    public long RestoredAudioBytes { get; init; }
    public int RestoredTranscriptMessages { get; init; }
    public int RestoredFactMessages { get; init; }
    public JsonElement? Data { get; init; }
    public StreamsAudioEventData? AudioEvent { get; init; }
    public JsonElement? Facts { get; init; }
    public double? Credits { get; init; }
    public string? Code { get; init; }
}

public sealed record StreamsAudioEventData
{
    public required string Event { get; init; }
    public required int Channel { get; init; }
    public required long StartTimeMs { get; init; }
}

public sealed class StreamsSessionException : InvalidOperationException
{
    public StreamsSessionException(string code, bool retryable = false)
        : base($"iCoDer managed Streams session failed ({code}).")
    {
        Code = code;
        Retryable = retryable;
    }

    public string Code { get; }
    public bool Retryable { get; }
}

public sealed class StreamsSession : IAsyncDisposable
{
    public const int MaximumAudioBytes = 32 * 1024 * 1024;
    public const int MaximumAudioChunkBytes = 64_000;
    public const int MaximumEventBytes = 1024 * 1024;

    private readonly WebSocket _socket;
    private readonly JsonSerializerOptions _jsonOptions;
    private readonly StreamsSessionOptions _options;
    private long _audioBytes;
    private long _durableAudioBytes;
    private bool _endSent;
    private bool _ended;
    private bool _disposed;

    internal StreamsSession(
        WebSocket socket,
        JsonSerializerOptions jsonOptions,
        StreamsSessionOptions options)
    {
        _socket = socket ?? throw new ArgumentNullException(nameof(socket));
        _jsonOptions = jsonOptions ?? throw new ArgumentNullException(nameof(jsonOptions));
        _options = options ?? throw new ArgumentNullException(nameof(options));
    }

    public WebSocketState State => _socket.State;
    public long SentAudioBytes => _audioBytes;
    public bool IsEnded => _ended;
    public StreamsEvent? Ready { get; private set; }

    internal async Task InitializeAsync(CancellationToken cancellationToken)
    {
        await SendJsonAsync(
            new { type = "config", configuration = _options.Configuration },
            cancellationToken).ConfigureAwait(false);
        var ready = await ReceiveEventFrameAsync(cancellationToken).ConfigureAwait(false);
        if (ready.Type.StartsWith("CONFIG_", StringComparison.Ordinal) &&
            ready.Type != "CONFIG_ACCEPTED")
        {
            throw new StreamsSessionException(ready.Type.ToLowerInvariant());
        }
        if (ready.Type != "CONFIG_ACCEPTED" ||
            !Guid.TryParse(ready.SessionId, out _) ||
            ready.Configuration is null ||
            ready.RestoredAudioBytes is < 0 or > MaximumAudioBytes ||
            ready.RestoredTranscriptMessages < 0 ||
            ready.RestoredFactMessages < 0)
        {
            throw new StreamsSessionException("invalid_configuration_response");
        }
        if (_options.RequireCheckpointResume && !ready.Resumed)
        {
            throw new StreamsSessionException("stream_checkpoint_not_found");
        }
        _audioBytes = ready.RestoredAudioBytes;
        _durableAudioBytes = ready.RestoredAudioBytes;
        Ready = ready;
    }

    public async Task SendAudioAsync(
        ReadOnlyMemory<byte> audio,
        CancellationToken cancellationToken = default)
    {
        ThrowIfNotWritable();
        if (audio.IsEmpty)
        {
            throw new ArgumentException("Audio chunk cannot be empty.", nameof(audio));
        }
        if (audio.Length > MaximumAudioChunkBytes)
        {
            throw new ArgumentOutOfRangeException(
                nameof(audio), $"Audio chunk exceeds {MaximumAudioChunkBytes} bytes.");
        }
        if (_audioBytes + audio.Length > MaximumAudioBytes)
        {
            throw new ArgumentOutOfRangeException(
                nameof(audio), $"Audio exceeds the {MaximumAudioBytes}-byte session limit.");
        }
        try
        {
            await _socket.SendAsync(
                Compatibility.AsArraySegment(audio),
                WebSocketMessageType.Binary,
                endOfMessage: true,
                cancellationToken).ConfigureAwait(false);
            _audioBytes += audio.Length;
        }
        catch (Exception exception) when (IsTransportFailure(exception))
        {
            throw new StreamsSessionException("audio_resume_unsupported");
        }
    }

    public Task FlushAsync(CancellationToken cancellationToken = default)
    {
        ThrowIfNotWritable();
        return SendJsonAsync(new { type = "flush" }, cancellationToken);
    }

    public async Task CompleteAsync(CancellationToken cancellationToken = default)
    {
        ThrowIfNotWritable();
        _endSent = true;
        try
        {
            await SendJsonAsync(new { type = "end" }, cancellationToken).ConfigureAwait(false);
        }
        catch (Exception exception) when (IsTransportFailure(exception))
        {
            throw InterruptionException();
        }
    }

    public async Task<StreamsEvent?> ReceiveAsync(CancellationToken cancellationToken = default)
    {
        Guard.NotDisposed(_disposed, this);
        if (_ended)
        {
            return null;
        }
        StreamsEvent message;
        try
        {
            message = await ReceiveEventFrameAsync(cancellationToken).ConfigureAwait(false);
        }
        catch (Exception exception) when (IsTransportFailure(exception))
        {
            throw InterruptionException();
        }
        if (message.Type == "CLOSED")
        {
            throw InterruptionException();
        }
        if (message.Type == "flushed")
        {
            _durableAudioBytes = _audioBytes;
        }
        if (message.Type == "ENDED")
        {
            _ended = true;
        }
        return message;
    }

    public async Task CloseAsync(CancellationToken cancellationToken = default)
    {
        if (_disposed || _socket.State is WebSocketState.Closed or WebSocketState.Aborted)
        {
            return;
        }
        if (_socket.State is WebSocketState.Open or WebSocketState.CloseReceived)
        {
            await _socket.CloseAsync(
                WebSocketCloseStatus.NormalClosure,
                "client closed",
                cancellationToken).ConfigureAwait(false);
        }
    }

    private void ThrowIfNotWritable()
    {
        Guard.NotDisposed(_disposed, this);
        if (_socket.State != WebSocketState.Open)
        {
            throw new StreamsSessionException("configuration_not_ready", retryable: true);
        }
        if (_endSent)
        {
            throw new StreamsSessionException("session_already_ended");
        }
    }

    private async Task SendJsonAsync(object value, CancellationToken cancellationToken)
    {
        var payload = JsonSerializer.SerializeToUtf8Bytes(value, _jsonOptions);
        await _socket.SendAsync(
            new ArraySegment<byte>(payload),
            WebSocketMessageType.Text,
            endOfMessage: true,
            cancellationToken).ConfigureAwait(false);
    }

    private async Task<StreamsEvent> ReceiveEventFrameAsync(CancellationToken cancellationToken)
    {
        var frame = new byte[8192];
        using var message = new MemoryStream();
        WebSocketReceiveResult result;
        do
        {
            result = await _socket.ReceiveAsync(
                new ArraySegment<byte>(frame), cancellationToken).ConfigureAwait(false);
            if (result.MessageType == WebSocketMessageType.Close)
            {
                return new StreamsEvent { Type = "CLOSED" };
            }
            if (result.MessageType != WebSocketMessageType.Text)
            {
                throw new InvalidDataException("iCoDer returned a non-text Streams event.");
            }
            if (message.Length + result.Count > MaximumEventBytes)
            {
                throw new InvalidDataException($"Streams event exceeds {MaximumEventBytes} bytes.");
            }
            message.Write(frame, 0, result.Count);
        }
        while (!result.EndOfMessage);

        try
        {
            using var document = JsonDocument.Parse(
                message.GetBuffer().AsMemory(0, checked((int)message.Length)));
            var root = document.RootElement;
            if (root.ValueKind != JsonValueKind.Object ||
                !root.TryGetProperty("type", out var typeElement) ||
                typeElement.ValueKind != JsonValueKind.String)
            {
                return new StreamsEvent { Type = "unknown" };
            }
            var type = typeElement.GetString() ?? "unknown";
            string? sessionId = null;
            JsonElement? configuration = null;
            var resumed = false;
            long restoredAudioBytes = 0;
            var restoredTranscriptMessages = 0;
            var restoredFactMessages = 0;
            JsonElement? data = null;
            JsonElement? facts = null;
            StreamsAudioEventData? audioEvent = null;
            double? credits = null;
            string? code = null;
            if (root.TryGetProperty("sessionId", out var session) && session.ValueKind == JsonValueKind.String)
            {
                sessionId = session.GetString();
            }
            if (root.TryGetProperty("configuration", out var config) && config.ValueKind == JsonValueKind.Object)
            {
                configuration = config.Clone();
            }
            if (root.TryGetProperty("resumed", out var resumedElement))
            {
                resumed = resumedElement.ValueKind == JsonValueKind.True;
            }
            restoredAudioBytes = ReadOptionalNonNegativeInt64(root, "restoredAudioBytes");
            restoredTranscriptMessages = ReadOptionalNonNegativeInt32(
                root, "restoredTranscriptMessages");
            restoredFactMessages = ReadOptionalNonNegativeInt32(root, "restoredFactMessages");
            if (root.TryGetProperty("data", out var dataElement) && dataElement.ValueKind is JsonValueKind.Array or JsonValueKind.Object)
            {
                data = dataElement.Clone();
            }
            if (type == "audioEvent")
            {
                if (dataElement.ValueKind != JsonValueKind.Object ||
                    !dataElement.TryGetProperty("event", out var audioEventName) ||
                    audioEventName.ValueKind != JsonValueKind.String ||
                    !IsAudioEventName(audioEventName.GetString()) ||
                    !dataElement.TryGetProperty("channel", out var audioChannel) ||
                    !audioChannel.TryGetInt32(out var parsedChannel) ||
                    parsedChannel is < 0 or > 15 ||
                    !dataElement.TryGetProperty("startTimeMs", out var startTime) ||
                    !startTime.TryGetInt64(out var parsedStartTime) ||
                    parsedStartTime < 0)
                {
                    return new StreamsEvent { Type = "unknown" };
                }
                audioEvent = new StreamsAudioEventData
                {
                    Event = audioEventName.GetString()!,
                    Channel = parsedChannel,
                    StartTimeMs = parsedStartTime,
                };
            }
            if (root.TryGetProperty("fact", out var factElement) && factElement.ValueKind == JsonValueKind.Array)
            {
                facts = factElement.Clone();
            }
            if (root.TryGetProperty("credits", out var creditElement) && creditElement.TryGetDouble(out var parsedCredits) && parsedCredits >= 0)
            {
                credits = parsedCredits;
            }
            if (type == "error" && root.TryGetProperty("error", out var error) &&
                error.ValueKind == JsonValueKind.Object &&
                error.TryGetProperty("id", out var id) && id.ValueKind == JsonValueKind.String)
            {
                var candidate = id.GetString();
                code = IsSafeCode(candidate) ? candidate : null;
            }
            return new StreamsEvent
            {
                Type = type,
                SessionId = sessionId,
                Configuration = configuration,
                Resumed = resumed,
                RestoredAudioBytes = restoredAudioBytes,
                RestoredTranscriptMessages = restoredTranscriptMessages,
                RestoredFactMessages = restoredFactMessages,
                Data = data,
                AudioEvent = audioEvent,
                Facts = facts,
                Credits = credits,
                Code = code,
            };
        }
        catch (JsonException)
        {
            return new StreamsEvent { Type = "unknown" };
        }
    }

    private static bool IsSafeCode(string? value)
    {
        if (value is null || value.Length == 0 || value.Length > 128)
        {
            return false;
        }
        return value.All(character =>
            Compatibility.IsAsciiLetterOrDigit(character) || character is '_' or '.' or ':' or '-');
    }

    private static bool IsAudioEventName(string? value)
        => value is "speechQualityIssueDetected" or "speechQualityIssueRecovered"
            or "longSilenceDetected" or "longSilenceRecovered";

    private static bool IsTransportFailure(Exception exception)
        => exception is WebSocketException or InvalidOperationException or IOException;

    private StreamsSessionException InterruptionException()
    {
        var safelyCheckpointed =
            _options.Configuration.RetentionPolicy == "retain" &&
            _audioBytes > 0 &&
            _durableAudioBytes == _audioBytes;
        return new StreamsSessionException(
            safelyCheckpointed
                ? "stream_resume_required"
                : _audioBytes > 0 ? "audio_resume_unsupported" : "stream_interrupted",
            retryable: safelyCheckpointed || _audioBytes == 0);
    }

    private static long ReadOptionalNonNegativeInt64(JsonElement root, string name)
    {
        if (!root.TryGetProperty(name, out var element))
        {
            return 0;
        }
        return element.ValueKind == JsonValueKind.Number &&
            element.TryGetInt64(out var value) && value >= 0
                ? value
                : -1;
    }

    private static int ReadOptionalNonNegativeInt32(JsonElement root, string name)
    {
        if (!root.TryGetProperty(name, out var element))
        {
            return 0;
        }
        return element.ValueKind == JsonValueKind.Number &&
            element.TryGetInt32(out var value) && value >= 0
                ? value
                : -1;
    }

    public ValueTask DisposeAsync()
    {
        if (!_disposed)
        {
            _disposed = true;
            _socket.Dispose();
        }
        return default;
    }
}
