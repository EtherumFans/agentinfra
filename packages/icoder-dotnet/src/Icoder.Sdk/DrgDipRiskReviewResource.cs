using System.Text.Json;
using System.Text.Json.Serialization;

namespace Icoder.Sdk;

/// <summary>
/// Development-only China DRG/DIP risk review. This is not an official
/// grouper and cannot produce payment or settlement values.
/// </summary>
public sealed class DrgDipRiskReviewResource(ICoDerClient client)
{
    public async Task<DrgDipGovernance> GetGovernanceAsync(
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        var result = await client.SendAsync<DrgDipGovernance>(
            HttpMethod.Get, "/api/drg/governance", cancellationToken: cancellationToken,
            requestOptions: requestOptions)
            .ConfigureAwait(false);
        AssertDevelopmentOnly(result);
        return result;
    }

    public async Task<DrgDipRulesResponse> ListRulesAsync(
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        var result = await client.SendAsync<DrgDipRulesResponse>(
            HttpMethod.Get, "/api/drg/rules", cancellationToken: cancellationToken,
            requestOptions: requestOptions)
            .ConfigureAwait(false);
        AssertDevelopmentOnly(result.Governance);
        return result;
    }

    public async Task<DrgDipAnalyzeResponse> AnalyzeAsync(
        DrgDipAnalyzeRequest request,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNull(request, nameof(request));
        ValidateCode(request.PrimaryDiagnosis, "primary_diagnosis");
        foreach (var (item, index) in request.SecondaryDiagnoses.Select((value, index) => (value, index)))
        {
            ValidateCode(item, $"secondary_diagnoses[{index}]");
        }
        foreach (var (item, index) in request.Procedures.Select((value, index) => (value, index)))
        {
            ValidateCode(item, $"procedures[{index}]");
        }
        if (request.PatientGender is not ("" or "M" or "F"))
        {
            throw new ArgumentException("PatientGender must be M, F, or empty.", nameof(request));
        }
        if (request.PatientAge is < 0 or > 150)
        {
            throw new ArgumentOutOfRangeException(nameof(request), "PatientAge must be between 0 and 150.");
        }

        var result = await client.SendAsync<DrgDipAnalyzeResponse>(
            HttpMethod.Post, "/api/drg/analyze", request,
            cancellationToken: cancellationToken,
            requestOptions: requestOptions).ConfigureAwait(false);
        AssertDevelopmentOnly(result.Governance);
        if (!result.ManualReviewRequired || result.Error ||
            result.ReviewConclusion is not ("WARNING" or "FAIL") ||
            result.DrgImpact.BillingAuthoritative ||
            result.DrgImpact.ResultStatus != "experimental_candidate" ||
            result.DrgImpact.PaymentWeight != 0 ||
            result.DrgImpact.PaymentEstimateYuan != 0 ||
            result.DipImpact.BillingAuthoritative ||
            result.DipImpact.DipScore != 0 ||
            result.DipImpact.DipScoreCeiling != 0 ||
            result.DipImpact.PaymentEstimateYuan != 0)
        {
            throw new InvalidDataException(
                "DRG/DIP response violated the non-authoritative, non-payment contract.");
        }
        return result;
    }

    private static void AssertDevelopmentOnly(DrgDipGovernance value)
    {
        if (value.AssetId != "cn.drg_dip.risk_heuristics" ||
            value.Version != "1.0.0-development" ||
            value.Jurisdiction != "CN_GENERIC_DEVELOPMENT" ||
            value.AuthorityStatus != "experimental_unverified" ||
            value.LicenseStatus != "external_review_required" ||
            value.BillingAuthoritative || !value.ManualReviewRequired ||
            value.UseRestriction !=
                "development_risk_review_only_not_for_grouping_payment_or_settlement")
        {
            throw new InvalidDataException(
                "DRG/DIP governance response is not a development-only, manual-review contract.");
        }
    }

    private static void ValidateCode(DrgDipCode value, string field)
    {
        Guard.NotNull(value, nameof(value));
        var code = value.Code;
        if (string.IsNullOrWhiteSpace(code) || code.Length > 64 ||
            code.Any(character => char.IsControl(character)))
        {
            throw new ArgumentException(
                $"{field}.code must contain between 1 and 64 printable characters.", field);
        }
        if (value.Confidence is < 0 or > 1)
        {
            throw new ArgumentOutOfRangeException(
                field, $"{field}.confidence must be between 0 and 1.");
        }
    }
}

public sealed record DrgDipCode
{
    [JsonPropertyName("code")]
    public required string Code { get; init; }

    [JsonPropertyName("name")]
    public string Name { get; init; } = "";

    [JsonPropertyName("description")]
    public string Description { get; init; } = "";

    [JsonPropertyName("confidence")]
    public double Confidence { get; init; } = 1;
}

public sealed record DrgDipAnalyzeRequest
{
    [JsonPropertyName("primary_diagnosis")]
    public required DrgDipCode PrimaryDiagnosis { get; init; }

    [JsonPropertyName("secondary_diagnoses")]
    public IReadOnlyList<DrgDipCode> SecondaryDiagnoses { get; init; } = [];

    [JsonPropertyName("procedures")]
    public IReadOnlyList<DrgDipCode> Procedures { get; init; } = [];

    [JsonPropertyName("patient_gender")]
    public string PatientGender { get; init; } = "";

    [JsonPropertyName("patient_age")]
    public int? PatientAge { get; init; }
}

public sealed record DrgDipGovernance
{
    [JsonPropertyName("asset_id")]
    public required string AssetId { get; init; }

    [JsonPropertyName("version")]
    public required string Version { get; init; }

    [JsonPropertyName("asset_type")]
    public required string AssetType { get; init; }

    [JsonPropertyName("jurisdiction")]
    public required string Jurisdiction { get; init; }

    [JsonPropertyName("authority_status")]
    public required string AuthorityStatus { get; init; }

    [JsonPropertyName("license_status")]
    public required string LicenseStatus { get; init; }

    [JsonPropertyName("effective_from")]
    public string? EffectiveFrom { get; init; }

    [JsonPropertyName("effective_to")]
    public string? EffectiveTo { get; init; }

    [JsonPropertyName("billing_authoritative")]
    public bool BillingAuthoritative { get; init; }

    [JsonPropertyName("manual_review_required")]
    public bool ManualReviewRequired { get; init; }

    [JsonPropertyName("use_restriction")]
    public required string UseRestriction { get; init; }
}

public sealed record DrgDipImpact
{
    [JsonPropertyName("predicted_drg")]
    public required string PredictedDrg { get; init; }

    [JsonPropertyName("drg_name")]
    public required string DrgName { get; init; }

    [JsonPropertyName("mdc")]
    public required string Mdc { get; init; }

    [JsonPropertyName("mdc_name")]
    public required string MdcName { get; init; }

    [JsonPropertyName("adrg")]
    public required string Adrg { get; init; }

    [JsonPropertyName("cc_level")]
    public required string CcLevel { get; init; }

    [JsonPropertyName("grouping_method")]
    public required string GroupingMethod { get; init; }

    [JsonPropertyName("coverage")]
    public bool Coverage { get; init; }

    [JsonPropertyName("payment_weight")]
    public double PaymentWeight { get; init; }

    [JsonPropertyName("payment_estimate_yuan")]
    public double PaymentEstimateYuan { get; init; }

    [JsonPropertyName("billing_authoritative")]
    public bool BillingAuthoritative { get; init; }

    [JsonPropertyName("result_status")]
    public required string ResultStatus { get; init; }
}

public sealed record DipImpact
{
    [JsonPropertyName("dip_score")]
    public double DipScore { get; init; }

    [JsonPropertyName("dip_score_ceiling")]
    public double DipScoreCeiling { get; init; }

    [JsonPropertyName("payment_estimate_yuan")]
    public double PaymentEstimateYuan { get; init; }

    [JsonPropertyName("note")]
    public required string Note { get; init; }

    [JsonPropertyName("billing_authoritative")]
    public bool BillingAuthoritative { get; init; }
}

public sealed record DrgDipRisk
{
    [JsonPropertyName("rule_id")]
    public required string RuleId { get; init; }

    [JsonPropertyName("severity")]
    public required string Severity { get; init; }

    [JsonPropertyName("risk_type")]
    public required string RiskType { get; init; }

    [JsonPropertyName("message")]
    public required string Message { get; init; }

    [JsonPropertyName("suggestion")]
    public required string Suggestion { get; init; }
}

public sealed record DrgDipAnalyzeResponse
{
    [JsonPropertyName("primary_diagnosis")]
    public required DrgDipCode PrimaryDiagnosis { get; init; }

    [JsonPropertyName("secondary_diagnoses")]
    public IReadOnlyList<DrgDipCode> SecondaryDiagnoses { get; init; } = [];

    [JsonPropertyName("procedures")]
    public IReadOnlyList<DrgDipCode> Procedures { get; init; } = [];

    [JsonPropertyName("drg_impact")]
    public required DrgDipImpact DrgImpact { get; init; }

    [JsonPropertyName("dip_impact")]
    public required DipImpact DipImpact { get; init; }

    [JsonPropertyName("risks")]
    public IReadOnlyList<DrgDipRisk> Risks { get; init; } = [];

    [JsonPropertyName("recommendations")]
    public IReadOnlyList<string> Recommendations { get; init; } = [];

    [JsonPropertyName("quality_flags")]
    public IReadOnlyDictionary<string, JsonElement> QualityFlags { get; init; }
        = new Dictionary<string, JsonElement>();

    [JsonPropertyName("governance")]
    public required DrgDipGovernance Governance { get; init; }

    [JsonPropertyName("manual_review_required")]
    public bool ManualReviewRequired { get; init; }

    [JsonPropertyName("review_conclusion")]
    public required string ReviewConclusion { get; init; }

    [JsonPropertyName("confidence")]
    public double Confidence { get; init; }

    [JsonPropertyName("notes")]
    public required string Notes { get; init; }

    [JsonPropertyName("provider")]
    public required string Provider { get; init; }

    [JsonPropertyName("model")]
    public required string Model { get; init; }

    [JsonPropertyName("is_mock")]
    public bool IsMock { get; init; }

    [JsonPropertyName("error")]
    public bool Error { get; init; }

    [JsonPropertyName("error_reason")]
    public required string ErrorReason { get; init; }
}

public sealed record DrgDipRule
{
    [JsonPropertyName("id")]
    public required string Id { get; init; }

    [JsonPropertyName("name")]
    public required string Name { get; init; }

    [JsonPropertyName("severity")]
    public required string Severity { get; init; }

    [JsonPropertyName("category")]
    public required string Category { get; init; }

    [JsonPropertyName("description")]
    public required string Description { get; init; }
}

public sealed record DrgDipRulesResponse
{
    [JsonPropertyName("rule_set")]
    public required string RuleSet { get; init; }

    [JsonPropertyName("total")]
    public int Total { get; init; }

    [JsonPropertyName("rules")]
    public IReadOnlyList<DrgDipRule> Rules { get; init; } = [];

    [JsonPropertyName("governance")]
    public required DrgDipGovernance Governance { get; init; }
}
