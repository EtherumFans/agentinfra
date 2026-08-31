import assert from 'node:assert/strict';
import test from 'node:test';

import iCoDer from '../dist/index.js';


test('AgentsResource uses agent_definitions CRUD and authenticated A2A execution', async () => {
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test',
    auth: { accessToken: 'test-token' },
  });
  const calls = [];
  sdk.client.http.defaults.adapter = async (config) => {
    calls.push({
      method: config.method?.toUpperCase(),
      url: config.url,
      headers: config.headers,
      data: typeof config.data === 'string' ? JSON.parse(config.data) : config.data,
    });
    const isRun = config.url?.includes('/v1/message:send');
    return {
      data: isRun
        ? {
            jsonrpc: '2.0',
            id: 'rpc-1',
            result: {
              kind: 'message',
              role: 'agent',
              messageId: 'msg-result',
              contextId: 'ctx-1',
              parts: [{ kind: 'text', text: 'done' }],
              metadata: {},
            },
          }
        : { agents: [] },
      status: 200,
      statusText: 'OK',
      headers: {},
      config,
      request: {},
    };
  };

  await sdk.agents.list();
  const result = await sdk.agents.run('medical/coding', 'de-identified note');

  assert.equal(calls[0].url, '/api/rest/v1/agent_definitions');
  assert.equal(
    calls[1].url,
    '/api/icoder/agents/medical%2Fcoding/v1/message:send',
  );
  assert.equal(calls[1].data.method, 'message/send');
  assert.equal(calls[1].headers['A2A-Protocol-Version'], '0.3');
  assert.equal(result.contextId, 'ctx-1');
  assert.ok(calls.every((call) => !call.url.startsWith('/api/agents')));
});


test('AgentsResource stream uses bearer-authenticated A2A message/stream SSE', async () => {
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test/',
    auth: { accessToken: 'stream-token' },
  });
  const originalFetch = globalThis.fetch;
  let captured;
  globalThis.fetch = async (url, init) => {
    captured = { url: String(url), init, body: JSON.parse(String(init.body)) };
    return new Response('event: done\ndata: {"ok":true}\n\n', {
      status: 200,
      headers: { 'content-type': 'text/event-stream; charset=utf-8' },
    });
  };
  try {
    const stream = await sdk.agents.stream('note completeness', 'safe input');
    const { value } = await stream.getReader().read();
    assert.match(new TextDecoder().decode(value), /event: done/);
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(
    captured.url,
    'https://api.cn.icoder.test/api/icoder/agents/note%20completeness/v1/message:stream',
  );
  assert.equal(captured.init.headers.Authorization, 'Bearer stream-token');
  assert.equal(captured.init.headers['A2A-Protocol-Version'], '0.3');
  assert.equal(captured.body.method, 'message/stream');
  assert.equal(captured.body.params.message.parts[0].text, 'safe input');
});


test('AgentsResource exposes typed Hub contract discovery routes', async () => {
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test',
    auth: { accessToken: 'test-token' },
  });
  const calls = [];
  sdk.client.http.defaults.adapter = async (config) => {
    calls.push({ url: config.url, params: config.params });
    const card = {
      agent_id: 'claim-check',
      agent_ref: 'icoder/claim-check@1.0.0',
      name: 'Claim Check',
      description: '',
      category: 'coding',
      runnable: true,
      launch_candidate_ready: true,
      production_ready: false,
      human_review: 'required',
      execution_path: 'provider_registry',
      execution_target: 'icoder.pure-llm.v1',
      runtime_readiness: {
        structural_status: 'ready',
        configuration_status: 'not_checked',
        run_action_enabled: false,
        reason: 'tenant_runtime_readiness_requires_authentication',
        runtime_dependencies: ['external_llm_gateway'],
        external_llm_required: true,
        live_health_verified: false,
        semantic_validation_status: 'not_verified',
        production_approval_status: 'not_approved',
      },
      output_contract: {
        schema_ref: 'icoder/ClaimCheckOutput/v1',
        required_fields: ['summary'],
        optional_fields: ['details'],
        field_types: { summary: 'string', details: 'array' },
        field_schemas: { details: { type: 'array', items: { type: 'string' } } },
          field_relations: [{
          id: 'details_require_summary',
          for_each: 'candidates',
          when: [{ path: 'details', operator: 'non_empty' }],
            must: [{ path: 'confidence', operator: 'gte', value: 0.7 }],
          }],
          evidence_bindings: [{
            id: 'candidate_evidence_matches_input',
            for_each: 'candidates',
            text_path: 'evidence_text',
            span_path: 'char_span',
          }],
          cross_agent_relations: [{
            id: 'candidate_matches_upstream',
            local_path: 'summary',
            upstream_agent_id: 'upstream-agent',
            upstream_path: 'items',
            upstream_item_path: 'code',
            operator: 'scalar_in_upstream_items',
            normalization: 'medical_code',
            required: false,
          }],
      },
    };
    const discoveryCard = {
      name: 'Claim Check',
      description: 'A2A discovery card',
      url: 'https://api.cn.icoder.test/api/icoder/agents/claim-check/v1/message:send',
      version: '1.0.0',
      provider: 'iCoDer',
      capabilities: {
        streaming: true,
        pushNotifications: false,
        stateTransitionHistory: true,
      },
      skills: [{
        id: 'claim-check',
        name: 'Claim Check',
        description: 'Validate claims',
        inputSchema: { type: 'object' },
        outputSchema: { type: 'object' },
      }],
      defaultInputModes: ['text'],
      defaultOutputModes: ['application/json'],
      securitySchemes: {},
    };
    const tenantReadiness = {
      schema_version: '1.0',
      generated_at: '2026-08-23T00:00:00Z',
      total: 1,
      agents: [{
        agent_id: 'claim-check',
        execution_target: 'icoder.pure-llm.v1',
        runtime_readiness: {
          structural_status: 'ready',
          configuration_status: 'configured',
          run_action_enabled: true,
          reason: 'tenant_model_configuration_present',
          runtime_dependencies: ['external_llm_gateway'],
          llm_required: true,
          live_health_verified: true,
          connectivity_status: 'verified',
          semantic_validation_status: 'not_verified',
          production_approval_status: 'not_approved',
        },
        evidence: {
          scope: 'tenant_configuration_and_connectivity',
          selection_mode: 'pinned',
          selection_version: 2,
          deployment_id: 'deepseek',
          provider_id: 'deepseek',
          configuration_probe_status: 'not_run',
          canary_checked_at: '2026-08-23T00:00:00Z',
          canary_expires_at: '2026-08-23T00:15:00Z',
        },
      }],
    };
    return {
      data: config.url.endsWith('/card')
        ? discoveryCard
        : config.url.endsWith('/hub/readiness')
          ? tenantReadiness
          : { agents: [card], total: 1, source: 'packs', schema_version: '1.3' },
      status: 200,
      statusText: 'OK',
      headers: {},
      config,
      request: {},
    };
  };

  const hub = await sdk.agents.hub('coding_revenue_cycle');
  const readiness = await sdk.agents.hubReadiness();
  const card = await sdk.agents.card('claim/check');

  assert.equal(calls[0].url, '/api/icoder/agents/hub');
  assert.equal(calls[0].params.use_case, 'coding_revenue_cycle');
  assert.equal(calls[1].url, '/api/icoder/agents/hub/readiness');
  assert.equal(calls[2].url, '/api/icoder/agents/claim%2Fcheck/card');
  assert.deepEqual(hub.agents[0].output_contract.optional_fields, ['details']);
  assert.equal(card.capabilities.streaming, true);
  assert.equal(card.skills[0].outputSchema.type, 'object');
  assert.equal(hub.agents[0].runtime_readiness.configuration_status, 'not_checked');
  assert.equal(hub.agents[0].runtime_readiness.live_health_verified, false);
  assert.equal(readiness.agents[0].runtime_readiness.configuration_status, 'configured');
  assert.equal(readiness.agents[0].runtime_readiness.connectivity_status, 'verified');
  assert.equal(readiness.agents[0].runtime_readiness.live_health_verified, true);
  assert.equal(readiness.agents[0].evidence.deployment_id, 'deepseek');
  assert.equal(hub.agents[0].output_contract.field_types.details, 'array');
  assert.equal(hub.agents[0].output_contract.field_schemas.details.items.type, 'string');
  assert.equal(hub.agents[0].output_contract.field_relations[0].for_each, 'candidates');
  assert.equal(hub.agents[0].output_contract.evidence_bindings[0].span_path, 'char_span');
});


test('AgentsResource clones a Hub Agent under the project runtime identity', async () => {
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test',
    auth: { accessToken: 'test-token' },
  });
  const calls = [];
  sdk.client.http.defaults.adapter = async (config) => {
    calls.push({
      method: config.method?.toUpperCase(),
      url: config.url,
      data: typeof config.data === 'string' ? JSON.parse(config.data) : config.data,
    });
    return {
      data: {
        project_agent_id: 'project-agent-1',
        runtime_agent_id: 'project-agent-1',
        source_runtime_agent_id: 'claim-check',
        source_agent_ref: 'icoder/claim-check@1.0.0',
        chat_url: '/ai-studio/agents/project-agent-1/chat',
        customize_url: '/ai-studio/agents/project-agent-1',
        run_url: '/api/icoder/agents/project-agent-1/v1/message:send',
        cloned: true,
      },
      status: 201,
      statusText: 'Created',
      headers: {},
      config,
      request: {},
    };
  };

  const clone = await sdk.agents.clone('claim/check', {
    name: 'Project Claim Check',
    project_id: 'project-cn-1',
  });

  assert.equal(calls[0].method, 'POST');
  assert.equal(calls[0].url, '/api/icoder/agents/claim%2Fcheck/clone');
  assert.deepEqual(calls[0].data, {
    name: 'Project Claim Check',
    project_id: 'project-cn-1',
  });
  assert.equal(clone.runtime_agent_id, clone.project_agent_id);
  assert.equal(clone.source_runtime_agent_id, 'claim-check');
});


test('AgentsResource rejects a clone response that bypasses project identity', async () => {
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test',
    auth: { accessToken: 'test-token' },
  });
  sdk.client.http.defaults.adapter = async (config) => ({
    data: {
      project_agent_id: 'project-agent-1',
      runtime_agent_id: 'claim-check',
      source_runtime_agent_id: 'claim-check',
      source_agent_ref: 'icoder/claim-check@1.0.0',
      chat_url: '/chat',
      customize_url: '/customize',
      run_url: '/api/icoder/agents/claim-check/v1/message:send',
      cloned: false,
    },
    status: 200,
    statusText: 'OK',
    headers: {},
    config,
    request: {},
  });

  await assert.rejects(
    sdk.agents.clone('claim-check'),
    /bypass the project runtime identity/,
  );
});


test('AgentsResource fails closed when Hub schema 1.3 enables an unavailable Agent', async () => {
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test',
    auth: { accessToken: 'test-token' },
  });
  sdk.client.http.defaults.adapter = async (config) => ({
    data: {
      agents: [{
        agent_id: 'claim-check',
        runtime_readiness: {
          structural_status: 'ready',
          configuration_status: 'unavailable',
          run_action_enabled: true,
          reason: 'mock_provider',
          runtime_dependencies: ['external_llm_gateway'],
          external_llm_required: true,
          live_health_verified: false,
          semantic_validation_status: 'not_verified',
          production_approval_status: 'not_approved',
        },
      }],
      total: 1,
      source: 'packs',
      schema_version: '1.3',
    },
    status: 200,
    statusText: 'OK',
    headers: {},
    config,
    request: {},
  });

  await assert.rejects(
    sdk.agents.hub(),
    /enables an unavailable Agent/,
  );
});


test('AgentsResource rejects tenant Hub readiness with an unverified live-health claim', async () => {
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test',
    auth: { accessToken: 'test-token' },
  });
  sdk.client.http.defaults.adapter = async (config) => ({
    data: {
      schema_version: '1.0',
      generated_at: '2026-08-23T00:00:00Z',
      total: 1,
      agents: [{
        agent_id: 'claim-check',
        execution_target: 'icoder.pure-llm.v1',
        runtime_readiness: {
          structural_status: 'ready',
          configuration_status: 'configured',
          run_action_enabled: true,
          reason: 'configured',
          runtime_dependencies: ['external_llm_gateway'],
          llm_required: true,
          live_health_verified: true,
          connectivity_status: 'not_run',
          semantic_validation_status: 'not_verified',
          production_approval_status: 'not_approved',
        },
        evidence: {
          scope: 'tenant_configuration_and_connectivity',
          selection_mode: 'pinned',
          selection_version: 1,
          deployment_id: 'deepseek',
          provider_id: 'deepseek',
          configuration_probe_status: 'not_run',
          canary_checked_at: null,
          canary_expires_at: null,
        },
      }],
    },
    status: 200,
    statusText: 'OK',
    headers: {},
    config,
    request: {},
  });

  await assert.rejects(
    sdk.agents.hubReadiness(),
    /claims live health without verified connectivity/,
  );
});


test('AgentsResource manages Connector resources and optimistic graph revisions', async () => {
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test',
    auth: { accessToken: 'test-token' },
  });
  const calls = [];
  sdk.client.http.defaults.adapter = async (config) => {
    const body = typeof config.data === 'string' ? JSON.parse(config.data) : config.data;
    calls.push({
      method: config.method?.toUpperCase(),
      url: config.url,
      params: config.params,
      body,
    });
    return {
      data: config.url.endsWith('/connector-graph')
        ? {
            version: '1.0', enabled: true, execution_mode: 'parallel', max_concurrency: 2,
            nodes: body?.nodes ?? [], revision: 1,
          }
        : {
            id: 'con-1', agent_id: 'agent/one', type: 'registry', name: 'Memory',
            description: '', enabled: false, config: { registry_key: 'memory' },
            version: 1, credential: { present: false }, created_by: 'u-1',
            created_at: '2026-08-22T00:00:00Z', updated_at: '2026-08-22T00:00:00Z',
          },
      status: 200,
      statusText: 'OK',
      headers: {},
      config,
      request: {},
    };
  };

  await sdk.agents.createConnector('agent/one', {
    type: 'registry',
    name: 'Memory',
    config: { registry_key: 'memory', capabilities: ['lookup'] },
  });
  await sdk.agents.bindConnectorCredential('agent/one', 'con/1', {
    provider: 'vault',
    secret_ref: 'vault://tenant/connectors/memory',
    secret_type: 'bearer',
  });
  await sdk.agents.putConnectorGraph('agent/one', {
    version: '1.0',
    enabled: true,
    execution_mode: 'parallel',
    max_concurrency: 2,
    expected_revision: 0,
    nodes: [{ id: 'lookup', connector_id: 'con-1', operation: 'lookup',
      when: { input_key: 'codingSystem', operator: 'equals', value: 'ICD-10-CN' } }],
  });
  await sdk.agents.deleteConnectorGraph('agent/one', 1);
  await sdk.agents.grantMemoryConsent('agent/one', {
    purpose_of_use: 'treatment', retention_days: 30, expires_in_days: 30,
    acknowledgement: true,
  });
  await sdk.agents.memoryConsent('agent/one', 'treatment');
  await sdk.agents.revokeMemoryConsent('agent/one', 'treatment');

  assert.equal(calls[0].url, '/api/v2/agentic/agents/agent%2Fone/connectors');
  assert.equal(calls[0].body.config.registry_key, 'memory');
  assert.equal(
    calls[1].url,
    '/api/v2/agentic/agents/agent%2Fone/connectors/con%2F1/credential',
  );
  assert.equal(calls[1].body.secret_ref, 'vault://tenant/connectors/memory');
  assert.equal(calls[2].url, '/api/v2/agentic/agents/agent%2Fone/connector-graph');
  assert.equal(calls[2].body.expected_revision, 0);
  assert.equal(calls[2].body.execution_mode, 'parallel');
  assert.equal(calls[2].body.max_concurrency, 2);
  assert.equal(calls[3].method, 'DELETE');
  assert.equal(calls[3].params.expected_revision, 1);
  assert.equal(calls[4].url, '/api/v2/agentic/agents/agent%2Fone/memory-consent');
  assert.equal(calls[4].body.acknowledgement, true);
  assert.equal(calls[5].params.purpose_of_use, 'treatment');
  assert.equal(calls[6].method, 'DELETE');
  assert.equal(calls[6].params.purpose_of_use, 'treatment');
});
