import assert from 'node:assert/strict';
import test from 'node:test';

import iCoDer from '../dist/index.js';


test('ModelsResource reads the authenticated secret-free model catalog', async () => {
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test',
    auth: { accessToken: 'test-token' },
  });
  let captured;
  sdk.client.http.defaults.adapter = async (config) => {
    captured = config;
    return {
      data: {
        active_provider: 'mock',
        active_model: 'mock/1.0',
        operator_default_provider: 'mock',
        operator_default_model: 'mock/1.0',
        effective_deployment_id: 'mock',
        tenant_selection: { mode: 'inherit', deployment_id: null, version: 0 },
        registered_deployments: [],
        selection_editable: true,
        tenant_region: 'cn',
        egress_policy: 'strict',
        external_llm_allowed: false,
        models: [],
        readiness_scope: 'configuration_and_policy_only',
        live_health_verified: false,
        disclaimer: 'configuration only',
      },
      status: 200,
      statusText: 'OK',
      headers: {},
      config,
      request: {},
    };
  };

  const result = await sdk.models.getCatalog();

  assert.equal(captured.url, '/api/v1/model-catalog');
  assert.equal(result.live_health_verified, false);
  assert.equal(result.readiness_scope, 'configuration_and_policy_only');
});

test('ModelsResource updates an optimistic tenant deployment selection', async () => {
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test',
    auth: { accessToken: 'test-token' },
  });
  let captured;
  sdk.client.http.defaults.adapter = async (config) => {
    captured = config;
    return {
      data: { mode: 'pinned', deployment_id: 'qwen-cn-a', version: 2 },
      status: 200,
      statusText: 'OK',
      headers: {},
      config,
      request: {},
    };
  };

  const result = await sdk.models.updateSelection({
    mode: 'pinned', deployment_id: 'qwen-cn-a', expected_version: 1,
  });

  assert.equal(captured.method, 'put');
  assert.equal(captured.url, '/api/v1/model-catalog/selection');
  assert.deepEqual(JSON.parse(captured.data), {
    mode: 'pinned', deployment_id: 'qwen-cn-a', expected_version: 1,
  });
  assert.equal(result.version, 2);
});

test('ModelsResource runs a no-network configuration health probe', async () => {
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test',
    auth: { accessToken: 'test-token' },
  });
  let captured;
  sdk.client.http.defaults.adapter = async (config) => {
    captured = config;
    return {
      data: {
        deployment_id: 'hospital-local',
        provider_id: 'local',
        model: 'hospital-model-v1',
        status: 'healthy',
        probe_mode: 'configuration',
        egress_decision: 'allow',
        credential_configured: false,
        circuit_open: false,
        checked_at: '2026-08-21T00:00:00Z',
      },
      status: 200,
      statusText: 'OK',
      headers: {},
      config,
      request: {},
    };
  };

  const result = await sdk.models.healthProbe('hospital-local');

  assert.equal(captured.method, 'post');
  assert.equal(captured.url, '/api/v1/model-catalog/health-probe');
  assert.deepEqual(JSON.parse(captured.data), { deployment_id: 'hospital-local' });
  assert.equal(result.probe_mode, 'configuration');
});

test('ModelsResource sends only the fixed explicitly acknowledged live canary contract', async () => {
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test',
    auth: { accessToken: 'test-token' },
  });
  let captured;
  sdk.client.http.defaults.adapter = async (config) => {
    captured = config;
    return {
      data: {
        deployment_id: 'deepseek', provider_id: 'deepseek', model: 'deepseek-chat',
        status: 'reachable', reason_code: 'ok',
        probe_mode: 'external_connectivity_canary', egress_decision: 'allow',
        synthetic_payload: true, patient_data_sent: false,
        expected_token_matched: true, latency_ms: 25,
        usage: { input_tokens: 31, output_tokens: 4 },
        cost: { amount: 0.000006, currency: 'CNY', billing_authoritative: false,
          source: 'provider_usage_pricing_estimate' },
        request_cost_cap_cny: 0.01, estimated_max_cost_cny: 0.000146,
        checked_at: '2026-08-21T00:00:00Z',
      },
      status: 200, statusText: 'OK', headers: {}, config, request: {},
    };
  };

  const result = await sdk.models.liveCanary('deepseek', 0.01);

  assert.equal(captured.url, '/api/v1/model-catalog/live-canary');
  assert.deepEqual(JSON.parse(captured.data), {
    deployment_id: 'deepseek',
    acknowledge_external_call: true,
    purpose: 'connectivity_only_no_patient_data',
    max_cost_cny: 0.01,
  });
  assert.equal(result.patient_data_sent, false);
  assert.equal(result.cost.billing_authoritative, false);
});

test('ModelsResource exposes metadata-only clinical package activation and rollback', async () => {
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test',
    auth: { accessToken: 'test-token' },
  });
  const calls = [];
  sdk.client.http.defaults.adapter = async (config) => {
    calls.push({ method: config.method, url: config.url, data: config.data });
    return {
      data: {
        id: 'activation-1', use_case: 'clinical_coding_decision_support',
        package_id: '11111111-1111-4111-8111-111111111111', previous_package_id: null,
        deployment_mode: 'hospital_private', record_version: calls.length,
        activated_by_user_id: 'user-1', created_at: '2026-08-27T00:00:00Z',
        updated_at: '2026-08-27T00:00:00Z', activation_blockers: [],
        runtime_loading_enabled: false,
      },
      status: 200, statusText: 'OK', headers: {}, config, request: {},
    };
  };
  const input = {
    package_id: '11111111-1111-4111-8111-111111111111',
    deployment_mode: 'hospital_private', expected_version: 0,
    acknowledge_clinical_governance: true,
  };

  const activated = await sdk.models.activateClinicalPackage(
    'clinical_coding_decision_support', input,
  );
  await sdk.models.rollbackClinicalPackage(
    'clinical_coding_decision_support', { ...input, expected_version: 1 },
  );

  assert.equal(calls[0].method, 'put');
  assert.equal(calls[0].url,
    '/api/v1/clinical-model-packages/activations/clinical_coding_decision_support');
  assert.equal(JSON.parse(calls[0].data).acknowledge_clinical_governance, true);
  assert.equal(calls[1].method, 'post');
  assert.equal(calls[1].url,
    '/api/v1/clinical-model-packages/activations/clinical_coding_decision_support/rollback');
  assert.equal(activated.runtime_loading_enabled, false);
});

test('ModelsResource exposes signed synthetic attestations and shadow-only binding', async () => {
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test',
    auth: { accessToken: 'test-token' },
  });
  const calls = [];
  sdk.client.http.defaults.adapter = async (config) => {
    calls.push({
      method: config.method,
      url: config.url,
      data: config.data,
      headers: config.headers,
    });
    return {
      data: calls.length === 1
        ? { items: [], count: 0, metadata_only: true }
        : calls.length === 2
          ? { id: 'att-1', bundle_stored: false, patient_data_stored: false,
            production_inference_enabled: false }
          : calls.length === 5
            ? { items: [], count: 0, aggregate_only: true }
            : calls.length === 6
              ? { id: 'evaluation-1', result: 'stopped', rollback_performed: true,
                aggregate_only: true, patient_data_used: false,
                predictions_emitted: false, production_inference_enabled: false }
              : calls.length === 8
                ? { items: [{ id: 'job-1', status: 'passed' }], count: 1,
                  aggregate_only: true, patient_data_used: false }
                : calls.length === 12
                  ? { status: 'healthy', status_counts: { queued: 0 },
                    due_queued_count: 0, active_lease_count: 0,
                    expired_lease_count: 0, exhausted_count: 0,
                    dead_letter_count: 0,
                    oldest_due_age_seconds: 0, alert_codes: [],
                    evaluated_at: '2026-08-27T00:00:00Z', aggregate_only: true,
                    patient_data_used: false, identifiers_emitted: false }
                  : calls.length === 13
                    ? { finalized_exhausted_count: 0, aggregate_only: true,
                      organizations_evaluated: 1, alerts_fired: 0, alerts_resolved: 0,
                      patient_data_used: false, identifiers_emitted: false }
                  : calls.length === 14
                    ? { items: [{ id: 'dead-1', status: 'available',
                      patient_data_used: false }], count: 1, aggregate_only: true }
                  : calls.length === 16
                    ? { items: [{ alert_code: 'dead_letter_backlog', state: 'resolved',
                      occurrence_count: 1 }], count: 1, aggregate_only: true,
                      patient_data_used: false, identifiers_emitted: false }
                : calls.length >= 7
                  ? { id: 'job-1', status: calls.length === 10 ? 'passed'
                    : calls.length === 11 ? 'cancelled' : 'queued',
                    lease_active: false, aggregate_only: true, patient_data_used: false,
                    predictions_emitted: false, production_inference_enabled: false }
          : { id: 'binding-1', mode: 'shadow_only', patient_data_allowed: false,
            runtime_inference_enabled: false, predictions_emitted: false },
      status: 200, statusText: 'OK', headers: {}, config, request: {},
    };
  };
  const useCase = 'clinical_coding_decision_support';
  await sdk.models.listClinicalArtifactAttestations('package/1');
  const attestation = await sdk.models.probeSyntheticClinicalArtifact('package/1', 'e30=', 3);
  const bindingInput = {
    attestation_id: 'att-1', expected_version: 0, acknowledge_shadow_only: true,
  };
  const binding = await sdk.models.bindClinicalShadowAttestation(useCase, bindingInput);
  await sdk.models.rollbackClinicalShadowBinding(
    useCase, { ...bindingInput, expected_version: 1 },
  );
  await sdk.models.listClinicalShadowEvaluations(useCase);
  const evaluation = await sdk.models.evaluateSyntheticClinicalShadow(useCase, {
    expected_binding_version: 2,
    fault_mode: 'worker_timeout',
    acknowledge_synthetic_only: true,
    acknowledge_fault_injection: true,
  });
  const jobInput = {
    expected_binding_version: 3,
    fault_mode: 'none',
    acknowledge_synthetic_only: true,
    acknowledge_fault_injection: false,
  };
  const job = await sdk.models.createClinicalShadowEvaluationJob(
    useCase, jobInput, 'shadow-job-0001',
  );
  await sdk.models.listClinicalShadowEvaluationJobs(useCase);
  await sdk.models.getClinicalShadowEvaluationJob('job-1');
  const executed = await sdk.models.executeClinicalShadowEvaluationJobSimulation('job-1');
  const cancelled = await sdk.models.cancelClinicalShadowEvaluationJob(
    'job-1', 'safety_stop',
  );
  const health = await sdk.models.getClinicalShadowEvaluationJobHealth();
  const maintenance = await sdk.models.maintainClinicalShadowEvaluationJobsSimulation();
  const deadLetters = await sdk.models.listClinicalShadowDeadLetters();
  const replay = await sdk.models.replayClinicalShadowDeadLetter(
    'dead-1', 'shadow-replay-0001',
  );
  const alertStates = await sdk.models.listClinicalShadowAlertStates();

  assert.equal(calls[0].url,
    '/api/v1/clinical-model-packages/package%2F1/artifact-attestations');
  assert.equal(calls[1].url,
    '/api/v1/clinical-model-packages/package%2F1/synthetic-artifact-probe');
  assert.deepEqual(JSON.parse(calls[1].data), {
    bundle_base64: 'e30=', expected_package_record_version: 3,
  });
  assert.equal(calls[2].method, 'put');
  assert.equal(calls[3].method, 'post');
  assert.equal(calls[4].url,
    `/api/v1/clinical-model-packages/shadow-bindings/${useCase}/evaluations`);
  assert.equal(calls[5].url,
    `/api/v1/clinical-model-packages/shadow-bindings/${useCase}/synthetic-evaluation`);
  assert.equal(JSON.parse(calls[5].data).acknowledge_fault_injection, true);
  assert.equal(calls[6].url,
    `/api/v1/clinical-model-packages/shadow-bindings/${useCase}/evaluation-jobs`);
  assert.equal(calls[6].headers['Idempotency-Key'], 'shadow-job-0001');
  assert.deepEqual(JSON.parse(calls[6].data), jobInput);
  assert.equal(calls[7].method, 'get');
  assert.equal(calls[8].url,
    '/api/v1/clinical-model-packages/shadow-evaluation-jobs/job-1');
  assert.equal(calls[9].url,
    '/api/v1/clinical-model-packages/shadow-evaluation-jobs/job-1/execute');
  assert.equal(calls[10].url,
    '/api/v1/clinical-model-packages/shadow-evaluation-jobs/job-1/cancel');
  assert.deepEqual(JSON.parse(calls[10].data), { reason: 'safety_stop' });
  assert.equal(calls[11].url,
    '/api/v1/clinical-model-packages/shadow-evaluation-jobs/health/summary');
  assert.equal(calls[12].url,
    '/api/v1/clinical-model-packages/shadow-evaluation-jobs/maintenance/run');
  assert.equal(calls[13].url,
    '/api/v1/clinical-model-packages/shadow-evaluation-jobs/dead-letters/list');
  assert.equal(calls[14].url,
    '/api/v1/clinical-model-packages/shadow-evaluation-jobs/dead-letters/dead-1/replay');
  assert.equal(calls[14].headers['Idempotency-Key'], 'shadow-replay-0001');
  assert.equal(calls[15].url,
    '/api/v1/clinical-model-packages/shadow-evaluation-jobs/alerts/states');
  assert.equal(JSON.parse(calls[2].data).acknowledge_shadow_only, true);
  assert.equal(attestation.production_inference_enabled, false);
  assert.equal(binding.runtime_inference_enabled, false);
  assert.equal(evaluation.rollback_performed, true);
  assert.equal(job.status, 'queued');
  assert.equal(executed.status, 'passed');
  assert.equal(cancelled.status, 'cancelled');
  assert.equal(health.status, 'healthy');
  assert.equal(maintenance.finalized_exhausted_count, 0);
  assert.equal(deadLetters.count, 1);
  assert.equal(replay.status, 'queued');
  assert.equal(alertStates.items[0].state, 'resolved');
});
