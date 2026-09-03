import assert from 'node:assert/strict';
import test from 'node:test';

import iCoDer, { ManagedStreamsSessionError } from '../dist/index.js';

const INTERACTION_ID = '11111111-1111-4111-8111-111111111111';
const SESSION_ID = '22222222-2222-4222-8222-222222222222';

function configuration(overrides = {}) {
  return {
    transcription: {
      primaryLanguage: 'zh-CN', diarize: false, isMultichannel: false,
      participants: [{ channel: 0, role: 'multiple' }],
    },
    mode: { type: 'facts', outputLocale: 'zh-CN' },
    retentionPolicy: 'none',
    ...overrides,
  };
}

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
      behavior?.onSend?.(this, data);
    }
    close(code = 1000) {
      if (this.readyState === 3) return;
      this.readyState = 3;
      queueMicrotask(() => this.onclose?.({ code, wasClean: code === 1000 }));
    }
    serverMessage(value) { this.onmessage?.({ data: JSON.stringify(value) }); }
    serverClose(code = 1006) {
      this.readyState = 3;
      this.onclose?.({ code, wasClean: false });
    }
  }
  globalThis.WebSocket = FakeWebSocket;
  t.after(() => { globalThis.WebSocket = original; });
  return instances;
}

function acceptConfiguration(socket, data) {
  if (typeof data !== 'string') return;
  const message = JSON.parse(data);
  if (message.type === 'config') {
    queueMicrotask(() => socket.serverMessage({
      type: 'CONFIG_ACCEPTED', sessionId: SESSION_ID,
      configuration: message.configuration,
    }));
  }
}

function sdk() {
  return new iCoDer({
    baseURL: 'https://api.cn.icoder.test',
    auth: { accessToken: 'tenant/token +' },
  });
}

test('Streams connects with tenant, environment, token and waits for resolved config', async (t) => {
  const instances = installWebSocket(t, { onSend: acceptConfiguration });
  const session = await sdk().streams.connect({
    interactionId: INTERACTION_ID,
    tenantName: 'hospital cn',
    environment: 'cn',
    configuration: configuration(),
  });

  assert.equal(session.isReady, true);
  const url = new URL(instances[0].url);
  assert.equal(url.protocol, 'wss:');
  assert.equal(url.pathname, `/api/v2/tools/streams/${INTERACTION_ID}`);
  assert.equal(url.searchParams.get('tenant-name'), 'hospital cn');
  assert.equal(url.searchParams.get('environment'), 'cn');
  assert.equal(url.searchParams.get('token'), 'tenant/token +');
  assert.deepEqual(JSON.parse(instances[0].sent[0]), {
    type: 'config', configuration: configuration(),
  });
  session.close();
});

test('Streams emits typed transcript, facts, usage and resolves only on ENDED', async (t) => {
  const instances = installWebSocket(t, { onSend: acceptConfiguration });
  const session = await sdk().streams.connect({
    interactionId: INTERACTION_ID,
    tenantName: 'hospital',
    configuration: configuration(),
  });
  const messages = [];
  session.on('message', (message) => messages.push(message));
  session.sendAudio(new Uint8Array([1, 2, 3]));
  session.flush();
  session.end();
  const ended = session.waitForEnded();
  instances[0].serverMessage({ type: 'transcript', data: [{ transcript: '患者胸痛' }] });
  instances[0].serverMessage({ type: 'facts', fact: [{ text: '胸痛' }] });
  instances[0].serverMessage({ type: 'flushed' });
  instances[0].serverMessage({ type: 'delta_usage', credits: 0 });
  instances[0].serverMessage({ type: 'usage', credits: 0 });
  instances[0].serverMessage({ type: 'ENDED' });
  await ended;

  assert.equal(session.isEnded, true);
  assert.deepEqual(messages.map((message) => message.type), [
    'transcript', 'facts', 'flushed', 'delta_usage', 'usage', 'ENDED',
  ]);
  assert.deepEqual(instances[0].sent.slice(1), [
    new Uint8Array([1, 2, 3]),
    JSON.stringify({ type: 'flush' }),
    JSON.stringify({ type: 'end' }),
  ]);
});

test('Streams accepts recommended PCM audio health and validates typed events', async (t) => {
  const instances = installWebSocket(t, { onSend: acceptConfiguration });
  const session = await sdk().streams.connect({
    interactionId: INTERACTION_ID,
    tenantName: 'hospital',
    configuration: configuration({
      audioFormat: 'audio/pcm; rate=16000; channels=1; bits=16',
      audioEvents: { enabled: true },
    }),
  });
  const messages = [];
  session.on('message', (message) => messages.push(message));
  instances[0].serverMessage({
    type: 'audioEvent',
    data: { event: 'longSilenceDetected', channel: 0, startTimeMs: 0 },
  });
  instances[0].serverMessage({
    type: 'audioEvent',
    data: { event: 'privateUnexpectedEvent', channel: 0, startTimeMs: 0, text: 'patient secret' },
  });

  assert.deepEqual(messages, [
    {
      type: 'audioEvent',
      data: { event: 'longSilenceDetected', channel: 0, startTimeMs: 0 },
    },
    { type: 'unknown' },
  ]);
  session.close();
});

test('Streams bounds each audio chunk and the aggregate session', async (t) => {
  const instances = installWebSocket(t, { onSend: acceptConfiguration });
  const session = await sdk().streams.connect({
    interactionId: INTERACTION_ID,
    tenantName: 'hospital',
    configuration: configuration(),
  });
  assert.throws(() => session.sendAudio(new Uint8Array(64_001)), /64000/);
  const chunk = new Uint8Array(64_000);
  for (let index = 0; index < 524; index += 1) session.sendAudio(chunk);
  assert.throws(() => session.sendAudio(chunk), /33554432-byte/);
  assert.equal(instances[0].sent.length, 525);
  session.close();
});

test('Streams rejects unsupported clinical capabilities before opening a socket', async () => {
  await assert.rejects(
    sdk().streams.connect({
      interactionId: INTERACTION_ID,
      tenantName: 'hospital',
      configuration: configuration({
        transcription: { primaryLanguage: 'zh-CN', diarize: true },
      }),
    }),
    (error) => error instanceof ManagedStreamsSessionError
      && error.code === 'diarization_not_available',
  );
});

test('Streams accepts governed PCM multichannel and fast-init before transport', async (t) => {
  const instances = installWebSocket(t, { onSend: acceptConfiguration });
  const session = await sdk().streams.connect({
    interactionId: INTERACTION_ID,
    tenantName: 'hospital',
    configuration: configuration({
      transcription: {
        primaryLanguage: 'zh-CN',
        isMultichannel: true,
        participants: [
          { channel: 0, role: 'clinician' },
          { channel: 1, role: 'patient' },
        ],
      },
      mode: { type: 'facts', outputLocale: 'zh-CN', factGenerationInterval: 'fast_init' },
      audioFormat: 'audio/pcm; rate=16000; channels=2; bits=16',
    }),
  });
  assert.equal(instances.length, 1);
  assert.equal(session.acceptedConfiguration.configuration.transcription.isMultichannel, true);
  session.close();
});

test('Streams accepts ordered case-sensitive keyterms before transport', async (t) => {
  const instances = installWebSocket(t, { onSend: acceptConfiguration });
  const keyterms = { terms: [{ term: '房颤' }, { term: 'Corti Health' }] };
  const session = await sdk().streams.connect({
    interactionId: INTERACTION_ID,
    tenantName: 'hospital',
    configuration: configuration({ keyterms }),
  });
  assert.equal(instances.length, 1);
  assert.deepEqual(session.acceptedConfiguration.configuration.keyterms, keyterms);
  session.close();
});

test('Streams bounds keyterms before transport', async () => {
  for (const [keyterms, code] of [
    [{ terms: Array.from({ length: 1001 }, () => ({ term: '房颤' })) }, 'keyterm_limit_exceeded'],
    [{ terms: [{ term: '' }] }, 'keyterm_invalid'],
    [{ terms: [{ term: 'x'.repeat(51) }] }, 'keyterm_invalid'],
  ]) {
    await assert.rejects(
      sdk().streams.connect({
        interactionId: INTERACTION_ID,
        tenantName: 'hospital',
        configuration: configuration({ keyterms }),
      }),
      (error) => error instanceof ManagedStreamsSessionError && error.code === code,
    );
  }
});

test('Streams rejects incomplete multichannel participant mapping before transport', async () => {
  await assert.rejects(
    sdk().streams.connect({
      interactionId: INTERACTION_ID,
      tenantName: 'hospital',
      configuration: configuration({
        transcription: {
          primaryLanguage: 'zh-CN', isMultichannel: true,
          participants: [{ channel: 0, role: 'clinician' }],
        },
        audioFormat: 'audio/pcm; rate=16000; channels=2; bits=16',
      }),
    }),
    (error) => error instanceof ManagedStreamsSessionError
      && error.code === 'multichannel_participants_must_match_channels',
  );
});

test('Streams rejects WAV and unknown streaming audio formats before transport', async () => {
  for (const [audioFormat, expectedCode] of [
    ['audio/wav', 'audio_format_not_supported'],
    ['audio/pcm', 'audio_format_not_supported'],
    ['audio/pcm; rate=48000; channels=1; bits=16', 'raw_pcm_profile_not_available'],
    ['audio/mpeg; codecs=mp3', 'audio_format_not_supported'],
  ]) {
    await assert.rejects(
      sdk().streams.connect({
        interactionId: INTERACTION_ID,
        tenantName: 'hospital',
        configuration: configuration({ audioFormat }),
      }),
      (error) => error instanceof ManagedStreamsSessionError
        && error.code === expectedCode,
    );
  }
});

test('Streams audio events require the governed PCM profile before transport', async () => {
  await assert.rejects(
    sdk().streams.connect({
      interactionId: INTERACTION_ID,
      tenantName: 'hospital',
      configuration: configuration({
        audioFormat: 'audio/ogg',
        audioEvents: { enabled: true },
      }),
    }),
    (error) => error instanceof ManagedStreamsSessionError
      && error.code === 'audio_events_require_pcm',
  );
});

test('Streams turns configuration denial into a typed PHI-safe error', async (t) => {
  installWebSocket(t, {
    onSend(socket, data) {
      if (typeof data === 'string' && JSON.parse(data).type === 'config') {
        queueMicrotask(() => socket.serverMessage({
          type: 'CONFIG_DENIED',
          reason: 'patient secret from server',
          interactionId: INTERACTION_ID,
        }));
      }
    },
  });
  await assert.rejects(
    sdk().streams.connect({
      interactionId: INTERACTION_ID,
      tenantName: 'hospital',
      configuration: configuration(),
    }),
    (error) => error instanceof ManagedStreamsSessionError
      && error.code === 'config_denied'
      && !error.message.includes('patient secret'),
  );
});

test('Streams fails closed when a connection drops after audio', async (t) => {
  const instances = installWebSocket(t, { onSend: acceptConfiguration });
  const session = await sdk().streams.connect({
    interactionId: INTERACTION_ID,
    tenantName: 'hospital',
    configuration: configuration(),
  });
  const terminal = new Promise((resolve) => session.on('error', resolve));
  session.sendAudio(new Uint8Array([1]));
  const ended = session.waitForEnded();
  instances[0].serverClose();
  const error = await terminal;
  await assert.rejects(ended, /audio_resume_unsupported/);
  assert.equal(error.code, 'audio_resume_unsupported');
  assert.equal(error.retryable, false);
});

test('Streams resumes only a flushed retained checkpoint acknowledged by the server', async (t) => {
  let connection = 0;
  const instances = installWebSocket(t, {
    onSend(socket, data) {
      if (typeof data !== 'string') return;
      const message = JSON.parse(data);
      if (message.type !== 'config') return;
      connection += 1;
      queueMicrotask(() => socket.serverMessage({
        type: 'CONFIG_ACCEPTED',
        sessionId: connection === 1 ? SESSION_ID : '33333333-3333-4333-8333-333333333333',
        configuration: message.configuration,
        resumed: connection === 2,
        restoredAudioBytes: connection === 2 ? 3 : 0,
        restoredTranscriptMessages: connection === 2 ? 1 : 0,
        restoredFactMessages: connection === 2 ? 1 : 0,
      }));
    },
  });
  const client = sdk();
  const options = {
    interactionId: INTERACTION_ID,
    tenantName: 'hospital',
    configuration: configuration({ retentionPolicy: 'retain' }),
  };
  const first = await client.streams.connect(options);
  const interrupted = new Promise((resolve) => first.on('error', resolve));
  first.sendAudio(new Uint8Array([1, 2, 3]));
  first.flush();
  instances[0].serverMessage({ type: 'flushed' });
  instances[0].serverMessage({ type: 'delta_usage', credits: 0 });
  instances[0].serverClose();
  const resumeRequired = await interrupted;
  assert.equal(resumeRequired.code, 'stream_resume_required');
  assert.equal(resumeRequired.retryable, true);

  const resumed = await client.streams.resume(options);
  assert.equal(resumed.acceptedConfiguration.resumed, true);
  assert.equal(resumed.acceptedConfiguration.restoredAudioBytes, 3);
  assert.equal(resumed.acceptedConfiguration.restoredTranscriptMessages, 1);
  assert.equal(resumed.acceptedConfiguration.restoredFactMessages, 1);
  resumed.sendAudio(new Uint8Array([4]));
  assert.deepEqual(instances[1].sent[1], new Uint8Array([4]));
  resumed.close();
});

test('Streams resume fails closed when the server has no retained checkpoint', async (t) => {
  installWebSocket(t, { onSend: acceptConfiguration });
  await assert.rejects(
    sdk().streams.resume({
      interactionId: INTERACTION_ID,
      tenantName: 'hospital',
      configuration: configuration({ retentionPolicy: 'retain' }),
    }),
    (error) => error instanceof ManagedStreamsSessionError
      && error.code === 'stream_checkpoint_not_found',
  );
});

test('Streams rejects malformed CONFIG_ACCEPTED and discards server free text', async (t) => {
  installWebSocket(t, {
    onSend(socket, data) {
      if (typeof data === 'string' && JSON.parse(data).type === 'config') {
        queueMicrotask(() => socket.serverMessage({
          type: 'CONFIG_ACCEPTED', sessionId: 'not-a-uuid',
          configuration: configuration(), secret: 'patient secret',
        }));
      }
    },
  });
  await assert.rejects(
    sdk().streams.connect({
      interactionId: INTERACTION_ID,
      tenantName: 'hospital',
      configuration: configuration(),
    }),
    (error) => error instanceof ManagedStreamsSessionError
      && error.code === 'invalid_configuration_response'
      && !error.message.includes('patient secret'),
  );
});

test('Streams runtime errors expose only a stable code', async (t) => {
  const instances = installWebSocket(t, { onSend: acceptConfiguration });
  const session = await sdk().streams.connect({
    interactionId: INTERACTION_ID,
    tenantName: 'hospital',
    configuration: configuration(),
  });
  const terminal = new Promise((resolve) => session.on('error', resolve));
  instances[0].serverMessage({
    type: 'error',
    error: { id: 'FACTS_UNAVAILABLE', details: 'patient secret' },
  });
  const error = await terminal;
  assert.equal(error.code, 'FACTS_UNAVAILABLE');
  assert.equal(error.message.includes('patient secret'), false);
  session.close();
});
