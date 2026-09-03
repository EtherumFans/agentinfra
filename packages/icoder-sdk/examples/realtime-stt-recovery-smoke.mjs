import iCoDer from '../dist/index.js';

const baseURL = process.env.ICODER_E2E_STT_BASE_URL;
const accessToken = process.env.ICODER_E2E_ACCESS_TOKEN;
if (!baseURL || !accessToken) throw new Error('missing local STT E2E environment');

const sdk = new iCoDer({ baseURL, auth: { accessToken } });
const session = await sdk.speechToText.connectManagedSession({
  reconnectAttempts: 2,
  reconnectInitialDelayMs: 0,
  reconnectMaxDelayMs: 0,
  setupTimeoutMs: 5000,
});
const messages = [];
const reconnecting = [];
session.on('message', (message) => messages.push(message));
session.on('reconnecting', (event) => reconnecting.push(event));

const terminal = new Promise((resolve, reject) => {
  const timeout = setTimeout(() => reject(new Error('STT recovery timeout')), 15000);
  session.on('error', (error) => {
    if (error.code === 'transcription_failed') {
      clearTimeout(timeout);
      resolve(error);
    }
  });
});

session.sendAudio(new Uint8Array([0x49, 0x43, 0x4f, 0x44, 0x45, 0x52]));
session.sendEnd();
await terminal;

const acknowledgements = messages.filter((message) => message.type === 'audio_ack');
if (reconnecting.length !== 1 || acknowledgements.length < 2) {
  throw new Error('managed STT did not prove one disconnect and replay');
}
session.close();
console.log(JSON.stringify({
  sdk: 'javascript',
  status: 'passed',
  reconnects: reconnecting.length,
  acknowledgements: acknowledgements.length,
  synthetic_audio_bytes: 6,
  real_stt_engine_used: false,
}));
