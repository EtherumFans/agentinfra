namespace Icoder.Sdk;

public sealed class PlatformResource(ICoDerClient client)
{
    public Task<PlatformCatalog> ListEnvironmentsAsync(
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
        => client.SendAsync<PlatformCatalog>(
            HttpMethod.Get, "/api/platform/environments", cancellationToken: cancellationToken,
            requestOptions: requestOptions);

    public Task<RegionCatalog> ListRegionsAsync(
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
        => client.SendAsync<RegionCatalog>(
            HttpMethod.Get, "/api/platform/regions", cancellationToken: cancellationToken,
            requestOptions: requestOptions);

    public Task<EnvironmentDeploymentPlan> PlanEnvironmentAsync(
        EnvironmentPlanRequest request,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNull(request, nameof(request));
        return client.SendAsync<EnvironmentDeploymentPlan>(
            HttpMethod.Post, "/api/platform/environments", request,
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task<TenantView> GetCurrentTenantAsync(
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
        => client.SendAsync<TenantView>(
            HttpMethod.Get, "/api/tenants/current", cancellationToken: cancellationToken,
            requestOptions: requestOptions);

    public Task<TenantEnvironmentAssignments> GetTenantEnvironmentsAsync(
        string tenantId,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(tenantId, nameof(tenantId));
        return client.SendAsync<TenantEnvironmentAssignments>(
            HttpMethod.Get,
            $"/api/tenants/{Uri.EscapeDataString(tenantId)}/environments",
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }
}
