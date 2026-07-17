// Phase 7 Gate 2 — verify SDK type declarations resolve from .tgz install.

import iCoDer, { iCoDerClient } from '@icoder/sdk';
import type {
  AgentRunRequest,
  AgentRunResponse,
  RunHistoryItem,
  RunTraceEvent,
  A2AEnvelope,
} from '@icoder/sdk';
import { RunsResource, RunHistoryResource, RunTraceResource } from '@icoder/sdk';

const client = new iCoDer({
  baseURL: 'http://localhost:8000',
  auth: { accessToken: 'partner-token-placeholder' },
});

const runs: RunsResource = client.runs;
const runHistory: RunHistoryResource = client.runHistory;
const runTrace: RunTraceResource = client.runTrace;

const req: AgentRunRequest = {
  input: { text: 'patient clinical text' },
  runtime_mode: 'corti_like_fast',
};
void req;
void client;
void runs;
void runHistory;
void runTrace;
void (null as unknown as AgentRunResponse);
void (null as unknown as RunHistoryItem);
void (null as unknown as RunTraceEvent);
void (null as unknown as A2AEnvelope);
void (null as unknown as iCoDerClient);
