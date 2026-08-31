using Icoder.Sdk;

namespace Icoder.Sdk.CompatibilityConsumer;

/// <summary>
/// Compile-only contract proving that representative public SDK entry points
/// remain consumable from the oldest supported target frameworks.
/// </summary>
public static class CompatibilityConsumerContract
{
    public static ICoDerClient CreateClient()
        => new(new ICoDerClientOptions
        {
            BaseUri = new Uri("https://api.example.invalid"),
            AccessToken = "compile-only-token",
            Timeout = TimeSpan.FromSeconds(30),
            MaxRetries = 1,
        });

    public static Type[] RepresentativeSurface()
        => new[]
        {
            typeof(AgentRunsResource),
            typeof(AgentHubResource),
            typeof(MedicalCodingResource),
            typeof(SpeechToTextResource),
            typeof(StreamsResource),
            typeof(DocumentsResource),
            typeof(A2AResource),
        };
}
