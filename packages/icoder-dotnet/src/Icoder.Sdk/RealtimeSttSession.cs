using System.Buffers.Binary;
using System.Net.WebSockets;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Icoder.Sdk;

public sealed record RealtimeSttSessionOptions
{
    public string Language { get; init; } = "zh-CN";
    public string Punctuation { get; init; } = "auto";
    public string MediaType { get; init; } = "audio/webm;codecs=opus";
    public int ReconnectAttempts { get; init; } = 3;
    public TimeSpan ReconnectInitialDelay { get; init; } = TimeSpan.FromMilliseconds(250);
    public TimeSpan ReconnectMaxDelay { get; init; } = TimeSpan.FromSeconds(2);
}

public sealed record RealtimeSttEvent
{
    [JsonPropertyName("type")]
    public required string Type { get; init; }

    [JsonPropertyName("text")]
    public string? Text { get; init; }

    [JsonPropertyName("code")]
    public string? Code { get; init; }

    [JsonPropertyName("message")]
    public string? Message { get; init; }

    [JsonPropertyName("language")]
    public string? Language { get; init; }

    [JsonPropertyName("maxSessionBytes")]
    public int? MaxSessionBytes { get; init; }

    [JsonPropertyName("protocol")]
    public string? Protocol { get; init; }

    [JsonPropertyName("resumeSupported")]
    public bool? ResumeSupported { get; init; }

    [JsonPropertyName("resumeMode")]
    public string? ResumeMode { get; init; }

    [JsonPropertyName("sessionId")]
    public string? SessionId { get; init; }

    [JsonPropertyName("sequence")]
    public int? Sequence { get; init; }

    [JsonPropertyName("nextAudioSequence")]
    public int? NextAudioSequence { get; init; }

    [JsonPropertyName("totalBytes")]
    public long? TotalBytes { get; init; }

    [JsonPropertyName("duplicate")]
    public bool? Duplicate { get; init; }

    [JsonPropertyName("audioSequence")]
    public int? AudioSequence { get; init; }

    [JsonPropertyName("diarization")]
    public JsonElement? Diarization { get; init; }

    [JsonExtensionData]
    public IDictionary<string, JsonElement>? AdditionalProperties { get; init; }
}

/// <summary>A PHI-safe failure from the managed real-time STT lifecycle.</summary>
public sealed class RealtimeSttSessionException : InvalidOperationException
{
    public RealtimeSttSessionException(string code, bool retryable = false)
        : base($"iCoDer real-time STT session failed ({code}).")
    {
        Code = code;
        Retryable = retryable;
    }

    public string Code { get; }
    public bool Retryable { get; }
}

/// <summary>
/// A tenant-authenticated real-time STT session with negotiated, bounded
/// client-replay recovery. Clinical audio remains in memory and is never
/// persisted by the SDK.
/// </summary>
public sealed class RealtimeSttSession : IAsyncDisposable
{
    public const int MaximumSessionBytes = 32 * 1024 * 1024;
    public const int MaximumEventBytes = 1024 * 1024;

    private const string ResumeProtocol = "icoder.stt-resume.v1";
    private const string ResumeMode = "client_replay";
    private const int AudioFrameHeaderBytes = 8;

    private readonly JsonSerializerOptions _jsonOptions;
    private readonly RealtimeSttSessionOptions _options;
    private readonly Func<CancellationToken, Task<WebSocket>> _connector;
    private readonly TimeSpan _setupTimeout;
    private readonly string _sessionId = $"stt_{Guid.NewGuid():N}";
    private readonly List<byte[]> _audioFrames = [];
    private readonly SemaphoreSlim _sendLock = new(1, 1);
    private readonly SemaphoreSlim _recoveryLock = new(1, 1);
    private WebSocket _socket;
    private long _sentAudioBytes;
    private int _maxSessionBytes = MaximumSessionBytes;
    private int _reconnectsUsed;
    private int _lastAcknowledgedSequence;
    private bool _resumeSupported;
    private bool _endSent;
    private bool _terminalReceived;
    private bool _manuallyClosed;
    private bool _disposed;

    internal RealtimeSttSession(
        WebSocket socket,
        JsonSerializerOptions jsonOptions,
        RealtimeSttSessionOptions options,
        Func<CancellationToken, Task<WebSocket>> connector,
        TimeSpan setupTimeout)
    {
        _socket = socket ?? throw new ArgumentNullException(nameof(socket));
        _jsonOptions = jsonOptions ?? throw new ArgumentNullException(nameof(jsonOptions));
        _options = options ?? throw new ArgumentNullException(nameof(options));
        _connector = connector ?? throw new ArgumentNullException(nameof(connector));
        _setupTimeout = setupTimeout;
    }

    public WebSocketState State => _socket.State;
    public long SentAudioBytes => _sentAudioBytes;
    public int AcknowledgedAudioSequence => _lastAcknowledgedSequence;
    public RealtimeSttEvent? Ready { get; private set; }

    internal async Task InitializeAsync(CancellationToken cancellationToken)
    {
        await SendStartAsync(_socket, cancellationToken).ConfigureAwait(false);
        var ready = await ReceiveSingleEventAsync(_socket, cancellationToken).ConfigureAwait(false);
        if (ready?.Type == "error")
        {
            throw new RealtimeSttSessionException(ready.Code ?? "server_error");
        }
        if (ready?.Type != "ready")
        {
            throw new RealtimeSttSessionException("configuration_not_ready");
        }
        await ApplyReadyAndReplayAsync(_socket, ready, cancellationToken).ConfigureAwait(false);
        Ready = ready;
    }

    public async Task SendAudioAsync(
        ReadOnlyMemory<byte> audio,
        CancellationToken cancellationToken = default)
    {
        if (audio.IsEmpty)
        {
            throw new ArgumentException("Audio chunk cannot be empty.", nameof(audio));
        }
        await _sendLock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            ThrowIfDisposed();
            await EnsureOpenAsync(cancellationToken).ConfigureAwait(false);
            if (_endSent)
            {
                throw new RealtimeSttSessionException("session_already_ended");
            }
            var nextTotal = _sentAudioBytes + audio.Length;
            if (nextTotal > _maxSessionBytes)
            {
                throw new ArgumentOutOfRangeException(
                    nameof(audio),
                    $"Real-time audio exceeds the {_maxSessionBytes}-byte session limit.");
            }

            if (_resumeSupported)
            {
                var sequence = checked(_audioFrames.Count + 1);
                var frame = CreateAudioFrame(sequence, audio.Span);
                _audioFrames.Add(frame);
                _sentAudioBytes = nextTotal;
                var failedSocket = _socket;
                try
                {
                    await SendBinaryAsync(failedSocket, frame, cancellationToken).ConfigureAwait(false);
                }
                catch (Exception exception) when (IsTransportFailure(exception))
                {
                    await RecoverAsync(failedSocket, cancellationToken).ConfigureAwait(false);
                }
            }
            else
            {
                var failedSocket = _socket;
                try
                {
                    await SendBinaryAsync(failedSocket, audio, cancellationToken).ConfigureAwait(false);
                    _sentAudioBytes = nextTotal;
                }
                catch (Exception exception) when (IsTransportFailure(exception))
                {
                    throw new RealtimeSttSessionException("audio_resume_unsupported");
                }
            }
        }
        finally
        {
            _sendLock.Release();
        }
    }

    public Task RequestInterimAsync(CancellationToken cancellationToken = default)
        => SendRecoverableCommandAsync(new { type = "interim" }, true, cancellationToken);

    public async Task CompleteAsync(CancellationToken cancellationToken = default)
    {
        await _sendLock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            ThrowIfDisposed();
            await EnsureOpenAsync(cancellationToken).ConfigureAwait(false);
            if (_endSent)
            {
                throw new RealtimeSttSessionException("session_already_ended");
            }
            _endSent = true;
            var failedSocket = _socket;
            try
            {
                if (_resumeSupported)
                {
                    await SendCommandAsync(
                        failedSocket,
                        new { type = "end", lastAudioSequence = _audioFrames.Count },
                        cancellationToken).ConfigureAwait(false);
                }
                else
                {
                    await SendCommandAsync(failedSocket, new { type = "end" }, cancellationToken)
                        .ConfigureAwait(false);
                }
            }
            catch (Exception exception) when (IsTransportFailure(exception))
            {
                if (!_resumeSupported)
                {
                    throw new RealtimeSttSessionException("audio_resume_unsupported");
                }
                await RecoverAsync(failedSocket, cancellationToken).ConfigureAwait(false);
            }
        }
        finally
        {
            _sendLock.Release();
        }
    }

    public Task PingAsync(CancellationToken cancellationToken = default)
        => SendRecoverableCommandAsync(new { type = "ping" }, true, cancellationToken);

    public async Task<RealtimeSttEvent?> ReceiveAsync(
        CancellationToken cancellationToken = default)
    {
        ThrowIfDisposed();
        if (_terminalReceived)
        {
            return null;
        }
        while (!_disposed && !_manuallyClosed)
        {
            var activeSocket = _socket;
            RealtimeSttEvent? realtimeEvent;
            try
            {
                realtimeEvent = await ReceiveSingleEventAsync(activeSocket, cancellationToken)
                    .ConfigureAwait(false);
            }
            catch (Exception exception) when (IsTransportFailure(exception))
            {
                await RecoverAsync(activeSocket, cancellationToken).ConfigureAwait(false);
                continue;
            }
            if (realtimeEvent is null)
            {
                await RecoverAsync(activeSocket, cancellationToken).ConfigureAwait(false);
                continue;
            }
            ValidateServerEvent(realtimeEvent);
            if (realtimeEvent.Type == "final" ||
                (realtimeEvent.Type == "error" && _endSent))
            {
                _terminalReceived = true;
            }
            return realtimeEvent;
        }
        return null;
    }

    public async Task CloseAsync(CancellationToken cancellationToken = default)
    {
        if (_disposed)
        {
            return;
        }
        _manuallyClosed = true;
        _terminalReceived = true;
        if (_socket.State is WebSocketState.Closed or WebSocketState.Aborted)
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

    private async Task SendRecoverableCommandAsync(
        object command,
        bool resendAfterRecovery,
        CancellationToken cancellationToken)
    {
        await _sendLock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            ThrowIfDisposed();
            if (_manuallyClosed)
            {
                throw new RealtimeSttSessionException("client_closed");
            }
            await EnsureOpenAsync(cancellationToken).ConfigureAwait(false);
            var failedSocket = _socket;
            try
            {
                await SendCommandAsync(failedSocket, command, cancellationToken).ConfigureAwait(false);
            }
            catch (Exception exception) when (IsTransportFailure(exception))
            {
                await RecoverAsync(failedSocket, cancellationToken).ConfigureAwait(false);
                if (resendAfterRecovery)
                {
                    await SendCommandAsync(_socket, command, cancellationToken).ConfigureAwait(false);
                }
            }
        }
        finally
        {
            _sendLock.Release();
        }
    }

    private async Task EnsureOpenAsync(CancellationToken cancellationToken)
    {
        if (_manuallyClosed)
        {
            throw new RealtimeSttSessionException("client_closed");
        }
        if (_socket.State == WebSocketState.Open)
        {
            return;
        }
        await RecoverAsync(_socket, cancellationToken).ConfigureAwait(false);
    }

    private async Task RecoverAsync(WebSocket failedSocket, CancellationToken cancellationToken)
    {
        await _recoveryLock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            ThrowIfDisposed();
            if (_manuallyClosed)
            {
                throw new RealtimeSttSessionException("client_closed");
            }
            if (!ReferenceEquals(_socket, failedSocket) && _socket.State == WebSocketState.Open)
            {
                return;
            }
            if ((_sentAudioBytes > 0 || _endSent) && !_resumeSupported)
            {
                throw new RealtimeSttSessionException("audio_resume_unsupported");
            }

            while (_reconnectsUsed < _options.ReconnectAttempts)
            {
                _reconnectsUsed++;
                var multiplier = Math.Pow(2, _reconnectsUsed - 1);
                var delay = TimeSpan.FromMilliseconds(Math.Min(
                    _options.ReconnectMaxDelay.TotalMilliseconds,
                    _options.ReconnectInitialDelay.TotalMilliseconds * multiplier));
                if (delay > TimeSpan.Zero)
                {
                    await Task.Delay(delay, cancellationToken).ConfigureAwait(false);
                }

                WebSocket? replacement = null;
                using var setup = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
                setup.CancelAfter(_setupTimeout);
                try
                {
                    replacement = await _connector(setup.Token).ConfigureAwait(false);
                    await SendStartAsync(replacement, setup.Token).ConfigureAwait(false);
                    var ready = await ReceiveSingleEventAsync(replacement, setup.Token)
                        .ConfigureAwait(false);
                    if (ready?.Type == "error")
                    {
                        throw new RealtimeSttSessionException(ready.Code ?? "server_error");
                    }
                    if (ready?.Type != "ready")
                    {
                        throw new RealtimeSttSessionException("configuration_not_ready");
                    }
                    await ApplyReadyAndReplayAsync(replacement, ready, setup.Token)
                        .ConfigureAwait(false);
                    var previous = _socket;
                    _socket = replacement;
                    replacement = null;
                    Ready = ready;
                    previous.Dispose();
                    return;
                }
                catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
                {
                    replacement?.Dispose();
                    throw;
                }
                catch (RealtimeSttSessionException exception) when (!exception.Retryable)
                {
                    replacement?.Dispose();
                    throw;
                }
                catch
                {
                    replacement?.Dispose();
                }
            }
            throw new RealtimeSttSessionException("reconnect_exhausted");
        }
        finally
        {
            _recoveryLock.Release();
        }
    }

    private async Task SendStartAsync(WebSocket socket, CancellationToken cancellationToken)
        => await SendCommandAsync(
            socket,
            new
            {
                type = "start",
                protocol = ResumeProtocol,
                sessionId = _sessionId,
                mimeType = _options.MediaType,
                language = _options.Language,
            },
            cancellationToken).ConfigureAwait(false);

    private async Task ApplyReadyAndReplayAsync(
        WebSocket socket,
        RealtimeSttEvent ready,
        CancellationToken cancellationToken)
    {
        var negotiatedResume = ready.Protocol == ResumeProtocol
            && ready.ResumeSupported is true
            && ready.ResumeMode == ResumeMode
            && ready.SessionId == _sessionId;
        if ((_sentAudioBytes > 0 || _endSent) && !negotiatedResume)
        {
            throw new RealtimeSttSessionException("audio_resume_unsupported");
        }
        var requestedSequence = negotiatedResume ? ready.NextAudioSequence : null;
        if (negotiatedResume &&
            (requestedSequence is null || requestedSequence < 1 ||
             requestedSequence > _audioFrames.Count + 1))
        {
            throw new RealtimeSttSessionException("invalid_resume_cursor");
        }
        _resumeSupported = negotiatedResume;
        if (ready.MaxSessionBytes is > 0)
        {
            _maxSessionBytes = Math.Min(MaximumSessionBytes, ready.MaxSessionBytes.Value);
        }
        if (_sentAudioBytes > _maxSessionBytes)
        {
            throw new RealtimeSttSessionException("session_too_large");
        }
        if (!negotiatedResume)
        {
            return;
        }

        _lastAcknowledgedSequence = requestedSequence!.Value - 1;
        for (var index = requestedSequence.Value - 1; index < _audioFrames.Count; index++)
        {
            await SendBinaryAsync(socket, _audioFrames[index], cancellationToken)
                .ConfigureAwait(false);
        }
        if (_endSent)
        {
            await SendCommandAsync(
                socket,
                new { type = "end", lastAudioSequence = _audioFrames.Count },
                cancellationToken).ConfigureAwait(false);
        }
    }

    private void ValidateServerEvent(RealtimeSttEvent realtimeEvent)
    {
        if (realtimeEvent.Type != "audio_ack")
        {
            return;
        }
        if (!_resumeSupported || realtimeEvent.SessionId != _sessionId ||
            realtimeEvent.Sequence is null or < 1 ||
            realtimeEvent.NextAudioSequence is null or < 1 ||
            realtimeEvent.Sequence > _audioFrames.Count ||
            realtimeEvent.NextAudioSequence < realtimeEvent.Sequence + 1 ||
            realtimeEvent.NextAudioSequence > _audioFrames.Count + 1)
        {
            _terminalReceived = true;
            _socket.Abort();
            throw new RealtimeSttSessionException("invalid_audio_ack");
        }
        _lastAcknowledgedSequence = Math.Max(
            _lastAcknowledgedSequence,
            realtimeEvent.NextAudioSequence.Value - 1);
    }

    private async Task<RealtimeSttEvent?> ReceiveSingleEventAsync(
        WebSocket socket,
        CancellationToken cancellationToken)
    {
        var frame = new byte[8192];
        using var message = new MemoryStream();
        WebSocketReceiveResult result;
        do
        {
            result = await socket.ReceiveAsync(
                new ArraySegment<byte>(frame), cancellationToken).ConfigureAwait(false);
            if (result.MessageType == WebSocketMessageType.Close)
            {
                return null;
            }
            if (result.MessageType != WebSocketMessageType.Text)
            {
                throw new InvalidDataException("iCoDer returned a non-text real-time STT event.");
            }
            if (message.Length + result.Count > MaximumEventBytes)
            {
                throw new InvalidDataException(
                    $"Real-time STT event exceeds {MaximumEventBytes} bytes.");
            }
            message.Write(frame, 0, result.Count);
        }
        while (!result.EndOfMessage);

        try
        {
            var parsed = JsonSerializer.Deserialize<RealtimeSttEvent>(
                message.GetBuffer().AsSpan(0, checked((int)message.Length)),
                _jsonOptions)
                ?? throw new InvalidDataException("iCoDer returned an empty real-time STT event.");
            return parsed with
            {
                Code = IsSafeCode(parsed.Code) ? parsed.Code : null,
                Message = null,
                AdditionalProperties = null,
            };
        }
        catch (JsonException exception)
        {
            throw new InvalidDataException("iCoDer returned an invalid real-time STT event.", exception);
        }
    }

    private async Task SendCommandAsync(
        WebSocket socket,
        object command,
        CancellationToken cancellationToken)
    {
        var bytes = JsonSerializer.SerializeToUtf8Bytes(command, _jsonOptions);
        await socket.SendAsync(
            new ArraySegment<byte>(bytes),
            WebSocketMessageType.Text,
            endOfMessage: true,
            cancellationToken).ConfigureAwait(false);
    }

    private static async Task SendBinaryAsync(
        WebSocket socket,
        ReadOnlyMemory<byte> bytes,
        CancellationToken cancellationToken)
    {
        if (!MemoryMarshal.TryGetArray(bytes, out ArraySegment<byte> segment))
        {
            segment = new ArraySegment<byte>(bytes.ToArray());
        }
        await socket.SendAsync(
            segment,
            WebSocketMessageType.Binary,
            endOfMessage: true,
            cancellationToken).ConfigureAwait(false);
    }

    private static byte[] CreateAudioFrame(int sequence, ReadOnlySpan<byte> audio)
    {
        var frame = new byte[AudioFrameHeaderBytes + audio.Length];
        "ICR1"u8.CopyTo(frame);
        BinaryPrimitives.WriteUInt32BigEndian(frame.AsSpan(4, 4), checked((uint)sequence));
        audio.CopyTo(frame.AsSpan(AudioFrameHeaderBytes));
        return frame;
    }

    private static bool IsTransportFailure(Exception exception)
        => exception is WebSocketException or InvalidOperationException or IOException;

    private static bool IsSafeCode(string? value)
    {
        if (value is null || value.Length == 0 || value.Length > 128)
        {
            return false;
        }
        foreach (var character in value)
        {
            if (!(Compatibility.IsAsciiLetterOrDigit(character) || character is '_' or '.' or ':' or '-'))
            {
                return false;
            }
        }
        return true;
    }

    private void ThrowIfDisposed()
        => Guard.NotDisposed(_disposed, this);

    public ValueTask DisposeAsync()
    {
        if (!_disposed)
        {
            _disposed = true;
            _manuallyClosed = true;
            _socket.Dispose();
            foreach (var frame in _audioFrames)
            {
                Compatibility.ZeroMemory(frame);
            }
            _audioFrames.Clear();
            _sendLock.Dispose();
            _recoveryLock.Dispose();
        }
        return default;
    }
}
