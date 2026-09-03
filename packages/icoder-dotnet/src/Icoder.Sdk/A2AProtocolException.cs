using System.Net;

namespace Icoder.Sdk;

/// <summary>An A2A protocol error that never retains the raw response body.</summary>
public sealed class A2AProtocolException : Exception
{
    public int JsonRpcCode { get; }
    public string? A2AErrorCode { get; }
    public HttpStatusCode StatusCode { get; }

    internal A2AProtocolException(
        int jsonRpcCode,
        string? a2aErrorCode,
        HttpStatusCode statusCode)
        : base($"iCoDer A2A request failed ({a2aErrorCode ?? jsonRpcCode.ToString()})")
    {
        JsonRpcCode = jsonRpcCode;
        A2AErrorCode = a2aErrorCode;
        StatusCode = statusCode;
    }
}
