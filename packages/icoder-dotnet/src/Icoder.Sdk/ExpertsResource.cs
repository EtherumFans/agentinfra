namespace Icoder.Sdk;

public sealed class ExpertsResource(ICoDerClient client)
{
    public Task<ExpertCapabilityReadiness> GetReadinessAsync(
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
        => client.SendAsync<ExpertCapabilityReadiness>(
            HttpMethod.Get,
            "/api/v1/experts/readiness",
            cancellationToken: cancellationToken,
            requestOptions: requestOptions);
}
