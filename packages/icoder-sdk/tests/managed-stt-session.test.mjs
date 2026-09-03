import assert from 'node:assert/strict';
import test from 'node:test';

import iCoDer, { ManagedSttSessionError } from '../dist/index.js';

function installWebSocket(t, behavior) {
  const original = globalThis.WebSocket;
  const instances = [];
  class FakeWebSocket {
    constructor(url) {
      this.url = url;
      this.readyState = 0;
      this.sent = [];
      instances.push(this);
      queueMicrotask(() => {
        this.readyState = 1;
        this.onopen?.();
      });
    }
    send(data) {
      this.sent.push(data);
      behavior?.onSend?.(this, data, instances.length);
    }
    close(code = 1000) {
      if (this.readyState === 3) return;
      this.readyState = 3;
      queueMicrotask(() => this.onclose?.({ code, wasClean: code === 1000 }));
    }
    serverMessage(value) {
      this.onmessage?.({ data: JSON.stringify(value) });
    }
    serverClose(code = 1006) {
      this.readyState = 3;
      this.onclose?.({ code, wasClean: false });
    }
  }
  globalThis.WebSocket = FakeWebSocket;
  t.after(() => { globalThis.WebSocket = original; });
  return instances;
}

function readyOnStart(socket, data) {
  if (typeof data === 'string' && JSON.parse(data).type === 'start') {
    const start = JSON.parse(data);
    queueMicrotask(() => socket.serverMessage({
      type: 'ready', language: 'zh-CN', maxSessionBytes: 33554432,
      protocol: 'icoder.stt-resume.v1', resumeSupported: true,
      resumeMode: 'client_replay', sessionId: start.sessionId, nextAudioSequence: 1,
    }));
  }
}

function legacyReadyOnStart(socket, data) {
  if (typeof data === 'string' && JSON.parse(data).type === 'start') {
    queueMicrotask(() => socket.serverMessage({
      type: 'ready', language: 'zh-CN', maxSessionBytes: 33554432,
    }));
  }
}

function bytes(value) {
  if (value instanceof Uint8Array) return value;
  throw new TypeError('expected Uint8Array test frame');
}

test('managed STT waits for ready and emits typed transcript messages', async (t) => {
  const instances = installWebSocket(t, { onSend: readyOnStart });
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test', auth: { accessToken: 'tenant/token +' },
  });
  const session = await sdk.speechToText.connectManagedSession({ reconnectAttempts: 0 });
  const messages = [];
  session.on('message', (message) => messages.push(message));
  instances[0].serverMessage({
    type: 'final', text: '患者主诉胸痛', diarization: [{ speaker: 0 }],
  });
  session.sendAudio(new Uint8Array([1, 2, 3]));
  session.requestInterim();
  session.sendEnd();

  assert.equal(session.isReady, true);
  assert.equal(instances[0].url,
    'wss://api.cn.icoder.test/ws/speech-to-text?token=tenant%2Ftoken%20%2B');
  assert.deepEqual(messages, [{
    type: 'final', text: '患者主诉胸痛', diarization: [{ speaker: 0 }],
  }]);
  assert.deepEqual(Array.from(bytes(instances[0].sent[1]).slice(0, 8)), [73, 67, 82, 49, 0, 0, 0, 1]);
  assert.deepEqual(Array.from(bytes(instances[0].sent[1]).slice(8)), [1, 2, 3]);
  assert.deepEqual(JSON.parse(instances[0].sent[2]), { type: 'interim' });
  assert.deepEqual(JSON.parse(instances[0].sent[3]), { type: 'end', lastAudioSequence: 1 });
  session.close();
});

test('managed STT reconnects before audio and refreshes the ready handshake', async (t) => {
  const instances = installWebSocket(t, { onSend: readyOnStart });
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test', auth: { accessToken: 'token' },
  });
  const session = await sdk.speechToText.connectManagedSession({
    reconnectAttempts: 1,
    reconnectInitialDelayMs: 0,
    reconnectMaxDelayMs: 0,
  });
  const reconnecting = [];
  session.on('reconnecting', (event) => reconnecting.push(event));
  instances[0].serverClose();
  await session.waitForReady();

  assert.equal(instances.length, 2);
  assert.deepEqual(reconnecting, [{ attempt: 1, delayMs: 0 }]);
  assert.equal(JSON.parse(instances[1].sent[0]).type, 'start');
  session.close();
});

test('managed STT replays bounded audio after disconnect', async (t) => {
  const instances = installWebSocket(t, { onSend: readyOnStart });
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test', auth: { accessToken: 'token' },
  });
  const session = await sdk.speechToText.connectManagedSession({
    reconnectAttempts: 3,
    reconnectInitialDelayMs: 0,
    reconnectMaxDelayMs: 0,
  });
  session.sendAudio(new Uint8Array([1, 2]));
  const originalFrame = Array.from(bytes(instances[0].sent[1]));
  instances[0].serverClose();
  await session.waitForReady();

  assert.equal(instances.length, 2);
  assert.deepEqual(Array.from(bytes(instances[1].sent[1])), originalFrame);
  session.close();
});

test('managed STT replays end after reconnect', async (t) => {
  const instances = installWebSocket(t, { onSend: readyOnStart });
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test', auth: { accessToken: 'token' },
  });
  const session = await sdk.speechToText.connectManagedSession({
    reconnectAttempts: 1, reconnectInitialDelayMs: 0, reconnectMaxDelayMs: 0,
  });
  session.sendAudio(new Uint8Array([7]));
  session.sendEnd();
  instances[0].serverClose();
  await session.waitForReady();

  assert.equal(instances.length, 2);
  assert.equal(bytes(instances[1].sent[1])[8], 7);
  assert.deepEqual(JSON.parse(instances[1].sent[2]), {
    type: 'end', lastAudioSequence: 1,
  });
  session.close();
});

test('managed STT refuses unsafe post-audio reconnect against a legacy server', async (t) => {
  const instances = installWebSocket(t, { onSend: legacyReadyOnStart });
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test', auth: { accessToken: 'token' },
  });
  const session = await sdk.speechToText.connectManagedSession({
    reconnectAttempts: 3, reconnectInitialDelayMs: 0, reconnectMaxDelayMs: 0,
  });
  const terminal = new Promise((resolve) => session.on('error', resolve));
  session.sendAudio(new Uint8Array([1]));
  instances[0].serverClose();
  const error = await terminal;

  assert.ok(error instanceof ManagedSttSessionError);
  assert.equal(error.code, 'audio_resume_unsupported');
  assert.equal(instances.length, 1);
});

test('managed STT parses acknowledgements and enforces advertised memory bound', async (t) => {
  const instances = installWebSocket(t, {
    onSend(socket, data) {
      if (typeof data !== 'string' || JSON.parse(data).type !== 'start') return;
      const start = JSON.parse(data);
      queueMicrotask(() => socket.serverMessage({
        type: 'ready', language: 'zh-CN', maxSessionBytes: 2,
        protocol: 'icoder.stt-resume.v1', resumeSupported: true,
        resumeMode: 'client_replay', sessionId: start.sessionId, nextAudioSequence: 1,
      }));
    },
  });
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test', auth: { accessToken: 'token' },
  });
  const session = await sdk.speechToText.connectManagedSession({ reconnectAttempts: 0 });
  const messages = [];
  session.on('message', (message) => messages.push(message));
  session.sendAudio(new Uint8Array([1, 2]));
  const start = JSON.parse(instances[0].sent[0]);
  instances[0].serverMessage({
    type: 'audio_ack', sequence: 1, nextAudioSequence: 2,
    totalBytes: 2, duplicate: false, sessionId: start.sessionId,
  });

  assert.equal(messages.at(-1).type, 'audio_ack');
  assert.throws(() => session.sendAudio(new Uint8Array([3])), /2-byte session limit/);
  session.close();
});

test('managed STT terminates on an invalid acknowledgement', async (t) => {
  const instances = installWebSocket(t, { onSend: readyOnStart });
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test', auth: { accessToken: 'token' },
  });
  const session = await sdk.speechToText.connectManagedSession({ reconnectAttempts: 1 });
  const terminal = new Promise((resolve) => session.on('error', resolve));
  session.sendAudio(new Uint8Array([1]));
  instances[0].serverMessage({
    type: 'audio_ack', sequence: 1, nextAudioSequence: 2,
    totalBytes: 1, duplicate: false, sessionId: 'stt_wrong_session_identifier_0000',
  });

  const error = await terminal;
  await new Promise((resolve) => queueMicrotask(resolve));
  assert.equal(error.code, 'invalid_audio_ack');
  assert.equal(session.isReady, false);
  assert.equal(instances[0].readyState, 3);
});

test('managed STT waitForReady rejects when reconnect budget is exhausted', async (t) => {
  const instances = installWebSocket(t, {
    onSend(socket, data, index) {
      if (typeof data !== 'string' || JSON.parse(data).type !== 'start') return;
      if (index === 1) queueMicrotask(() => socket.serverMessage({ type: 'ready' }));
      else queueMicrotask(() => socket.serverClose());
    },
  });
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test', auth: { accessToken: 'token' },
  });
  const session = await sdk.speechToText.connectManagedSession({
    reconnectAttempts: 1,
    reconnectInitialDelayMs: 0,
    reconnectMaxDelayMs: 0,
  });
  instances[0].serverClose();

  await assert.rejects(
    session.waitForReady(),
    (error) => error instanceof ManagedSttSessionError
      && error.code === 'reconnect_exhausted',
  );
  assert.equal(session.isReady, false);
  assert.equal(instances.length, 2);
});

test('managed STT configuration errors are typed and discard server free text', async (t) => {
  installWebSocket(t, {
    onSend(socket, data) {
      if (typeof data === 'string' && JSON.parse(data).type === 'start') {
        queueMicrotask(() => socket.serverMessage({
          type: 'error',
          code: 'unsupported_language',
          message: 'patient secret from upstream',
        }));
      }
    },
  });
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test', auth: { accessToken: 'token' },
  });
  await assert.rejects(
    sdk.speechToText.connectManagedSession({ reconnectAttempts: 0 }),
    (error) => {
      assert.ok(error instanceof ManagedSttSessionError);
      assert.equal(error.code, 'unsupported_language');
      assert.doesNotMatch(String(error), /patient secret/);
      assert.equal(Object.hasOwn(error, 'url'), false);
      return true;
    },
  );
});
