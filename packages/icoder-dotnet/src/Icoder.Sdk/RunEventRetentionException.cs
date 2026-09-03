using System.Net;

namespace Icoder.Sdk;

/// <summary>A Run trace or resume cursor was removed by retention policy.</summary>
public sealed class RunEventRetentionException : ICoDerApiException
{
    public RunEventRetentionException(
        string errorCode,
        int? retentionDays = null,
        string? requestId = null)
        : base(
            HttpStatusCode.Gone,
            "iCoDer run event cursor is outside retention.",
            errorCode,
            requestId)
    {
        RetentionDays = retentionDays;
    }

    public int? RetentionDays { get; }
}
