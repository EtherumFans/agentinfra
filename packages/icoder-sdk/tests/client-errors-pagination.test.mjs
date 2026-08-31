import assert from 'node:assert/strict';
import test from 'node:test';

import axios from 'axios';

import iCoDer, {
  A2AProtocolError,
  AsyncCursorPager,
  BadGatewayError,
  BadRequestError,
  ConflictError,
  ForbiddenError,
  GatewayTimeoutError,
  InternalServerError,
  NotFoundError,
  UnauthorizedError,
  UnprocessableEntityError,
} from '../dist/index.js';

function ok(config, data) {
  return { data, status: 200, statusText: 'OK', headers: {}, config, request: {} };
}

function reject(config, status, data = {}, headers = {}) {
  const response = { data, status, statusText: String(status), headers, config, request: {} };
  throw new axios.AxiosError('unsafe upstream message', 'ERR_BAD_RESPONSE', config, {}, response);
}

test('HTTP status families map to typed PHI-safe API errors', async () => {
  const expected = new Map([
    [400, BadRequestError], [401, UnauthorizedError], [403, ForbiddenError],
    [404, NotFoundError], [409, ConflictError], [422, UnprocessableEntityError],
    [500, InternalServerError], [502, BadGatewayError], [504, GatewayTimeoutError],
  ]);
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test',
    auth: { accessToken: 'fixed-token' },
    retry: false,
  });
  sdk.client.http.defaults.adapter = async (config) => reject(
    config,
    Number(config.url.slice(1)),
    {
      detail: [{
        loc: ['body', 'clinical_text'],
        type: 'value_error',
        msg: 'patient Zhang San secret diagnosis',
        input: 'patient Zhang San secret diagnosis',
      }],
      secret: 'patient Zhang San secret diagnosis',
    },
    { 'x-request-id': 'req-safe-1' },
  );

  for (const [status, ErrorType] of expected) {
    await assert.rejects(sdk.client.http.get(`/${status}`), (error) => {
      assert.ok(error instanceof ErrorType);
      assert.equal(error.statusCode, status);
      assert.equal(error.requestId, 'req-safe-1');
      assert.deepEqual(error.details, [{
        location: ['body', 'clinical_text'], type: 'value_error',
      }]);
      assert.doesNotMatch(JSON.stringify(error), /Zhang San|secret diagnosis/);
      assert.equal(Object.hasOwn(error, 'request'), false);
      return true;
    });
  }
});

test('HTTP 408 participates in the same bounded retry policy', async () => {
  let calls = 0;
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test',
    auth: { accessToken: 'fixed-token' },
    retry: { maxRetries: 1, initialDelayMs: 0, maxDelayMs: 0 },
  });
  sdk.client.http.defaults.adapter = async (config) => {
    calls += 1;
    if (calls === 1) return reject(config, 408);
    return ok(config, { ok: true });
  };
  assert.equal((await sdk.client.http.get('/timeout')).status, 200);
  assert.equal(calls, 2);
});

test('Agentic cursor resources expose lazy for-await pagination', async () => {
  const tokens = [];
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test',
    auth: { accessToken: 'fixed-token' },
    retry: false,
  });
  sdk.client.http.defaults.adapter = async (config) => {
    const token = config.params?.pageToken;
    tokens.push(token ?? null);
    return ok(config, token
      ? { contexts: [{ id: 'context-2' }], nextPageToken: null, totalSize: 2 }
      : { contexts: [{ id: 'context-1' }], nextPageToken: 'cursor-2', totalSize: 2 });
  };

  const pager = sdk.a2a.iterateContextsV2({ pageSize: 1 });
  assert.deepEqual(tokens, []);
  const ids = [];
  for await (const context of pager) ids.push(context.id);
  assert.deepEqual(ids, ['context-1', 'context-2']);
  assert.deepEqual(tokens, [null, 'cursor-2']);
});

test('cursor pagination fails closed on repeated tokens and page ceilings', async () => {
  const repeated = new AsyncCursorPager(
    async () => ({ items: [1], next: 'same' }),
    { items: (page) => page.items, nextPageToken: (page) => page.next },
    { initialPageToken: 'same' },
  );
  await assert.rejects(async () => {
    for await (const _item of repeated) { /* consume */ }
  }, /repeated page token/);

  const unbounded = new AsyncCursorPager(
    async (token) => ({ items: [1], next: `${token ?? 'root'}-next` }),
    { items: (page) => page.items, nextPageToken: (page) => page.next },
    { maxPages: 2 },
  );
  await assert.rejects(async () => {
    for await (const _item of unbounded) { /* consume */ }
  }, /exceeded maxPages=2/);
});

test('typed transport errors retain only stable A2A protocol reason', async () => {
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test',
    auth: { accessToken: 'fixed-token' },
    retry: false,
  });
  sdk.client.http.defaults.adapter = async (config) => reject(config, 404, {
    error: {
      code: 404,
      message: 'patient secret text',
      details: [{ reason: 'TASK_NOT_FOUND', metadata: { patient: 'secret' } }],
    },
  });
  await assert.rejects(sdk.a2a.getTaskV1('agent', 'missing'), (error) => {
    assert.ok(error instanceof A2AProtocolError);
    assert.equal(error.a2aErrorCode, 'TASK_NOT_FOUND');
    assert.doesNotMatch(JSON.stringify(error), /patient secret|metadata/);
    return true;
  });
});
