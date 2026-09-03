import { readFileSync } from 'node:fs';
import iCoDer from '../dist/index.js';

const baseURL = process.env.ICODER_E2E_STREAMS_BASE_URL;
const accessToken = process.env.ICODER_E2E_ACCESS_TOKEN;
const tenantName = process.env.ICODER_E2E_TENANT_NAME;
const audioPath = process.env.ICODER_E2E_STREAMS_AUDIO_PATH;
if (!baseURL || !accessToken || !tenantName || !audioPath) {
  throw new Error('missing local Streams E2E environment');
}
const audio = readFileSync(audioPath);

const interactionId = crypto.randomUUID();
const sdk = new iCoDer({ baseURL, auth: { accessToken } });
const session = await sdk.streams.connect({
  interactionId,
  tenantName,
  environment: 'cn',
  configuration: {
    transcription: {
      primaryLanguage: 'zh-CN', diarize: false, isMultichannel: false,
      participants: [{ channel: 0, role: 'multiple' }],
    },
    mode: { type: 'transcription' },
    retentionPolicy: 'retain',
    audioFormat: 'audio/ogg; codecs=opus',
  },
});
const messages = [];
session.on('message', (message) => messages.push(message));
session.sendAudio(audio);
session.flush();
session.end();
await Promise.race([
  session.waitForEnded(),
  new Promise((_, reject) => setTimeout(() => reject(new Error('Streams timeout')), 15000)),
]);
const types = messages.map((message) => message.type);
for (const required of ['flushed', 'delta_usage', 'usage', 'ENDED']) {
  if (!types.includes(required)) throw new Error(`missing Streams event: ${required}`);
}
const errorCodes = messages
  .filter((message) => message.type === 'error')
  .map((message) => message.code)
  .sort();
if (JSON.stringify(errorCodes) !== JSON.stringify(['STT_UNAVAILABLE'])) {
  throw new Error('local disabled-provider errors were not explicit and bounded');
}
const usage = messages.find((message) => message.type === 'usage');
if (usage?.credits !== 0) throw new Error('local Streams usage must not invent credits');
session.close();
console.log(JSON.stringify({
  sdk: 'javascript', status: 'passed', interaction_id: interactionId,
  retention_policy: 'retain', event_types: types,
  expected_error_codes: errorCodes,
  synthetic_audio_bytes: audio.length, synthetic_silence_ogg_opus: true,
  real_stt_engine_used: false, real_llm_used: false,
}));
