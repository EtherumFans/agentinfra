using System.Net.WebSockets;

namespace Icoder.Sdk;

public sealed class StreamsResource(ICoDerClient client)
{
    public Task<StreamsSession> ResumeSessionAsync(
        StreamsSessionOptions options,
        CancellationToken cancellationToken = default)
    {
        Guard.NotNull(options, nameof(options));
        if (options.Configuration.RetentionPolicy != "retain")
        {
            throw new StreamsSessionException("stream_resume_requires_retention");
        }
        return CreateSessionAsync(
            options with { RequireCheckpointResume = true },
            cancellationToken);
    }

    public async Task<StreamsSession> CreateSessionAsync(
        StreamsSessionOptions options,
        CancellationToken cancellationToken = default)
    {
        Guard.NotNull(options, nameof(options));
        Validate(options);
        var token = client.Options.AccessToken;
        if (string.IsNullOrWhiteSpace(token))
        {
            throw new StreamsSessionException("missing_access_token");
        }
        var baseUri = client.Options.BaseUri;
        var builder = new UriBuilder(baseUri)
        {
            Scheme = baseUri.Scheme == Uri.UriSchemeHttps ? "wss" : "ws",
            Path = $"/api/v2/tools/streams/{options.InteractionId:D}",
            Query = string.Join("&", new[]
            {
                $"environment={Uri.EscapeDataString(options.Environment)}",
                $"tenant-name={Uri.EscapeDataString(options.TenantName)}",
                $"token={Uri.EscapeDataString(token)}",
            }),
        };

        WebSocket socket;
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        timeout.CancelAfter(client.Options.Timeout);
        try
        {
            socket = await client.ConnectWebSocketAsync(builder.Uri, timeout.Token)
                .ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch
        {
            throw new StreamsSessionException("connection_failed", retryable: true);
        }

        var session = new StreamsSession(socket, client.JsonOptions, options);
        try
        {
            await session.InitializeAsync(timeout.Token).ConfigureAwait(false);
            return session;
        }
        catch
        {
            await session.DisposeAsync().ConfigureAwait(false);
            throw;
        }
    }

    private static void Validate(StreamsSessionOptions options)
    {
        if (options.InteractionId == Guid.Empty)
        {
            throw new ArgumentException("InteractionId must not be empty.", nameof(options));
        }
        if (string.IsNullOrWhiteSpace(options.TenantName) || options.TenantName.Length > 128)
        {
            throw new ArgumentException("TenantName is invalid.", nameof(options));
        }
        if (options.Environment is not ("cn" or "eu" or "us"))
        {
            throw new ArgumentException("Environment must be cn, eu, or us.", nameof(options));
        }
        var configuration = options.Configuration;
        if (string.IsNullOrWhiteSpace(configuration.Transcription.PrimaryLanguage) ||
            !configuration.Transcription.PrimaryLanguage.StartsWith("zh", StringComparison.OrdinalIgnoreCase))
        {
            throw new StreamsSessionException("unsupported_primary_language");
        }
        if (configuration.Transcription.Diarize)
        {
            throw new StreamsSessionException("diarization_not_available");
        }
        if (configuration.Mode.Type is not ("facts" or "transcription"))
        {
            throw new StreamsSessionException("mode_not_available");
        }
        if (configuration.Mode.Type == "facts" && string.IsNullOrWhiteSpace(configuration.Mode.OutputLocale))
        {
            throw new StreamsSessionException("output_locale_required");
        }
        if (configuration.Keyterms.Terms.Count > 1000)
        {
            throw new StreamsSessionException("keyterm_limit_exceeded");
        }
        if (configuration.Keyterms.Terms.Any(item =>
                item is null || string.IsNullOrEmpty(item.Term) || item.Term.Length > 50))
        {
            throw new StreamsSessionException("keyterm_invalid");
        }
        var audioProfile = configuration.AudioFormat is null
            ? ((string Container, int? Channels)?)null
            : ValidateAudioFormat(configuration.AudioFormat);
        if (configuration.AudioEvents.Enabled && audioProfile?.Container != "pcm")
        {
            throw new StreamsSessionException("audio_events_require_pcm");
        }
        var participantChannels = new HashSet<int>(configuration.Transcription.Participants
            .Select(item => item.Channel));
        if (configuration.Transcription.IsMultichannel)
        {
            var channels = audioProfile?.Container == "pcm" ? audioProfile?.Channels : null;
            if (channels is null or < 2)
            {
                throw new StreamsSessionException("multichannel_pcm_format_required");
            }
            if (!participantChannels.SetEquals(Enumerable.Range(0, channels.Value)))
            {
                throw new StreamsSessionException("multichannel_participants_must_match_channels");
            }
        }
        else
        {
            if (audioProfile?.Container == "pcm" && audioProfile?.Channels != 1)
            {
                throw new StreamsSessionException("multichannel_flag_required");
            }
            if (participantChannels.Any(channel => channel != 0))
            {
                throw new StreamsSessionException("mono_participant_channel_required");
            }
        }
        if (configuration.RetentionPolicy is not ("none" or "retain"))
        {
            throw new StreamsSessionException("retention_policy_invalid");
        }
        if (configuration.Replacements.Count > 1000)
        {
            throw new StreamsSessionException("replacement_limit_exceeded");
        }
    }

    private static (string Container, int? Channels) ValidateAudioFormat(string value)
    {
        var containers = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
        {
            ["audio/ogg"] = "ogg", ["audio/webm"] = "webm", ["audio/opus"] = "ogg",
            ["audio/vorbis"] = "ogg", ["audio/mpeg"] = "mpeg", ["audio/mp3"] = "mpeg",
            ["audio/mpeg3"] = "mpeg", ["audio/flac"] = "flac", ["audio/mp4"] = "mp4",
            ["audio/m4a"] = "mp4",
            ["audio/pcm"] = "pcm",
        };
        var parts = value.Split(new[] { ';' }, StringSplitOptions.None)
            .Select(part => part.Trim()).ToArray();
        if (parts.Length == 0 || !containers.TryGetValue(parts[0], out var container))
        {
            throw new StreamsSessionException("audio_format_not_supported");
        }
        if (container == "pcm")
        {
            var parameters = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            foreach (var parameter in parts.Skip(1))
            {
                var pair = parameter.Split(new[] { '=' }, 2, StringSplitOptions.None)
                    .Select(part => part.Trim()).ToArray();
                var key = pair.Length == 2 ? pair[0].ToLowerInvariant() : "";
                if (pair.Length != 2 ||
                    key is not ("rate" or "channels" or "bits" or "endian" or "encoding") ||
                    parameters.ContainsKey(key))
                {
                    throw new StreamsSessionException("audio_format_not_supported");
                }
                parameters[key] = pair[1].Trim('"').ToLowerInvariant();
            }
            if (!parameters.TryGetValue("rate", out var rate) ||
                !parameters.TryGetValue("channels", out var channels) ||
                !parameters.TryGetValue("bits", out var bits))
            {
                throw new StreamsSessionException("audio_format_not_supported");
            }
            var endian = parameters.TryGetValue("endian", out var endianValue)
                ? endianValue : "little";
            var encoding = parameters.TryGetValue("encoding", out var encodingValue)
                ? encodingValue : "sint";
            if (!int.TryParse(channels, out var channelCount) ||
                rate != "16000" || channelCount is < 1 or > 8 || bits != "16" ||
                endian != "little" || encoding != "sint")
            {
                throw new StreamsSessionException("raw_pcm_profile_not_available");
            }
            return (container, channelCount);
        }
        string? codec = null;
        foreach (var parameter in parts.Skip(1))
        {
            var pair = parameter.Split(new[] { '=' }, 2, StringSplitOptions.None)
                .Select(part => part.Trim()).ToArray();
            var candidate = pair.Length == 2 && pair[0].Equals("codecs", StringComparison.OrdinalIgnoreCase)
                ? pair[1].Trim('"').ToLowerInvariant()
                : "";
            if (codec is not null || candidate is not ("flac" or "opus" or "vorbis"))
            {
                throw new StreamsSessionException("audio_format_not_supported");
            }
            codec = candidate;
        }
        if (codec is not null && container is not ("ogg" or "webm"))
        {
            throw new StreamsSessionException("audio_format_not_supported");
        }
        var implied = parts[0].Equals("audio/opus", StringComparison.OrdinalIgnoreCase)
            ? "opus"
            : parts[0].Equals("audio/vorbis", StringComparison.OrdinalIgnoreCase) ? "vorbis" : null;
        if (implied is not null && codec is not null && codec != implied)
        {
            throw new StreamsSessionException("audio_format_not_supported");
        }
        return (container, null);
    }
}
