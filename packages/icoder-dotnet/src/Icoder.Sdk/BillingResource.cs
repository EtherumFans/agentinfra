using System.Text.Json.Serialization;

namespace Icoder.Sdk;

/// <summary>Development ledger and PHI-free Agent Run settlement endpoints.</summary>
public sealed class BillingResource(ICoDerClient client)
{
    public Task<BillingBalance> GetBalanceAsync(
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
        => client.SendAsync<BillingBalance>(
            HttpMethod.Get, "/api/billing/balance", cancellationToken: cancellationToken,
            requestOptions: requestOptions);

    public Task<BillingRunSettlementList> ListRunSettlementsAsync(
        int limit = 20,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        if (limit is < 1 or > 100)
        {
            throw new ArgumentOutOfRangeException(
                nameof(limit), "Settlement limit must be between 1 and 100.");
        }
        return client.SendAsync<BillingRunSettlementList>(
            HttpMethod.Get,
            $"/api/billing/run-settlements?limit={limit}",
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task<AgentRunBilling> RetryRunSettlementAsync(
        string runId,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(runId, nameof(runId));
        return client.SendAsync<AgentRunBilling>(
            HttpMethod.Post,
            $"/api/billing/run-settlements/{Uri.EscapeDataString(runId)}/retry",
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task<BillingReconciliationOutcome> ReconcileStaleRunSettlementsAsync(
        int olderThanSeconds = 3600,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        if (olderThanSeconds is < 300 or > 604800)
        {
            throw new ArgumentOutOfRangeException(
                nameof(olderThanSeconds),
                "Reconciliation age must be between 300 and 604800 seconds.");
        }
        return client.SendAsync<BillingReconciliationOutcome>(
            HttpMethod.Post,
            "/api/billing/run-settlements/reconcile-stale" +
            $"?older_than_seconds={olderThanSeconds}",
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }
}

public sealed record BillingReconciliationOutcome
{
    [JsonPropertyName("simulation")]
    public bool Simulation { get; init; }

    [JsonPropertyName("released")]
    public int Released { get; init; }

    [JsonPropertyName("marked_retryable")]
    public int MarkedRetryable { get; init; }

    [JsonPropertyName("skipped_active")]
    public int SkippedActive { get; init; }

    [JsonPropertyName("inspected")]
    public int Inspected { get; init; }

    [JsonPropertyName("older_than_seconds")]
    public int OlderThanSeconds { get; init; }
}

public sealed record BillingBalance
{
    [JsonPropertyName("balance")]
    public decimal Balance { get; init; }

    [JsonPropertyName("reserved")]
    public decimal Reserved { get; init; }

    [JsonPropertyName("available")]
    public decimal Available { get; init; }

    [JsonPropertyName("currency")]
    public string Currency { get; init; } = "CNY";

    [JsonPropertyName("simulation")]
    public bool Simulation { get; init; }

    [JsonPropertyName("ledger_authoritative")]
    public bool LedgerAuthoritative { get; init; }

    [JsonPropertyName("quota")]
    public BillingQuota? Quota { get; init; }

    [JsonPropertyName("alerts")]
    public BillingAlerts? Alerts { get; init; }
}

public sealed record BillingQuota
{
    [JsonPropertyName("kind")]
    public required string Kind { get; init; }

    [JsonPropertyName("limit")]
    public decimal? Limit { get; init; }

    [JsonPropertyName("remaining")]
    public decimal Remaining { get; init; }

    [JsonPropertyName("enforced")]
    public bool Enforced { get; init; }
}

public sealed record BillingAlerts
{
    [JsonPropertyName("low_balance")]
    public bool LowBalance { get; init; }

    [JsonPropertyName("threshold")]
    public decimal Threshold { get; init; }
}

public sealed record BillingRunSettlement
{
    [JsonPropertyName("run_id")]
    public required string RunId { get; init; }

    [JsonPropertyName("status")]
    public required string Status { get; init; }

    [JsonPropertyName("reserved_amount")]
    public decimal ReservedAmount { get; init; }

    [JsonPropertyName("settled_amount")]
    public decimal SettledAmount { get; init; }

    [JsonPropertyName("currency")]
    public string Currency { get; init; } = "CNY";

    [JsonPropertyName("error_code")]
    public string? ErrorCode { get; init; }

    [JsonPropertyName("created_at")]
    public string? CreatedAt { get; init; }
}

public sealed record BillingRunSettlementList
{
    [JsonPropertyName("items")]
    public IReadOnlyList<BillingRunSettlement> Items { get; init; } = [];

    [JsonPropertyName("total")]
    public int Total { get; init; }

    [JsonPropertyName("simulation")]
    public bool Simulation { get; init; }
}
