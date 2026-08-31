using System.Text.Json;
using Icoder.Sdk;

var baseUrl = Environment.GetEnvironmentVariable("ICODER_E2E_STREAMS_BASE_URL");
var accessToken = Environment.GetEnvironmentVariable("ICODER_E2E_ACCESS_TOKEN");
var tenantName = Environment.GetEnvironmentVariable("ICODER_E2E_TENANT_NAME");
var audioPath = Environment.GetEnvironmentVariable("ICODER_E2E_STREAMS_AUDIO_PATH");
if (string.IsNullOrWhiteSpace(baseUrl) || string.IsNullOrWhiteSpace(accessToken) ||
    string.IsNullOrWhiteSpace(tenantName) || string.IsNullOrWhiteSpace(audioPath))
{
    throw new InvalidOperationException("missing local Streams E2E environment");
}
var audio = await File.ReadAllBytesAsync(audioPath);

var interactionId = Guid.NewGuid();
using var client = new ICoDerClient(new ICoDerClientOptions
{
    BaseUri = new Uri(baseUrl),
    AccessToken = accessToken,
    Timeout = TimeSpan.FromSeconds(10),
});
await using var session = await client.Streams.CreateSessionAsync(new StreamsSessionOptions
{
    InteractionId = interactionId,
    TenantName = tenantName,
    Environment = "cn",
    Configuration = new StreamsConfiguration
    {
        Transcription = new StreamsTranscriptionConfiguration
        {
            PrimaryLanguage = "zh-CN",
            Participants = [new StreamsParticipant { Channel = 0, Role = "multiple" }],
        },
        Mode = new StreamsModeConfiguration { Type = "transcription" },
        RetentionPolicy = "none",
        AudioFormat = "audio/ogg; codecs=opus",
    },
});
await session.SendAudioAsync(audio);
await session.FlushAsync();
await session.CompleteAsync();

var types = new List<string>();
var errorCodes = new List<string>();
double? finalCredits = null;
using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(15));
while (true)
{
    var message = await session.ReceiveAsync(timeout.Token)
        ?? throw new InvalidOperationException("Streams closed before ENDED");
    types.Add(message.Type);
    if (message.Type == "error" && message.Code is not null) errorCodes.Add(message.Code);
    if (message.Type == "usage") finalCredits = message.Credits;
    if (message.Type == "ENDED") break;
}
foreach (var required in new[] { "flushed", "delta_usage", "usage", "ENDED" })
{
    if (!types.Contains(required)) throw new InvalidOperationException($"missing Streams event: {required}");
}
if (finalCredits != 0) throw new InvalidOperationException("local Streams usage must not invent credits");
errorCodes.Sort(StringComparer.Ordinal);
if (!errorCodes.SequenceEqual(new[] { "STT_UNAVAILABLE" }))
{
    throw new InvalidOperationException("local disabled-provider errors were not explicit and bounded");
}
await session.CloseAsync();
Console.WriteLine(JsonSerializer.Serialize(new
{
    sdk = "dotnet",
    status = "passed",
    interaction_id = interactionId,
    retention_policy = "none",
    event_types = types,
    expected_error_codes = errorCodes,
    synthetic_audio_bytes = audio.Length,
    synthetic_silence_ogg_opus = true,
    real_stt_engine_used = false,
    real_llm_used = false,
}));
