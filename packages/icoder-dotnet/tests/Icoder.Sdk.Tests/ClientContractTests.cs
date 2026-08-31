using System.IO;
using System.Net;
using System.Net.WebSockets;
using System.Text;
using System.Text.Json;
using Icoder.Sdk;
using Xunit;

namespace Icoder.Sdk.Tests;

public sealed class ClientContractTests
{
    [Fact]
    public async Task AgentConnectorsExposeTypedResourcesCredentialsAndParallelGraph()
    {
        var captured = new List<CapturedRequest>();
        using var client = CreateClient(async request =>
        {
            var item = await CapturedRequest.FromAsync(request);
            captured.Add(item);
            if (request.Method == HttpMethod.Get)
            {
                return Json(HttpStatusCode.OK, """
                    {"connectors":[{"id":"con-1","agent_id":"agent/one","type":"mcp",
                    "name":"policy","description":"","enabled":true,
                    "config":{"url":"https://mcp.example","redirect_policy":"deny","max_redirects":0},
                    "target_agent_id":null,"normalized_url":"https://mcp.example",
                    "schema_ref":null,"schema_digest":null,"version":1,
                    "credential":{"present":false},"created_by":"test",
                    "created_at":"2026-08-22T00:00:00Z","updated_at":"2026-08-22T00:00:00Z"}],
                    "total":1}
                    """);
            }
            return Json(HttpStatusCode.OK, """
                {"version":"1.0","enabled":true,"execution_mode":"parallel",
                "max_concurrency":2,"nodes":[],"revision":1}
                """);
        });

        var list = await client.AgentConnectors.ListAsync("agent/one");
        var graph = await client.AgentConnectors.PutGraphAsync(
            "agent/one",
            new ConnectorGraphPutRequest
            {
                ExpectedRevision = 0,
                Enabled = true,
                ExecutionMode = "parallel",
                MaxConcurrency = 2,
            });

        Assert.Single(list.Connectors);
        Assert.Equal("mcp", list.Connectors[0].Type);
        Assert.Equal("parallel", graph.ExecutionMode);
        Assert.Equal("/api/v2/agentic/agents/agent%2Fone/connectors", captured[0].PathAndQuery);
        Assert.Equal("/api/v2/agentic/agents/agent%2Fone/connector-graph", captured[1].PathAndQuery);
        Assert.Contains("\"expected_revision\":0", captured[1].Body);
        Assert.Contains("\"execution_mode\":\"parallel\"", captured[1].Body);
    }

    [Fact]
    public async Task DrgDipRiskReviewAcceptsOnlyDevelopmentZeroPaymentContract()
    {
        CapturedRequest? captured = null;
        using var client = CreateClient(async request =>
        {
            captured = await CapturedRequest.FromAsync(request);
            return Json(HttpStatusCode.OK, """
                {"primary_diagnosis":{"code":"I10","name":"","description":"","confidence":1},
                 "secondary_diagnoses":[],"procedures":[],
                 "drg_impact":{"predicted_drg":"FR19","drg_name":"candidate","mdc":"MDCF",
                  "mdc_name":"","adrg":"FR1","cc_level":"","grouping_method":"medical",
                  "coverage":true,"payment_weight":0,"payment_estimate_yuan":0,
                  "billing_authoritative":false,"result_status":"experimental_candidate"},
                 "dip_impact":{"dip_score":0,"dip_score_ceiling":0,"payment_estimate_yuan":0,
                  "note":"not available","billing_authoritative":false},
                 "risks":[],"recommendations":[],"quality_flags":{},
                 "governance":{"asset_id":"cn.drg_dip.risk_heuristics",
                  "version":"1.0.0-development","asset_type":"risk_review_rule_pack",
                  "jurisdiction":"CN_GENERIC_DEVELOPMENT","authority_status":"experimental_unverified",
                  "license_status":"external_review_required","effective_from":null,"effective_to":null,
                  "billing_authoritative":false,"manual_review_required":true,
                  "use_restriction":"development_risk_review_only_not_for_grouping_payment_or_settlement"},
                 "manual_review_required":true,"review_conclusion":"WARNING","confidence":0.5,
                 "notes":"development only","provider":"drg-analyzer","model":"development",
                 "is_mock":false,"error":false,"error_reason":""}
                """);
        });

        var result = await client.DrgDipRiskReview.AnalyzeAsync(new DrgDipAnalyzeRequest
        {
            PrimaryDiagnosis = new DrgDipCode { Code = "I10" },
        });

        Assert.NotNull(captured);
        Assert.Equal("POST", captured!.Method);
        Assert.Equal("/api/drg/analyze", captured.PathAndQuery);
        Assert.Equal("Bearer token-old", captured.Authorization);
        Assert.Equal(0, result.DrgImpact.PaymentEstimateYuan);
        Assert.True(result.ManualReviewRequired);
    }

    [Fact]
    public async Task DrgDipRiskReviewFailsClosedOnBillingGovernance()
    {
        using var client = CreateClient(_ => Task.FromResult(Json(HttpStatusCode.OK, """
            {"asset_id":"cn.drg_dip.risk_heuristics","version":"1.0.0-development",
             "asset_type":"risk_review_rule_pack","jurisdiction":"CN_GENERIC_DEVELOPMENT",
             "authority_status":"experimental_unverified","license_status":"external_review_required",
             "effective_from":null,"effective_to":null,"billing_authoritative":true,
             "manual_review_required":true,
             "use_restriction":"development_risk_review_only_not_for_grouping_payment_or_settlement"}
            """)));

        await Assert.ThrowsAsync<InvalidDataException>(
            () => client.DrgDipRiskReview.GetGovernanceAsync());
    }

    [Fact]
    public async Task ModelsCatalogUsesAuthenticatedSecretFreeEndpoint()
    {
        CapturedRequest? captured = null;
        using var client = CreateClient(async request =>
        {
            captured = await CapturedRequest.FromAsync(request);
            return Json(HttpStatusCode.OK, """
                {"active_provider":"mock","active_model":"mock/1.0",
                 "operator_default_provider":"mock","operator_default_model":"mock/1.0",
                 "effective_deployment_id":"mock",
                 "tenant_selection":{"mode":"inherit","deployment_id":null,"version":0},
                 "registered_deployments":[],"selection_editable":true,"tenant_region":"cn",
                 "live_canary_available":false,
                 "live_canary_policy":{"purpose":"connectivity_only_no_patient_data",
                  "fixed_synthetic_payload":true,"patient_data_allowed":false,
                  "requires_owner_admin":true,"requires_explicit_acknowledgement":true,
                  "max_cost_cny":0.05,"max_output_tokens":8,"timeout_seconds":15,
                  "cooldown_seconds":300},
                 "egress_policy":"strict","external_llm_allowed":false,"models":[],
                 "readiness_scope":"configuration_and_policy_only",
                 "live_health_verified":false,"disclaimer":"configuration only"}
                """);
        });

        var catalog = await client.Models.GetCatalogAsync();

        Assert.NotNull(captured);
        Assert.Equal("/api/v1/model-catalog", captured!.PathAndQuery);
        Assert.Equal("Bearer token-old", captured.Authorization);
        Assert.False(catalog.LiveHealthVerified);
        Assert.Equal("configuration_and_policy_only", catalog.ReadinessScope);
    }

    [Fact]
    public async Task ModelsLiveCanarySendsOnlyFixedExplicitBudgetedContract()
    {
        CapturedRequest? captured = null;
        using var client = CreateClient(async request =>
        {
            captured = await CapturedRequest.FromAsync(request);
            return Json(HttpStatusCode.OK, """
                {"deployment_id":"deepseek","provider_id":"deepseek","model":"deepseek-chat",
                 "status":"reachable","reason_code":"ok",
                 "probe_mode":"external_connectivity_canary","egress_decision":"allow",
                 "synthetic_payload":true,"patient_data_sent":false,
                 "expected_token_matched":true,"latency_ms":25,
                 "usage":{"input_tokens":31,"output_tokens":4},
                 "cost":{"amount":0.000006,"currency":"CNY","billing_authoritative":false,
                  "source":"provider_usage_pricing_estimate"},
                 "request_cost_cap_cny":0.01,"estimated_max_cost_cny":0.000146,
                 "checked_at":"2026-08-21T00:00:00Z"}
                """);
        });

        var result = await client.Models.LiveCanaryAsync("deepseek", 0.01m);

        Assert.NotNull(captured);
        Assert.Equal("POST", captured!.Method);
        Assert.Equal("/api/v1/model-catalog/live-canary", captured.PathAndQuery);
        Assert.Contains("\"acknowledge_external_call\":true", captured.Body);
        Assert.Contains("\"purpose\":\"connectivity_only_no_patient_data\"", captured.Body);
        Assert.DoesNotContain("prompt", captured.Body, StringComparison.OrdinalIgnoreCase);
        Assert.False(result.PatientDataSent);
        Assert.False(result.Cost.BillingAuthoritative);
    }

    [Fact]
    public async Task ModelsSelectionUsesVersionedTenantEndpoint()
    {
        CapturedRequest? captured = null;
        using var client = CreateClient(async request =>
        {
            captured = await CapturedRequest.FromAsync(request);
            return Json(HttpStatusCode.OK, """
                {"mode":"pinned","deployment_id":"qwen-cn-a","version":2}
                """);
        });

        var selection = await client.Models.UpdateSelectionAsync(
            new UpdateModelSelectionRequest("pinned", 1, "qwen-cn-a"));

        Assert.NotNull(captured);
        Assert.Equal("PUT", captured!.Method);
        Assert.Equal("/api/v1/model-catalog/selection", captured.PathAndQuery);
        Assert.Contains("\"expected_version\":1", captured.Body);
        Assert.Equal(2, selection.Version);
    }

    [Fact]
    public async Task ModelsClinicalPackageActivationIsExplicitAndMetadataOnly()
    {
        CapturedRequest? captured = null;
        using var client = CreateClient(async request =>
        {
            captured = await CapturedRequest.FromAsync(request);
            return Json(HttpStatusCode.OK, """
                {"id":"activation-1","use_case":"clinical_coding_decision_support",
                 "package_id":"11111111-1111-4111-8111-111111111111",
                 "previous_package_id":null,"deployment_mode":"hospital_private",
                 "record_version":1,"activated_by_user_id":"user-1",
                 "created_at":"2026-08-27T00:00:00Z","updated_at":"2026-08-27T00:00:00Z",
                 "activation_blockers":[],"runtime_loading_enabled":false}
                """);
        });

        var result = await client.Models.ActivateClinicalPackageAsync(
            "clinical_coding_decision_support",
            new ClinicalModelActivationRequest(
                "11111111-1111-4111-8111-111111111111", "hospital_private", 0));

        Assert.NotNull(captured);
        Assert.Equal("PUT", captured!.Method);
        Assert.Equal(
            "/api/v1/clinical-model-packages/activations/clinical_coding_decision_support",
            captured.PathAndQuery);
        Assert.Contains("\"acknowledge_clinical_governance\":true", captured.Body);
        Assert.DoesNotContain("patient", captured.Body, StringComparison.OrdinalIgnoreCase);
        Assert.False(result.RuntimeLoadingEnabled);
    }

    [Fact]
    public async Task ModelsSyntheticArtifactShadowBindingIsExplicitAndNoInference()
    {
        CapturedRequest? captured = null;
        using var client = CreateClient(async request =>
        {
            captured = await CapturedRequest.FromAsync(request);
            return Json(HttpStatusCode.OK, """
                {"id":"binding-1","use_case":"clinical_coding_decision_support",
                 "package_id":"package-1","attestation_id":"attestation-1",
                 "previous_package_id":null,"previous_attestation_id":null,
                 "mode":"shadow_only","record_version":1,"bound_by_user_id":"user-1",
                 "created_at":"2026-08-27T00:00:00Z","updated_at":"2026-08-27T00:00:00Z",
                 "evaluation_gate_status":"not_evaluated","last_evaluation_id":null,
                 "last_evaluated_at":null,
                 "patient_data_allowed":false,"runtime_inference_enabled":false,
                 "predictions_emitted":false}
                """);
        });

        var result = await client.Models.BindClinicalShadowAttestationAsync(
            "clinical_coding_decision_support",
            new ClinicalModelShadowBindingRequest("attestation-1", 0));

        Assert.NotNull(captured);
        Assert.Equal("PUT", captured!.Method);
        Assert.Equal(
            "/api/v1/clinical-model-packages/shadow-bindings/clinical_coding_decision_support",
            captured.PathAndQuery);
        Assert.Contains("\"acknowledge_shadow_only\":true", captured.Body);
        Assert.False(result.PatientDataAllowed);
        Assert.False(result.RuntimeInferenceEnabled);
        Assert.False(result.PredictionsEmitted);
    }

    [Fact]
    public async Task ModelsSyntheticShadowEvaluationUsesAggregateFaultContract()
    {
        CapturedRequest? captured = null;
        using var client = CreateClient(async request =>
        {
            captured = await CapturedRequest.FromAsync(request);
            return Json(HttpStatusCode.OK, """
                {"id":"evaluation-1","binding_id":"binding-1",
                 "use_case":"clinical_coding_decision_support","package_id":"package-1",
                 "attestation_id":"attestation-1","source":"synthetic_fault_injection",
                 "suite_id":"suite-1","suite_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                 "artifact_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                 "observation_report_sha256":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
                 "result":"stopped","reason_code":"worker_timeout","fault_mode":"worker_timeout",
                 "run_count":1,"vector_observation_count":0,"success_count":0,"mismatch_count":0,
                 "error_count":1,"latency_p50_ms":5001,"latency_p95_ms":5001,
                 "artifact_reverified":false,"rollback_performed":true,
                 "binding_version_before":2,"binding_version_after":3,
                 "evaluated_by_user_id":"user-1","created_at":"2026-08-27T00:00:00Z",
                 "aggregate_only":true,"patient_data_used":false,"raw_input_stored":false,
                 "predictions_emitted":false,"network_used":false,
                 "production_inference_enabled":false}
                """);
        });

        var result = await client.Models.EvaluateSyntheticClinicalShadowAsync(
            "clinical_coding_decision_support",
            new ClinicalModelShadowEvaluationRequest(
                2, FaultMode: "worker_timeout", AcknowledgeFaultInjection: true));

        Assert.NotNull(captured);
        Assert.Equal("POST", captured!.Method);
        Assert.EndsWith("/synthetic-evaluation", captured.PathAndQuery);
        Assert.Contains("\"acknowledge_synthetic_only\":true", captured.Body);
        Assert.Contains("\"acknowledge_fault_injection\":true", captured.Body);
        Assert.True(result.RollbackPerformed);
        Assert.False(result.PatientDataUsed);
        Assert.False(result.PredictionsEmitted);
        Assert.False(result.ProductionInferenceEnabled);
    }

    [Fact]
    public async Task ModelsShadowEvaluationJobUsesIdempotencyAndNoPatientPayload()
    {
        CapturedRequest? captured = null;
        using var client = CreateClient(async request =>
        {
            captured = await CapturedRequest.FromAsync(request);
            return Json(HttpStatusCode.Accepted, """
                {"id":"job-1","binding_id":"binding-1",
                 "use_case":"clinical_coding_decision_support","package_id":"package-1",
                 "attestation_id":"attestation-1","binding_record_version":3,
                 "request_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                 "fault_mode":"none","status":"queued","attempt_count":0,"max_attempts":3,
                 "evaluation_id":null,"error_code":null,"rollback_performed":false,
                 "created_by_user_id":"user-1","started_at":null,"completed_at":null,
                 "created_at":"2026-08-27T00:00:00Z","updated_at":"2026-08-27T00:00:00Z",
                 "lease_active":false,"artifact_source":"repository_fixture",
                 "aggregate_only":true,"patient_data_used":false,"raw_input_stored":false,
                 "predictions_emitted":false,"network_used":false,
                 "production_inference_enabled":false}
                """);
        });

        var result = await client.Models.CreateClinicalShadowEvaluationJobAsync(
            "clinical_coding_decision_support",
            new ClinicalModelShadowJobRequest(3),
            "shadow-job-0001");

        Assert.NotNull(captured);
        Assert.Equal("POST", captured!.Method);
        Assert.EndsWith("/evaluation-jobs", captured.PathAndQuery);
        Assert.Equal("shadow-job-0001", captured.IdempotencyKey);
        Assert.Contains("\"acknowledge_synthetic_only\":true", captured.Body);
        Assert.DoesNotContain("patient", captured.Body, StringComparison.OrdinalIgnoreCase);
        Assert.Equal("queued", result.Status);
        Assert.False(result.LeaseActive);
        Assert.False(result.PatientDataUsed);
        Assert.False(result.PredictionsEmitted);
    }

    [Fact]
    public async Task ModelsShadowJobOperationsExposeCancellationAndAggregateHealth()
    {
        var calls = new List<CapturedRequest>();
        using var client = CreateClient(async request =>
        {
            calls.Add(await CapturedRequest.FromAsync(request));
            return calls.Count switch
            {
                1 => Json(HttpStatusCode.OK, """
                    {"id":"job-1","binding_id":"binding-1",
                     "use_case":"clinical_coding_decision_support","package_id":"package-1",
                     "attestation_id":"attestation-1","binding_record_version":3,
                     "request_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                     "fault_mode":"none","status":"cancelled","attempt_count":1,"max_attempts":3,
                     "evaluation_id":null,"error_code":null,"rollback_performed":false,
                     "created_by_user_id":"user-1","started_at":"2026-08-27T00:00:00Z",
                     "completed_at":"2026-08-27T00:00:01Z","cancellation_reason":"safety_stop",
                     "cancelled_at":"2026-08-27T00:00:01Z","cancelled_by_user_id":"user-1",
                     "created_at":"2026-08-27T00:00:00Z","updated_at":"2026-08-27T00:00:01Z",
                     "lease_active":false,"artifact_source":"repository_synthetic_fixture",
                     "aggregate_only":true,"patient_data_used":false,"raw_input_stored":false,
                     "predictions_emitted":false,"network_used":false,
                     "production_inference_enabled":false}
                    """),
                2 => Json(HttpStatusCode.OK, """
                    {"status":"healthy","status_counts":{"queued":0,"running":0,
                     "passed":0,"stopped":0,"failed":0,"cancelled":1},
                     "due_queued_count":0,"active_lease_count":0,"expired_lease_count":0,
                     "exhausted_count":0,"oldest_due_age_seconds":0,"alert_codes":[],
                     "evaluated_at":"2026-08-27T00:00:02Z","aggregate_only":true,
                     "patient_data_used":false,"identifiers_emitted":false}
                    """),
                _ => Json(HttpStatusCode.OK, """
                    {"finalized_exhausted_count":0,"aggregate_only":true,
                     "patient_data_used":false,"identifiers_emitted":false}
                    """),
            };
        });

        var cancelled = await client.Models.CancelClinicalShadowEvaluationJobAsync(
            "job-1", "safety_stop");
        var health = await client.Models.GetClinicalShadowEvaluationJobHealthAsync();
        var maintenance = await client.Models
            .MaintainClinicalShadowEvaluationJobsSimulationAsync();

        Assert.Equal("/api/v1/clinical-model-packages/shadow-evaluation-jobs/job-1/cancel",
            calls[0].PathAndQuery);
        Assert.Contains("\"reason\":\"safety_stop\"", calls[0].Body);
        Assert.EndsWith("/health/summary", calls[1].PathAndQuery);
        Assert.EndsWith("/maintenance/run", calls[2].PathAndQuery);
        Assert.Equal("cancelled", cancelled.Status);
        Assert.Equal("safety_stop", cancelled.CancellationReason);
        Assert.Equal("healthy", health.Status);
        Assert.False(health.IdentifiersEmitted);
        Assert.Equal(0, maintenance.FinalizedExhaustedCount);
        Assert.False(maintenance.PatientDataUsed);
    }

    [Fact]
    public async Task ModelsShadowDeadLetterReplayIsIdempotentAndAlertsAreAggregateOnly()
    {
        var calls = new List<CapturedRequest>();
        using var client = CreateClient(async request =>
        {
            calls.Add(await CapturedRequest.FromAsync(request));
            return calls.Count switch
            {
                1 => Json(HttpStatusCode.OK, """
                    {"items":[{"id":"dead-1","source_job_id":"job-failed",
                     "binding_id":"binding-1","use_case":"clinical_coding_decision_support",
                     "package_id":"package-1","attestation_id":"attestation-1",
                     "binding_record_version":3,"error_code":"LEASE_EXPIRED",
                     "attempt_count":3,"max_attempts":3,"status":"available",
                     "replayed_job_id":null,"replayed_at":null,"replayed_by_user_id":null,
                     "created_at":"2026-08-27T00:00:00Z","updated_at":"2026-08-27T00:00:00Z",
                     "aggregate_only":true,"patient_data_used":false,"raw_input_stored":false}],
                     "count":1,"aggregate_only":true}
                    """),
                2 => Json(HttpStatusCode.Accepted, """
                    {"id":"job-replay","binding_id":"binding-1",
                     "use_case":"clinical_coding_decision_support","package_id":"package-1",
                     "attestation_id":"attestation-1","binding_record_version":3,
                     "request_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                     "fault_mode":"none","status":"queued","attempt_count":0,"max_attempts":3,
                     "evaluation_id":null,"error_code":null,"rollback_performed":false,
                     "created_by_user_id":"user-1","started_at":null,"completed_at":null,
                     "cancellation_reason":null,"cancelled_at":null,"cancelled_by_user_id":null,
                     "created_at":"2026-08-27T00:00:00Z","updated_at":"2026-08-27T00:00:00Z",
                     "lease_active":false,"artifact_source":"repository_synthetic_fixture",
                     "aggregate_only":true,"patient_data_used":false,"raw_input_stored":false,
                     "predictions_emitted":false,"network_used":false,
                     "production_inference_enabled":false}
                    """),
                _ => Json(HttpStatusCode.OK, """
                    {"items":[{"alert_code":"dead_letter_backlog","state":"resolved",
                     "occurrence_count":1,"opened_at":"2026-08-27T00:00:00Z",
                     "last_evaluated_at":"2026-08-27T00:01:00Z",
                     "last_transition_at":"2026-08-27T00:01:00Z",
                     "resolved_at":"2026-08-27T00:01:00Z"}],"count":1,
                     "aggregate_only":true,"patient_data_used":false,
                     "identifiers_emitted":false}
                    """),
            };
        });

        var deadLetters = await client.Models.ListClinicalShadowDeadLettersAsync();
        var replay = await client.Models.ReplayClinicalShadowDeadLetterAsync(
            "dead-1", "shadow-replay-0001");
        var alerts = await client.Models.ListClinicalShadowAlertStatesAsync();

        Assert.EndsWith("/dead-letters/list", calls[0].PathAndQuery);
        Assert.EndsWith("/dead-letters/dead-1/replay", calls[1].PathAndQuery);
        Assert.Equal("shadow-replay-0001", calls[1].IdempotencyKey);
        Assert.EndsWith("/alerts/states", calls[2].PathAndQuery);
        Assert.Equal(1, deadLetters.Count);
        Assert.False(deadLetters.Items[0].PatientDataUsed);
        Assert.Equal("queued", replay.Status);
        Assert.Equal("resolved", alerts.Items[0].State);
        Assert.False(alerts.IdentifiersEmitted);
    }

    [Fact]
    public async Task A2AMultiTurnContextUsesProtocolHeaderAndServerContextId()
    {
        var calls = new List<CapturedRequest>();
        using var client = CreateClient(async request =>
        {
            calls.Add(await CapturedRequest.FromAsync(request));
            return calls.Count switch
            {
                1 => Json(HttpStatusCode.OK, """
                    {"jsonrpc":"2.0","id":"rpc-1","result":{"kind":"message","role":"agent",
                     "messageId":"agent-1","contextId":"11111111-1111-4111-8111-111111111111",
                     "parts":[],"metadata":{}}}
                    """),
                2 => Json(HttpStatusCode.OK, """
                    {"jsonrpc":"2.0","id":"rpc-2","result":{"kind":"message","role":"agent",
                     "messageId":"agent-2","contextId":"11111111-1111-4111-8111-111111111111",
                     "parts":[],"metadata":{}}}
                    """),
                3 => Json(HttpStatusCode.OK, """
                    {"id":"11111111-1111-4111-8111-111111111111","items":[{},{},{},{}]}
                    """),
                _ => Json(HttpStatusCode.OK, """
                    {"jsonrpc":"2.0","id":null,"result":{"kind":"context",
                     "contextId":"11111111-1111-4111-8111-111111111111","deleted":true,
                     "reason":"user_requested"}}
                    """),
            };
        });

        var first = await client.A2A.MessageSendTextAsync("note-completeness-agent", "first");
        var second = await client.A2A.MessageSendTextAsync(
            "note-completeness-agent", "second", first.ContextId);
        var context = await client.A2A.GetContextAsync(
            "note-completeness-agent", first.ContextId);
        var deleted = await client.A2A.DeleteContextAsync(first.ContextId);

        Assert.Equal(first.ContextId, second.ContextId);
        Assert.Equal(4, context.Items.Count);
        Assert.True(deleted.Deleted);
        Assert.All(calls, call => Assert.Equal("0.3", call.A2AProtocolVersion));
        using var secondBody = JsonDocument.Parse(calls[1].Body!);
        Assert.Equal(
            first.ContextId,
            secondBody.RootElement.GetProperty("params").GetProperty("message")
                .GetProperty("contextId").GetString());
    }

    [Fact]
    public async Task A2AProtocolErrorDoesNotRetainServerDetails()
    {
        using var client = CreateClient(_ => Task.FromResult(Json(
            HttpStatusCode.InternalServerError,
            """
            {"jsonrpc":"2.0","id":"rpc-1","error":{"code":-32603,"message":"Internal error",
             "data":{"a2a_error_code":"PLANNING_FAILED","details":"patient-secret-value"}}}
            """)));

        var error = await Assert.ThrowsAsync<A2AProtocolException>(
            () => client.A2A.MessageSendTextAsync("note-completeness-agent", "synthetic"));

        Assert.Equal(-32603, error.JsonRpcCode);
        Assert.Equal("PLANNING_FAILED", error.A2AErrorCode);
        Assert.DoesNotContain("patient-secret-value", error.ToString());
    }

    [Fact]
    public async Task AgenticV2ContextTaskAndArtifactResourcesUseTypedProtocolContract()
    {
        var calls = new List<CapturedRequest>();
        using var client = CreateClient(async request =>
        {
            calls.Add(await CapturedRequest.FromAsync(request));
            return calls.Count switch
            {
                1 => Json(HttpStatusCode.OK, """
                    {"contexts":[{"id":"context-1","agentId":"agent-1","taskCount":1,
                     "createdAt":"2026-08-22T00:00:00Z","updatedAt":"2026-08-22T00:00:01Z",
                     "expiresAt":"2026-08-23T00:00:00Z"}],"nextPageToken":"next","totalSize":1}
                    """),
                2 => Json(HttpStatusCode.OK, """
                    {"id":"context-1","agentId":"agent-1","taskCount":1,
                     "createdAt":"2026-08-22T00:00:00Z","updatedAt":"2026-08-22T00:00:01Z",
                     "expiresAt":"2026-08-23T00:00:00Z","tasks":[]}
                    """),
                3 => Json(HttpStatusCode.OK, """
                    {"tasks":[{"id":"task-1","contextId":"context-1",
                     "status":{"state":"TASK_STATE_COMPLETED"},"artifacts":[],
                     "history":[],"metadata":{}}],"nextPageToken":null,"totalSize":1}
                    """),
                4 => Json(HttpStatusCode.OK, """
                    {"id":"task-1","contextId":"context-1",
                     "status":{"state":"TASK_STATE_COMPLETED"},"artifacts":[],
                     "history":[],"metadata":{}}
                    """),
                5 => Json(HttpStatusCode.OK, """
                    {"artifactId":"artifact/1","parts":[{"text":"result"}],"metadata":{}}
                    """),
                _ => new HttpResponseMessage(HttpStatusCode.NoContent),
            };
        });

        var contexts = await client.A2A.ListContextsV2Async(
            "agent/1", DateTimeOffset.Parse("2026-08-01T00:00:00Z"), pageSize: 10);
        var context = await client.A2A.GetContextV2Async("context/1", historyLength: 2);
        var tasks = await client.A2A.ListContextTasksV2Async(
            "context/1", pageSize: 5, historyLength: 1);
        var task = await client.A2A.GetContextTaskV2Async("context/1", "task/1");
        var artifact = await client.A2A.GetTaskArtifactV2Async(
            "context/1", "task/1", "artifact/1");
        await client.A2A.DeleteContextV2Async("context/1");

        Assert.Equal(1, contexts.TotalSize);
        Assert.Equal(1, context.TaskCount);
        Assert.Equal("task-1", tasks.Tasks.Single().Id);
        Assert.Equal("TASK_STATE_COMPLETED", task.Status.State);
        Assert.Equal("artifact/1", artifact.ArtifactId);
        Assert.Contains("agentId=agent%2F1", calls[0].PathAndQuery);
        Assert.Contains("historyLength=2", calls[1].PathAndQuery);
        Assert.Contains("historyLength=1", calls[2].PathAndQuery);
        Assert.Equal(
            "/api/v2/agentic/contexts/context%2F1/tasks/task%2F1/artifacts/artifact%2F1",
            calls[4].PathAndQuery);
        Assert.Equal("DELETE", calls[5].Method);
        Assert.All(calls, call => Assert.Equal("1.0", call.A2AVersion));
    }

    [Fact]
    public async Task ManagedArtifactObjectsUseQuarantineAuthorizationAndSingleDownloadContract()
    {
        var calls = new List<CapturedRequest>();
        using var client = CreateClient(async request =>
        {
            calls.Add(await CapturedRequest.FromAsync(request));
            return calls.Count switch
            {
                1 => Json(HttpStatusCode.Created, """
                    {"objectId":"obj/1","artifactId":"artifact/1","filename":"result.json",
                     "mediaType":"application/json","sizeBytes":2,
                     "sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                     "status":"available","malwareScanStatus":"clean","dlpScanStatus":"clear",
                     "dataClassification":"deidentified","rejectionCode":null,
                     "scanEngine":"icoder-safe-file-v1","createdAt":"2026-08-22T00:00:00Z",
                     "scannedAt":"2026-08-22T00:00:01Z"}
                    """),
                2 => Json(HttpStatusCode.OK, """
                    {"objects":[{"objectId":"obj/1","artifactId":"artifact/1",
                     "filename":"result.json","mediaType":"application/json","sizeBytes":2,
                     "sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                     "status":"available","malwareScanStatus":"clean","dlpScanStatus":"clear",
                     "dataClassification":"deidentified","rejectionCode":null,
                     "scanEngine":"icoder-safe-file-v1","createdAt":"2026-08-22T00:00:00Z",
                     "scannedAt":"2026-08-22T00:00:01Z"}],"totalSize":1}
                    """),
                3 => Json(HttpStatusCode.OK, """
                    {"objectId":"obj/1","expiresAt":"2026-08-22T00:01:00Z",
                     "singleUse":true,"purposeOfUse":"treatment",
                     "part":{"url":"https://api.cn.icoder.cloud/api/v2/agentic/artifact-objects/download/grant-123",
                     "filename":"result.json","mediaType":"application/json","metadata":{}}}
                    """),
                4 => new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new ByteArrayContent([1, 2]),
                },
                _ => new HttpResponseMessage(HttpStatusCode.NoContent),
            };
        });

        var uploaded = await client.A2A.UploadTaskArtifactObjectV2Async(
            "context/1", "task/1", "artifact/1", [123, 125],
            "result.json", "application/json");
        var listed = await client.A2A.ListTaskArtifactObjectsV2Async(
            "context/1", "task/1", "artifact/1");
        var authorized = await client.A2A.AuthorizeTaskArtifactObjectDownloadV2Async(
            "context/1", "task/1", "artifact/1", "obj/1", "treatment", 30);
        var bytes = await client.A2A.DownloadAuthorizedArtifactObjectV2Async(authorized);
        await client.A2A.DeleteTaskArtifactObjectV2Async(
            "context/1", "task/1", "artifact/1", "obj/1");

        Assert.Equal("available", uploaded.Status);
        Assert.Equal(1, listed.TotalSize);
        Assert.True(authorized.SingleUse);
        Assert.Equal(new byte[] { 1, 2 }, bytes);
        Assert.Equal(
            "/api/v2/agentic/contexts/context%2F1/tasks/task%2F1/artifacts/artifact%2F1/objects",
            calls[0].PathAndQuery);
        Assert.Contains("\"raw\":\"e30=\"", calls[0].Body);
        Assert.EndsWith("/objects/obj%2F1:authorize-download", calls[2].PathAndQuery);
        Assert.Contains("\"purposeOfUse\":\"treatment\"", calls[2].Body);
        Assert.Contains("artifact-objects/download/grant-123", calls[3].PathAndQuery);
        Assert.DoesNotContain("?", calls[3].PathAndQuery);
        Assert.Equal("Bearer token-old", calls[3].Authorization);
        Assert.Equal("DELETE", calls[4].Method);
        Assert.Equal("1.0", calls[0].A2AVersion);
        Assert.Equal("1.0", calls[2].A2AVersion);
    }

    [Fact]
    public async Task A2AStreamUsesAuthenticatedProtocolEndpointAndParsesEvents()
    {
        CapturedRequest? captured = null;
        using var client = CreateClient(async request =>
        {
            captured = await CapturedRequest.FromAsync(request);
            return new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(
                    "event: status\ndata: {\"state\":\"working\"}\n\n" +
                    "event: done\ndata: {}\n\n",
                    Encoding.UTF8,
                    "text/event-stream"),
            };
        });

        var events = new List<A2AStreamEvent>();
        await foreach (var item in client.A2A.MessageStreamTextAsync(
            "note/completeness", "safe input"))
        {
            events.Add(item);
        }

        Assert.NotNull(captured);
        Assert.Equal("POST", captured!.Method);
        Assert.Equal(
            "/api/icoder/agents/note%2Fcompleteness/v1/message:stream",
            captured.PathAndQuery);
        Assert.Equal("Bearer token-old", captured.Authorization);
        Assert.Equal("0.3", captured.A2AProtocolVersion);
        Assert.Equal(new[] { "status", "done" }, events.Select(item => item.Event));
        Assert.Contains("working", events[0].Data);
    }

    [Fact]
    public async Task A2AV1DurableTaskCoversPollListCancelAndSubscriptionResume()
    {
        var calls = new List<CapturedRequest>();
        using var client = CreateClient(async request =>
        {
            calls.Add(await CapturedRequest.FromAsync(request));
            return calls.Count switch
            {
                1 => Json(HttpStatusCode.OK, """
                    {"task":{"id":"task-1","contextId":"context-1",
                     "status":{"state":"TASK_STATE_SUBMITTED"},
                     "artifacts":[],"history":[],"metadata":{}}}
                    """),
                2 => Json(HttpStatusCode.OK, """
                    {"id":"task-1","contextId":"context-1",
                     "status":{"state":"TASK_STATE_WORKING"},
                     "artifacts":[],"history":[],"metadata":{}}
                    """),
                3 => Json(HttpStatusCode.OK, """
                    {"id":"task-1","contextId":"context-1",
                     "status":{"state":"TASK_STATE_COMPLETED"},
                     "artifacts":[],"history":[],"metadata":{}}
                    """),
                4 => Json(HttpStatusCode.OK, """
                    {"tasks":[],"nextPageToken":"","pageSize":10,"totalSize":0}
                    """),
                5 => Json(HttpStatusCode.OK, """
                    {"id":"task-1","contextId":"context-1",
                     "status":{"state":"TASK_STATE_CANCELED"},
                     "artifacts":[],"history":[],"metadata":{}}
                    """),
                _ => new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent(
                        "id: 2\nevent: status-update\ndata: {\"statusUpdate\":{\"taskId\":\"task-1\"}}\n\n" +
                        "id: 3\nevent: artifact-update\ndata: {\"artifactUpdate\":{\"taskId\":\"task-1\"}}\n\n",
                        Encoding.UTF8,
                        "text/event-stream"),
                },
            };
        });

        var submitted = await client.A2A.MessageSendV1TextAsync(
            "note/completeness",
            "safe input",
            returnImmediately: true,
            messageId: "message-1");
        var completed = await client.A2A.WaitTaskV1Async(
            "note/completeness",
            submitted.Task!.Id,
            timeout: TimeSpan.FromSeconds(1),
            pollInterval: TimeSpan.FromMilliseconds(1));
        var listed = await client.A2A.ListTasksV1Async(
            "note/completeness",
            pageSize: 10,
            includeArtifacts: true);
        var canceled = await client.A2A.CancelTaskV1Async(
            "note/completeness",
            "task-1");
        var events = new List<A2AStreamEvent>();
        await foreach (var item in client.A2A.SubscribeTaskV1Async(
            "note/completeness",
            "task-1",
            afterSequence: 1,
            lastEventId: "1"))
        {
            events.Add(item);
        }

        Assert.Equal("TASK_STATE_COMPLETED", completed.Status.State);
        Assert.Equal(0, listed.TotalSize);
        Assert.Equal("TASK_STATE_CANCELED", canceled.Status.State);
        Assert.Equal(new[] { "2", "3" }, events.Select(item => item.Id));
        Assert.Equal(
            new[] { "status-update", "artifact-update" },
            events.Select(item => item.Event));
        Assert.Contains("statusUpdate", events[0].Data);
        Assert.Contains("artifactUpdate", events[1].Data);
        Assert.All(calls, call => Assert.Equal("1.0", call.A2AVersion));
        Assert.Contains(
            "/api/v2/agentic/agents/note%2Fcompleteness/message:send",
            calls[0].PathAndQuery);
        Assert.Contains("\"returnImmediately\":true", calls[0].Body);
        Assert.Equal("1", calls[^1].LastEventId);
        Assert.EndsWith("afterSequence=1", calls[^1].PathAndQuery);
    }

    [Fact]
    public async Task A2AV1WaitReturnsOnResumableInterruption()
    {
        using var client = CreateClient(_ => Task.FromResult(Json(
            HttpStatusCode.OK,
            """
            {"id":"task-input","contextId":"context-input",
             "status":{"state":"TASK_STATE_INPUT_REQUIRED"},
             "artifacts":[],"history":[],"metadata":{}}
            """)));

        var settled = await client.A2A.WaitTaskV1Async(
            "note/completeness",
            "task-input",
            timeout: TimeSpan.FromMilliseconds(100),
            pollInterval: TimeSpan.FromMilliseconds(1));

        Assert.Equal("TASK_STATE_INPUT_REQUIRED", settled.Status.State);
    }

    [Fact]
    public async Task A2AV1MessageStreamCarriesIncrementalArtifactFlags()
    {
        CapturedRequest? captured = null;
        using var client = CreateClient(async request =>
        {
            captured = await CapturedRequest.FromAsync(request);
            return new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(
                    "id: 1\nevent: task\ndata: {\"task\":{\"id\":\"task-stream\"}}\n\n" +
                    "id: 2\nevent: artifact-update\ndata: {\"artifactUpdate\":{\"taskId\":\"task-stream\",\"append\":false,\"lastChunk\":false}}\n\n" +
                    "id: 3\nevent: artifact-update\ndata: {\"artifactUpdate\":{\"taskId\":\"task-stream\",\"append\":true,\"lastChunk\":true}}\n\n",
                    Encoding.UTF8,
                    "text/event-stream"),
            };
        });

        var events = new List<A2AStreamEvent>();
        await foreach (var item in client.A2A.MessageStreamV1TextAsync(
            "note/completeness",
            "safe streamed input",
            contextId: "context-input",
            messageId: "message-stream-1",
            taskId: "task-input"))
        {
            events.Add(item);
        }

        Assert.NotNull(captured);
        Assert.Equal("POST", captured!.Method);
        Assert.Equal(
            "/api/v2/agentic/agents/note%2Fcompleteness/message:stream",
            captured.PathAndQuery);
        Assert.Equal("1.0", captured.A2AVersion);
        Assert.Contains("\"messageId\":\"message-stream-1\"", captured.Body);
        Assert.Contains("\"contextId\":\"context-input\"", captured.Body);
        Assert.Contains("\"taskId\":\"task-input\"", captured.Body);
        Assert.Equal(
            new[] { "task", "artifact-update", "artifact-update" },
            events.Select(item => item.Event));
        Assert.Contains("\"append\":false", events[1].Data);
        Assert.Contains("\"lastChunk\":false", events[1].Data);
        Assert.Contains("\"append\":true", events[2].Data);
        Assert.Contains("\"lastChunk\":true", events[2].Data);
    }

    [Fact]
    public async Task A2AV1ProtocolErrorRetainsOnlyStableGoogleRpcReason()
    {
        using var client = CreateClient(_ => Task.FromResult(Json(
            HttpStatusCode.NotFound,
            """
            {"error":{"code":404,"status":"NOT_FOUND","message":"Task not found",
             "details":[{"@type":"type.googleapis.com/google.rpc.ErrorInfo",
             "reason":"TASK_NOT_FOUND","metadata":{"secret":"patient-secret-value"}}]}}
            """)));

        var error = await Assert.ThrowsAsync<A2AProtocolException>(
            () => client.A2A.GetTaskV1Async("agent", "missing"));

        Assert.Equal(404, error.JsonRpcCode);
        Assert.Equal("TASK_NOT_FOUND", error.A2AErrorCode);
        Assert.DoesNotContain("patient-secret-value", error.ToString());
    }

    [Fact]
    public async Task AgenticTraceAndCallerFeedbackUseCurrentContextTaskPaths()
    {
        var calls = new List<CapturedRequest>();
        using var client = CreateClient(async request =>
        {
            calls.Add(await CapturedRequest.FromAsync(request));
            var path = request.RequestUri!.AbsolutePath;
            if (path.EndsWith("/trace"))
                return Json(HttpStatusCode.OK,
                    """{"traces":[],"nextPageToken":null,"totalSize":null}""");
            if (path.EndsWith("/training-authorization") && request.Method != HttpMethod.Delete)
                return Json(HttpStatusCode.OK,
                    """{"id":"ftg-1","feedbackId":"fb/one","taskId":"task/one","trainingAuthorized":true,"authorizationStatus":"active","purposeOfUse":"quality_improvement","dataScope":"feedback_metadata_only","expiresAt":"2026-08-23T00:00:00Z","createdAt":"2026-08-22T00:00:00Z","updatedAt":"2026-08-22T00:00:00Z","revokedAt":null,"version":1}""");
            if (request.Method == HttpMethod.Post)
                return Json(HttpStatusCode.Created,
                    """{"id":"fb-1","taskId":"task/one","rating":{"scale":"binary","value":1},"normalizedScore":1,"labels":["helpful"],"reason":null,"createdAt":"2026-08-22T00:00:00Z","target":{"messageId":"message-1"}}""");
            if (request.Method == HttpMethod.Get)
                return Json(HttpStatusCode.OK, """{"feedbacks":[]}""");
            return new HttpResponseMessage(HttpStatusCode.NoContent);
        });

        var traces = await client.A2A.ExportContextTracesAsync("context/one", 20);
        var feedback = await client.A2A.SubmitTaskFeedbackAsync(
            "context/one", "task/one", new AgenticFeedbackInput
            {
                Rating = new AgenticBinaryRating { Value = 1 },
                Labels = ["helpful"],
                Target = new AgenticFeedbackTarget { MessageId = "message-1" },
            });
        var listed = await client.A2A.ListTaskFeedbackAsync("context/one", "task/one");
        await client.A2A.DeleteTaskFeedbackAsync("context/one", "task/one");
        var training = await client.A2A.AuthorizeFeedbackForTrainingAsync(
            "context/one", "task/one", "fb/one",
            new FeedbackTrainingAuthorizationInput
            {
                ExpiresAt = DateTimeOffset.Parse("2026-08-23T00:00:00Z"),
                ApprovalReference = "qi-review-001",
            });
        await client.A2A.GetFeedbackTrainingAuthorizationAsync(
            "context/one", "task/one", "fb/one");
        await client.A2A.RevokeFeedbackTrainingAuthorizationAsync(
            "context/one", "task/one", "fb/one");

        Assert.Empty(traces.Traces);
        Assert.Equal("fb-1", feedback.Id);
        Assert.Empty(listed.Feedbacks);
        Assert.Equal("GET", calls[0].Method);
        Assert.Contains("/contexts/context%2Fone/trace?pageSize=20", calls[0].PathAndQuery);
        Assert.Contains("/tasks/task%2Fone/feedback", calls[1].PathAndQuery);
        Assert.Contains("\"messageId\":\"message-1\"", calls[1].Body);
        Assert.True(training.TrainingAuthorized);
        Assert.Contains(
            "/tasks/task%2Fone/feedback/fb%2Fone/training-authorization",
            calls[4].PathAndQuery);
        Assert.Equal("PUT", calls[4].Method);
        Assert.Contains("\"dataScope\":\"feedback_metadata_only\"", calls[4].Body);
        Assert.Equal("DELETE", calls[^1].Method);
    }

    [Fact]
    public async Task AgenticAgentUsageUsesCurrentDailyAggregationPath()
    {
        CapturedRequest? captured = null;
        using var client = CreateClient(async request =>
        {
            captured = await CapturedRequest.FromAsync(request);
            return Json(HttpStatusCode.OK, """
                {"granularity":"day","from":"2026-08-01T00:00:00Z","to":"2026-08-03T00:00:00Z",
                 "totals":{"invocations":3,"uniqueContexts":2},
                 "buckets":[{"periodStart":"2026-08-01T00:00:00Z","periodEnd":"2026-08-02T00:00:00Z",
                 "invocations":3,"uniqueContexts":2}]}
                """);
        });

        var usage = await client.A2A.GetAgentUsageAsync(
            "agent/one",
            DateTimeOffset.Parse("2026-08-01T00:00:00Z"),
            DateTimeOffset.Parse("2026-08-03T00:00:00Z"),
            "hour");

        Assert.Equal("day", usage.Granularity);
        Assert.Equal(2, usage.Totals.UniqueContexts);
        Assert.NotNull(captured);
        Assert.Contains("/agents/agent%2Fone/usage?", captured!.PathAndQuery);
        Assert.Contains("granularity=hour", captured.PathAndQuery);
        await Assert.ThrowsAsync<ArgumentOutOfRangeException>(
            () => client.A2A.GetAgentUsageAsync("agent", granularity: "month"));
    }

    [Fact]
    public async Task A2AV1AgentCardUsesAuthenticatedStandardDiscoveryPath()
    {
        CapturedRequest? captured = null;
        using var client = CreateClient(async request =>
        {
            captured = await CapturedRequest.FromAsync(request);
            return Json(HttpStatusCode.OK, """
                {"name":"Clinical Agent","description":"Synthetic contract fixture", "version":"1.0.0",
                 "supportedInterfaces":[{"url":"https://api.cn.icoder.cloud/api/v2/agentic/agents/agent%2Fone",
                 "protocolBinding":"JSONRPC","protocolVersion":"1.0"}],
                 "capabilities":{"streaming":true,"pushNotifications":false,"extendedAgentCard":false},
                 "defaultInputModes":["text/plain"],"defaultOutputModes":["application/json"],
                 "skills":[{"id":"run","name":"Run","description":"Run agent","tags":["clinical"],
                 "examples":[],"inputModes":["text/plain"],"outputModes":["application/json"]}],
                 "securitySchemes":{"bearerAuth":{"type":"http","scheme":"bearer"}},
                 "securityRequirements":[{"schemes":{"bearerAuth":{"list":[]}}}]}
                """);
        });

        var card = await client.A2A.GetAgentCardAsync("agent/one");

        Assert.Equal("Clinical Agent", card.Name);
        Assert.True(card.Capabilities.Streaming);
        Assert.Equal("JSONRPC", card.SupportedInterfaces.Single().ProtocolBinding);
        Assert.NotNull(captured);
        Assert.Equal("GET", captured!.Method);
        Assert.Equal(
            "/api/v2/agentic/agents/agent%2Fone/.well-known/agent-card.json",
            captured.PathAndQuery);
        Assert.Equal("1.0", captured.A2AVersion);
        Assert.Equal("Bearer token-old", captured.Authorization);
    }

    [Fact]
    public async Task MedicalCodingPricingUsesAuthenticatedServerEstimate()
    {
        CapturedRequest? captured = null;
        using var client = CreateClient(async request =>
        {
            captured = await CapturedRequest.FromAsync(request);
            return Json(HttpStatusCode.OK, """
                {"input_chars":600,"runtime_mode":"corti_like_fast","currency":"CNY",
                 "estimated_cost_min":0.0001,"estimated_cost_max":0.0009,
                 "estimated_model_calls_min":1,"estimated_model_calls_max":1,
                 "price_source":"server_configuration","billing_authoritative":false,
                 "disclaimer":"Provider usage is final."}
                """);
        });

        var estimate = await client.MedicalCoding.EstimateCostAsync(600);

        Assert.NotNull(captured);
        Assert.Equal("GET", captured!.Method);
        Assert.Equal(
            "/api/v1/coding/pricing?input_chars=600&mode=corti_like_fast",
            captured.PathAndQuery);
        Assert.Equal("Bearer token-old", captured.Authorization);
        Assert.False(estimate.BillingAuthoritative);
        Assert.Equal(0.0009, estimate.EstimatedCostMax);
    }

    [Fact]
    public async Task MedicalCodingPredictSendsNormalizedCortiFilter()
    {
        CapturedRequest? captured = null;
        using var client = CreateClient(async request =>
        {
            captured = await CapturedRequest.FromAsync(request);
            return Json(HttpStatusCode.OK, """
                {"codes":[],"summary":"ok","runtime_mode":"corti_like_fast",
                 "latency_ms":1,"llm_provider":"test","trace_id":"trace-1",
                 "run_id":"run-1","cost":{},"error":false,"error_reason":""}
                """);
        });

        await client.MedicalCoding.PredictAsync(new CodingPredictRequest
        {
            Text = "去标识病历",
            CodingSystems = ["icd10cn", "icd9cm3"],
            Filter = new CodingCodeFilter
            {
                Include = [" E11 ", "e11"],
                Exclude = ["E11.0"],
                Expand = false,
            },
        });

        Assert.NotNull(captured);
        Assert.Equal("/api/v1/coding/predict", captured!.PathAndQuery);
        using var body = JsonDocument.Parse(captured.Body!);
        var filter = body.RootElement.GetProperty("filter");
        Assert.Equal(["icd10cn", "icd9cm3"],
            body.RootElement.GetProperty("coding_systems").EnumerateArray()
                .Select(item => item.GetString()!).ToArray());
        Assert.False(body.RootElement.TryGetProperty("coding_system", out _));
        Assert.Equal(["E11"], filter.GetProperty("include").EnumerateArray()
            .Select(item => item.GetString()!).ToArray());
        Assert.Equal(["E11.0"], filter.GetProperty("exclude").EnumerateArray()
            .Select(item => item.GetString()!).ToArray());
        Assert.False(filter.GetProperty("expand").GetBoolean());
    }

    [Fact]
    public async Task MedicalCodingPredictRejectsInvalidFilterBeforeTransport()
    {
        var calls = 0;
        using var client = CreateClient(request =>
        {
            calls++;
            return Task.FromResult(Json(HttpStatusCode.OK, "{}"));
        });

        await Assert.ThrowsAsync<ArgumentException>(() =>
            client.MedicalCoding.PredictAsync(new CodingPredictRequest
            {
                Text = "去标识病历",
                Filter = new CodingCodeFilter { Include = [""] },
            }));
        Assert.Equal(0, calls);

        await Assert.ThrowsAsync<ArgumentException>(() =>
            client.MedicalCoding.PredictAsync(new CodingPredictRequest
            {
                Text = "去标识病历",
                CodingSystems = ["icd10cn", "icd10cn"],
            }));
        Assert.Equal(0, calls);
    }

    [Fact]
    public async Task AgentRunSendsBearerIdempotencyAndContractBody()
    {
        CapturedRequest? captured = null;
        using var client = CreateClient(async request =>
        {
            captured = await CapturedRequest.FromAsync(request);
            return Json(HttpStatusCode.OK, """
                {"agent_id":"medical-coding-agent","run_id":"run-1","trace_id":"trace-1",
                 "summary":"ok","result":{},"cost":{},"evidence":[],"warnings":[],
                 "trace_events":[],"manual_review_required":true,"error":false,
                 "billing":{"simulation":true,"status":"SETTLED","reserved_amount":0.05,
                  "settled_amount":0.013,"balance_after":9.987,"currency":"CNY",
                  "error_code":null}}
                """);
        });

        var response = await client.AgentRuns.RunTextAsync(
            "medical-coding-agent",
            "患者胸痛",
            "corti_like_fast",
            "idem-001");

        Assert.Equal("run-1", response.RunId);
        Assert.NotNull(response.Billing);
        Assert.Equal(0.013m, response.Billing!.SettledAmount);
        Assert.NotNull(captured);
        Assert.Equal("POST", captured.Method);
        Assert.Equal("/api/v1/agents/medical-coding-agent/run", captured.PathAndQuery);
        Assert.Equal("Bearer token-old", captured.Authorization);
        Assert.Equal("idem-001", captured.IdempotencyKey);
        using var body = JsonDocument.Parse(captured.Body!);
        Assert.Equal("患者胸痛", body.RootElement.GetProperty("input").GetProperty("text").GetString());
        Assert.Equal("corti_like_fast", body.RootElement.GetProperty("runtime_mode").GetString());
    }

    [Fact]
    public async Task AgentRunAcceptsEmptyBillingWhenDevelopmentBillingIsDisabled()
    {
        using var client = CreateClient(_ => Task.FromResult(Json(HttpStatusCode.OK, """
            {"agent_id":"note-completeness-agent","run_id":"run-2","trace_id":"trace-2",
             "summary":"ok","result":{},"cost":{},"billing":{},"evidence":[],"warnings":[],
             "trace_events":[],"manual_review_required":false,"error":false}
            """)));

        var response = await client.AgentRuns.RunTextAsync(
            "note-completeness-agent",
            "synthetic de-identified note",
            purposeOfUse: "treatment");

        Assert.NotNull(response.Billing);
        Assert.Equal("", response.Billing!.Status);
        Assert.False(response.Billing.Simulation);
        Assert.Equal(0m, response.Billing.SettledAmount);
    }

    [Fact]
    public async Task BillingUsesBalanceAndIdempotentRunSettlementContracts()
    {
        var calls = new List<CapturedRequest>();
        using var client = CreateClient(async request =>
        {
            calls.Add(await CapturedRequest.FromAsync(request));
            return calls.Count switch
            {
                1 => Json(HttpStatusCode.OK, """
                    {"balance":10.0,"reserved":0.05,"available":9.95,"currency":"CNY",
                     "simulation":true,"ledger_authoritative":false,
                     "quota":{"kind":"credits","limit":null,"remaining":9.95,"enforced":true},
                     "alerts":{"low_balance":false,"threshold":5.0}}
                    """),
                2 => Json(HttpStatusCode.OK, """
                    {"items":[{"run_id":"run/id","status":"SETTLEMENT_FAILED",
                     "reserved_amount":0.05,"settled_amount":2.0,"currency":"CNY",
                     "error_code":"INSUFFICIENT_CREDITS_AT_SETTLEMENT"}],
                     "total":1,"simulation":true}
                    """),
                3 => Json(HttpStatusCode.OK, """
                    {"simulation":true,"status":"SETTLED","reserved_amount":0.05,
                     "settled_amount":2.0,"balance_after":8.0,"currency":"CNY",
                     "error_code":null}
                    """),
                _ => Json(HttpStatusCode.OK, """
                    {"simulation":true,"released":1,"marked_retryable":1,
                     "skipped_active":1,"inspected":3,"older_than_seconds":3600}
                    """),
            };
        });

        var balance = await client.Billing.GetBalanceAsync();
        var settlements = await client.Billing.ListRunSettlementsAsync(10);
        var retried = await client.Billing.RetryRunSettlementAsync("run/id");
        var reconciled = await client.Billing.ReconcileStaleRunSettlementsAsync();

        Assert.Equal(9.95m, balance.Available);
        Assert.False(balance.LedgerAuthoritative);
        Assert.Single(settlements.Items);
        Assert.Equal("SETTLEMENT_FAILED", settlements.Items[0].Status);
        Assert.Equal("SETTLED", retried.Status);
        Assert.Equal(1, reconciled.Released);
        Assert.Equal("/api/billing/balance", calls[0].PathAndQuery);
        Assert.Equal("/api/billing/run-settlements?limit=10", calls[1].PathAndQuery);
        Assert.Equal("/api/billing/run-settlements/run%2Fid/retry", calls[2].PathAndQuery);
        Assert.Equal("POST", calls[2].Method);
        Assert.Equal(
            "/api/billing/run-settlements/reconcile-stale?older_than_seconds=3600",
            calls[3].PathAndQuery);
        Assert.Equal("POST", calls[3].Method);
    }

    [Fact]
    public async Task AgentRunLifecycleUsesStatusCancelAndSignedSseContracts()
    {
        var calls = new List<CapturedRequest>();
        using var client = CreateClient(async request =>
        {
            calls.Add(await CapturedRequest.FromAsync(request));
            var path = request.RequestUri!.AbsolutePath;
            if (path.EndsWith("/events", StringComparison.Ordinal))
            {
                return new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent(
                        "id: event-2\n" +
                        "event: run.provider\n" +
                        "data: {\"name\":\"run.provider\"}\n\n" +
                        ": keepalive\n\n" +
                        "id: event-3\n" +
                        "event: run.completion\n" +
                        "data: {\"name\":\"run.completion\"}\n\n" +
                        "event: stream.completed\n" +
                        "data: {\"name\":\"stream.completed\"}\n\n",
                        Encoding.UTF8,
                        "text/event-stream"),
                };
            }
            if (path.EndsWith("/cancel", StringComparison.Ordinal))
            {
                return Json(HttpStatusCode.Accepted, """
                    {"run_id":"run/id","outcome":"RECORDED_ONLY","status":"RUNNING",
                     "message":"request recorded"}
                    """);
            }
            return Json(HttpStatusCode.OK, """
                {"run_id":"run/id","status":"RUNNING","terminal":false,
                 "agent_id":"note-completeness-agent","trace_id":"trace-1",
                 "runtime_mode":"default","latency_ms":12,"cost_amount":0.01,
                 "cost_currency":"CNY","error":false}
                """);
        });

        var status = await client.AgentRuns.GetAsync("run/id");
        var cancellation = await client.AgentRuns.CancelAsync(
            "run/id", "operator request");
        var events = new List<RunStreamEvent>();
        await foreach (var item in client.AgentRuns.StreamEventsAsync(
                           "run/id", "signed token+value", "event-1"))
        {
            events.Add(item);
        }

        Assert.False(status.Terminal);
        Assert.Equal("RECORDED_ONLY", cancellation.Outcome);
        Assert.Equal(3, calls.Count);
        Assert.Equal("GET", calls[0].Method);
        Assert.Equal("/api/v1/runs/run%2Fid", calls[0].PathAndQuery);
        Assert.Equal("POST", calls[1].Method);
        Assert.Equal("/api/v1/runs/run%2Fid/cancel", calls[1].PathAndQuery);
        using var cancelBody = JsonDocument.Parse(calls[1].Body!);
        Assert.Equal("operator request", cancelBody.RootElement.GetProperty("reason").GetString());
        Assert.Equal(
            "/api/v1/runs/run%2Fid/events?token=signed%20token%2Bvalue",
            calls[2].PathAndQuery);
        Assert.Equal("event-1", calls[2].LastEventId);
        Assert.Equal(new[] { "run.provider", "run.completion", "stream.completed" },
            events.Select(item => JsonDocument.Parse(item.Data).RootElement
                .GetProperty("name").GetString()));
        Assert.Equal(new string?[] { "event-2", "event-3", null },
            events.Select(item => item.Id));
    }

    [Fact]
    public async Task AgentRunResilientStreamResumesFromLastAcknowledgedId()
    {
        var calls = new List<CapturedRequest>();
        using var client = CreateClient(async request =>
        {
            calls.Add(await CapturedRequest.FromAsync(request));
            var content = calls.Count == 1
                ? "id: event-1\nevent: run.ingest\ndata: {\"name\":\"run.ingest\"}\n\n"
                : "id: event-2\nevent: run.completion\ndata: {\"name\":\"run.completion\"}\n\n" +
                  "event: stream.completed\ndata: {\"name\":\"stream.completed\"}\n\n";
            return new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(content, Encoding.UTF8, "text/event-stream"),
            };
        });

        var events = new List<RunStreamEvent>();
        await foreach (var item in client.AgentRuns.StreamEventsResilientAsync(
            "run-1",
            "trace-token",
            new RunStreamRetryOptions
            {
                MaxAttempts = 3,
                InitialDelay = TimeSpan.Zero,
                MaxDelay = TimeSpan.Zero,
                JitterRatio = 0,
            }))
        {
            events.Add(item);
        }

        Assert.Equal(2, calls.Count);
        Assert.Null(calls[0].LastEventId);
        Assert.Equal("event-1", calls[1].LastEventId);
        Assert.Equal(new[] { "run.ingest", "run.completion", "stream.completed" },
            events.Select(item => item.Event));
    }

    [Fact]
    public async Task AgentRunResilientStreamRenewsSignedTokenOnlyOn401()
    {
        var calls = new List<CapturedRequest>();
        using var client = CreateClient(async request =>
        {
            calls.Add(await CapturedRequest.FromAsync(request));
            var path = request.RequestUri!.AbsolutePath;
            if (path.EndsWith("/trace-token", StringComparison.Ordinal))
            {
                return Json(HttpStatusCode.OK, """
                    {"run_id":"run-1","trace_token":"renewed-token","expires_at":9999999999,
                     "events_url":"/api/v1/runs/run-1/events",
                     "trace_url":"/api/v1/runs/run-1/trace"}
                    """);
            }
            if (request.RequestUri.Query.Contains("expired-token", StringComparison.Ordinal))
            {
                return Json(HttpStatusCode.Unauthorized, "{\"detail\":\"expired\"}");
            }
            return new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(
                    "event: stream.completed\ndata: {\"name\":\"stream.completed\"}\n\n",
                    Encoding.UTF8,
                    "text/event-stream"),
            };
        });

        var events = new List<RunStreamEvent>();
        await foreach (var item in client.AgentRuns.StreamEventsResilientAsync(
            "run-1",
            "expired-token",
            new RunStreamRetryOptions
            {
                MaxAttempts = 2,
                InitialDelay = TimeSpan.Zero,
                MaxDelay = TimeSpan.Zero,
                JitterRatio = 0,
            }))
        {
            events.Add(item);
        }

        Assert.Equal(3, calls.Count);
        Assert.Contains("token=expired-token", calls[0].PathAndQuery);
        Assert.Equal("POST", calls[1].Method);
        Assert.Equal("/api/v1/runs/run-1/trace-token", calls[1].PathAndQuery);
        Assert.Equal("Bearer token-old", calls[1].Authorization);
        Assert.Contains("token=renewed-token", calls[2].PathAndQuery);
        Assert.Equal("stream.completed", events[^1].Event);
    }

    [Fact]
    public async Task AgentRunResilientStreamDoesNotRetryCursorErrors()
    {
        var calls = 0;
        using var client = CreateClient(_ =>
        {
            calls++;
            return Task.FromResult(Json(HttpStatusCode.Conflict, "{\"detail\":\"cursor\"}"));
        });

        var error = await Assert.ThrowsAsync<ICoDerApiException>(async () =>
        {
            await foreach (var _ in client.AgentRuns.StreamEventsResilientAsync(
                "run-1",
                "trace-token",
                new RunStreamRetryOptions
                {
                    MaxAttempts = 4,
                    InitialDelay = TimeSpan.Zero,
                    MaxDelay = TimeSpan.Zero,
                }))
            {
            }
        });

        Assert.Equal(HttpStatusCode.Conflict, error.StatusCodeValue);
        Assert.Equal(1, calls);
    }

    [Fact]
    public async Task AgentRunRetentionExpiryIsTypedSanitizedAndNotRetried()
    {
        var calls = 0;
        using var client = CreateClient(_ =>
        {
            calls++;
            return Task.FromResult(Json(
                HttpStatusCode.Gone,
                "{\"detail\":{\"code\":\"SSE_CURSOR_EXPIRED\"," +
                "\"retention_days\":90,\"raw_clinical_text\":\"must not escape\"}}"));
        });

        var error = await Assert.ThrowsAsync<RunEventRetentionException>(async () =>
        {
            await foreach (var _ in client.AgentRuns.StreamEventsResilientAsync(
                "run-1",
                "trace-token",
                new RunStreamRetryOptions
                {
                    MaxAttempts = 4,
                    InitialDelay = TimeSpan.Zero,
                    MaxDelay = TimeSpan.Zero,
                }))
            {
            }
        });

        Assert.Equal(HttpStatusCode.Gone, error.StatusCodeValue);
        Assert.Equal("SSE_CURSOR_EXPIRED", error.ErrorCode);
        Assert.Equal(90, error.RetentionDays);
        Assert.DoesNotContain("raw_clinical_text", error.Message);
        Assert.Equal(1, calls);
    }

    [Fact]
    public async Task AgentHubDeserializesStrictTypedOutputContract()
    {
        using var client = CreateClient(_ => Task.FromResult(Json(
            HttpStatusCode.OK,
            "{\"agents\":[{\"agent_id\":\"claim-check\"," +
            "\"agent_ref\":\"icoder/claim-check@1.0.0\",\"name\":\"Claim Check\"," +
            "\"human_review\":\"required\",\"execution_path\":\"provider_registry\"," +
            "\"execution_target\":\"icoder.pure-llm.v1\",\"runtime_readiness\":{" +
            "\"structural_status\":\"ready\",\"configuration_status\":\"configured_not_live_verified\"," +
            "\"run_action_enabled\":true,\"reason\":\"external_provider_configuration_present\"," +
            "\"runtime_dependencies\":[\"external_llm_gateway\"],\"external_llm_required\":true," +
            "\"live_health_verified\":false,\"semantic_validation_status\":\"not_verified\"," +
            "\"production_approval_status\":\"not_approved\"},\"output_contract\":{" +
            "\"schema_ref\":\"icoder/ClaimCheckOutput/v1\"," +
            "\"required_fields\":[\"summary\"],\"optional_fields\":[\"details\"]," +
            "\"field_types\":{\"summary\":\"string\",\"details\":\"array\"}," +
            "\"field_schemas\":{\"summary\":{\"type\":\"string\",\"maxLength\":32768}," +
            "\"details\":{\"type\":\"array\",\"maxItems\":100,\"uniqueItems\":true," +
            "\"items\":{\"type\":\"string\",\"enum\":[\"a\",\"b\"]}}}," +
            "\"field_relations\":[{\"id\":\"details_require_summary\",\"for_each\":\"candidates\"," +
              "\"when\":[{\"path\":\"details\",\"operator\":\"non_empty\"}]," +
              "\"must\":[{\"path\":\"confidence\",\"operator\":\"gte\",\"value\":0.7}]}]," +
              "\"evidence_bindings\":[{\"id\":\"candidate_evidence_matches_input\"," +
              "\"for_each\":\"candidates\",\"text_path\":\"evidence_text\",\"span_path\":\"char_span\"}]," +
              "\"cross_agent_relations\":[{\"id\":\"candidate_matches_upstream\"," +
              "\"local_path\":\"summary\",\"upstream_agent_id\":\"upstream-agent\"," +
              "\"upstream_path\":\"items\",\"upstream_item_path\":\"code\"," +
              "\"operator\":\"scalar_in_upstream_items\",\"normalization\":\"medical_code\"," +
              "\"required\":false}]}}]," +
            "\"total\":1,\"source\":\"packs\",\"schema_version\":\"1.3\"}")));

        var response = await client.AgentHub.ListAsync();
        var card = Assert.Single(response.Agents);

        Assert.Equal("required", card.HumanReview);
        Assert.Equal("icoder/ClaimCheckOutput/v1", card.OutputContract.SchemaRef);
        Assert.Equal(new[] { "summary" }, card.OutputContract.RequiredFields);
        Assert.Equal(new[] { "details" }, card.OutputContract.OptionalFields);
        Assert.Equal("array", card.OutputContract.FieldTypes["details"]);
        Assert.Equal("string", card.OutputContract.FieldSchemas["details"].Items?.Type);
        Assert.Equal(32768, card.OutputContract.FieldSchemas["summary"].MaxLength);
        Assert.Equal(100, card.OutputContract.FieldSchemas["details"].MaxItems);
        Assert.True(card.OutputContract.FieldSchemas["details"].UniqueItems);
        Assert.Equal(2, card.OutputContract.FieldSchemas["details"].Items?.Enum?.Count);
          var relation = Assert.Single(card.OutputContract.FieldRelations);
          Assert.Equal("details_require_summary", relation.Id);
          Assert.Equal("candidates", relation.ForEach);
          Assert.Equal("gte", Assert.Single(relation.Must).Operator);
          Assert.Equal("char_span", Assert.Single(card.OutputContract.EvidenceBindings).SpanPath);
          Assert.Equal(
              "medical_code",
              Assert.Single(card.OutputContract.CrossAgentRelations).Normalization
          );
          Assert.Equal("configured_not_live_verified", card.RuntimeReadiness?.ConfigurationStatus);
          Assert.False(card.RuntimeReadiness!.LiveHealthVerified);
    }

    [Fact]
    public async Task AgentHubRejectsUnavailableAgentWithEnabledRunAction()
    {
        using var client = CreateClient(_ => Task.FromResult(Json(
            HttpStatusCode.OK,
            "{\"agents\":[{\"agent_id\":\"claim-check\"," +
            "\"agent_ref\":\"icoder/claim-check@1.0.0\",\"name\":\"Claim Check\"," +
            "\"runtime_readiness\":{\"structural_status\":\"ready\"," +
            "\"configuration_status\":\"unavailable\",\"run_action_enabled\":true," +
            "\"reason\":\"mock_provider\",\"runtime_dependencies\":[\"external_llm_gateway\"]," +
            "\"external_llm_required\":true,\"live_health_verified\":false," +
            "\"semantic_validation_status\":\"not_verified\"," +
            "\"production_approval_status\":\"not_approved\"}," +
            "\"output_contract\":{}}],\"total\":1,\"source\":\"packs\"," +
            "\"schema_version\":\"1.3\"}")));

        var error = await Assert.ThrowsAsync<InvalidDataException>(
            () => client.AgentHub.ListAsync());

        Assert.Contains("enables an unavailable Agent", error.Message);
    }

    [Fact]
    public async Task AgentHubDeserializesTenantBoundConnectivityReadiness()
    {
        var calls = new List<CapturedRequest>();
        using var client = CreateClient(async request =>
        {
            calls.Add(await CapturedRequest.FromAsync(request));
            return Json(HttpStatusCode.OK,
                "{\"agents\":[{\"agent_id\":\"claim-check\"," +
                "\"execution_target\":\"icoder.pure-llm.v1\"," +
                "\"runtime_readiness\":{\"structural_status\":\"ready\"," +
                "\"configuration_status\":\"configured\",\"run_action_enabled\":true," +
                "\"reason\":\"tenant_model_configuration_present\"," +
                "\"runtime_dependencies\":[\"external_llm_gateway\"]," +
                "\"llm_required\":true,\"live_health_verified\":true," +
                "\"connectivity_status\":\"verified\"," +
                "\"semantic_validation_status\":\"not_verified\"," +
                "\"production_approval_status\":\"not_approved\"}," +
                "\"evidence\":{\"scope\":\"tenant_configuration_and_connectivity\"," +
                "\"selection_mode\":\"pinned\",\"selection_version\":2," +
                "\"deployment_id\":\"deepseek\",\"provider_id\":\"deepseek\"," +
                "\"configuration_probe_status\":\"not_run\"," +
                "\"canary_checked_at\":\"2026-08-23T00:00:00Z\"," +
                "\"canary_expires_at\":\"2026-08-23T00:15:00Z\"}}]," +
                "\"total\":1,\"generated_at\":\"2026-08-23T00:00:01Z\"," +
                "\"schema_version\":\"1.0\"}");
        });

        var response = await client.AgentHub.GetReadinessAsync();
        var item = Assert.Single(response.Agents);

        Assert.Equal("/api/icoder/agents/hub/readiness", calls[0].PathAndQuery);
        Assert.Equal("configured", item.RuntimeReadiness.ConfigurationStatus);
        Assert.Equal("verified", item.RuntimeReadiness.ConnectivityStatus);
        Assert.True(item.RuntimeReadiness.LiveHealthVerified);
        Assert.Equal("deepseek", item.Evidence.DeploymentId);
    }

    [Fact]
    public async Task AgentHubRejectsUnverifiedTenantLiveHealthClaim()
    {
        using var client = CreateClient(_ => Task.FromResult(Json(
            HttpStatusCode.OK,
            "{\"agents\":[{\"agent_id\":\"claim-check\"," +
            "\"execution_target\":\"icoder.pure-llm.v1\"," +
            "\"runtime_readiness\":{\"structural_status\":\"ready\"," +
            "\"configuration_status\":\"configured\",\"run_action_enabled\":true," +
            "\"reason\":\"configured\",\"runtime_dependencies\":[]," +
            "\"llm_required\":true,\"live_health_verified\":true," +
            "\"connectivity_status\":\"not_run\"," +
            "\"semantic_validation_status\":\"not_verified\"," +
            "\"production_approval_status\":\"not_approved\"}," +
            "\"evidence\":{\"scope\":\"tenant_configuration_and_connectivity\"," +
            "\"selection_mode\":\"pinned\",\"selection_version\":1," +
            "\"deployment_id\":\"deepseek\",\"provider_id\":\"deepseek\"," +
            "\"configuration_probe_status\":\"not_run\"," +
            "\"canary_checked_at\":null,\"canary_expires_at\":null}}]," +
            "\"total\":1,\"generated_at\":\"2026-08-23T00:00:00Z\"," +
            "\"schema_version\":\"1.0\"}")));

        var error = await Assert.ThrowsAsync<InvalidDataException>(
            () => client.AgentHub.GetReadinessAsync());

        Assert.Contains("claims live health without verified connectivity", error.Message);
    }

    [Fact]
    public async Task AgentHubGetCardDeserializesLegacyA2ADiscoveryCard()
    {
        using var client = CreateClient(_ => Task.FromResult(Json(
            HttpStatusCode.OK,
            "{\"name\":\"Claim Check\",\"description\":\"A2A discovery card\"," +
            "\"url\":\"https://api.example.cn/api/icoder/agents/claim-check/v1/message:send\"," +
            "\"version\":\"1.0.0\",\"provider\":\"iCoDer\",\"capabilities\":{" +
            "\"streaming\":true,\"pushNotifications\":false," +
            "\"stateTransitionHistory\":true},\"skills\":[{" +
            "\"id\":\"claim-check\",\"name\":\"Claim Check\"," +
            "\"description\":\"Validate claims\",\"inputSchema\":{\"type\":\"object\"}," +
            "\"outputSchema\":{\"type\":\"object\"}}]," +
            "\"defaultInputModes\":[\"text\"]," +
            "\"defaultOutputModes\":[\"application/json\"],\"securitySchemes\":{}}")));

        var card = await client.AgentHub.GetCardAsync("claim-check");

        Assert.True(card.Capabilities.Streaming);
        Assert.Equal("object", Assert.Single(card.Skills).OutputSchema["type"].GetString());
    }

    [Fact]
    public async Task AgentHubCloneUsesProjectRuntimeIdentityAndEncodedSourceId()
    {
        CapturedRequest? captured = null;
        using var client = CreateClient(async request =>
        {
            captured = await CapturedRequest.FromAsync(request);
            return Json(HttpStatusCode.Created,
                "{\"project_agent_id\":\"project-agent-1\"," +
                "\"runtime_agent_id\":\"project-agent-1\"," +
                "\"source_runtime_agent_id\":\"claim-check\"," +
                "\"source_agent_ref\":\"icoder/claim-check@1.0.0\"," +
                "\"chat_url\":\"/ai-studio/agents/project-agent-1/chat\"," +
                "\"customize_url\":\"/ai-studio/agents/project-agent-1\"," +
                "\"run_url\":\"/api/icoder/agents/project-agent-1/v1/message:send\"," +
                "\"cloned\":true}");
        });

        var clone = await client.AgentHub.CloneAsync(
            "claim/check",
            new AgentCloneRequest
            {
                Name = "Project Claim Check",
                ProjectId = "project-cn-1",
            });

        Assert.NotNull(captured);
        Assert.Equal("POST", captured.Method);
        Assert.Equal("/api/icoder/agents/claim%2Fcheck/clone", captured.PathAndQuery);
        Assert.Contains("\"project_id\":\"project-cn-1\"", captured.Body);
        Assert.Equal(clone.ProjectAgentId, clone.RuntimeAgentId);
        Assert.Equal("claim-check", clone.SourceRuntimeAgentId);
    }

    [Fact]
    public async Task AgentHubCloneRejectsSourceIdentityAsPublicRuntimeIdentity()
    {
        using var client = CreateClient(_ => Task.FromResult(Json(
            HttpStatusCode.OK,
            "{\"project_agent_id\":\"project-agent-1\"," +
            "\"runtime_agent_id\":\"claim-check\"," +
            "\"source_runtime_agent_id\":\"claim-check\"," +
            "\"source_agent_ref\":\"icoder/claim-check@1.0.0\"," +
            "\"chat_url\":\"/chat\",\"customize_url\":\"/customize\"," +
            "\"run_url\":\"/api/icoder/agents/claim-check/v1/message:send\"," +
            "\"cloned\":false}")));

        var error = await Assert.ThrowsAsync<InvalidDataException>(
            () => client.AgentHub.CloneAsync("claim-check"));

        Assert.Contains("bypass the project runtime identity", error.Message);
    }

    [Fact]
    public async Task UnauthorizedRefreshesOnceAndRetriesWithNewToken()
    {
        var calls = new List<CapturedRequest>();
        using var client = CreateClient(async request =>
        {
            calls.Add(await CapturedRequest.FromAsync(request));
            return calls.Count switch
            {
                1 => Json(HttpStatusCode.Unauthorized, "{\"detail\":\"expired\"}"),
                2 => Json(HttpStatusCode.OK, "{\"access_token\":\"token-new\",\"refresh_token\":\"refresh-new\",\"token_type\":\"bearer\"}"),
                _ => Json(HttpStatusCode.OK, "{\"agents\":[],\"total\":0,\"source\":\"test\",\"schema_version\":\"1.3\"}"),
            };
        }, refreshToken: "refresh-old");

        var response = await client.AgentHub.ListAsync();

        Assert.Equal(0, response.Total);
        Assert.Equal(3, calls.Count);
        Assert.Equal("/api/auth/refresh", calls[1].PathAndQuery);
        Assert.Null(calls[1].Authorization);
        Assert.Equal("Bearer token-new", calls[2].Authorization);
        Assert.Equal("refresh-new", client.Options.RefreshToken);
    }

    [Fact]
    public async Task SttUploadAndAsyncCreateMatchV2Contract()
    {
        var calls = new List<CapturedRequest>();
        using var client = CreateClient(async request =>
        {
            calls.Add(await CapturedRequest.FromAsync(request));
            if (calls.Count == 1)
            {
                return Json(HttpStatusCode.OK, "{\"recordingId\":\"rec-1\"}");
            }
            var response = Json(HttpStatusCode.Accepted, "{\"id\":\"tr-1\",\"recordingId\":\"rec-1\",\"status\":\"processing\"}");
            response.Headers.Location = new Uri("/api/v2/tools/interactions/i-1/transcripts/tr-1/status", UriKind.Relative);
            return response;
        });

        var recording = await client.SpeechToText.UploadRecordingAsync(
            "i-1", new byte[] { 1, 2, 3 }, "audio/flac");
        var transcript = await client.SpeechToText.CreateTranscriptAsync(
            "i-1",
            new TranscriptCreateRequest
            {
                RecordingId = recording.RecordingId,
                Async = true,
                IsDictation = true,
                SpokenPunctuation = true,
                AutomaticPunctuation = false,
                IsMultichannel = true,
                Participants =
                [
                    new TranscriptParticipant { Channel = 0, Role = "doctor" },
                    new TranscriptParticipant { Channel = 1, Role = "patient" },
                ],
                Keyterms = new TranscriptKeyterms
                {
                    Terms =
                    [
                        new TranscriptKeyterm { Term = "房颤" },
                        new TranscriptKeyterm { Term = "Corti Health" },
                    ],
                },
            });

        Assert.Equal("rec-1", recording.RecordingId);
        Assert.Equal(HttpStatusCode.Accepted, transcript.StatusCode);
        Assert.Equal("processing", transcript.Value.Status);
        Assert.Equal("audio/flac", calls[0].ContentType);
        Assert.Equal(new byte[] { 1, 2, 3 }, calls[0].Bytes);
        using var body = JsonDocument.Parse(calls[1].Body!);
        Assert.True(body.RootElement.GetProperty("async").GetBoolean());
        Assert.True(body.RootElement.GetProperty("isDictation").GetBoolean());
        Assert.True(body.RootElement.GetProperty("spokenPunctuation").GetBoolean());
        Assert.False(body.RootElement.GetProperty("automaticPunctuation").GetBoolean());
        Assert.True(body.RootElement.GetProperty("isMultichannel").GetBoolean());
        var participants = body.RootElement.GetProperty("participants");
        Assert.Equal(0, participants[0].GetProperty("channel").GetInt32());
        Assert.Equal("doctor", participants[0].GetProperty("role").GetString());
        Assert.Equal(1, participants[1].GetProperty("channel").GetInt32());
        Assert.Equal("patient", participants[1].GetProperty("role").GetString());
        var keyterms = body.RootElement.GetProperty("keyterms").GetProperty("terms");
        Assert.Equal("房颤", keyterms[0].GetProperty("term").GetString());
        Assert.Equal("Corti Health", keyterms[1].GetProperty("term").GetString());
        Assert.Equal("zh-CN", body.RootElement.GetProperty("primaryLanguage").GetString());
    }

    [Fact]
    public async Task SttClientRejectsUnsupportedMediaAndCapabilitiesBeforeTransport()
    {
        var calls = 0;
        using var client = CreateClient(_ =>
        {
            calls++;
            return Task.FromResult(Json(HttpStatusCode.OK, "{}"));
        });

        await Assert.ThrowsAsync<ArgumentException>(() =>
            client.SpeechToText.UploadRecordingAsync(
                "i-1", new byte[] { 1 }, "application/json"));
        await Assert.ThrowsAsync<ArgumentException>(() =>
            client.SpeechToText.CreateTranscriptAsync(
                "i-1",
                new TranscriptCreateRequest
                {
                    RecordingId = "rec-1",
                    PrimaryLanguage = "en-US",
                }));
        await Assert.ThrowsAsync<ArgumentException>(() =>
            client.SpeechToText.CreateTranscriptAsync(
                "i-1",
                new TranscriptCreateRequest
                {
                    RecordingId = "rec-1",
                    Diarize = true,
                }));
        await Assert.ThrowsAsync<ArgumentException>(() =>
            client.SpeechToText.CreateTranscriptAsync(
                "i-1",
                new TranscriptCreateRequest
                {
                    RecordingId = "rec-1",
                    IsMultichannel = true,
                    Participants =
                    [
                        new TranscriptParticipant { Channel = 0, Role = "doctor" },
                    ],
                }));
        await Assert.ThrowsAsync<ArgumentException>(() =>
            client.SpeechToText.CreateTranscriptAsync(
                "i-1",
                new TranscriptCreateRequest
                {
                    RecordingId = "rec-1",
                    Keyterms = new TranscriptKeyterms
                    {
                        Terms = [new TranscriptKeyterm { Term = new string('术', 51) }],
                    },
                }));
        await Assert.ThrowsAsync<ArgumentException>(() =>
            client.SpeechToText.CreateTranscriptAsync(
                "i-1",
                new TranscriptCreateRequest
                {
                    RecordingId = "rec-1",
                    Keyterms = new TranscriptKeyterms
                    {
                        Terms = Enumerable.Range(0, 1001)
                            .Select(index => new TranscriptKeyterm { Term = $"term-{index}" })
                            .ToArray(),
                    },
                }));

        Assert.Equal(0, calls);
    }

    [Fact]
    public async Task RealtimeSttConnectsWithTenantTokenAndSendsTypedProtocolFrames()
    {
        var socket = new FakeWebSocket { AutoResumeReady = true };
        Uri? connectedUri = null;
        using var client = new ICoDerClient(
            new ICoDerClientOptions
            {
                BaseUri = new Uri("https://api.cn.icoder.cloud/base"),
                AccessToken = "token/old +",
            },
            new HttpClient(new FakeHandler(_ => Task.FromResult(Json(HttpStatusCode.OK, "{}")))),
            (uri, _) =>
            {
                connectedUri = uri;
                return Task.FromResult<WebSocket>(socket);
            });

        await using var session = await client.SpeechToText.CreateRealtimeSessionAsync(
            new RealtimeSttSessionOptions
            {
                Language = "zh-CN",
                MediaType = "audio/webm;codecs=opus",
            });
        await session.SendAudioAsync(new byte[] { 1, 2, 3 });
        await session.RequestInterimAsync();
        await session.CompleteAsync();

        Assert.NotNull(connectedUri);
        Assert.Equal("wss", connectedUri!.Scheme);
        Assert.Equal("/ws/speech-to-text", connectedUri.AbsolutePath);
        Assert.Equal("?token=token%2Fold%20%2B", connectedUri.Query);
        Assert.Equal(4, socket.Sent.Count);
        using var start = JsonDocument.Parse(socket.Sent[0].Payload);
        Assert.Equal("start", start.RootElement.GetProperty("type").GetString());
        Assert.Equal("icoder.stt-resume.v1", start.RootElement.GetProperty("protocol").GetString());
        Assert.Equal("audio/webm;codecs=opus", start.RootElement.GetProperty("mimeType").GetString());
        Assert.Equal(WebSocketMessageType.Binary, socket.Sent[1].MessageType);
        Assert.Equal(
            new byte[] { 73, 67, 82, 49, 0, 0, 0, 1, 1, 2, 3 },
            socket.Sent[1].Payload);
        using var end = JsonDocument.Parse(socket.Sent[3].Payload);
        Assert.Equal(1, end.RootElement.GetProperty("lastAudioSequence").GetInt32());
        Assert.Equal(3, session.SentAudioBytes);
        Assert.Equal("ready", session.Ready!.Type);
        Assert.Equal(RealtimeSttSession.MaximumSessionBytes, session.Ready.MaxSessionBytes);
    }

    [Fact]
    public async Task RealtimeSttReplaysAudioAndEndAfterDisconnect()
    {
        var first = new FakeWebSocket { AutoResumeReady = true };
        var second = new FakeWebSocket
        {
            AutoResumeReady = true,
            AutoReadyFollowUp = "{\"type\":\"final\",\"text\":\"恢复完成\",\"diarization\":[]}",
        };
        var sockets = new Queue<WebSocket>([first, second]);
        var connections = 0;
        using var client = new ICoDerClient(
            new ICoDerClientOptions
            {
                BaseUri = new Uri("https://api.cn.icoder.cloud"),
                AccessToken = "token",
            },
            new HttpClient(new FakeHandler(_ => Task.FromResult(Json(HttpStatusCode.OK, "{}")))),
            (_, _) =>
            {
                connections++;
                return Task.FromResult(sockets.Dequeue());
            });

        await using var session = await client.SpeechToText.CreateRealtimeSessionAsync(
            new RealtimeSttSessionOptions
            {
                ReconnectAttempts = 1,
                ReconnectInitialDelay = TimeSpan.Zero,
                ReconnectMaxDelay = TimeSpan.Zero,
            });
        await session.SendAudioAsync(new byte[] { 7, 8 });
        await session.CompleteAsync();
        first.QueueClose();

        var final = await session.ReceiveAsync();

        Assert.Equal("final", final!.Type);
        Assert.Equal("恢复完成", final.Text);
        Assert.Equal(2, connections);
        Assert.Equal(3, second.Sent.Count);
        Assert.Equal(first.Sent[1].Payload, second.Sent[1].Payload);
        using var replayedEnd = JsonDocument.Parse(second.Sent[2].Payload);
        Assert.Equal(1, replayedEnd.RootElement.GetProperty("lastAudioSequence").GetInt32());
    }

    [Fact]
    public async Task RealtimeSttLegacyServerRefusesUnsafePostAudioRecovery()
    {
        var socket = new FakeWebSocket();
        socket.QueueText("{\"type\":\"ready\",\"language\":\"zh-CN\",\"maxSessionBytes\":33554432}");
        using var client = new ICoDerClient(
            new ICoDerClientOptions
            {
                BaseUri = new Uri("https://api.cn.icoder.cloud"),
                AccessToken = "token",
            },
            new HttpClient(new FakeHandler(_ => Task.FromResult(Json(HttpStatusCode.OK, "{}")))),
            (_, _) => Task.FromResult<WebSocket>(socket));

        await using var session = await client.SpeechToText.CreateRealtimeSessionAsync(
            new RealtimeSttSessionOptions
            {
                ReconnectAttempts = 1,
                ReconnectInitialDelay = TimeSpan.Zero,
                ReconnectMaxDelay = TimeSpan.Zero,
            });
        await session.SendAudioAsync(new byte[] { 1 });
        socket.QueueClose();

        var error = await Assert.ThrowsAsync<RealtimeSttSessionException>(
            () => session.ReceiveAsync());
        Assert.Equal("audio_resume_unsupported", error.Code);
    }

    [Fact]
    public async Task RealtimeSttValidatesAckAndAdvertisedMemoryBound()
    {
        var socket = new FakeWebSocket
        {
            AutoResumeReady = true,
            AutoReadyMaxSessionBytes = 2,
        };
        using var client = new ICoDerClient(
            new ICoDerClientOptions
            {
                BaseUri = new Uri("https://api.cn.icoder.cloud"),
                AccessToken = "token",
            },
            new HttpClient(new FakeHandler(_ => Task.FromResult(Json(HttpStatusCode.OK, "{}")))),
            (_, _) => Task.FromResult<WebSocket>(socket));

        await using var session = await client.SpeechToText.CreateRealtimeSessionAsync();
        await session.SendAudioAsync(new byte[] { 1, 2 });
        using var start = JsonDocument.Parse(socket.Sent[0].Payload);
        var sessionId = start.RootElement.GetProperty("sessionId").GetString();
        socket.QueueText(JsonSerializer.Serialize(new
        {
            type = "audio_ack",
            sequence = 1,
            nextAudioSequence = 2,
            totalBytes = 2,
            duplicate = false,
            sessionId,
        }));

        var acknowledgement = await session.ReceiveAsync();

        Assert.Equal("audio_ack", acknowledgement!.Type);
        await Assert.ThrowsAsync<ArgumentOutOfRangeException>(
            () => session.SendAudioAsync(new byte[] { 3 }));
    }

    [Fact]
    public async Task RealtimeSttTerminatesOnInvalidAcknowledgement()
    {
        var socket = new FakeWebSocket { AutoResumeReady = true };
        using var client = new ICoDerClient(
            new ICoDerClientOptions
            {
                BaseUri = new Uri("https://api.cn.icoder.cloud"),
                AccessToken = "token",
            },
            new HttpClient(new FakeHandler(_ => Task.FromResult(Json(HttpStatusCode.OK, "{}")))),
            (_, _) => Task.FromResult<WebSocket>(socket));

        await using var session = await client.SpeechToText.CreateRealtimeSessionAsync();
        await session.SendAudioAsync(new byte[] { 1 });
        socket.QueueText("""
            {"type":"audio_ack","sequence":1,"nextAudioSequence":2,
             "totalBytes":1,"duplicate":false,
             "sessionId":"stt_wrong_session_identifier_0000"}
            """);

        var error = await Assert.ThrowsAsync<RealtimeSttSessionException>(
            () => session.ReceiveAsync());
        Assert.Equal("invalid_audio_ack", error.Code);
        Assert.Equal(WebSocketState.Aborted, session.State);
    }

    [Fact]
    public async Task RealtimeSttRejectsUnsupportedOptionsBeforeConnecting()
    {
        var connections = 0;
        using var client = new ICoDerClient(
            new ICoDerClientOptions
            {
                BaseUri = new Uri("https://api.cn.icoder.cloud"),
                AccessToken = "token-old",
            },
            new HttpClient(new FakeHandler(_ => Task.FromResult(Json(HttpStatusCode.OK, "{}")))),
            (_, _) =>
            {
                connections++;
                return Task.FromResult<WebSocket>(new FakeWebSocket());
            });

        await Assert.ThrowsAsync<ArgumentException>(() =>
            client.SpeechToText.CreateRealtimeSessionAsync(
                new RealtimeSttSessionOptions { Language = "en-US" }));
        await Assert.ThrowsAsync<ArgumentException>(() =>
            client.SpeechToText.CreateRealtimeSessionAsync(
                new RealtimeSttSessionOptions { Punctuation = "spoken" }));
        await Assert.ThrowsAsync<ArgumentException>(() =>
            client.SpeechToText.CreateRealtimeSessionAsync(
                new RealtimeSttSessionOptions { MediaType = "application/json" }));
        await Assert.ThrowsAsync<ArgumentException>(() =>
            client.SpeechToText.CreateRealtimeSessionAsync(
                new RealtimeSttSessionOptions { ReconnectAttempts = 21 }));

        Assert.Equal(0, connections);
    }

    [Fact]
    public async Task RealtimeSttRequiresAccessTokenBeforeConnecting()
    {
        var connections = 0;
        using var client = new ICoDerClient(
            new ICoDerClientOptions { BaseUri = new Uri("https://api.cn.icoder.cloud") },
            new HttpClient(new FakeHandler(_ => Task.FromResult(Json(HttpStatusCode.OK, "{}")))),
            (_, _) =>
            {
                connections++;
                return Task.FromResult<WebSocket>(new FakeWebSocket());
            });

        await Assert.ThrowsAsync<InvalidOperationException>(() =>
            client.SpeechToText.CreateRealtimeSessionAsync());
        Assert.Equal(0, connections);
    }

    [Fact]
    public async Task RealtimeSttConnectionFailureDoesNotRetainToken()
    {
        const string secretToken = "tenant-secret-token-value";
        using var client = new ICoDerClient(
            new ICoDerClientOptions
            {
                BaseUri = new Uri("https://api.cn.icoder.cloud"),
                AccessToken = secretToken,
            },
            new HttpClient(new FakeHandler(_ => Task.FromResult(Json(HttpStatusCode.OK, "{}")))),
            (uri, _) => throw new WebSocketException($"failed to connect {uri}"));

        var error = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            client.SpeechToText.CreateRealtimeSessionAsync());
        Assert.DoesNotContain(secretToken, error.ToString());
        Assert.Null(error.InnerException);
    }

    [Fact]
    public async Task StreamsConnectsWithTenantEnvironmentTokenAndTypedConfiguration()
    {
        var socket = new FakeWebSocket();
        socket.QueueText("""
            {"type":"CONFIG_ACCEPTED","sessionId":"22222222-2222-4222-8222-222222222222",
             "configuration":{"transcription":{"primaryLanguage":"zh-CN"},
             "mode":{"type":"facts","outputLocale":"zh-CN"},"retentionPolicy":"none"}}
            """);
        Uri? connectedUri = null;
        using var client = new ICoDerClient(
            new ICoDerClientOptions
            {
                BaseUri = new Uri("https://api.cn.icoder.cloud/base"),
                AccessToken = "token/old +",
            },
            new HttpClient(new FakeHandler(_ => Task.FromResult(Json(HttpStatusCode.OK, "{}")))),
            (uri, _) =>
            {
                connectedUri = uri;
                return Task.FromResult<WebSocket>(socket);
            });

        await using var session = await client.Streams.CreateSessionAsync(ValidStreamsOptions());

        Assert.NotNull(connectedUri);
        Assert.Equal("wss", connectedUri!.Scheme);
        Assert.Equal(
            "/api/v2/tools/streams/11111111-1111-4111-8111-111111111111",
            connectedUri.AbsolutePath);
        Assert.Contains("environment=cn", connectedUri.Query);
        Assert.Contains("tenant-name=hospital%20cn", connectedUri.Query);
        Assert.Contains("token=token%2Fold%20%2B", connectedUri.Query);
        Assert.Equal("CONFIG_ACCEPTED", session.Ready!.Type);
        using var sent = JsonDocument.Parse(socket.Sent[0].Payload);
        Assert.Equal("config", sent.RootElement.GetProperty("type").GetString());
        Assert.Equal(
            "zh-CN",
            sent.RootElement.GetProperty("configuration")
                .GetProperty("transcription").GetProperty("primaryLanguage").GetString());
    }

    [Fact]
    public async Task StreamsSendsBoundedAudioFlushAndEndAndReadsCurrentOrder()
    {
        var socket = new FakeWebSocket();
        socket.QueueText("""
            {"type":"CONFIG_ACCEPTED","sessionId":"22222222-2222-4222-8222-222222222222",
             "configuration":{"transcription":{"primaryLanguage":"zh-CN"},
             "mode":{"type":"facts","outputLocale":"zh-CN"}}}
            """);
        using var client = new ICoDerClient(
            new ICoDerClientOptions
            {
                BaseUri = new Uri("https://api.cn.icoder.cloud"),
                AccessToken = "token",
            },
            new HttpClient(new FakeHandler(_ => Task.FromResult(Json(HttpStatusCode.OK, "{}")))),
            (_, _) => Task.FromResult<WebSocket>(socket));
        await using var session = await client.Streams.CreateSessionAsync(ValidStreamsOptions());

        await session.SendAudioAsync(new byte[] { 1, 2, 3 });
        await session.FlushAsync();
        await session.CompleteAsync();
        socket.QueueText("{\"type\":\"transcript\",\"data\":[{\"transcript\":\"患者胸痛\"}]}");
        socket.QueueText("{\"type\":\"facts\",\"fact\":[{\"text\":\"胸痛\"}]}");
        socket.QueueText("{\"type\":\"delta_usage\",\"credits\":0}");
        socket.QueueText("{\"type\":\"usage\",\"credits\":0}");
        socket.QueueText("{\"type\":\"ENDED\"}");

        var events = new List<StreamsEvent?>();
        for (var index = 0; index < 5; index++)
        {
            events.Add(await session.ReceiveAsync());
        }
        Assert.Equal(
            ["transcript", "facts", "delta_usage", "usage", "ENDED"],
            events.Select(item => item!.Type));
        Assert.True(session.IsEnded);
        Assert.Equal(3, session.SentAudioBytes);
        Assert.Equal(WebSocketMessageType.Binary, socket.Sent[1].MessageType);
        Assert.Equal(new byte[] { 1, 2, 3 }, socket.Sent[1].Payload);
        using var flush = JsonDocument.Parse(socket.Sent[2].Payload);
        using var end = JsonDocument.Parse(socket.Sent[3].Payload);
        Assert.Equal("flush", flush.RootElement.GetProperty("type").GetString());
        Assert.Equal("end", end.RootElement.GetProperty("type").GetString());
        await Assert.ThrowsAsync<StreamsSessionException>(
            () => session.SendAudioAsync(new byte[] { 4 }));
    }

    [Fact]
    public async Task StreamsRejectsUnsupportedClinicalCapabilitiesBeforeConnecting()
    {
        var connections = 0;
        using var client = new ICoDerClient(
            new ICoDerClientOptions
            {
                BaseUri = new Uri("https://api.cn.icoder.cloud"),
                AccessToken = "token",
            },
            new HttpClient(new FakeHandler(_ => Task.FromResult(Json(HttpStatusCode.OK, "{}")))),
            (_, _) =>
            {
                connections++;
                return Task.FromResult<WebSocket>(new FakeWebSocket());
            });
        var options = ValidStreamsOptions() with
        {
            Configuration = ValidStreamsOptions().Configuration with
            {
                Transcription = ValidStreamsOptions().Configuration.Transcription with
                {
                    Diarize = true,
                },
            },
        };

        var error = await Assert.ThrowsAsync<StreamsSessionException>(
            () => client.Streams.CreateSessionAsync(options));
        Assert.Equal("diarization_not_available", error.Code);
        Assert.Equal(0, connections);
    }

    [Fact]
    public async Task StreamsAcceptsGovernedMultichannelAndFastInit()
    {
        var socket = new FakeWebSocket();
        socket.QueueText("""
            {"type":"CONFIG_ACCEPTED","sessionId":"22222222-2222-4222-8222-222222222222",
             "configuration":{"transcription":{"primaryLanguage":"zh-CN","isMultichannel":true,
             "participants":[{"channel":0,"role":"clinician"},{"channel":1,"role":"patient"}]},
             "mode":{"type":"facts","outputLocale":"zh-CN","factGenerationInterval":"fast_init"},
             "audioFormat":"audio/pcm; rate=16000; channels=2; bits=16"}}
            """);
        using var client = new ICoDerClient(
            new ICoDerClientOptions
            {
                BaseUri = new Uri("https://api.cn.icoder.cloud"),
                AccessToken = "token",
            },
            new HttpClient(new FakeHandler(_ => Task.FromResult(Json(HttpStatusCode.OK, "{}")))),
            (_, _) => Task.FromResult<WebSocket>(socket));
        var baseline = ValidStreamsOptions();
        var options = baseline with
        {
            Configuration = baseline.Configuration with
            {
                Transcription = baseline.Configuration.Transcription with
                {
                    IsMultichannel = true,
                    Participants =
                    [
                        new StreamsParticipant { Channel = 0, Role = "clinician" },
                        new StreamsParticipant { Channel = 1, Role = "patient" },
                    ],
                },
                Mode = baseline.Configuration.Mode with
                {
                    FactGenerationInterval = "fast_init",
                },
                AudioFormat = "audio/pcm; rate=16000; channels=2; bits=16",
            },
        };

        await using var session = await client.Streams.CreateSessionAsync(options);
        Assert.True(session.Ready!.Configuration!.Value
            .GetProperty("transcription").GetProperty("isMultichannel").GetBoolean());
    }

    [Fact]
    public async Task StreamsAcceptsOrderedCaseSensitiveKeytermsAndUsesCurrentDiarizeField()
    {
        var socket = new FakeWebSocket();
        socket.QueueText("""
            {"type":"CONFIG_ACCEPTED","sessionId":"22222222-2222-4222-8222-222222222222",
             "configuration":{"transcription":{"primaryLanguage":"zh-CN","diarize":false},
             "mode":{"type":"transcription"},
             "keyterms":{"terms":[{"term":"房颤"},{"term":"Corti Health"}]}}}
            """);
        using var client = new ICoDerClient(
            new ICoDerClientOptions
            {
                BaseUri = new Uri("https://api.cn.icoder.cloud"),
                AccessToken = "token",
            },
            new HttpClient(new FakeHandler(_ => Task.FromResult(Json(HttpStatusCode.OK, "{}")))),
            (_, _) => Task.FromResult<WebSocket>(socket));
        var baseline = ValidStreamsOptions();
        var options = baseline with
        {
            Configuration = baseline.Configuration with
            {
                Keyterms = new StreamsKeytermsConfiguration
                {
                    Terms =
                    [
                        new StreamsKeyterm { Term = "房颤" },
                        new StreamsKeyterm { Term = "Corti Health" },
                    ],
                },
            },
        };

        await using var session = await client.Streams.CreateSessionAsync(options);
        using var sent = JsonDocument.Parse(socket.Sent[0].Payload);
        var transcription = sent.RootElement.GetProperty("configuration")
            .GetProperty("transcription");
        Assert.True(transcription.TryGetProperty("diarize", out _));
        Assert.False(transcription.TryGetProperty("isDiarization", out _));
        var terms = sent.RootElement.GetProperty("configuration")
            .GetProperty("keyterms").GetProperty("terms");
        Assert.Equal(["房颤", "Corti Health"],
            terms.EnumerateArray().Select(item => item.GetProperty("term").GetString()));
    }

    [Theory]
    [InlineData("", "keyterm_invalid")]
    [InlineData("xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", "keyterm_invalid")]
    public async Task StreamsRejectsInvalidKeytermsBeforeConnecting(
        string term,
        string expectedCode)
    {
        var connections = 0;
        using var client = new ICoDerClient(
            new ICoDerClientOptions
            {
                BaseUri = new Uri("https://api.cn.icoder.cloud"),
                AccessToken = "token",
            },
            new HttpClient(new FakeHandler(_ => Task.FromResult(Json(HttpStatusCode.OK, "{}")))),
            (_, _) =>
            {
                connections++;
                return Task.FromResult<WebSocket>(new FakeWebSocket());
            });
        var baseline = ValidStreamsOptions();
        var options = baseline with
        {
            Configuration = baseline.Configuration with
            {
                Keyterms = new StreamsKeytermsConfiguration
                {
                    Terms = [new StreamsKeyterm { Term = term }],
                },
            },
        };

        var error = await Assert.ThrowsAsync<StreamsSessionException>(
            () => client.Streams.CreateSessionAsync(options));
        Assert.Equal(expectedCode, error.Code);
        Assert.Equal(0, connections);
    }

    [Fact]
    public async Task StreamsRejectsMoreThanOneThousandKeytermsBeforeConnecting()
    {
        var connections = 0;
        using var client = new ICoDerClient(
            new ICoDerClientOptions
            {
                BaseUri = new Uri("https://api.cn.icoder.cloud"),
                AccessToken = "token",
            },
            new HttpClient(new FakeHandler(_ => Task.FromResult(Json(HttpStatusCode.OK, "{}")))),
            (_, _) =>
            {
                connections++;
                return Task.FromResult<WebSocket>(new FakeWebSocket());
            });
        var baseline = ValidStreamsOptions();
        var options = baseline with
        {
            Configuration = baseline.Configuration with
            {
                Keyterms = new StreamsKeytermsConfiguration
                {
                    Terms = Enumerable.Range(0, 1001)
                        .Select(_ => new StreamsKeyterm { Term = "房颤" })
                        .ToArray(),
                },
            },
        };

        var error = await Assert.ThrowsAsync<StreamsSessionException>(
            () => client.Streams.CreateSessionAsync(options));
        Assert.Equal("keyterm_limit_exceeded", error.Code);
        Assert.Equal(0, connections);
    }

    [Fact]
    public async Task StreamsRejectsWavAndUnknownStreamingAudioFormatsBeforeConnecting()
    {
        var connections = 0;
        using var client = new ICoDerClient(
            new ICoDerClientOptions
            {
                BaseUri = new Uri("https://api.cn.icoder.cloud"),
                AccessToken = "token",
            },
            new HttpClient(new FakeHandler(_ => Task.FromResult(Json(HttpStatusCode.OK, "{}")))),
            (_, _) =>
            {
                connections++;
                return Task.FromResult<WebSocket>(new FakeWebSocket());
            });

        foreach (var (audioFormat, expectedCode) in new[]
        {
            ("audio/wav", "audio_format_not_supported"),
            ("audio/pcm", "audio_format_not_supported"),
            ("audio/pcm; rate=48000; channels=1; bits=16", "raw_pcm_profile_not_available"),
            ("audio/mpeg; codecs=mp3", "audio_format_not_supported"),
        })
        {
            var options = ValidStreamsOptions() with
            {
                Configuration = ValidStreamsOptions().Configuration with
                {
                    AudioFormat = audioFormat,
                },
            };
            var error = await Assert.ThrowsAsync<StreamsSessionException>(
                () => client.Streams.CreateSessionAsync(options));
            Assert.Equal(expectedCode, error.Code);
        }
        Assert.Equal(0, connections);
    }

    [Fact]
    public async Task StreamsAcceptsRecommendedPcmAndValidatesTypedAudioEvents()
    {
        var socket = new FakeWebSocket();
        socket.QueueText("""
            {"type":"CONFIG_ACCEPTED","sessionId":"22222222-2222-4222-8222-222222222222",
             "configuration":{"transcription":{"primaryLanguage":"zh-CN"},
             "mode":{"type":"facts","outputLocale":"zh-CN"},
             "audioFormat":"audio/pcm; rate=16000; channels=1; bits=16",
             "audioEvents":{"enabled":true}}}
            """);
        using var client = new ICoDerClient(
            new ICoDerClientOptions
            {
                BaseUri = new Uri("https://api.cn.icoder.cloud"),
                AccessToken = "token",
            },
            new HttpClient(new FakeHandler(_ => Task.FromResult(Json(HttpStatusCode.OK, "{}")))),
            (_, _) => Task.FromResult<WebSocket>(socket));
        var options = ValidStreamsOptions() with
        {
            Configuration = ValidStreamsOptions().Configuration with
            {
                AudioFormat = "audio/pcm; rate=16000; channels=1; bits=16",
                AudioEvents = new StreamsAudioEventsConfiguration { Enabled = true },
            },
        };
        await using var session = await client.Streams.CreateSessionAsync(options);
        socket.QueueText("""
            {"type":"audioEvent","data":{"event":"longSilenceDetected",
             "channel":0,"startTimeMs":0}}
            """);
        socket.QueueText("""
            {"type":"audioEvent","data":{"event":"privateUnexpectedEvent",
             "channel":0,"startTimeMs":0,"text":"patient secret"}}
            """);

        var audioEvent = await session.ReceiveAsync();
        Assert.Equal("audioEvent", audioEvent!.Type);
        Assert.Equal("longSilenceDetected", audioEvent.AudioEvent!.Event);
        Assert.Equal(0, audioEvent.AudioEvent.Channel);
        Assert.Equal(0, audioEvent.AudioEvent.StartTimeMs);
        var invalid = await session.ReceiveAsync();
        Assert.Equal("unknown", invalid!.Type);
        Assert.Null(invalid.AudioEvent);
    }

    [Fact]
    public async Task StreamsAudioEventsRequireGovernedPcmBeforeConnecting()
    {
        var connections = 0;
        using var client = new ICoDerClient(
            new ICoDerClientOptions
            {
                BaseUri = new Uri("https://api.cn.icoder.cloud"),
                AccessToken = "token",
            },
            new HttpClient(new FakeHandler(_ => Task.FromResult(Json(HttpStatusCode.OK, "{}")))),
            (_, _) =>
            {
                connections++;
                return Task.FromResult<WebSocket>(new FakeWebSocket());
            });
        var options = ValidStreamsOptions() with
        {
            Configuration = ValidStreamsOptions().Configuration with
            {
                AudioFormat = "audio/ogg",
                AudioEvents = new StreamsAudioEventsConfiguration { Enabled = true },
            },
        };

        var error = await Assert.ThrowsAsync<StreamsSessionException>(
            () => client.Streams.CreateSessionAsync(options));
        Assert.Equal("audio_events_require_pcm", error.Code);
        Assert.Equal(0, connections);
    }

    [Fact]
    public async Task StreamsConfigurationFailuresAreTypedAndPhiSafe()
    {
        var socket = new FakeWebSocket();
        socket.QueueText("""
            {"type":"CONFIG_DENIED","reason":"patient secret from server",
             "interactionId":"11111111-1111-4111-8111-111111111111"}
            """);
        using var client = new ICoDerClient(
            new ICoDerClientOptions
            {
                BaseUri = new Uri("https://api.cn.icoder.cloud"),
                AccessToken = "token",
            },
            new HttpClient(new FakeHandler(_ => Task.FromResult(Json(HttpStatusCode.OK, "{}")))),
            (_, _) => Task.FromResult<WebSocket>(socket));

        var error = await Assert.ThrowsAsync<StreamsSessionException>(
            () => client.Streams.CreateSessionAsync(ValidStreamsOptions()));
        Assert.Equal("config_denied", error.Code);
        Assert.DoesNotContain("patient secret", error.ToString());
    }

    [Fact]
    public async Task StreamsFailsClosedWhenConnectionDropsAfterAudio()
    {
        var socket = new FakeWebSocket();
        socket.QueueText("""
            {"type":"CONFIG_ACCEPTED","sessionId":"22222222-2222-4222-8222-222222222222",
             "configuration":{"transcription":{"primaryLanguage":"zh-CN"},
             "mode":{"type":"facts","outputLocale":"zh-CN"}}}
            """);
        using var client = new ICoDerClient(
            new ICoDerClientOptions
            {
                BaseUri = new Uri("https://api.cn.icoder.cloud"),
                AccessToken = "token",
            },
            new HttpClient(new FakeHandler(_ => Task.FromResult(Json(HttpStatusCode.OK, "{}")))),
            (_, _) => Task.FromResult<WebSocket>(socket));
        await using var session = await client.Streams.CreateSessionAsync(ValidStreamsOptions());
        await session.SendAudioAsync(new byte[] { 1 });
        socket.QueueClose();

        var error = await Assert.ThrowsAsync<StreamsSessionException>(
            () => session.ReceiveAsync());
        Assert.Equal("audio_resume_unsupported", error.Code);
        Assert.False(error.Retryable);
    }

    [Fact]
    public async Task StreamsRetainedFlushedDropRequiresCheckpointResume()
    {
        var socket = new FakeWebSocket();
        socket.QueueText("""
            {"type":"CONFIG_ACCEPTED","sessionId":"22222222-2222-4222-8222-222222222222",
             "configuration":{"transcription":{"primaryLanguage":"zh-CN"},
             "mode":{"type":"facts","outputLocale":"zh-CN"},"retentionPolicy":"retain"},
             "resumed":false,"restoredAudioBytes":0,
             "restoredTranscriptMessages":0,"restoredFactMessages":0}
            """);
        using var client = new ICoDerClient(
            new ICoDerClientOptions
            {
                BaseUri = new Uri("https://api.cn.icoder.cloud"),
                AccessToken = "token",
            },
            new HttpClient(new FakeHandler(_ => Task.FromResult(Json(HttpStatusCode.OK, "{}")))),
            (_, _) => Task.FromResult<WebSocket>(socket));
        var options = ValidStreamsOptions() with
        {
            Configuration = ValidStreamsOptions().Configuration with
            {
                RetentionPolicy = "retain",
            },
        };
        await using var session = await client.Streams.CreateSessionAsync(options);
        await session.SendAudioAsync(new byte[] { 1, 2, 3 });
        await session.FlushAsync();
        socket.QueueText("{\"type\":\"flushed\"}");
        Assert.Equal("flushed", (await session.ReceiveAsync())!.Type);
        socket.QueueClose();

        var error = await Assert.ThrowsAsync<StreamsSessionException>(
            () => session.ReceiveAsync());
        Assert.Equal("stream_resume_required", error.Code);
        Assert.True(error.Retryable);
    }

    [Fact]
    public async Task StreamsResumeRequiresRetentionBeforeConnecting()
    {
        var connections = 0;
        using var client = new ICoDerClient(
            new ICoDerClientOptions
            {
                BaseUri = new Uri("https://api.cn.icoder.cloud"),
                AccessToken = "token",
            },
            new HttpClient(new FakeHandler(_ => Task.FromResult(Json(HttpStatusCode.OK, "{}")))),
            (_, _) =>
            {
                connections++;
                return Task.FromResult<WebSocket>(new FakeWebSocket());
            });

        var error = await Assert.ThrowsAsync<StreamsSessionException>(
            () => client.Streams.ResumeSessionAsync(ValidStreamsOptions()));
        Assert.Equal("stream_resume_requires_retention", error.Code);
        Assert.Equal(0, connections);
    }

    [Fact]
    public async Task StreamsResumeRequiresServerAckAndExposesRecoveryCounts()
    {
        var accepted = new FakeWebSocket();
        accepted.QueueText("""
            {"type":"CONFIG_ACCEPTED","sessionId":"22222222-2222-4222-8222-222222222222",
             "configuration":{"transcription":{"primaryLanguage":"zh-CN"},
             "mode":{"type":"facts","outputLocale":"zh-CN"},"retentionPolicy":"retain"},
             "resumed":true,"restoredAudioBytes":640,
             "restoredTranscriptMessages":2,"restoredFactMessages":1}
            """);
        using var client = new ICoDerClient(
            new ICoDerClientOptions
            {
                BaseUri = new Uri("https://api.cn.icoder.cloud"),
                AccessToken = "token",
            },
            new HttpClient(new FakeHandler(_ => Task.FromResult(Json(HttpStatusCode.OK, "{}")))),
            (_, _) => Task.FromResult<WebSocket>(accepted));
        var retained = ValidStreamsOptions() with
        {
            Configuration = ValidStreamsOptions().Configuration with
            {
                RetentionPolicy = "retain",
            },
        };

        await using var resumed = await client.Streams.ResumeSessionAsync(retained);
        Assert.True(resumed.Ready!.Resumed);
        Assert.Equal(640, resumed.Ready.RestoredAudioBytes);
        Assert.Equal(2, resumed.Ready.RestoredTranscriptMessages);
        Assert.Equal(1, resumed.Ready.RestoredFactMessages);
        Assert.Equal(640, resumed.SentAudioBytes);

        var missing = new FakeWebSocket();
        missing.QueueText("""
            {"type":"CONFIG_ACCEPTED","sessionId":"33333333-3333-4333-8333-333333333333",
             "configuration":{"transcription":{"primaryLanguage":"zh-CN"},
             "mode":{"type":"facts","outputLocale":"zh-CN"},"retentionPolicy":"retain"},
             "resumed":false,"restoredAudioBytes":0,
             "restoredTranscriptMessages":0,"restoredFactMessages":0}
            """);
        using var missingClient = new ICoDerClient(
            new ICoDerClientOptions
            {
                BaseUri = new Uri("https://api.cn.icoder.cloud"),
                AccessToken = "token",
            },
            new HttpClient(new FakeHandler(_ => Task.FromResult(Json(HttpStatusCode.OK, "{}")))),
            (_, _) => Task.FromResult<WebSocket>(missing));
        var error = await Assert.ThrowsAsync<StreamsSessionException>(
            () => missingClient.Streams.ResumeSessionAsync(retained));
        Assert.Equal("stream_checkpoint_not_found", error.Code);
        Assert.False(error.Retryable);
    }

    [Fact]
    public async Task StreamsRuntimeErrorsExposeOnlyStableCode()
    {
        var socket = new FakeWebSocket();
        socket.QueueText("""
            {"type":"CONFIG_ACCEPTED","sessionId":"22222222-2222-4222-8222-222222222222",
             "configuration":{"transcription":{"primaryLanguage":"zh-CN"},
             "mode":{"type":"facts","outputLocale":"zh-CN"}}}
            """);
        socket.QueueText("""
            {"type":"error","error":{"id":"FACTS_UNAVAILABLE",
             "details":"patient secret from upstream"}}
            """);
        using var client = new ICoDerClient(
            new ICoDerClientOptions
            {
                BaseUri = new Uri("https://api.cn.icoder.cloud"),
                AccessToken = "token",
            },
            new HttpClient(new FakeHandler(_ => Task.FromResult(Json(HttpStatusCode.OK, "{}")))),
            (_, _) => Task.FromResult<WebSocket>(socket));
        await using var session = await client.Streams.CreateSessionAsync(ValidStreamsOptions());

        var runtimeError = await session.ReceiveAsync();
        Assert.Equal("error", runtimeError!.Type);
        Assert.Equal("FACTS_UNAVAILABLE", runtimeError.Code);
        Assert.DoesNotContain("patient secret", runtimeError.ToString());
    }

    [Fact]
    public async Task DocumentPreviewRequiresZeroRetentionAcknowledgement()
    {
        CapturedRequest? captured = null;
        using var client = CreateClient(async request =>
        {
            captured = await CapturedRequest.FromAsync(request);
            var response = Json(HttpStatusCode.OK, """
                {"id":"doc-1","sections":[],"usageInfo":{"creditsConsumed":0.02}}
                """);
            response.Headers.TryAddWithoutValidation(
                "X-Corti-Retention-Policy", "acknowledged");
            return response;
        });

        var document = await client.Documents.PreviewAsync(
            "interaction/1",
            new DocumentCreateRequest
            {
                Context = [DocumentContext.Facts([
                    new DocumentFact { Text = "患者主诉胸痛", Group = "clinical" },
                ])],
                OutputLanguage = "zh-CN",
                DocumentationMode = DocumentationModes.RoutedParallel,
                Template = new DocumentTemplate
                {
                    SectionKeys = ["chief-complaint", "assessment"],
                },
            });

        Assert.Equal("doc-1", document.Id);
        Assert.NotNull(captured);
        Assert.Equal("POST", captured.Method);
        Assert.Equal(
            "/api/v2/tools/interactions/interaction%2F1/documents/",
            captured.PathAndQuery);
        Assert.Equal("none", captured.RetentionPolicy);
        using var body = JsonDocument.Parse(captured.Body!);
        Assert.Equal(
            "facts",
            body.RootElement.GetProperty("context")[0].GetProperty("type").GetString());
        Assert.Equal(
            "routed_parallel",
            body.RootElement.GetProperty("documentationMode").GetString());
        Assert.Equal(
            2,
            body.RootElement.GetProperty("template").GetProperty("sectionKeys").GetArrayLength());
    }

    [Fact]
    public async Task DocumentPreviewFailsClosedWithoutRetentionAcknowledgement()
    {
        using var client = CreateClient(_ => Task.FromResult(Json(
            HttpStatusCode.OK,
            """{"id":"doc-1","sections":[],"usageInfo":{"creditsConsumed":0}}""")));

        await Assert.ThrowsAsync<InvalidOperationException>(() =>
            client.Documents.PreviewAsync(
                "interaction-1",
                new DocumentCreateRequest
                {
                    Context = [DocumentContext.String("去标识文本")],
                    OutputLanguage = "zh-CN",
                    TemplateKey = "template-1",
                }));
    }

    [Fact]
    public async Task DocumentLifecycleUsesEscapedResourcePaths()
    {
        var calls = new List<CapturedRequest>();
        using var client = CreateClient(async request =>
        {
            calls.Add(await CapturedRequest.FromAsync(request));
            return calls.Count switch
            {
                1 => Json(HttpStatusCode.OK, "{\"data\":[]}"),
                2 => Json(HttpStatusCode.OK, "{\"id\":\"doc-1\",\"sections\":[]}"),
                3 => Json(HttpStatusCode.OK, "{\"id\":\"doc-1\",\"name\":\"新名称\",\"sections\":[]}"),
                _ => new HttpResponseMessage(HttpStatusCode.NoContent),
            };
        });

        Assert.Empty(await client.Documents.ListAsync("interaction/1"));
        await client.Documents.GetAsync("interaction/1", "document/1");
        var updated = await client.Documents.UpdateAsync(
            "interaction/1",
            "document/1",
            new DocumentUpdateRequest { Name = "新名称" });
        await client.Documents.DeleteAsync("interaction/1", "document/1");

        Assert.Equal("新名称", updated.Name);
        Assert.Equal("GET", calls[0].Method);
        Assert.Equal("PATCH", calls[2].Method);
        Assert.Equal("DELETE", calls[3].Method);
        Assert.All(
            calls.Skip(1),
            call => Assert.Contains("/documents/document%2F1", call.PathAndQuery));
    }

    [Fact]
    public async Task TemplateDiscoveryPreservesRepeatedFiltersAndSectionLifecycle()
    {
        var calls = new List<CapturedRequest>();
        using var client = CreateClient(async request =>
        {
            calls.Add(await CapturedRequest.FromAsync(request));
            return calls.Count switch
            {
                1 or 2 => Json(HttpStatusCode.OK, "[]"),
                3 => Json(HttpStatusCode.Created, "{\"id\":\"section-1\",\"name\":\"主诉\"}"),
                4 => Json(HttpStatusCode.OK, "{\"id\":\"section-1\",\"name\":\"主诉与症状\"}"),
                _ => new HttpResponseMessage(HttpStatusCode.NoContent),
            };
        });
        var filters = new GuidedDiscoveryFilters
        {
            Languages = ["zh-CN", "en-US"],
            Regions = ["CHN"],
            Labels = ["规范:病历书写"],
            Published = true,
            Source = "user",
        };

        Assert.Empty(await client.Templates.ListAsync(filters));
        Assert.Empty(await client.Templates.ListSectionsAsync(filters));
        var created = await client.Templates.CreateSectionAsync(
            new SectionCreateRequest { Name = "主诉", Language = "zh-CN" });
        var updated = await client.Templates.UpdateSectionAsync(
            "section/1",
            new SectionUpdateRequest { Name = "主诉与症状" });
        await client.Templates.DeleteSectionAsync("section/1");

        Assert.Equal("section-1", created.Id);
        Assert.Equal("主诉与症状", updated.Name);
        Assert.Equal(
            "/api/v2/tools/templates/?lang=zh-CN&lang=en-US&region=CHN&label=%E8%A7%84%E8%8C%83%3A%E7%97%85%E5%8E%86%E4%B9%A6%E5%86%99&published=true&source=user",
            calls[0].PathAndQuery);
        Assert.StartsWith("/api/v2/tools/sections/?lang=zh-CN&lang=en-US", calls[1].PathAndQuery);
        Assert.Equal("POST", calls[2].Method);
        Assert.Equal("PATCH", calls[3].Method);
        Assert.Equal("/api/v2/tools/sections/section%2F1", calls[3].PathAndQuery);
        Assert.Equal("DELETE", calls[4].Method);
    }

    [Fact]
    public async Task TemplatePublishUsesOpaquePublicIdAndReturnsImmutableVersion()
    {
        CapturedRequest? captured = null;
        using var client = CreateClient(async request =>
        {
            captured = await CapturedRequest.FromAsync(request);
            return Json(
                HttpStatusCode.Created,
                "{\"id\":\"version-1\",\"versionNumber\":0,\"generation\":{\"instructions\":{\"prompt\":\"grounded\"}},\"deletedAt\":null}");
        });

        var version = await client.Templates.PublishAsync("template/1");

        Assert.Equal("version-1", version.Id);
        Assert.Equal(0, version.VersionNumber);
        Assert.NotNull(captured);
        Assert.Equal("POST", captured!.Method);
        Assert.Equal(
            "/api/v2/tools/templates/template%2F1/publish",
            captured.PathAndQuery);
    }

    [Fact]
    public async Task ClientCredentialsUsesRfc6749FormEncoding()
    {
        CapturedRequest? captured = null;
        using var client = CreateClient(async request =>
        {
            captured = await CapturedRequest.FromAsync(request);
            return Json(HttpStatusCode.OK, """
                {"access_token":"tenant-token","token_type":"Bearer",
                 "expires_in":300,"scope":"api:read api:write"}
                """);
        });

        var token = await client.AuthenticateClientCredentialsAsync("client id/+", "secret &=");

        Assert.Equal("tenant-token", token.AccessToken);
        Assert.Null(token.RefreshToken);
        Assert.NotNull(captured);
        Assert.Equal("POST", captured!.Method);
        Assert.Equal("/api/oauth/token", captured.PathAndQuery);
        Assert.Null(captured.Authorization);
        Assert.Equal("application/x-www-form-urlencoded", captured.ContentType);
        Assert.Equal(
            "grant_type=client_credentials&client_id=client+id%2F%2B&client_secret=secret+%26%3D&scope=api%3Aread+api%3Awrite",
            Encoding.UTF8.GetString(captured.Bytes!));
    }

    [Fact]
    public async Task FactsExtractUsesCortiV2ShapeAndPreservesServerUsage()
    {
        CapturedRequest? captured = null;
        using var client = CreateClient(async request =>
        {
            captured = await CapturedRequest.FromAsync(request);
            return Json(HttpStatusCode.OK, """
                {"facts":[{"group":"diagnosis","text":"腰椎间盘突出","value":"confirmed"}],
                 "outputLanguage":"zh-CN","usageInfo":{"creditsConsumed":0.012}}
                """);
        });

        var result = await client.Facts.ExtractAsync(new FactExtractionRequest
        {
            Context = [new FactExtractionContext { Text = "去标识临床文本" }],
            OutputLanguage = "zh-CN",
        });

        Assert.Single(result.Facts);
        Assert.Equal(0.012, result.UsageInfo.CreditsConsumed);
        Assert.NotNull(captured);
        Assert.Equal("POST", captured!.Method);
        Assert.Equal("/api/v2/tools/extract-facts", captured.PathAndQuery);
        Assert.Equal("Bearer token-old", captured.Authorization);
        using var body = JsonDocument.Parse(captured.Body!);
        Assert.Equal("text", body.RootElement.GetProperty("context")[0].GetProperty("type").GetString());
        Assert.Equal("zh-CN", body.RootElement.GetProperty("outputLanguage").GetString());
    }

    [Fact]
    public async Task FactsExtractRejectsInvalidContextBeforeTransport()
    {
        var calls = 0;
        using var client = CreateClient(request =>
        {
            calls++;
            return Task.FromResult(Json(HttpStatusCode.OK, "{}"));
        });

        await Assert.ThrowsAsync<ArgumentException>(() => client.Facts.ExtractAsync(
            new FactExtractionRequest
            {
                Context = [new FactExtractionContext { Text = " " }],
            }));
        Assert.Equal(0, calls);
    }

    [Fact]
    public async Task ApiExceptionExposesSafeDetailButNeverRetainsRawPhiBody()
    {
        using var client = CreateClient(_ => Task.FromResult(Json(
            HttpStatusCode.UnprocessableEntity,
            "{\"detail\":{\"type\":\"invalid_audio\",\"detail\":\"格式不支持\",\"requestid\":\"req-1\",\"patient\":\"张三\"}}")));

        var error = await Assert.ThrowsAsync<ICoDerApiException>(
            () => client.SpeechToText.ListRecordingsAsync("i-1"));

        Assert.Equal(HttpStatusCode.UnprocessableEntity, error.StatusCodeValue);
        Assert.Equal("invalid_audio", error.ErrorCode);
        Assert.Equal("req-1", error.RequestId);
        Assert.Contains("格式不支持", error.Message);
        Assert.DoesNotContain("张三", error.Message);
        Assert.DoesNotContain("patient", error.ToString());
    }

    [Fact]
    public async Task PerRequestOptionsAddSafeMetadataAndRetryOnlyBoundedStatuses()
    {
        var calls = new List<CapturedRequest>();
        var customHeaders = new List<string?>();
        using var client = CreateClient(async request =>
        {
            calls.Add(await CapturedRequest.FromAsync(request));
            customHeaders.Add(
                request.Headers.TryGetValues("X-Request-Id", out var values)
                    ? values.Single()
                    : null);
            if (calls.Count < 3)
            {
                var retry = Json(HttpStatusCode.ServiceUnavailable, "{\"detail\":\"retry\"}");
                retry.Headers.TryAddWithoutValidation("Retry-After", "0");
                return retry;
            }
            return Json(HttpStatusCode.OK, "{}");
        });

        await client.Platform.ListEnvironmentsAsync(requestOptions: new ICoDerRequestOptions
        {
            Timeout = TimeSpan.FromSeconds(2),
            MaxRetries = 2,
            AdditionalHeaders = new Dictionary<string, string?>
            {
                ["X-Request-Id"] = "request-1",
            },
            AdditionalQueryParameters = new Dictionary<string, string>
            {
                ["trace_mode"] = "safe",
            },
        });

        Assert.Equal(3, calls.Count);
        Assert.All(calls, item =>
            Assert.Equal("/api/platform/environments?trace_mode=safe", item.PathAndQuery));
        Assert.All(customHeaders, value => Assert.Equal("request-1", value));
    }

    [Fact]
    public async Task PerRequestOptionsFailClosedOnIdentityAndDomainCollisions()
    {
        var calls = 0;
        using var client = CreateClient(_ =>
        {
            calls++;
            return Task.FromResult(Json(HttpStatusCode.OK, "{}"));
        });

        await Assert.ThrowsAsync<ArgumentException>(() =>
            client.Platform.ListEnvironmentsAsync(requestOptions: new ICoDerRequestOptions
            {
                AdditionalHeaders = new Dictionary<string, string?>
                {
                    ["Authorization"] = "Bearer attacker",
                },
            }));
        await Assert.ThrowsAsync<ArgumentException>(() =>
            client.Billing.ListRunSettlementsAsync(requestOptions: new ICoDerRequestOptions
            {
                AdditionalQueryParameters = new Dictionary<string, string>
                {
                    ["limit"] = "999",
                },
            }));
        await Assert.ThrowsAsync<ArgumentException>(() =>
            client.AgentRuns.RunTextAsync(
                "agent-1",
                "safe synthetic input",
                idempotencyKey: "owned-idempotency",
                requestOptions: new ICoDerRequestOptions
                {
                    AdditionalHeaders = new Dictionary<string, string?>
                    {
                        ["Idempotency-Key"] = "attacker",
                    },
                }));
        await Assert.ThrowsAsync<ArgumentException>(() =>
            client.A2A.ListTasksV1Async(
                "agent-1",
                requestOptions: new ICoDerRequestOptions
                {
                    AdditionalHeaders = new Dictionary<string, string?>
                    {
                        ["A2A-Version"] = "attacker",
                    },
                }));
        await Assert.ThrowsAsync<ArgumentOutOfRangeException>(() =>
            client.Platform.ListEnvironmentsAsync(requestOptions: new ICoDerRequestOptions
            {
                Timeout = TimeSpan.Zero,
            }));

        Assert.Equal(0, calls);
    }

    [Fact]
    public async Task RequestOptionsRejectCrossOriginAndNeverRetrySingleUseDownload()
    {
        var calls = 0;
        using var client = CreateClient(_ =>
        {
            calls++;
            return Task.FromResult(Json(
                HttpStatusCode.ServiceUnavailable, "{\"detail\":\"retry\"}"));
        });
        var authorization = new AgenticArtifactDownloadAuthorization
        {
            ObjectId = "object-1",
            PurposeOfUse = "treatment",
            SingleUse = true,
            Part = new AgenticArtifactDownloadPart
            {
                Url = "https://api.cn.icoder.cloud/api/v2/agentic/artifact-objects/download/grant",
            },
        };

        await Assert.ThrowsAsync<ICoDerApiException>(() =>
            client.A2A.DownloadAuthorizedArtifactObjectV2Async(
                authorization,
                requestOptions: new ICoDerRequestOptions { MaxRetries = 3 }));
        Assert.Equal(1, calls);

        var crossOrigin = authorization with
        {
            Part = authorization.Part with { Url = "https://attacker.example/download" },
        };
        await Assert.ThrowsAsync<ArgumentException>(() =>
            client.A2A.DownloadAuthorizedArtifactObjectV2Async(crossOrigin));
        Assert.Equal(1, calls);
    }

    [Fact]
    public void EveryPublicHttpResourceMethodExposesRequestOptions()
    {
        Type[] resources =
        [
            typeof(A2AResource), typeof(AgentRunsResource), typeof(AgentHubResource),
            typeof(MedicalCodingResource), typeof(AgentConnectorsResource),
            typeof(BillingResource), typeof(DocumentsResource), typeof(DrgDipRiskReviewResource),
            typeof(FactsResource), typeof(ModelsResource), typeof(PlatformResource),
            typeof(SpeechToTextResource), typeof(StreamsResource), typeof(TemplatesResource),
        ];

        var missing = resources
            .SelectMany(type => type.GetMethods(
                System.Reflection.BindingFlags.Public |
                System.Reflection.BindingFlags.Instance |
                System.Reflection.BindingFlags.DeclaredOnly))
            .Where(method => method.Name.EndsWith("Async", StringComparison.Ordinal))
            .Where(method => method.Name != nameof(SpeechToTextResource.CreateRealtimeSessionAsync))
            .Where(method => method.Name != nameof(StreamsResource.CreateSessionAsync))
            .Where(method => method.Name != nameof(StreamsResource.ResumeSessionAsync))
            .Where(method => method.GetParameters().All(
                parameter => parameter.ParameterType != typeof(ICoDerRequestOptions)))
            .Select(method => $"{method.DeclaringType!.Name}.{method.Name}")
            .OrderBy(value => value)
            .ToArray();

        Assert.Empty(missing);
        Assert.Contains(
            typeof(ICoDerClient).GetMethod(
                nameof(ICoDerClient.AuthenticateClientCredentialsAsync))!.GetParameters(),
            parameter => parameter.ParameterType == typeof(ICoDerRequestOptions));
    }

    [Fact]
    public async Task PerRequestTimeoutCancelsTheTransportWithoutExternalNetwork()
    {
        var http = new HttpClient(new CancellationAwareHandler(async (_, cancellationToken) =>
        {
            await Task.Delay(TimeSpan.FromSeconds(5), cancellationToken);
            return Json(HttpStatusCode.OK, "{}");
        }));
        using var client = new ICoDerClient(
            new ICoDerClientOptions
            {
                BaseUri = new Uri("https://api.cn.icoder.cloud"),
                AccessToken = "token-old",
                MaxRetries = 0,
            },
            http);

        await Assert.ThrowsAnyAsync<OperationCanceledException>(() =>
            client.Platform.ListEnvironmentsAsync(requestOptions: new ICoDerRequestOptions
            {
                Timeout = TimeSpan.FromMilliseconds(25),
            }));
    }

    [Fact]
    public void NonLoopbackHttpFailsClosedUnlessExplicitlyAllowed()
    {
        var error = Assert.Throws<ArgumentException>(() => new ICoDerClient(
            new ICoDerClientOptions { BaseUri = new Uri("http://hospital.example") }));
        Assert.Contains("HTTPS", error.Message);

        using var allowed = new ICoDerClient(
            new ICoDerClientOptions
            {
                BaseUri = new Uri("http://hospital.example"),
                AllowInsecureHttp = true,
            },
            new HttpClient(new FakeHandler(_ => Task.FromResult(Json(HttpStatusCode.OK, "{}")))));
    }

    private static ICoDerClient CreateClient(
        Func<HttpRequestMessage, Task<HttpResponseMessage>> responder,
        string? refreshToken = null)
    {
        var http = new HttpClient(new FakeHandler(responder));
        return new ICoDerClient(
            new ICoDerClientOptions
            {
                BaseUri = new Uri("https://api.cn.icoder.cloud"),
                AccessToken = "token-old",
                RefreshToken = refreshToken,
                MaxRetries = 0,
            },
            http);
    }

    private static StreamsSessionOptions ValidStreamsOptions() => new()
    {
        InteractionId = Guid.Parse("11111111-1111-4111-8111-111111111111"),
        TenantName = "hospital cn",
        Environment = "cn",
        Configuration = new StreamsConfiguration
        {
            Transcription = new StreamsTranscriptionConfiguration
            {
                PrimaryLanguage = "zh-CN",
                Participants = [new StreamsParticipant { Channel = 0, Role = "multiple" }],
            },
            Mode = new StreamsModeConfiguration
            {
                Type = "facts",
                OutputLocale = "zh-CN",
            },
            RetentionPolicy = "none",
        },
    };

    private static HttpResponseMessage Json(HttpStatusCode statusCode, string content)
        => new(statusCode)
        {
            Content = new StringContent(content, Encoding.UTF8, "application/json"),
        };

    private sealed class FakeHandler(Func<HttpRequestMessage, Task<HttpResponseMessage>> responder)
        : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
            => responder(request);
    }

    private sealed class CancellationAwareHandler(
        Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>> responder)
        : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
            => responder(request, cancellationToken);
    }

    private sealed class FakeWebSocket : WebSocket
    {
        private readonly Queue<(byte[] Payload, WebSocketMessageType MessageType)> _incoming = new();
        private WebSocketState _state = WebSocketState.Open;
        private WebSocketCloseStatus? _closeStatus;
        private string? _closeStatusDescription;

        public List<(WebSocketMessageType MessageType, byte[] Payload)> Sent { get; } = [];
        public bool AutoResumeReady { get; init; }
        public int AutoReadyMaxSessionBytes { get; init; } = RealtimeSttSession.MaximumSessionBytes;
        public string? AutoReadyFollowUp { get; init; }
        public override WebSocketCloseStatus? CloseStatus => _closeStatus;
        public override string? CloseStatusDescription => _closeStatusDescription;
        public override WebSocketState State => _state;
        public override string? SubProtocol => null;

        public void QueueText(string value)
            => _incoming.Enqueue((Encoding.UTF8.GetBytes(value), WebSocketMessageType.Text));

        public void QueueClose()
            => _incoming.Enqueue(([], WebSocketMessageType.Close));

        public override void Abort() => _state = WebSocketState.Aborted;

        public override Task CloseAsync(
            WebSocketCloseStatus closeStatus,
            string? statusDescription,
            CancellationToken cancellationToken)
        {
            _closeStatus = closeStatus;
            _closeStatusDescription = statusDescription;
            _state = WebSocketState.Closed;
            return Task.CompletedTask;
        }

        public override Task CloseOutputAsync(
            WebSocketCloseStatus closeStatus,
            string? statusDescription,
            CancellationToken cancellationToken)
            => CloseAsync(closeStatus, statusDescription, cancellationToken);

        public override void Dispose() => _state = WebSocketState.Closed;

        public override Task<WebSocketReceiveResult> ReceiveAsync(
            ArraySegment<byte> buffer,
            CancellationToken cancellationToken)
        {
            var incoming = _incoming.Dequeue();
            incoming.Payload.CopyTo(buffer.Array!, buffer.Offset);
            if (incoming.MessageType == WebSocketMessageType.Close)
            {
                _state = WebSocketState.CloseReceived;
            }
            return Task.FromResult(new WebSocketReceiveResult(
                incoming.Payload.Length,
                incoming.MessageType,
                endOfMessage: true));
        }

        public override Task SendAsync(
            ArraySegment<byte> buffer,
            WebSocketMessageType messageType,
            bool endOfMessage,
            CancellationToken cancellationToken)
        {
            Sent.Add((messageType, buffer.ToArray()));
            if (AutoResumeReady && messageType == WebSocketMessageType.Text)
            {
                using var message = JsonDocument.Parse(buffer);
                if (message.RootElement.GetProperty("type").GetString() == "start")
                {
                    var sessionId = message.RootElement.GetProperty("sessionId").GetString();
                    QueueText(JsonSerializer.Serialize(new
                    {
                        type = "ready",
                        language = "zh-CN",
                        maxSessionBytes = AutoReadyMaxSessionBytes,
                        protocol = "icoder.stt-resume.v1",
                        resumeSupported = true,
                        resumeMode = "client_replay",
                        sessionId,
                        nextAudioSequence = 1,
                    }));
                    if (AutoReadyFollowUp is not null)
                    {
                        QueueText(AutoReadyFollowUp);
                    }
                }
            }
            return Task.CompletedTask;
        }
    }

    private sealed record CapturedRequest(
        string Method,
        string PathAndQuery,
        string? Authorization,
        string? IdempotencyKey,
        string? A2AProtocolVersion,
        string? A2AVersion,
        string? RetentionPolicy,
        string? LastEventId,
        string? ContentType,
        string? Body,
        byte[]? Bytes)
    {
        public static async Task<CapturedRequest> FromAsync(HttpRequestMessage request)
        {
            var contentType = request.Content?.Headers.ContentType?.MediaType;
            byte[]? bytes = null;
            string? body = null;
            if (request.Content is not null)
            {
                bytes = await request.Content.ReadAsByteArrayAsync();
                if (contentType == "application/json")
                {
                    body = Encoding.UTF8.GetString(bytes);
                }
            }
            return new CapturedRequest(
                request.Method.Method,
                request.RequestUri!.PathAndQuery,
                request.Headers.Authorization?.ToString(),
                request.Headers.TryGetValues("Idempotency-Key", out var values) ? values.Single() : null,
                request.Headers.TryGetValues("A2A-Protocol-Version", out var protocolValues)
                    ? protocolValues.Single()
                    : null,
                request.Headers.TryGetValues("A2A-Version", out var v1ProtocolValues)
                    ? v1ProtocolValues.Single()
                    : null,
                request.Headers.TryGetValues("X-Corti-Retention-Policy", out var retentionValues)
                    ? retentionValues.Single()
                    : null,
                request.Headers.TryGetValues("Last-Event-ID", out var lastEventValues)
                    ? lastEventValues.Single()
                    : null,
                contentType,
                body,
                bytes);
        }
    }
}
