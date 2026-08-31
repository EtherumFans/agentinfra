import assert from 'node:assert/strict';
import test from 'node:test';

import iCoDer, { A2AProtocolError } from '../dist/index.js';


test('A2A v1 SDK covers durable send, polling, list, cancel, and resume stream', async () => {
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test',
    auth: { accessToken: 'v1-token' },
  });
  const calls = [];
  let taskReads = 0;
  sdk.client.http.defaults.adapter = async (config) => {
    const data = typeof config.data === 'string' ? JSON.parse(config.data) : config.data;
    calls.push({
      method: config.method,
      url: config.url,
      headers: config.headers,
      params: config.params,
      data,
    });
    let responseData;
    if (config.url.endsWith('/message:send')) {
      responseData = {
        task: {
          id: 'task-1',
          contextId: 'context-1',
          status: { state: 'TASK_STATE_SUBMITTED' },
          artifacts: [],
          history: [],
          metadata: {},
        },
      };
    } else if (config.url.endsWith('/tasks/task-1:cancel')) {
      responseData = {
        id: 'task-1',
        contextId: 'context-1',
        status: { state: 'TASK_STATE_CANCELED' },
        artifacts: [],
        history: [],
        metadata: {},
      };
    } else if (config.url.endsWith('/tasks/task-1')) {
      taskReads += 1;
      responseData = {
        id: 'task-1',
        contextId: 'context-1',
        status: {
          state: taskReads === 1 ? 'TASK_STATE_WORKING' : 'TASK_STATE_COMPLETED',
        },
        artifacts: [],
        history: [],
        metadata: {},
      };
    } else if (config.url.endsWith('/tasks')) {
      responseData = {
        tasks: [],
        pageSize: 10,
        totalSize: 0,
        nextPageToken: '',
      };
    } else {
      throw new Error(`unexpected URL ${config.url}`);
    }
    return {
      data: responseData,
      status: 200,
      statusText: 'OK',
      headers: {},
      config,
      request: {},
    };
  };

  const originalFetch = globalThis.fetch;
  let subscription;
  let directStream;
  globalThis.fetch = async (url, init) => {
    if (String(url).endsWith('/message:stream')) {
      directStream = { url: String(url), init };
      return new Response(
        'id: 1\nevent: task\ndata: {"task":{"id":"task-stream"}}\n\n' +
          'id: 2\nevent: artifact-update\ndata: {"artifactUpdate":{"taskId":"task-stream","append":false,"lastChunk":false}}\n\n' +
          'id: 3\nevent: artifact-update\ndata: {"artifactUpdate":{"taskId":"task-stream","append":true,"lastChunk":true}}\n\n',
        { status: 200, headers: { 'content-type': 'text/event-stream' } },
      );
    }
    subscription = { url: String(url), init };
    return new Response(
      'id: 2\nevent: status-update\ndata: {"statusUpdate":{"taskId":"task-1"}}\n\n' +
        'id: 3\nevent: artifact-update\ndata: {"artifactUpdate":{"taskId":"task-1"}}\n\n',
      { status: 200, headers: { 'content-type': 'text/event-stream' } },
    );
  };
  try {
    const submitted = await sdk.a2a.messageSendV1(
      'note completeness',
      'safe note',
      { messageId: 'message-1', returnImmediately: true },
    );
    const completed = await sdk.a2a.waitTaskV1(
      'note completeness',
      submitted.task.id,
      { timeoutMs: 1000, pollIntervalMs: 1 },
    );
    const listed = await sdk.a2a.listTasksV1('note completeness', {
      pageSize: 10,
      includeArtifacts: true,
    });
    const canceled = await sdk.a2a.cancelTaskV1('note completeness', 'task-1');
    const direct = await sdk.a2a.messageStreamV1(
      'note completeness',
      'safe streamed note',
      {
        messageId: 'message-stream-1',
        contextId: 'context-input',
        taskId: 'task-input',
      },
    );
    const directChunk = await direct.getReader().read();
    const stream = await sdk.a2a.subscribeTaskV1('note completeness', 'task-1', {
      afterSequence: 1,
      lastEventId: '1',
    });
    const firstChunk = await stream.getReader().read();

    assert.equal(completed.status.state, 'TASK_STATE_COMPLETED');
    assert.equal(listed.totalSize, 0);
    assert.equal(canceled.status.state, 'TASK_STATE_CANCELED');
    assert.match(new TextDecoder().decode(directChunk.value), /lastChunk/);
    assert.match(
      new TextDecoder().decode(firstChunk.value),
      /statusUpdate|artifactUpdate/,
    );
  } finally {
    globalThis.fetch = originalFetch;
  }

  const send = calls.find((call) => call.url.endsWith('/message:send'));
  assert.equal(send.headers['A2A-Version'], '1.0');
  assert.equal(send.data.configuration.returnImmediately, true);
  assert.equal(send.data.message.role, 'ROLE_USER');
  assert.equal(send.data.message.parts[0].mediaType, 'text/plain');
  assert.equal(
    directStream.url,
    'https://api.cn.icoder.test/api/v2/agentic/agents/note%20completeness/message:stream',
  );
  assert.equal(directStream.init.headers['A2A-Version'], '1.0');
  assert.equal(JSON.parse(directStream.init.body).message.messageId, 'message-stream-1');
  assert.equal(JSON.parse(directStream.init.body).message.contextId, 'context-input');
  assert.equal(JSON.parse(directStream.init.body).message.taskId, 'task-input');
  assert.equal(
    subscription.url,
    'https://api.cn.icoder.test/api/v2/agentic/agents/note%20completeness/' +
      'tasks/task-1:subscribe?afterSequence=1',
  );
  assert.equal(subscription.init.headers.Authorization, 'Bearer v1-token');
  assert.equal(subscription.init.headers['A2A-Version'], '1.0');
  assert.equal(subscription.init.headers['Last-Event-ID'], '1');
});


test('A2A v1 SDK retains only stable protocol reason from google.rpc details', async () => {
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test',
    auth: { accessToken: 'v1-token' },
  });
  sdk.client.http.defaults.adapter = async (config) => ({
    data: {
      error: {
        code: 404,
        status: 'NOT_FOUND',
        message: 'Task not found',
        details: [{
          '@type': 'type.googleapis.com/google.rpc.ErrorInfo',
          reason: 'TASK_NOT_FOUND',
          metadata: { secret: 'patient-secret-value' },
        }],
      },
    },
    status: 404,
    statusText: 'Not Found',
    headers: {},
    config,
    request: {},
  });

  await assert.rejects(
    sdk.a2a.getTaskV1('agent', 'missing'),
    (error) => {
      assert.ok(error instanceof A2AProtocolError);
      assert.equal(error.a2aErrorCode, 'TASK_NOT_FOUND');
      assert.doesNotMatch(error.message, /patient-secret-value/);
      return true;
    },
  );
});

test('Agentic SDK exports context traces and manages task or message feedback', async () => {
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test',
    auth: { accessToken: 'v1-token' },
  });
  const calls = [];
  sdk.client.http.defaults.adapter = async (config) => {
    const data = typeof config.data === 'string' ? JSON.parse(config.data) : config.data;
    calls.push({ method: config.method, url: config.url, params: config.params, data });
    if (config.url.endsWith('/trace')) {
      return { data: { traces: [], nextPageToken: null, totalSize: null }, status: 200,
        statusText: 'OK', headers: {}, config, request: {} };
    }
    if (config.url.endsWith('/training-authorization') && config.method !== 'delete') {
      return { data: { id: 'ftg-1', feedbackId: 'fb/one', taskId: 'task/one',
        trainingAuthorized: true, authorizationStatus: 'active',
        purposeOfUse: 'quality_improvement', dataScope: 'feedback_metadata_only',
        expiresAt: '2026-08-23T00:00:00Z', createdAt: '2026-08-22T00:00:00Z',
        updatedAt: '2026-08-22T00:00:00Z', revokedAt: null, version: 1 },
      status: 200, statusText: 'OK', headers: {}, config, request: {} };
    }
    if (config.method === 'post') {
      return { data: { id: 'fb-1', taskId: 'task-1', rating: data.rating,
        normalizedScore: 1, labels: data.labels, reason: null,
        createdAt: '2026-08-22T00:00:00Z', target: data.target }, status: 201,
        statusText: 'Created', headers: {}, config, request: {} };
    }
    if (config.method === 'get') {
      return { data: { feedbacks: [] }, status: 200, statusText: 'OK',
        headers: {}, config, request: {} };
    }
    return { data: undefined, status: 204, statusText: 'No Content',
      headers: {}, config, request: {} };
  };

  const trace = await sdk.a2a.exportContextTraces('context/one', { pageSize: 20 });
  const feedback = await sdk.a2a.submitTaskFeedback('context/one', 'task/one', {
    rating: { scale: 'binary', value: 1 }, labels: ['helpful'],
    target: { messageId: 'message-1' },
  });
  await sdk.a2a.listTaskFeedback('context/one', 'task/one');
  await sdk.a2a.deleteTaskFeedback('context/one', 'task/one');
  const training = await sdk.a2a.authorizeFeedbackForTraining(
    'context/one', 'task/one', 'fb/one', {
      purposeOfUse: 'quality_improvement', dataScope: 'feedback_metadata_only',
      expiresAt: '2026-08-23T00:00:00Z', approvalReference: 'qi-review-001',
      acknowledgement: true,
    },
  );
  await sdk.a2a.getFeedbackTrainingAuthorization('context/one', 'task/one', 'fb/one');
  await sdk.a2a.revokeFeedbackTrainingAuthorization('context/one', 'task/one', 'fb/one');

  assert.deepEqual(trace.traces, []);
  assert.equal(feedback.id, 'fb-1');
  assert.equal(calls[0].url, '/api/v2/agentic/contexts/context%2Fone/trace');
  assert.equal(calls[0].params.pageSize, 20);
  assert.match(calls[1].url, /contexts\/context%2Fone\/tasks\/task%2Fone\/feedback$/);
  assert.equal(calls[1].data.target.messageId, 'message-1');
  assert.equal(calls[3].method, 'delete');
  assert.equal(training.trainingAuthorized, true);
  assert.match(
    calls[4].url,
    /tasks\/task%2Fone\/feedback\/fb%2Fone\/training-authorization$/,
  );
  assert.equal(calls[4].method, 'put');
  assert.equal(calls[4].data.dataScope, 'feedback_metadata_only');
  assert.equal(calls[6].method, 'delete');
});

test('Agentic SDK manages first-class v2 Context, Task, and Artifact resources', async () => {
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test',
    auth: { accessToken: 'v1-token' },
  });
  const calls = [];
  sdk.client.http.defaults.adapter = async (config) => {
    calls.push({ method: config.method, url: config.url, params: config.params,
      headers: config.headers });
    const context = {
      id: 'context-1', agentId: 'agent-1', taskCount: 1,
      createdAt: '2026-08-22T00:00:00Z', updatedAt: '2026-08-22T00:00:01Z',
      expiresAt: '2026-08-23T00:00:00Z',
    };
    const task = {
      id: 'task-1', contextId: 'context-1',
      status: { state: 'TASK_STATE_COMPLETED' }, artifacts: [], history: [], metadata: {},
    };
    let data;
    if (config.method === 'delete') data = undefined;
    else if (config.url.endsWith('/artifacts/artifact%2F1')) {
      data = { artifactId: 'artifact/1', parts: [{ text: 'result' }], metadata: {} };
    } else if (config.url.endsWith('/tasks/task%2F1')) data = task;
    else if (config.url.endsWith('/tasks')) {
      data = { tasks: [task], nextPageToken: null, totalSize: 1 };
    } else if (config.url.endsWith('/contexts/context%2F1')) {
      data = { ...context, tasks: [task] };
    } else if (config.url.endsWith('/contexts')) {
      data = { contexts: [context], nextPageToken: 'next', totalSize: 1 };
    } else throw new Error(`unexpected URL ${config.url}`);
    return { data, status: config.method === 'delete' ? 204 : 200,
      statusText: 'OK', headers: {}, config, request: {} };
  };

  const contexts = await sdk.a2a.listContextsV2({
    agentId: 'agent/1', from: '2026-08-01T00:00:00Z', pageSize: 10,
  });
  const context = await sdk.a2a.getContextV2('context/1', { historyLength: 2 });
  const tasks = await sdk.a2a.listContextTasksV2('context/1', {
    pageSize: 5, historyLength: 1,
  });
  const task = await sdk.a2a.getContextTaskV2('context/1', 'task/1');
  const artifact = await sdk.a2a.getTaskArtifactV2('context/1', 'task/1', 'artifact/1');
  await sdk.a2a.deleteContextV2('context/1');

  assert.equal(contexts.totalSize, 1);
  assert.equal(context.taskCount, 1);
  assert.equal(tasks.tasks[0].id, 'task-1');
  assert.equal(task.status.state, 'TASK_STATE_COMPLETED');
  assert.equal(artifact.artifactId, 'artifact/1');
  assert.equal(calls[0].params.agentId, 'agent/1');
  assert.equal(calls[1].params.historyLength, 2);
  assert.equal(calls[2].params.historyLength, 1);
  assert.equal(calls[4].url,
    '/api/v2/agentic/contexts/context%2F1/tasks/task%2F1/artifacts/artifact%2F1');
  assert.equal(calls[5].method, 'delete');
  assert.ok(calls.every((call) => call.headers['A2A-Version'] === '1.0'));
});

test('Agentic SDK reads current per-Agent daily usage contract', async () => {
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test',
    auth: { accessToken: 'v1-token' },
  });
  let captured;
  sdk.client.http.defaults.adapter = async (config) => {
    captured = config;
    return { data: {
      granularity: 'day', from: '2026-08-01T00:00:00Z', to: '2026-08-03T00:00:00Z',
      totals: { invocations: 3, uniqueContexts: 2 },
      buckets: [{ periodStart: '2026-08-01T00:00:00Z', periodEnd: '2026-08-02T00:00:00Z',
        invocations: 3, uniqueContexts: 2 }],
    }, status: 200, statusText: 'OK', headers: {}, config, request: {} };
  };

  const usage = await sdk.a2a.getAgentUsage('agent/one', {
    from: '2026-08-01T00:00:00Z', to: '2026-08-03T00:00:00Z', granularity: 'hour',
  });
  assert.equal(usage.granularity, 'day');
  assert.equal(usage.totals.uniqueContexts, 2);
  assert.equal(captured.url, '/api/v2/agentic/agents/agent%2Fone/usage');
  assert.equal(captured.params.from, '2026-08-01T00:00:00Z');
  assert.equal(captured.params.granularity, 'hour');
});

test('Agentic SDK manages quarantined Artifact objects and one-time downloads', async () => {
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test',
    auth: { accessToken: 'v1-token' },
  });
  const calls = [];
  const object = {
    objectId: 'obj/1', artifactId: 'artifact/1', filename: 'result.json',
    mediaType: 'application/json', sizeBytes: 2, sha256: 'a'.repeat(64),
    status: 'available', malwareScanStatus: 'clean', dlpScanStatus: 'clear',
    dataClassification: 'deidentified', rejectionCode: null,
    scanEngine: 'icoder-safe-file-v1', createdAt: '2026-08-22T00:00:00Z',
    scannedAt: '2026-08-22T00:00:01Z',
  };
  const authorization = {
    objectId: 'obj/1', expiresAt: '2026-08-22T00:01:00Z', singleUse: true,
    purposeOfUse: 'treatment',
    part: { url: 'https://api.cn.icoder.test/api/v2/agentic/artifact-objects/download/grant-123',
      filename: 'result.json', mediaType: 'application/json' },
  };
  sdk.client.http.defaults.adapter = async (config) => {
    calls.push(config);
    let data;
    let status = 200;
    if (config.url.includes('/artifact-objects/download/grant-')) {
      data = new Uint8Array([1, 2]).buffer;
    } else if (config.method === 'post' && config.url.endsWith(':authorize-download')) {
      data = authorization;
    } else if (config.method === 'post') data = object;
    else if (config.method === 'get') data = { objects: [object], totalSize: 1 };
    else { data = undefined; status = 204; }
    return { data, status, statusText: 'OK', headers: {}, config, request: {} };
  };

  const uploaded = await sdk.a2a.uploadTaskArtifactObjectV2(
    'context/1', 'task/1', 'artifact/1',
    { raw: 'e30=', filename: 'result.json', mediaType: 'application/json' },
  );
  const listed = await sdk.a2a.listTaskArtifactObjectsV2(
    'context/1', 'task/1', 'artifact/1');
  const authorized = await sdk.a2a.authorizeTaskArtifactObjectDownloadV2(
    'context/1', 'task/1', 'artifact/1', 'obj/1',
    { purposeOfUse: 'treatment', expiresInSeconds: 30 });
  const bytes = await sdk.a2a.downloadAuthorizedArtifactObjectV2(authorized);
  await sdk.a2a.deleteTaskArtifactObjectV2(
    'context/1', 'task/1', 'artifact/1', 'obj/1');

  assert.equal(uploaded.status, 'available');
  assert.equal(listed.totalSize, 1);
  assert.equal(authorized.singleUse, true);
  assert.equal(bytes.byteLength, 2);
  assert.equal(calls[0].url,
    '/api/v2/agentic/contexts/context%2F1/tasks/task%2F1/artifacts/artifact%2F1/objects');
  assert.match(calls[2].url, /objects\/obj%2F1:authorize-download$/);
  assert.equal(JSON.parse(calls[2].data).purposeOfUse, 'treatment');
  assert.equal(calls[3].responseType, 'arraybuffer');
  assert.equal(calls[3].url.includes('?'), false);
  assert.equal(calls[3].headers.Authorization, 'Bearer v1-token');
  assert.equal(calls[4].method, 'delete');
  assert.equal(calls[0].headers['A2A-Version'], '1.0');
});

test('A2A SDK discovers the authenticated tenant Agent Card', async () => {
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test',
    auth: { accessToken: 'v1-token' },
  });
  let captured;
  sdk.client.http.defaults.adapter = async (config) => {
    captured = config;
    return { data: {
      name: 'Tenant Agent', description: 'Scoped Agent', version: '1.0.0',
      supportedInterfaces: [{ url: 'https://api.cn.icoder.test/a2a',
        protocolBinding: 'JSONRPC', protocolVersion: '1.0' }],
      capabilities: { streaming: true, pushNotifications: false },
      defaultInputModes: ['text/plain'], defaultOutputModes: ['application/json'],
      skills: [{ id: 'run', name: 'Run', description: 'Run Agent', tags: ['a2a'] }],
    }, status: 200, statusText: 'OK', headers: {}, config, request: {} };
  };

  const card = await sdk.a2a.getAgentCard('agent/one');
  assert.equal(card.supportedInterfaces[0].protocolVersion, '1.0');
  assert.equal(
    captured.url,
    '/api/v2/agentic/agents/agent%2Fone/.well-known/agent-card.json',
  );
  assert.equal(captured.headers['A2A-Version'], '1.0');
});
