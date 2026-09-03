import assert from 'node:assert/strict';
import test from 'node:test';

import axios from 'axios';

import iCoDer, { AsyncPageNumberPager } from '../dist/index.js';

function ok(config, data) {
  return { data, status: 200, statusText: 'OK', headers: {}, config, request: {} };
}

function reject(config, status) {
  const response = { data: {}, status, statusText: String(status), headers: {}, config, request: {} };
  throw new axios.AxiosError('upstream detail must not escape', 'ERR_BAD_RESPONSE', config, {}, response);
}

test('low-level requests apply bounded Corti-style per-request options', async () => {
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test',
    auth: { accessToken: 'fixed-token' },
    retry: false,
  });
  let observed;
  sdk.client.http.defaults.adapter = async (config) => {
    observed = config;
    return ok(config, { ok: true });
  };

  const result = await sdk.client.get('/api/safe-resource', {
    timeoutInSeconds: 1.25,
    maxRetries: 0,
    headers: { 'X-Trace-Mode': 'safe' },
    queryParams: { include: 'metadata' },
  });

  assert.deepEqual(result, { ok: true });
  assert.equal(observed.timeout, 1250);
  assert.equal(observed._icoderMaxRetries, 0);
  assert.equal(observed.headers.get('X-Trace-Mode'), 'safe');
  assert.deepEqual(observed.params, { include: 'metadata' });
  assert.equal(observed.headers.get('Authorization'), 'Bearer fixed-token');
});

test('per-request retry override works and abort interrupts retry backoff', async () => {
  let calls = 0;
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test',
    auth: { accessToken: 'fixed-token' },
    retry: { maxRetries: 0, initialDelayMs: 0, maxDelayMs: 0 },
  });
  sdk.client.http.defaults.adapter = async (config) => {
    calls += 1;
    if (calls === 1) return reject(config, 503);
    return ok(config, { retried: true });
  };
  assert.deepEqual(
    await sdk.client.get('/api/retry', { maxRetries: 1 }),
    { retried: true },
  );
  assert.equal(calls, 2);

  const aborting = new iCoDer({
    baseURL: 'https://api.cn.icoder.test',
    auth: { accessToken: 'fixed-token' },
    retry: { maxRetries: 0, initialDelayMs: 5000, maxDelayMs: 5000 },
  });
  aborting.client.http.defaults.adapter = async (config) => reject(config, 503);
  const controller = new AbortController();
  const pending = aborting.client.get('/api/abort-backoff', {
    maxRetries: 1,
    abortSignal: controller.signal,
  });
  setTimeout(() => controller.abort(), 5);
  await assert.rejects(pending, (error) => error?.name === 'AbortError');
});

test('request options reject origin escapes, protected fields, and query collisions', async () => {
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test',
    auth: { accessToken: 'fixed-token' },
    retry: false,
  });
  await assert.rejects(
    sdk.client.get('https://evil.example/api'),
    /configured origin/,
  );
  await assert.rejects(
    sdk.client.get('/api/safe?override=true'),
    /configured origin/,
  );
  await assert.rejects(
    sdk.client.get('/api/safe', { headers: { Authorization: 'Bearer attacker' } }),
    /controlled by the SDK/,
  );
  await assert.rejects(
    sdk.billing.transactions(1, 20, { queryParams: { page: '99' } }),
    /conflicts with a resource parameter/,
  );
  assert.equal('reviews' in sdk, false);
});

test('page-number pagination is lazy, bounded, and backed by authoritative totals', async () => {
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test',
    auth: { accessToken: 'fixed-token' },
    retry: false,
  });
  const pages = [];
  sdk.client.http.defaults.adapter = async (config) => {
    const page = config.params.page;
    pages.push(page);
    return ok(config, {
      transactions: [{ id: `txn-${page}` }],
      total: 2,
      page,
      page_size: 1,
    });
  };
  const pager = sdk.billing.iterateTransactions(
    1,
    { queryParams: { include: 'source' } },
  );
  assert.deepEqual(pages, []);
  const ids = [];
  for await (const item of pager) ids.push(item.id);
  assert.deepEqual(ids, ['txn-1', 'txn-2']);
  assert.deepEqual(pages, [1, 2]);

  const invalidTotal = new AsyncPageNumberPager(
    async () => ({ items: [1], total: -1 }),
    { items: (page) => page.items, totalItems: (page) => page.total },
  );
  await assert.rejects(async () => {
    for await (const _item of invalidTotal) { /* consume */ }
  }, /invalid total/);

  const endless = new AsyncPageNumberPager(
    async () => ({ items: [1], total: 999 }),
    { items: (page) => page.items, totalItems: (page) => page.total },
    { maxPages: 2 },
  );
  await assert.rejects(async () => {
    for await (const _item of endless) { /* consume */ }
  }, /exceeded maxPages=2/);
});

test('public Expert SDK surface maps only to real read-only v1 routes', async () => {
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test',
    auth: { accessToken: 'fixed-token' },
    retry: false,
  });
  const paths = [];
  sdk.client.http.defaults.adapter = async (config) => {
    paths.push(config.url);
    if (config.url.endsWith('/mcp_servers')) return ok(config, []);
    if (config.url.endsWith('/registry/reconcile')) return ok(config, { summary: {} });
    if (config.url.endsWith('/readiness')) return ok(config, { production_ready: false });
    if (config.url === '/api/v1/experts') return ok(config, { experts: [], total: 0 });
    return ok(config, { id: 'expert-1', name: 'Expert' });
  };

  await sdk.experts.list('coding', 'validator');
  await sdk.experts.get('expert/1');
  await sdk.experts.mcpServers('expert/1', 'oauth2.0');
  await sdk.experts.reconcileRegistry();
  await sdk.experts.readiness();

  assert.deepEqual(paths, [
    '/api/v1/experts',
    '/api/v1/experts/expert%2F1',
    '/api/v1/experts/expert%2F1/mcp_servers',
    '/api/v1/experts/registry/reconcile',
    '/api/v1/experts/readiness',
  ]);
  assert.equal('call' in sdk.experts, false);
  assert.equal('create' in sdk.experts, false);
  assert.equal('delete' in sdk.experts, false);
  assert.equal('punctuate' in sdk.speechToText, false);
  assert.equal('marketplace' in sdk, false);
});

test('A2A controls remain bounded across REST, SSE, and signed artifact downloads', async () => {
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test',
    auth: { accessToken: 'fixed-token' },
    retry: false,
  });
  let restConfig;
  sdk.client.http.defaults.adapter = async (config) => {
    restConfig = config;
    return ok(config, { id: 'task-1', status: { state: 'TASK_STATE_COMPLETED' } });
  };
  await sdk.a2a.getTaskV1('agent/1', 'task/1', {
    timeoutInSeconds: 2,
    headers: { 'X-Trace-Mode': 'safe' },
    queryParams: { projection: 'summary' },
  });
  assert.equal(restConfig.timeout, 2000);
  assert.equal(restConfig.headers.get('A2A-Version'), '1.0');
  assert.equal(restConfig.headers.get('X-Trace-Mode'), 'safe');
  assert.deepEqual(restConfig.params, { projection: 'summary' });

  await assert.rejects(
    sdk.a2a.messageStreamV1('agent-1', 'hello', {}, { maxRetries: 1 }),
    /require maxRetries to be 0/,
  );
  await assert.rejects(
    sdk.a2a.downloadAuthorizedArtifactObjectV2({
      objectId: 'obj-1', expiresAt: '', singleUse: true, purposeOfUse: 'treatment',
      part: { url: 'https://evil.example/api/v2/agentic/artifact-objects/download/grant' },
    }),
    /configured iCoDer origin/,
  );

  const originalFetch = globalThis.fetch;
  let streamRequest;
  globalThis.fetch = async (url, init) => {
    streamRequest = { url, init };
    return new Response(new Uint8Array(), {
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
    });
  };
  try {
    await sdk.a2a.subscribeTaskV1(
      'agent-1',
      'task-1',
      { afterSequence: 3 },
      { maxRetries: 0, headers: { 'X-Trace-Mode': 'safe' }, queryParams: { view: 'safe' } },
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
  assert.match(streamRequest.url, /afterSequence=3/);
  assert.match(streamRequest.url, /view=safe/);
  assert.equal(streamRequest.init.headers['A2A-Version'], '1.0');
  assert.equal(streamRequest.init.headers['X-Trace-Mode'], 'safe');
  assert.equal(streamRequest.init.headers.Authorization, 'Bearer fixed-token');

  streamRequest = undefined;
  globalThis.fetch = async (url, init) => {
    streamRequest = { url, init };
    return new Response(new Uint8Array(), {
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
    });
  };
  try {
    await sdk.runs.streamEvents(
      'run-1',
      'signed-token',
      undefined,
      undefined,
      { maxRetries: 0, headers: { 'X-Trace-Mode': 'safe' }, queryParams: { view: 'safe' } },
    );
    await assert.rejects(
      sdk.runs.streamEvents(
        'run-1', 'signed-token', undefined, undefined,
        { queryParams: { token: 'attacker' } },
      ),
      /conflicts with a resource parameter/,
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
  assert.match(streamRequest.url, /token=signed-token/);
  assert.match(streamRequest.url, /view=safe/);
  assert.equal(streamRequest.init.headers.Accept, 'text/event-stream');
  assert.equal(streamRequest.init.headers['X-Trace-Mode'], 'safe');
});
