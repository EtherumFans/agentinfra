import { Role } from '@a2a-js/sdk';

import iCoDer from '../../dist/index.js';
import {
  convertToParams,
  createA2AClientFactory,
  toUIMessageStream,
} from '../../dist/ai-sdk-adapter.js';


const baseURL = process.argv[2];
if (!baseURL) throw new Error('base URL argument is required');

const sdk = new iCoDer({
  baseURL,
  auth: { accessToken: 'official-a2a-package-test-token' },
});
const cardUrl = `${baseURL}/api/v2/agentic/agents/medcoder-coding-review/` +
  '.well-known/agent-card.json';
const client = await createA2AClientFactory(sdk).createFromUrl(cardUrl, '');

const sendResult = await client.sendMessage(convertToParams([
  {
    id: 'official-js-send',
    role: 'user',
    parts: [{ type: 'text', text: 'de-identified documentation review' }],
  },
]));
if (sendResult.role !== Role.ROLE_AGENT) {
  throw new Error('live SendMessage did not return an Agent message');
}

const eventCases = [];
const uiChunks = [];
const uiStream = toUIMessageStream(client.sendMessageStream(convertToParams([
  {
    id: 'official-js-stream',
    role: 'user',
    parts: [{ type: 'text', text: 'de-identified streaming review' }],
  },
])), {
  callbacks: {
    onEvent(event) {
      eventCases.push(event.payload?.$case ?? 'missing');
    },
  },
});
for await (const chunk of uiStream) uiChunks.push(chunk);

const metadata = uiChunks.find((chunk) => chunk.type === 'message-metadata');
const finish = uiChunks.findLast((chunk) => chunk.type === 'finish');
if (!metadata || !metadata.messageMetadata.contextId || !metadata.messageMetadata.taskId) {
  throw new Error('live stream did not expose resumable Context/Task metadata');
}
if (!finish || finish.finishReason !== 'stop') {
  throw new Error('live stream did not reach a settled finish');
}

process.stdout.write(JSON.stringify({
  send: {
    role: sendResult.role,
    contextId: sendResult.contextId,
    partCases: sendResult.parts.map((part) => part.content?.$case ?? 'missing'),
  },
  stream: {
    eventCases,
    contextId: metadata.messageMetadata.contextId,
    taskId: metadata.messageMetadata.taskId,
    state: metadata.messageMetadata.state,
    finishReason: finish.finishReason,
    chunkTypes: uiChunks.map((chunk) => chunk.type),
  },
}));
