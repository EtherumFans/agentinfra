namespace Icoder.Sdk;

public sealed class AgentConnectorsResource(ICoDerClient client)
{
    private static string Root(string agentId)
    {
        Guard.NotNullOrWhiteSpace(agentId, nameof(agentId));
        return $"/api/v2/agentic/agents/{Uri.EscapeDataString(agentId)}";
    }

    private static string ConnectorPath(string agentId, string connectorId)
    {
        Guard.NotNullOrWhiteSpace(connectorId, nameof(connectorId));
        return $"{Root(agentId)}/connectors/{Uri.EscapeDataString(connectorId)}";
    }

    public Task<AgentConnectorList> ListAsync(
        string agentId,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
        => client.SendAsync<AgentConnectorList>(
            HttpMethod.Get,
            $"{Root(agentId)}/connectors",
            cancellationToken: cancellationToken, requestOptions: requestOptions);

    public Task<AgentConnector> GetAsync(
        string agentId,
        string connectorId,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
        => client.SendAsync<AgentConnector>(
            HttpMethod.Get,
            ConnectorPath(agentId, connectorId),
            cancellationToken: cancellationToken, requestOptions: requestOptions);

    public Task<AgentConnector> CreateAsync(
        string agentId,
        AgentConnectorCreateRequest request,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNull(request, nameof(request));
        return client.SendAsync<AgentConnector>(
            HttpMethod.Post,
            $"{Root(agentId)}/connectors",
            request,
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task<AgentConnector> UpdateAsync(
        string agentId,
        string connectorId,
        AgentConnectorUpdateRequest request,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNull(request, nameof(request));
        return client.SendAsync<AgentConnector>(
            Compatibility.Patch,
            ConnectorPath(agentId, connectorId),
            request,
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task DeleteAsync(
        string agentId,
        string connectorId,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
        => client.SendNoContentAsync(
            HttpMethod.Delete,
            ConnectorPath(agentId, connectorId),
            cancellationToken: cancellationToken, requestOptions: requestOptions);

    public Task<AgentConnectorCredentialMetadata> BindCredentialAsync(
        string agentId,
        string connectorId,
        ConnectorCredentialBindRequest request,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNull(request, nameof(request));
        return client.SendAsync<AgentConnectorCredentialMetadata>(
            HttpMethod.Put,
            $"{ConnectorPath(agentId, connectorId)}/credential",
            request,
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task DeleteCredentialAsync(
        string agentId,
        string connectorId,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
        => client.SendNoContentAsync(
            HttpMethod.Delete,
            $"{ConnectorPath(agentId, connectorId)}/credential",
            cancellationToken: cancellationToken, requestOptions: requestOptions);

    public Task<ConnectorGraph> GetGraphAsync(
        string agentId,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
        => client.SendAsync<ConnectorGraph>(
            HttpMethod.Get,
            $"{Root(agentId)}/connector-graph",
            cancellationToken: cancellationToken, requestOptions: requestOptions);

    public Task<ConnectorGraph> PutGraphAsync(
        string agentId,
        ConnectorGraphPutRequest request,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNull(request, nameof(request));
        if (request.ExecutionMode is not ("sequential" or "parallel"))
        {
            throw new ArgumentException("Unsupported Connector graph execution mode.", nameof(request));
        }
        if (request.MaxConcurrency is < 1 or > 8)
        {
            throw new ArgumentOutOfRangeException(nameof(request), "MaxConcurrency must be 1 to 8.");
        }
        return client.SendAsync<ConnectorGraph>(
            HttpMethod.Put,
            $"{Root(agentId)}/connector-graph",
            request,
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task DeleteGraphAsync(
        string agentId,
        int expectedRevision,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        if (expectedRevision < 0)
        {
            throw new ArgumentOutOfRangeException(nameof(expectedRevision));
        }
        return client.SendNoContentAsync(
            HttpMethod.Delete,
            $"{Root(agentId)}/connector-graph?expected_revision={expectedRevision}",
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task<MemoryConsent> GrantMemoryConsentAsync(
        string agentId,
        MemoryConsentGrantRequest request,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNull(request, nameof(request));
        if (!request.Acknowledgement)
        {
            throw new ArgumentException("Memory consent requires explicit acknowledgement.", nameof(request));
        }
        return client.SendAsync<MemoryConsent>(
            HttpMethod.Post,
            $"{Root(agentId)}/memory-consent",
            request,
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task<MemoryConsent> GetMemoryConsentAsync(
        string agentId,
        string purposeOfUse = "treatment",
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
        => client.SendAsync<MemoryConsent>(
            HttpMethod.Get,
            $"{Root(agentId)}/memory-consent?purpose_of_use={Uri.EscapeDataString(purposeOfUse)}",
            cancellationToken: cancellationToken, requestOptions: requestOptions);

    public Task<MemoryReadiness> GetMemoryReadinessAsync(
        string agentId,
        string purposeOfUse = "treatment",
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
        => client.SendAsync<MemoryReadiness>(
            HttpMethod.Get,
            $"{Root(agentId)}/memory-readiness?purpose_of_use={Uri.EscapeDataString(purposeOfUse)}",
            cancellationToken: cancellationToken, requestOptions: requestOptions);

    public Task RevokeMemoryConsentAsync(
        string agentId,
        string purposeOfUse = "treatment",
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
        => client.SendNoContentAsync(
            HttpMethod.Delete,
            $"{Root(agentId)}/memory-consent?purpose_of_use={Uri.EscapeDataString(purposeOfUse)}",
            cancellationToken: cancellationToken, requestOptions: requestOptions);
}
