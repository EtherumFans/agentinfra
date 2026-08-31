import assert from 'node:assert/strict';
import test from 'node:test';

import iCoDer, { RunEventRetentionError } from '../dist/index.js';


test('RunTraceResource preserves the safe run audit summary contract', async () => {
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test',
    auth: { accessToken: 'test-token' },
  });
  sdk.client.http.defaults.adapter = async (config) => ({
    data: {
      run_id: 'run/id',
      timeline: [],
      step_count: 0,
      summary: {
        agent_id: 'diagnosis-extractor',
        trace_id: 'trace-1',
        run_status: 'COMPLETED',
        runtime_mode: 'provider_registry',
        latency_ms: 12,
        cost: { amount: 0.01, currency: 'CNY' },
        error: false,
        trace_capture_status: 'PERSISTED',
        review_signal: {
          state: 'required',
          sources: ['completion.provider_status:requires_review'],
          authoritative: false,
        },
      },
    },
    status: 200,
    statusText: 'OK',
    headers: {},
    config,
    request: {},
  });

  const response = await sdk.runTrace.timeline('run/id');

  assert.equal(response.data.summary.cost.currency, 'CNY');
  assert.equal(response.data.summary.review_signal.authoritative, false);
  assert.equal(response.config.url, '/api/runtime/runs/run%2Fid/trace');
});


test('RunsResource sends versioned documents and upstream Agent results', async () => {
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test',
    auth: { accessToken: 'test-token' },
  });
  let body;
  sdk.client.http.defaults.adapter = async (config) => {
    body = typeof config.data === 'string' ? JSON.parse(config.data) : config.data;
    return {
      data: { agent_id: 'principal-diagnosis-review', run_id: 'run-1' },
      status: 200,
      statusText: 'OK',
      headers: {},
      config,
      request: {},
    };
  };

  await sdk.runs.runText('principal-diagnosis-review', 'primary', {
    purpose_of_use: 'treatment',
    documents: [{
      document_id: 'admission',
      document_version: 'v2',
      normalization: 'NFKC',
      text: 'ＡＢ',
    }],
    upstream_results: [{
      agent_id: 'diagnosis-extractor',
      run_id: 'upstream-run',
      schema_ref: 'icoder/DiagnosisExtractionOutput/v6',
      attestation: 'signed-upstream-result',
      result: { diagnoses: [{ icd10_cn_code: 'I21.0' }] },
    }],
  });

  assert.equal(body.input.documents[0].document_version, 'v2');
  assert.equal(body.input.upstream_results[0].agent_id, 'diagnosis-extractor');
  assert.equal(body.purpose_of_use, 'treatment');
});


test('RunsResource exposes status and honest cancellation contracts', async () => {
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
    const isCancel = config.url?.endsWith('/cancel');
    return {
      data: isCancel
        ? {
            run_id: 'run/id',
            outcome: 'RECORDED_ONLY',
            status: 'RUNNING',
            message: 'request recorded',
          }
        : {
            run_id: 'run/id',
            status: 'RUNNING',
            terminal: false,
            agent_id: 'note-completeness-agent',
            trace_id: 'trace-1',
            runtime_mode: 'default',
            latency_ms: 12,
            cost_amount: 0.01,
            cost_currency: 'CNY',
            error: false,
          },
      status: isCancel ? 202 : 200,
      statusText: isCancel ? 'Accepted' : 'OK',
      headers: {},
      config,
      request: {},
    };
  };

  const status = await sdk.runs.get('run/id');
  const cancellation = await sdk.runs.cancel('run/id', 'operator request');

  assert.equal(status.data.terminal, false);
  assert.equal(cancellation.status, 202);
  assert.equal(cancellation.data.outcome, 'RECORDED_ONLY');
  assert.deepEqual(calls, [
    { method: 'GET', url: '/api/v1/runs/run%2Fid', data: undefined },
    {
      method: 'POST',
      url: '/api/v1/runs/run%2Fid/cancel',
      data: { reason: 'operator request' },
    },
  ]);
});


test('RunsResource opens signed lifecycle SSE on the configured origin', async () => {
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test/',
    auth: { accessToken: 'bearer-must-not-enter-query' },
  });
  const originalFetch = globalThis.fetch;
  let captured;
  globalThis.fetch = async (url, init) => {
    captured = { url: String(url), init };
    return new Response(
      'data: {"name":"run.ingest"}\n\n' +
      ': keepalive\n\n' +
      'data: {"name":"run.completion"}\n\n' +
      'data: {"name":"stream.completed"}\n\n', {
      status: 200,
      headers: { 'content-type': 'text/event-stream; charset=utf-8' },
      },
    );
  };
  try {
    const stream = await sdk.runs.streamEvents(
      'run/id', 'signed token+value', undefined, 'event-previous',
    );
    const { value } = await stream.getReader().read();
    const body = new TextDecoder().decode(value);
    assert.match(body, /: keepalive/);
    assert.match(body, /run\.completion/);
    assert.match(body, /stream\.completed/);
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(
    captured.url,
    'https://api.cn.icoder.test/api/v1/runs/run%2Fid/events?token=signed+token%2Bvalue',
  );
  assert.equal(captured.init.method, 'GET');
  assert.equal(captured.init.headers.Accept, 'text/event-stream');
  assert.equal(captured.init.headers['Last-Event-ID'], 'event-previous');
  assert.ok(!captured.url.includes('bearer-must-not-enter-query'));
  await assert.rejects(() => sdk.runs.streamEvents('run-1', ''), /traceToken is required/);
  await assert.rejects(
    () => sdk.runs.streamEvents('run-1', 'token', undefined, 'x'.repeat(129)),
    /lastEventId is malformed/,
  );
});


test('RunsResource resilient stream reconnects from the last acknowledged event ID', async () => {
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test',
    auth: { accessToken: 'test-token' },
  });
  const originalFetch = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url: String(url), lastEventId: init.headers['Last-Event-ID'] });
    if (calls.length === 1) {
      return new Response(
        'id: event-1\nevent: run.ingest\ndata: {"name":"run.ingest"}\n\n',
        { status: 200, headers: { 'content-type': 'text/event-stream' } },
      );
    }
    return new Response(
      'id: event-2\nevent: run.completion\ndata: {"name":"run.completion"}\n\n' +
      'event: stream.completed\ndata: {"name":"stream.completed"}\n\n',
      { status: 200, headers: { 'content-type': 'text/event-stream' } },
    );
  };
  try {
    const events = [];
    for await (const event of sdk.runs.streamEventsResilient('run-1', 'token-1', {
      maxAttempts: 3,
      initialDelayMs: 0,
      maxDelayMs: 0,
      jitterRatio: 0,
    })) {
      events.push(event);
    }
    assert.deepEqual(events.map((event) => event.event), [
      'run.ingest', 'run.completion', 'stream.completed',
    ]);
    assert.equal(calls.length, 2);
    assert.equal(calls[0].lastEventId, undefined);
    assert.equal(calls[1].lastEventId, 'event-1');
  } finally {
    globalThis.fetch = originalFetch;
  }
});


test('RunsResource resilient stream renews only a signed-token 401', async () => {
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test',
    auth: { accessToken: 'bearer-token' },
  });
  const originalFetch = globalThis.fetch;
  const streamUrls = [];
  let renewCalls = 0;
  sdk.client.http.defaults.adapter = async (config) => {
    renewCalls += 1;
    assert.equal(config.url, '/api/v1/runs/run-1/trace-token');
    return {
      data: {
        run_id: 'run-1', trace_token: 'renewed-token', expires_at: 9999999999,
        events_url: '/api/v1/runs/run-1/events', trace_url: '/api/v1/runs/run-1/trace',
      },
      status: 200, statusText: 'OK', headers: {}, config, request: {},
    };
  };
  globalThis.fetch = async (url) => {
    streamUrls.push(String(url));
    if (streamUrls.length === 1) {
      return new Response('', { status: 401 });
    }
    return new Response(
      'event: stream.completed\ndata: {"name":"stream.completed"}\n\n',
      { status: 200, headers: { 'content-type': 'text/event-stream' } },
    );
  };
  try {
    const events = [];
    for await (const event of sdk.runs.streamEventsResilient('run-1', 'expired-token', {
      maxAttempts: 2, initialDelayMs: 0, maxDelayMs: 0, jitterRatio: 0,
    })) events.push(event);
    assert.equal(renewCalls, 1);
    assert.match(streamUrls[0], /token=expired-token/);
    assert.match(streamUrls[1], /token=renewed-token/);
    assert.equal(events.at(-1).event, 'stream.completed');
  } finally {
    globalThis.fetch = originalFetch;
  }
});


test('RunsResource resilient stream does not retry cursor and authorization failures', async () => {
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test',
    auth: { accessToken: 'test-token' },
  });
  const originalFetch = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    return new Response('', { status: 409 });
  };
  try {
    await assert.rejects(async () => {
      for await (const _ of sdk.runs.streamEventsResilient('run-1', 'token', {
        maxAttempts: 4, initialDelayMs: 0, maxDelayMs: 0,
      })) { /* consume */ }
    }, /HTTP 409/);
    assert.equal(calls, 1);
  } finally {
    globalThis.fetch = originalFetch;
  }
});


test('RunsResource exposes sanitized retention expiry without retrying', async () => {
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test',
    auth: { accessToken: 'test-token' },
  });
  const originalFetch = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    return new Response(JSON.stringify({
      detail: {
        code: 'SSE_CURSOR_EXPIRED',
        retention_days: 90,
        message: 'must not be retained by the SDK',
        raw_clinical_text: 'must not escape',
      },
    }), { status: 410, headers: { 'content-type': 'application/json' } });
  };
  try {
    await assert.rejects(async () => {
      for await (const _ of sdk.runs.streamEventsResilient('run-1', 'token', {
        maxAttempts: 4, initialDelayMs: 0, maxDelayMs: 0,
      })) { /* consume */ }
    }, (error) => {
      assert.ok(error instanceof RunEventRetentionError);
      assert.equal(error.httpStatus, 410);
      assert.equal(error.errorCode, 'SSE_CURSOR_EXPIRED');
      assert.equal(error.retentionDays, 90);
      assert.ok(!String(error).includes('raw_clinical_text'));
      return true;
    });
    assert.equal(calls, 1);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
