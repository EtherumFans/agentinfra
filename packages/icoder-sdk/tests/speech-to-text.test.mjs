import assert from 'node:assert/strict';
import test from 'node:test';

import iCoDer from '../dist/index.js';


test('SpeechToTextResource uploads audio and preserves async response metadata', async () => {
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test',
    auth: { accessToken: 'test-token' },
  });
  const calls = [];
  sdk.client.http.defaults.adapter = async (config) => {
    calls.push(config);
    return {
      data: config.url.endsWith('/recordings')
        ? { recordingId: 'rec-1' }
        : { id: 'tr-1', recordingId: 'rec-1', status: 'processing' },
      status: config.url.endsWith('/recordings') ? 201 : 202,
      statusText: 'OK',
      headers: config.url.endsWith('/recordings') ? {} : { location: '/status/tr-1' },
      config,
      request: {},
    };
  };

  const recording = await sdk.speechToText.uploadRecording(
    'interaction/1',
    new Uint8Array([1, 2, 3]),
    'audio/flac',
  );
  const result = await sdk.speechToText.createTranscript('interaction/1', {
    recordingId: recording.recordingId,
    primaryLanguage: 'zh-CN',
    async: true,
    isDictation: true,
    spokenPunctuation: true,
    automaticPunctuation: false,
    isMultichannel: true,
    participants: [
      { channel: 0, role: 'doctor' },
      { channel: 1, role: 'patient' },
    ],
    keyterms: { terms: [{ term: '房颤' }, { term: 'Corti Health' }] },
  });

  assert.equal(calls[0].url, '/api/v2/tools/interactions/interaction%2F1/recordings');
  assert.equal(calls[0].headers['Content-Type'], 'audio/flac');
  assert.equal(calls[1].url, '/api/v2/tools/interactions/interaction%2F1/transcripts');
  const transcriptRequest = JSON.parse(calls[1].data);
  assert.equal(transcriptRequest.async, true);
  assert.equal(transcriptRequest.isDictation, true);
  assert.equal(transcriptRequest.spokenPunctuation, true);
  assert.equal(transcriptRequest.automaticPunctuation, false);
  assert.equal(transcriptRequest.isMultichannel, true);
  assert.deepEqual(transcriptRequest.participants, [
    { channel: 0, role: 'doctor' },
    { channel: 1, role: 'patient' },
  ]);
  assert.deepEqual(transcriptRequest.keyterms, {
    terms: [{ term: '房颤' }, { term: 'Corti Health' }],
  });
  assert.equal(result.statusCode, 202);
  assert.equal(result.location, '/status/tr-1');
});


test('SpeechToTextResource rejects misleading unsupported capabilities before transport', async () => {
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test',
    auth: { accessToken: 'test-token' },
  });
  await assert.rejects(
    () => sdk.speechToText.uploadRecording('i-1', new Uint8Array([1]), 'application/json'),
    /unsupported recording media type/,
  );
  await assert.rejects(
    () => sdk.speechToText.createTranscript('i-1', {
      recordingId: 'rec-1',
      primaryLanguage: 'en-US',
    }),
    /Chinese audio only/,
  );
  await assert.rejects(
    () => sdk.speechToText.createTranscript('i-1', {
      recordingId: 'rec-1',
      diarize: true,
    }),
    /unsupported STT features: diarize/,
  );
  await assert.rejects(
    () => sdk.speechToText.createTranscript('i-1', {
      recordingId: 'rec-1',
      isMultichannel: true,
      participants: [{ channel: 0, role: 'doctor' }],
    }),
    /participants for channels 0 and 1/,
  );
  await assert.rejects(
    () => sdk.speechToText.createTranscript('i-1', {
      recordingId: 'rec-1',
      keyterms: { terms: [{ term: '术'.repeat(51) }] },
    }),
    /1 to 50 characters/,
  );
  await assert.rejects(
    () => sdk.speechToText.createTranscript('i-1', {
      recordingId: 'rec-1',
      keyterms: { terms: Array.from({ length: 1001 }, (_, index) => ({ term: `t-${index}` })) },
    }),
    /cannot exceed 1000 items/,
  );
});


test('SpeechToTextResource real-time session rejects unverified language before opening a socket', async () => {
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test',
    auth: { accessToken: 'test-token' },
  });
  await assert.rejects(
    () => sdk.speechToText.createSession({ language: 'en-US' }),
    /zh-CN only/,
  );
});


test('SpeechToTextResource waits for the server ready acknowledgement', async (t) => {
  const originalWebSocket = globalThis.WebSocket;
  let openedUrl = '';
  let startMessage = null;
  class ReadyWebSocket {
    constructor(url) {
      openedUrl = url;
      this.readyState = 0;
      queueMicrotask(() => {
        this.readyState = 1;
        this.onopen?.();
      });
    }
    send(value) {
      startMessage = JSON.parse(value);
      queueMicrotask(() => this.onmessage?.({
        data: JSON.stringify({ type: 'ready', language: 'zh-CN', maxSessionBytes: 33554432 }),
      }));
    }
    close() {
      this.readyState = 3;
      this.onclose?.();
    }
  }
  globalThis.WebSocket = ReadyWebSocket;
  t.after(() => { globalThis.WebSocket = originalWebSocket; });
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test',
    auth: { accessToken: 'tenant/token +' },
  });

  const session = await sdk.speechToText.createSession();

  assert.equal(session.readyState, 1);
  assert.equal(openedUrl, 'wss://api.cn.icoder.test/ws/speech-to-text?token=tenant%2Ftoken%20%2B');
  assert.deepEqual(startMessage, {
    type: 'start', mimeType: 'audio/webm;codecs=opus', language: 'zh-CN',
  });
});
