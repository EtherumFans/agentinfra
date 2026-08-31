using System.Text.Json;
using Icoder.Sdk;

var baseUrl = Environment.GetEnvironmentVariable("ICODER_E2E_STT_BASE_URL");
var accessToken = Environment.GetEnvironmentVariable("ICODER_E2E_ACCESS_TOKEN");
if (string.IsNullOrWhiteSpace(baseUrl) || string.IsNullOrWhiteSpace(accessToken))
{
    throw new InvalidOperationException("missing local STT E2E environment");
}

using var client = new ICoDerClient(new ICoDerClientOptions
{
    BaseUri = new Uri(baseUrl),
    AccessToken = accessToken,
    Timeout = TimeSpan.FromSeconds(5),
});
await using var session = await client.SpeechToText.CreateRealtimeSessionAsync(
    new RealtimeSttSessionOptions
    {
        ReconnectAttempts = 2,
        ReconnectInitialDelay = TimeSpan.Zero,
        ReconnectMaxDelay = TimeSpan.Zero,
    });
await session.SendAudioAsync("ICODER"u8.ToArray());
await session.CompleteAsync();

var acknowledgements = 0;
using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(15));
while (true)
{
    var realtimeEvent = await session.ReceiveAsync(timeout.Token);
    if (realtimeEvent is null)
    {
        throw new InvalidOperationException("STT closed without a terminal event");
    }
    if (realtimeEvent.Type == "audio_ack")
    {
        acknowledgements++;
    }
    if (realtimeEvent.Type == "error")
    {
        if (realtimeEvent.Code != "transcription_failed")
        {
            throw new InvalidOperationException($"unexpected STT error code: {realtimeEvent.Code}");
        }
        break;
    }
}
if (acknowledgements < 2 || session.AcknowledgedAudioSequence != 1)
{
    throw new InvalidOperationException("managed STT did not prove disconnect replay acknowledgements");
}
await session.CloseAsync();
Console.WriteLine(JsonSerializer.Serialize(new
{
    sdk = "dotnet",
    status = "passed",
    acknowledgements,
    acknowledged_audio_sequence = session.AcknowledgedAudioSequence,
    synthetic_audio_bytes = 6,
    real_stt_engine_used = false,
}));
