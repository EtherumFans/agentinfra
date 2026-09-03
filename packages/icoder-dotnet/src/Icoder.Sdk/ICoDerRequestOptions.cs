namespace Icoder.Sdk;

/// <summary>
/// Bounded overrides for one HTTP request. Cancellation remains an explicit
/// <see cref="CancellationToken"/> parameter on asynchronous resource methods.
/// </summary>
public sealed class ICoDerRequestOptions
{
    /// <summary>Override the client timeout for this request.</summary>
    public TimeSpan? Timeout { get; init; }

    /// <summary>Override retries for HTTP 408, 429, and 5xx responses.</summary>
    public int? MaxRetries { get; init; }

    /// <summary>
    /// Extra non-identity headers. Authentication, cookie, host, content
    /// framing, and tenant headers are controlled by the SDK.
    /// </summary>
    public IReadOnlyDictionary<string, string?> AdditionalHeaders { get; init; }
        = new Dictionary<string, string?>();

    /// <summary>
    /// Extra query parameters. A key already owned by the resource method
    /// cannot be overridden.
    /// </summary>
    public IReadOnlyDictionary<string, string> AdditionalQueryParameters { get; init; }
        = new Dictionary<string, string>();
}
