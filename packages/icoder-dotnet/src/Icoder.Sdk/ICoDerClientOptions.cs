namespace Icoder.Sdk;

/// <summary>Configuration for <see cref="ICoDerClient"/>.</summary>
public sealed class ICoDerClientOptions
{
    public required Uri BaseUri { get; init; }
    public string? AccessToken { get; set; }
    public string? RefreshToken { get; set; }
    public TimeSpan Timeout { get; init; } = TimeSpan.FromSeconds(120);
    public int MaxRetries { get; init; } = 2;

    /// <summary>Non-identity headers sent with every HTTP request.</summary>
    public IReadOnlyDictionary<string, string?> AdditionalHeaders { get; init; }
        = new Dictionary<string, string?>();

    /// <summary>
    /// Allows clear-text HTTP for a non-loopback host. Keep false outside an
    /// isolated development network; localhost HTTP is allowed automatically.
    /// </summary>
    public bool AllowInsecureHttp { get; init; }

    public Action<TokenResponse>? OnTokenRefreshed { get; init; }
}
