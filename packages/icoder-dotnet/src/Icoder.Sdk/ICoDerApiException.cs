using System.Net;

namespace Icoder.Sdk;

/// <summary>A sanitized API failure. Raw response bodies are never retained.</summary>
public class ICoDerApiException : HttpRequestException
{
    public ICoDerApiException(
        HttpStatusCode statusCode,
        string message,
        string? errorCode = null,
        string? requestId = null)
#if NETSTANDARD2_0
        : base(message)
#else
        : base(message, null, statusCode)
#endif
    {
        StatusCodeValue = statusCode;
        ErrorCode = errorCode;
        RequestId = requestId;
    }

    public HttpStatusCode StatusCodeValue { get; }
    public string? ErrorCode { get; }
    public string? RequestId { get; }
}
