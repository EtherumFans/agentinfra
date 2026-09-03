namespace Icoder.Sdk;

public sealed class FactsResource(ICoDerClient client)
{
    public Task<FactExtractionResponse> ExtractAsync(
        FactExtractionRequest request,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNull(request, nameof(request));
        if (request.Context.Count is < 1 or > 64)
        {
            throw new ArgumentException("Facts context must contain between 1 and 64 items.", nameof(request));
        }
        if (request.Context.Any(item => string.IsNullOrWhiteSpace(item.Text)))
        {
            throw new ArgumentException("Every Facts context item must contain non-empty text.", nameof(request));
        }
        if (request.Context.Sum(item => item.Text.Length) > 200_000)
        {
            throw new ArgumentException("Facts context exceeds the 200,000 character limit.", nameof(request));
        }
        return client.SendAsync<FactExtractionResponse>(
            HttpMethod.Post,
            "/api/v2/tools/extract-facts",
            request,
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task<FactsEnvelope> ListAsync(
        string interactionId,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
        => client.SendAsync<FactsEnvelope>(
            HttpMethod.Get,
            $"/api/v2/tools/interactions/{Escape(interactionId)}/facts",
            cancellationToken: cancellationToken, requestOptions: requestOptions);

    public Task<FactsEnvelope> CreateAsync(
        string interactionId,
        IReadOnlyList<FactCreateInput> facts,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNull(facts, nameof(facts));
        return client.SendAsync<FactsEnvelope>(
            HttpMethod.Post,
            $"/api/v2/tools/interactions/{Escape(interactionId)}/facts",
            new { facts },
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task<FactsEnvelope> UpdateBatchAsync(
        string interactionId,
        IReadOnlyList<FactUpdateInput> facts,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNull(facts, nameof(facts));
        return client.SendAsync<FactsEnvelope>(
            Compatibility.Patch,
            $"/api/v2/tools/interactions/{Escape(interactionId)}/facts",
            new { facts },
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task<FactRecord> UpdateAsync(
        string interactionId,
        FactUpdateInput fact,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNull(fact, nameof(fact));
        return client.SendAsync<FactRecord>(
            Compatibility.Patch,
            $"/api/v2/tools/interactions/{Escape(interactionId)}/facts/{Escape(fact.FactId)}",
            new
            {
                text = fact.Text,
                group = fact.Group,
                source = fact.Source,
                isDiscarded = fact.IsDiscarded,
            },
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    private static string Escape(string value)
    {
        Guard.NotNullOrWhiteSpace(value, nameof(value));
        return Uri.EscapeDataString(value);
    }
}
