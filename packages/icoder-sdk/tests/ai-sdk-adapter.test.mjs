import assert from 'node:assert/strict';
import test from 'node:test';

import { Role, TaskState } from '@a2a-js/sdk';
import { ClientFactory } from '@a2a-js/sdk/client';
import { createUIMessageStreamResponse } from 'ai';

import iCoDer from '../dist/index.js';
import {
  convertToParams,
  createA2AClientFactory,
  createFetchImplementation,
  toUIMessageStream,
} from '../dist/ai-sdk-adapter.js';


const ORIGIN = 'https://api.cn.icoder.test';
const AGENT_ROOT = `${ORIGIN}/api/v2/agentic/agents/note-completeness`;
const CARD_URL = `${AGENT_ROOT}/.well-known/agent-card.json`;
const A2A_URL = `${AGENT_ROOT}/a2a`;


function agentCard() {
  return {
    name: '病历完整性 Agent',
    description: 'De-identified official SDK interoperability fixture',
    supportedInterfaces: [{
      url: A2A_URL,
      protocolBinding: 'JSONRPC',
      protocolVersion: '1.0',
    }],
    version: '1.0.0',
    capabilities: {
      streaming: true,
      pushNotifications: false,
      extendedAgentCard: false,
    },
    defaultInputModes: ['text/plain'],
    defaultOutputModes: ['application/json'],
    skills: [{
      id: 'note-completeness',
      name: 'Note completeness',
      description: 'Checks de-identified note completeness',
      tags: ['clinical-documentation'],
      examples: ['去标识病历'],
      inputModes: ['text/plain'],
      outputModes: ['application/json'],
    }],
  };
}


function sdk() {
  return new iCoDer({
    baseURL: ORIGIN,
    auth: { accessToken: 'authoritative-token' },
  });
}


function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}


async function chunks(stream) {
  const result = [];
  for await (const chunk of stream) result.push(chunk);
  return result;
}


function completedMessageWire(contextId = 'context-e2e') {
  return {
    messageId: 'agent-message-1',
    contextId,
    taskId: '',
    role: 'ROLE_AGENT',
    parts: [{ text: '已生成结构化建议', mediaType: 'text/plain' }],
    metadata: { credits: 1 },
    extensions: [],
    referenceTaskIds: [],
  };
}


function sseResponse(requestId) {
  const events = [
    {
      jsonrpc: '2.0', id: requestId,
      result: {
        task: {
          id: 'task-1', contextId: 'context-1',
          status: { state: 'TASK_STATE_SUBMITTED' },
          artifacts: [], history: [], metadata: {},
        },
      },
    },
    {
      jsonrpc: '2.0', id: requestId,
      result: {
        artifactUpdate: {
          taskId: 'task-1', contextId: 'context-1', append: false, lastChunk: true,
          artifact: {
            artifactId: 'artifact-1', name: 'Suggestion', description: '',
            parts: [{ text: '编码建议', mediaType: 'text/plain' }],
            metadata: {}, extensions: [],
          },
          metadata: {},
        },
      },
    },
    {
      jsonrpc: '2.0', id: requestId,
      result: {
        statusUpdate: {
          taskId: 'task-1', contextId: 'context-1',
          status: {
            state: 'TASK_STATE_INPUT_REQUIRED',
            message: {
              messageId: 'prompt-1', contextId: 'context-1', taskId: 'task-1',
              role: 'ROLE_AGENT',
              parts: [{ text: '请确认主要诊断', mediaType: 'text/plain' }],
              metadata: {}, extensions: [], referenceTaskIds: [],
            },
          },
          metadata: { credits: 2 },
        },
      },
    },
  ];
  return new Response(events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join(''), {
    status: 200,
    headers: { 'content-type': 'text/event-stream' },
  });
}


test('convertToParams returns official A2A v1 protobuf types and scopes credentials', () => {
  const credential = {
    mcp_name: 'hospital-fhir',
    token: 'secret-token-that-must-not-enter-metadata',
    type: 'bearer',
  };
  const first = convertToParams([
    { id: 'u1', role: 'user', parts: [{ type: 'text', text: '脱敏病历' }] },
  ], [credential]);
  assert.equal(first.tenant, '');
  assert.equal(first.message.role, Role.ROLE_USER);
  assert.equal(first.message.parts[0].content.$case, 'text');
  assert.equal(first.message.parts[0].content.value, '脱敏病历');
  assert.equal(first.message.parts[1].content.$case, 'data');
  assert.equal(first.message.parts[1].content.value.type, 'token');
  assert.equal(first.message.parts[1].content.value.token, credential.token);
  assert.equal(first.message.metadata, undefined);
  assert.equal(first.metadata, undefined);

  const resumed = convertToParams([
    { id: 'u1', role: 'user', parts: [{ type: 'text', text: '首轮' }] },
    {
      id: 'a1', role: 'assistant', parts: [{ type: 'text', text: '请确认' }],
      metadata: {
        contextId: 'context-1', taskId: 'task-1', state: 'input-required',
      },
    },
    { id: 'u2', role: 'user', parts: [{ type: 'data-json', data: { confirmed: true } }] },
  ], [credential]);
  assert.equal(resumed.message.contextId, 'context-1');
  assert.equal(resumed.message.taskId, 'task-1');
  assert.equal(resumed.message.parts.length, 1, 'credentials are omitted on continuation');
  assert.equal(resumed.message.parts[0].content.$case, 'data');

  const nextTurn = convertToParams([
    {
      id: 'a2', role: 'assistant', parts: [{ type: 'text', text: '完成' }],
      metadata: { contextId: 'context-2', taskId: 'task-old', state: 'completed' },
    },
    { id: 'u3', role: 'user', parts: [{ type: 'text', text: '新问题' }] },
  ], [credential]);
  assert.equal(nextTurn.message.contextId, 'context-2');
  assert.equal(nextTurn.message.taskId, '');
  assert.equal(nextTurn.message.parts[1].content.value.type, 'token');
});


test('convertToParams validates credentials and bounded file conversion', () => {
  assert.throws(
    () => convertToParams([{ id: 'a', role: 'assistant', parts: [{ type: 'text', text: 'x' }] }]),
    /last UI message/,
  );
  assert.throws(
    () => convertToParams(
      [{ id: 'u', role: 'user', parts: [{ type: 'text', text: 'x' }] }],
      [
        { mcp_name: 'same', token: 'one', type: 'bearer' },
        { mcp_name: 'same', token: 'two', type: 'bearer' },
      ],
    ),
    /unique mcp_name/,
  );
  const jsonFile = convertToParams([{
    id: 'u-file', role: 'user', parts: [{
      type: 'file',
      mediaType: 'application/json',
      filename: 'safe.json',
      url: 'data:application/json;base64,eyJvayI6dHJ1ZX0=',
    }],
  }]);
  assert.deepEqual(jsonFile.message.parts[0].content, {
    $case: 'data', value: { ok: true },
  });
  assert.throws(
    () => convertToParams([{
      id: 'u-file', role: 'user', parts: [{
        type: 'file', mediaType: 'text/plain',
        url: 'data:application/json;base64,e30=',
      }],
    }]),
    /must match/,
  );
  assert.throws(
    () => convertToParams([{
      id: 'u-file', role: 'user', parts: [{
        type: 'file', mediaType: 'application/json',
        url: 'data:application/json;base64,e30',
      }],
    }]),
    /canonical padded Base64/,
  );
  assert.throws(
    () => convertToParams([{
      id: 'u-file', role: 'user', parts: [{
        type: 'file', mediaType: 'text/plain',
        url: 'https://user:secret@example.invalid/file',
      }],
    }]),
    /must not contain credentials/,
  );
});


test('createFetchImplementation injects authoritative auth and rejects cross-origin egress', async () => {
  const originalFetch = globalThis.fetch;
  let captured;
  globalThis.fetch = async (input, init) => {
    captured = { url: String(input), init };
    return jsonResponse({});
  };
  try {
    const secureFetch = createFetchImplementation(sdk());
    await secureFetch('/api/v2/agentic/agents/a/agent-card', {
      headers: { Authorization: 'Bearer attacker-token', Cookie: 'session=unsafe' },
    });
    assert.equal(captured.url, `${ORIGIN}/api/v2/agentic/agents/a/agent-card`);
    assert.equal(captured.init.headers.get('Authorization'), 'Bearer authoritative-token');
    assert.equal(captured.init.headers.get('A2A-Version'), '1.0');
    assert.equal(captured.init.headers.get('Cookie'), null);
    assert.equal(captured.init.credentials, 'omit');
    assert.equal(captured.init.redirect, 'error');
    await assert.rejects(
      secureFetch('https://attacker.invalid/steal'),
      /configured SDK origin/,
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});


test('official ClientFactory discovers the iCoDer card and performs ProtoJSON SendMessage', async () => {
  const originalFetch = globalThis.fetch;
  const requests = [];
  globalThis.fetch = async (input, init = {}) => {
    requests.push({ url: String(input), init });
    if (String(input) === CARD_URL && (init.method ?? 'GET') === 'GET') {
      return jsonResponse(agentCard());
    }
    assert.equal(String(input), A2A_URL);
    const body = JSON.parse(init.body);
    return jsonResponse({
      jsonrpc: '2.0',
      id: body.id,
      result: { message: completedMessageWire() },
    });
  };
  try {
    const factory = createA2AClientFactory(sdk(), { preferredTransports: ['JSONRPC'] });
    assert.ok(factory instanceof ClientFactory);
    const client = await factory.createFromUrl(CARD_URL, '');
    const result = await client.sendMessage(convertToParams([
      { id: 'u1', role: 'user', parts: [{ type: 'text', text: '去标识病历' }] },
    ]));
    assert.equal(result.role, Role.ROLE_AGENT);
    assert.equal(result.parts[0].content.$case, 'text');
    assert.equal(result.parts[0].content.value, '已生成结构化建议');

    assert.equal(requests.length, 2);
    for (const request of requests) {
      assert.equal(request.init.headers.get('Authorization'), 'Bearer authoritative-token');
      assert.equal(request.init.headers.get('A2A-Version'), '1.0');
    }
    const wire = JSON.parse(requests[1].init.body);
    assert.equal(wire.method, 'SendMessage');
    assert.equal(wire.params.message.role, 'ROLE_USER');
    assert.deepEqual(wire.params.message.parts[0], {
      text: '去标识病历',
      mediaType: 'text/plain',
    });
    assert.equal('content' in wire.params.message.parts[0], false);
    await assert.rejects(
      factory.createFromUrl('https://attacker.invalid/.well-known/agent-card.json', ''),
      /configured SDK origin/,
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});


test('official client SSE feeds resumable Vercel chunks end to end', async () => {
  const originalFetch = globalThis.fetch;
  let streamingWire;
  globalThis.fetch = async (input, init = {}) => {
    if (String(input) === CARD_URL && (init.method ?? 'GET') === 'GET') {
      return jsonResponse(agentCard());
    }
    streamingWire = JSON.parse(init.body);
    return sseResponse(streamingWire.id);
  };
  try {
    const client = await createA2AClientFactory(sdk()).createFromUrl(CARD_URL, '');
    const params = convertToParams([
      {
        id: 'a1', role: 'assistant', parts: [{ type: 'text', text: 'input' }],
        metadata: { contextId: 'context-1', taskId: 'task-1', state: 'input-required' },
      },
      { id: 'u2', role: 'user', parts: [{ type: 'text', text: 'confirmed' }] },
    ]);
    const callbackEvents = [];
    let finished;
    const output = await chunks(toUIMessageStream(client.sendMessageStream(params), {
      callbacks: {
        onEvent: (event) => callbackEvents.push(event),
        onFinish: (state) => { finished = state; },
      },
    }));

    assert.equal(streamingWire.method, 'SendStreamingMessage');
    assert.equal(streamingWire.params.message.contextId, 'context-1');
    assert.equal(streamingWire.params.message.taskId, 'task-1');
    assert.equal(callbackEvents.length, 3);
    assert.equal(callbackEvents[0].payload.$case, 'task');
    assert.equal(callbackEvents[1].payload.$case, 'artifactUpdate');
    assert.equal(callbackEvents[2].payload.$case, 'statusUpdate');
    assert.equal(finished.state, TaskState.TASK_STATE_INPUT_REQUIRED);
    assert.ok(output.some((chunk) =>
      chunk.type === 'text-delta' && chunk.delta === '编码建议'));
    assert.ok(output.some((chunk) =>
      chunk.type === 'text-delta' && chunk.delta === '请确认主要诊断'));
    const metadata = output.find((chunk) => chunk.type === 'message-metadata');
    assert.equal(metadata.messageMetadata.contextId, 'context-1');
    assert.equal(metadata.messageMetadata.taskId, 'task-1');
    assert.equal(metadata.messageMetadata.state, 'input-required');
    assert.equal(metadata.messageMetadata.credits, 2);
    assert.equal(output.at(-1).type, 'finish');
    assert.equal(output.at(-1).finishReason, 'stop');
  } finally {
    globalThis.fetch = originalFetch;
  }
});


test('toUIMessageStream fails closed without leaking upstream errors', async () => {
  async function* broken() {
    throw new Error('patient-secret-and-provider-token');
  }
  let callbackError;
  const output = await chunks(toUIMessageStream(broken(), {
    callbacks: { onError: (error) => { callbackError = error; } },
  }));
  assert.equal(callbackError.message, 'A2A stream conversion failed');
  assert.equal(output.at(-2).errorText, 'A2A stream conversion failed');
  assert.doesNotMatch(JSON.stringify(output), /patient-secret|provider-token/);
});


test('actual Vercel AI SDK response consumes official StreamResponse objects', async () => {
  async function* events() {
    yield {
      payload: {
        $case: 'message',
        value: {
          messageId: 'agent-message-1',
          contextId: 'context-e2e',
          taskId: '',
          role: Role.ROLE_AGENT,
          parts: [{
            content: { $case: 'text', value: '已生成结构化建议' },
            metadata: undefined,
            filename: '',
            mediaType: 'text/plain',
          }],
          metadata: { credits: 1 },
          extensions: [],
          referenceTaskIds: [],
        },
      },
    };
  }
  const response = createUIMessageStreamResponse({
    stream: toUIMessageStream(events()),
  });
  assert.match(response.headers.get('content-type') ?? '', /^text\/event-stream/);
  assert.equal(response.headers.get('x-vercel-ai-ui-message-stream'), 'v1');
  const body = await response.text();
  assert.match(body, /"type":"text-delta"/);
  assert.match(body, /已生成结构化建议/);
  assert.match(body, /"contextId":"context-e2e"/);
  assert.match(body, /\[DONE\]/);
});
