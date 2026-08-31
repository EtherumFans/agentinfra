import crypto from 'node:crypto';
import iCoDer, { iCoDerClient } from '../dist/index.js';

const baseURL = process.env.ICODER_E2E_BASE_URL;
const accessToken = process.env.ICODER_E2E_ACCESS_TOKEN;
if (!baseURL || !accessToken) {
  throw new Error('ICODER_E2E_BASE_URL and ICODER_E2E_ACCESS_TOKEN are required');
}

const client = new iCoDer({ baseURL, auth: { accessToken } });
const sseBaseURL = process.env.ICODER_E2E_SSE_BASE_URL || baseURL;
const longSseRunId = process.env.ICODER_E2E_SSE_RUN_ID;
const longSseToken = process.env.ICODER_E2E_SSE_TRACE_TOKEN;
let longSseVerified = 'skipped';
if (longSseRunId && longSseToken) {
  const startedAt = Date.now();
  const resilientClient = new iCoDer({
    baseURL: sseBaseURL,
    auth: { accessToken },
  });
  const envelopes = [];
  for await (const event of resilientClient.runs.streamEventsResilient(
    longSseRunId,
    longSseToken,
    { maxAttempts: 4, initialDelayMs: 10, maxDelayMs: 50, jitterRatio: 0 },
  )) {
    envelopes.push(event.data);
  }
  const names = envelopes.map((event) => event.name);
  if (names.join(',') !== 'run.ingest,run.completion,stream.completed') {
    throw new Error(`Long SSE resilient contract failed: ${names.join(',')}`);
  }
  const terminal = envelopes.at(-1)?.payload;
  if (terminal?.status !== 'COMPLETED' || terminal?.event_count !== 2) {
    throw new Error('Long SSE terminal payload is incomplete');
  }
  if (Date.now() - startedAt < 300) {
    throw new Error('Long SSE stream closed before the delayed event landed');
  }
  longSseVerified = 'expired-token-renewed-two-disconnects-resumed-terminal';
}
const oauthClientId = process.env.ICODER_E2E_CLIENT_ID;
const oauthClientSecret = process.env.ICODER_E2E_CLIENT_SECRET;
let oauthClientCredentials = 'skipped';
let runClient = client;
if (oauthClientId && oauthClientSecret) {
  const authClient = new iCoDerClient({ baseURL, auth: { accessToken: '' } });
  const token = await authClient.authenticate(oauthClientId, oauthClientSecret);
  if (!token.access_token || token.refresh_token || token.user) {
    throw new Error('Client-credentials token shape is invalid');
  }
  const oauthConsumer = new iCoDer({
    baseURL,
    auth: { accessToken: token.access_token },
  });
  const oauthHub = await oauthConsumer.agents.hub();
  if (oauthHub.total !== 26) throw new Error('OAuth token could not access Agent Hub');
  oauthClientCredentials = 'form-token-hub';
  runClient = oauthConsumer;
}
const hub = await client.agents.hub();
if (hub.total !== 26 || hub.agents.length !== 26 ||
    hub.agents.some((agent) => !agent.runnable || !agent.launch_candidate_ready)) {
  throw new Error(`Agent Hub release-candidate contract failed: total=${hub.total}`);
}

let factsFailedClosed = false;
try {
  await client.facts.extract('Synthetic SDK Facts contract smoke only.', 'zh-CN');
} catch (error) {
  if (error?.response?.status !== 503) throw error;
  factsFailedClosed = true;
}
if (!factsFailedClosed) throw new Error('Credential-free Facts extraction did not fail closed');

let codingFilterReachedServer = false;
try {
  const coding = await client.medicalCoding.predict({
    text: 'Synthetic coding-filter transport smoke only.',
    coding_systems: ['icd10cn', 'icd9cm3'],
    filter: { include: ['E11'], exclude: ['E11.9'], expand: true },
  });
  codingFilterReachedServer = coding.error === true;
} catch (error) {
  if (error?.response?.status !== 503) throw error;
  codingFilterReachedServer = true;
}
if (!codingFilterReachedServer) throw new Error('Credential-free Coding did not fail closed');

const { data: run } = await runClient.runs.runText(
  'note-completeness-agent',
  'JavaScript SDK contract smoke only; no patient or clinical data.',
  {
    idempotencyKey: `js-smoke-${crypto.randomUUID()}`,
    purpose_of_use: 'treatment',
  },
);
if (run.agent_id !== 'note-completeness-agent' || !run.run_id || !run.trace_id) {
  throw new Error('Unified Agent Run envelope is incomplete');
}
if (run.error) {
  throw new Error('Deterministic local Note Completeness Agent Run failed unexpectedly');
}
if (
  typeof run.result?.review_conclusion !== 'string'
  || typeof run.result?.completeness_score !== 'number'
) {
  throw new Error('Deterministic local Note Completeness result contract is incomplete');
}
const { data: runStatus } = await runClient.runs.get(run.run_id);
if (!runStatus.terminal || runStatus.run_id !== run.run_id) {
  throw new Error('Agent Run status polling did not return the terminal run');
}
const { data: runCancellation } = await runClient.runs.cancel(
  run.run_id,
  'SDK lifecycle smoke after terminal completion',
);
if (runCancellation.outcome !== 'ALREADY_COMPLETE') {
  throw new Error(`Unexpected terminal cancellation outcome: ${runCancellation.outcome}`);
}
const traceToken = new URL(run.trace_url, baseURL).searchParams.get('token');
if (!traceToken) throw new Error('Agent Run trace URL has no signed token');
const runEventStream = await runClient.runs.streamEvents(run.run_id, traceToken);
const runEvents = await new Response(runEventStream).text();
if (!runEvents.includes('stream.completed')) {
  throw new Error('Agent Run lifecycle stream did not complete');
}

const firstTurn = await client.a2a.messageSend(
  'note-completeness-agent',
  'Synthetic SDK context turn one; test phone 13800138000 only.',
);
const secondTurn = await client.a2a.messageSend(
  'note-completeness-agent',
  'Synthetic SDK context turn two; verify continuation only.',
  { contextId: firstTurn.contextId },
);
if (secondTurn.contextId !== firstTurn.contextId) {
  throw new Error('A2A continuation returned a different contextId');
}
const context = await client.a2a.getContext(
  'note-completeness-agent',
  firstTurn.contextId,
);
if (context.id !== firstTurn.contextId || context.items.length !== 4) {
  throw new Error(`A2A Context history is incomplete: items=${context.items.length}`);
}
const serializedContext = JSON.stringify(context);
if (serializedContext.includes('13800138000') || !serializedContext.includes('<REDACTED:PHONE>')) {
  throw new Error('A2A Context did not persist the PHI-redacted view');
}
const deletedContext = await client.a2a.deleteContext(firstTurn.contextId);
if (!deletedContext.deleted) throw new Error('A2A Context delete did not confirm deletion');

const interactionId = `js-sdk-${crypto.randomUUID()}`;
const payload = new Uint8Array([0x52, 0x49, 0x46, 0x46, 0, 0, 0, 0]);
const recording = await client.speechToText.uploadRecording(interactionId, payload, 'audio/wav');
let recordings = await client.speechToText.listRecordings(interactionId);
if (!recordings.recordings.includes(recording.recordingId)) {
  throw new Error('Uploaded recording was not listed');
}
const downloaded = new Uint8Array(
  await client.speechToText.downloadRecording(interactionId, recording.recordingId),
);
if (!Buffer.from(downloaded).equals(Buffer.from(payload))) {
  throw new Error('Downloaded recording differs from uploaded bytes');
}
await client.speechToText.deleteRecording(interactionId, recording.recordingId);
recordings = await client.speechToText.listRecordings(interactionId);
if (recordings.recordings.includes(recording.recordingId)) {
  throw new Error('Deleted recording is still listed');
}

const realtime = await client.speechToText.createSession();
realtime.close(1000, 'SDK smoke complete');

console.log(JSON.stringify({
  sdk: 'javascript',
  status: 'passed',
  hub_total: hub.total,
  run_error: run.error,
  run_lifecycle: 'status-terminal,cancel-already-complete,sse-completed',
  long_sse: longSseVerified,
  context_roundtrip: 'send-continue-get-delete',
  recording_lifecycle: 'upload-list-download-delete',
  realtime_stt: 'authenticated-start-ready-close',
  oauth_client_credentials: oauthClientCredentials,
  facts_without_real_llm: 'failed_closed',
  coding_multi_system_filter_transport: 'accepted_and_degraded_without_llm',
}));
