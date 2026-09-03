import assert from 'node:assert/strict';
import test from 'node:test';

import axios from 'axios';

import { iCoDerAuthenticationError, iCoDerClient } from '../dist/index.js';

function response(config, status, data = {}, headers = {}) {
  return { data, status, statusText: String(status), headers, config, request: {} };
}

function rejectStatus(config, status, headers = {}) {
  const result = response(config, status, { detail: 'redacted upstream failure' }, headers);
  throw new axios.AxiosError('request failed', 'ERR_BAD_RESPONSE', config, {}, result);
}

test('client credentials are acquired automatically and coalesced across concurrent requests', async () => {
  const originalAdapter = axios.defaults.adapter;
  let tokenCalls = 0;
  let apiCalls = 0;
  axios.defaults.adapter = async (config) => {
    if (config.url.endsWith('/api/oauth/token')) {
      tokenCalls += 1;
      await new Promise((resolve) => setTimeout(resolve, 5));
      return response(config, 200, {
        access_token: 'managed-token', token_type: 'Bearer', expires_in: 300,
      });
    }
    apiCalls += 1;
    assert.equal(config.headers.get('Authorization'), 'Bearer managed-token');
    return response(config, 200, { ok: true });
  };
  try {
    const client = new iCoDerClient({
      baseURL: 'https://api.cn.icoder.test',
      auth: { clientId: 'client-id', clientSecret: 'client-secret' },
      retry: false,
    });
    await Promise.all(Array.from({ length: 8 }, () => client.http.get('/api/health')));
    assert.equal(tokenCalls, 1);
    assert.equal(apiCalls, 8);
    assert.equal(client.accessToken, 'managed-token');
  } finally {
    axios.defaults.adapter = originalAdapter;
  }
});

test('concurrent 401 responses cause one client-credential refresh and one retry each', async () => {
  const originalAdapter = axios.defaults.adapter;
  let tokenCalls = 0;
  axios.defaults.adapter = async (config) => {
    if (config.url.endsWith('/api/oauth/token')) {
      tokenCalls += 1;
      await new Promise((resolve) => setTimeout(resolve, 5));
      return response(config, 200, {
        access_token: `managed-token-${tokenCalls}`, token_type: 'Bearer', expires_in: 300,
      });
    }
    if (config.headers.get('Authorization') === 'Bearer managed-token-1') {
      return rejectStatus(config, 401);
    }
    assert.equal(config.headers.get('Authorization'), 'Bearer managed-token-2');
    return response(config, 200, { ok: true });
  };
  try {
    const client = new iCoDerClient({
      baseURL: 'https://api.cn.icoder.test',
      auth: { clientId: 'client-id', clientSecret: 'client-secret' },
      retry: false,
    });
    const results = await Promise.all(
      Array.from({ length: 6 }, () => client.http.get('/api/protected')),
    );
    assert.ok(results.every((item) => item.status === 200));
    assert.equal(tokenCalls, 2);
  } finally {
    axios.defaults.adapter = originalAdapter;
  }
});

test('429 and 5xx retries are bounded and require idempotency for unsafe methods', async () => {
  const originalAdapter = axios.defaults.adapter;
  const calls = new Map();
  axios.defaults.adapter = async (config) => {
    const key = `${config.method}:${config.url}`;
    const count = (calls.get(key) || 0) + 1;
    calls.set(key, count);
    if (config.url === '/safe' && count < 3) return rejectStatus(config, 429, { 'retry-after': '60' });
    if (config.url === '/unsafe') return rejectStatus(config, 503);
    if (config.url === '/idempotent' && count === 1) return rejectStatus(config, 503);
    return response(config, 200, { ok: true });
  };
  try {
    const client = new iCoDerClient({
      baseURL: 'https://api.cn.icoder.test',
      auth: { accessToken: 'fixed-token' },
      retry: { maxRetries: 2, initialDelayMs: 0, maxDelayMs: 0 },
    });
    assert.equal((await client.http.get('/safe')).status, 200);
    await assert.rejects(client.http.post('/unsafe', { value: 1 }));
    assert.equal(calls.get('get:/safe'), 3);
    assert.equal(calls.get('post:/unsafe'), 1);
    assert.equal((await client.http.post(
      '/idempotent',
      { value: 1 },
      { headers: { 'Idempotency-Key': 'request-1' } },
    )).status, 200);
    assert.equal(calls.get('post:/idempotent'), 2);
  } finally {
    axios.defaults.adapter = originalAdapter;
  }
});

test('authentication failures expose sanitized typed errors without client secrets', async () => {
  const originalAdapter = axios.defaults.adapter;
  axios.defaults.adapter = async (config) => rejectStatus(config, 401, { 'x-request-id': 'req-1' });
  try {
    const client = new iCoDerClient({
      baseURL: 'https://api.cn.icoder.test',
      auth: { clientId: 'client-id', clientSecret: 'never-print-this-secret' },
      retry: false,
    });
    await assert.rejects(
      client.http.get('/api/protected'),
      (error) => {
        assert.ok(error instanceof iCoDerAuthenticationError);
        assert.equal(error.status, 401);
        assert.equal(error.requestId, 'req-1');
        assert.ok(!String(error).includes('never-print-this-secret'));
        assert.ok(!JSON.stringify(error).includes('never-print-this-secret'));
        return true;
      },
    );
  } finally {
    axios.defaults.adapter = originalAdapter;
  }
});
