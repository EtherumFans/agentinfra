import {
  Role,
  TaskState,
  type Message,
  type Part,
  type SendMessageRequest,
  type StreamResponse,
  type TaskStatus,
} from '@a2a-js/sdk';
import {
  ClientFactory,
  ClientFactoryOptions,
  DefaultAgentCardResolver,
  JsonRpcTransportFactory,
  type Client,
} from '@a2a-js/sdk/client';
import type {
  UIDataTypes,
  UIMessage,
  UIMessageChunk,
  UITools,
} from 'ai';

import type { iCoDerClient } from './client.js';


export type JSONValue =
  | null
  | boolean
  | number
  | string
  | JSONValue[]
  | { [key: string]: JSONValue };

export type ExpertCredential =
  | { mcp_name: string; token: string; type: 'bearer' }
  | {
      mcp_name: string;
      client_id: string;
      client_secret: string;
      type: 'oauth2.0';
    };

export interface CortiMessageMetadata {
  contextId?: string;
  taskId?: string;
  history?: boolean;
  credits?: number;
  state?: string;
}

export type CortiJSONPart = JSONValue;
export type CortiTextPart = string;
export interface CortiStatusUpdate {
  state: string;
  message?: string;
}

export type CortiUIDataTypes = {
  text: CortiTextPart;
  json: CortiJSONPart;
  'status-update': CortiStatusUpdate;
};

export type CortiUIMessage<
  TAdditionalMetadata = unknown,
  TAdditionalDataTypes extends UIDataTypes = UIDataTypes,
  TTools extends UITools = UITools,
> = UIMessage<
  CortiMessageMetadata & TAdditionalMetadata,
  CortiUIDataTypes & TAdditionalDataTypes,
  TTools
>;

export type CortiUIMessageChunk<
  TAdditionalMetadata = unknown,
  TAdditionalDataTypes extends UIDataTypes = UIDataTypes,
> = UIMessageChunk<
  CortiMessageMetadata & TAdditionalMetadata,
  CortiUIDataTypes & TAdditionalDataTypes
>;

export interface ResponseMetadata {
  contextId: string;
  taskId: string;
  credits: number;
  state: string;
}

export interface StreamCallbacks {
  onStart?(): void;
  onFinish?(state: TaskStatus | undefined): void;
  onError?(error: Error): void;
  onEvent?(event: StreamResponse): void;
}

export interface StreamConversionOptions {
  callbacks?: StreamCallbacks;
}

/** Accept either the low-level client or the public iCoDer resource facade. */
export type iCoDerAdapterClient = iCoDerClient | { client: iCoDerClient };

const MAX_MESSAGES = 1_000;
const MAX_PARTS = 64;
const MAX_TEXT_CHARS = 1_000_000;
const MAX_CREDENTIALS = 16;
const MAX_CREDENTIAL_FIELD = 8_192;
const MAX_FILE_DATA_URL_CHARS = 14_000_000;
const MAX_FILE_BYTES = 10_000_000;


function nonEmpty(value: unknown, field: string, max = MAX_CREDENTIAL_FIELD): string {
  if (typeof value !== 'string' || !value.trim() || value.length > max) {
    throw new TypeError(`${field} must be a non-empty bounded string`);
  }
  return value;
}


function messageId(): string {
  const randomUUID = globalThis.crypto?.randomUUID?.bind(globalThis.crypto);
  return `msg-${randomUUID ? randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`}`;
}


function textPart(value: string, mediaType = 'text/plain'): Part {
  return {
    content: { $case: 'text', value },
    metadata: undefined,
    filename: '',
    mediaType,
  };
}


function dataPart(value: unknown, metadata?: Record<string, unknown>): Part {
  return {
    content: { $case: 'data', value },
    metadata,
    filename: '',
    mediaType: 'application/json',
  };
}


function decodeBase64(value: string, field: string): Uint8Array {
  if (!value || value.length > MAX_FILE_DATA_URL_CHARS) {
    throw new RangeError(`${field} exceeds the adapter file limit`);
  }
  let decoded: string;
  try {
    decoded = globalThis.atob(value);
  } catch {
    throw new TypeError(`${field} must contain canonical Base64 data`);
  }
  if (value.length % 4 !== 0 || globalThis.btoa(decoded) !== value) {
    throw new TypeError(`${field} must contain canonical padded Base64 data`);
  }
  if (decoded.length > MAX_FILE_BYTES) {
    throw new RangeError(`${field} exceeds the adapter file limit`);
  }
  return Uint8Array.from(decoded, (character) => character.charCodeAt(0));
}


function filePart(part: { url: string; mediaType: string; filename?: string }): Part {
  const url = nonEmpty(part.url, 'file.url', MAX_FILE_DATA_URL_CHARS);
  const mediaType = nonEmpty(part.mediaType, 'file.mediaType', 255);
  const filename = part.filename
    ? nonEmpty(part.filename, 'file.filename', 255)
    : 'file';
  if (url.startsWith('http://') || url.startsWith('https://')) {
    const parsed = new URL(url);
    if (parsed.username || parsed.password) {
      throw new TypeError('file.url must not contain credentials');
    }
    return {
      content: { $case: 'url', value: parsed.toString() },
      metadata: undefined,
      filename,
      mediaType,
    };
  }
  const match = /^data:([^;,]+);base64,([A-Za-z0-9+/]*={0,2})$/.exec(url);
  if (!match) throw new TypeError('file.url must be an HTTP(S) URL or a Base64 data URL');
  const declaredMediaType = match[1];
  if (declaredMediaType !== mediaType) {
    throw new TypeError('file.mediaType must match the data URL media type');
  }
  const raw = decodeBase64(match[2], 'file.url');
  if (mediaType === 'application/json') {
    let value: unknown;
    try {
      value = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(raw));
    } catch {
      throw new TypeError('application/json file data must contain valid UTF-8 JSON');
    }
    return dataPart(value, { filename });
  }
  return {
    content: { $case: 'raw', value: raw },
    metadata: undefined,
    filename,
    mediaType,
  };
}


function credentialParts(credentials: ExpertCredential[]): Part[] {
  if (credentials.length > MAX_CREDENTIALS) {
    throw new RangeError(`credentials cannot contain more than ${MAX_CREDENTIALS} items`);
  }
  const names = new Set<string>();
  return credentials.map((credential, index) => {
    const mcpName = nonEmpty(credential.mcp_name, `credentials[${index}].mcp_name`, 128);
    if (names.has(mcpName)) throw new TypeError('credentials must use unique mcp_name values');
    names.add(mcpName);
    if (credential.type === 'bearer') {
      return dataPart({
        mcp_name: mcpName,
        token: nonEmpty(credential.token, `credentials[${index}].token`),
        type: 'token',
      });
    }
    if (credential.type === 'oauth2.0') {
      return dataPart({
        client_id: nonEmpty(credential.client_id, `credentials[${index}].client_id`),
        client_secret: nonEmpty(
          credential.client_secret,
          `credentials[${index}].client_secret`,
        ),
        mcp_name: mcpName,
        type: 'credentials',
      });
    }
    throw new TypeError(`credentials[${index}].type is unsupported`);
  });
}


/** Convert Vercel AI SDK UI messages into the official A2A v1 request type. */
export function convertToParams(
  messages: CortiUIMessage[],
  credentials: ExpertCredential[] = [],
): SendMessageRequest {
  if (!Array.isArray(messages) || messages.length === 0 || messages.length > MAX_MESSAGES) {
    throw new TypeError(`messages must contain between 1 and ${MAX_MESSAGES} items`);
  }
  const current = messages[messages.length - 1];
  if (!current || current.role !== 'user' || !Array.isArray(current.parts)) {
    throw new TypeError('the last UI message must be a user message with parts');
  }
  if (current.parts.length === 0 || current.parts.length > MAX_PARTS) {
    throw new RangeError(`the current message must contain between 1 and ${MAX_PARTS} parts`);
  }

  const parts: Part[] = current.parts.map((part, index) => {
    if (part.type === 'text') {
      return textPart(nonEmpty(part.text, `messages[last].parts[${index}].text`, MAX_TEXT_CHARS));
    }
    if (part.type === 'file') {
      return filePart(part);
    }
    if (part.type === 'data-text') {
      return textPart(
        nonEmpty(part.data, `messages[last].parts[${index}].data`, MAX_TEXT_CHARS),
      );
    }
    if (part.type === 'data-json') {
      return dataPart(part.data);
    }
    throw new TypeError(`messages[last].parts[${index}].type is unsupported`);
  });

  const lastAssistant = [...messages].reverse().find((item) => item.role === 'assistant');
  const contextId = lastAssistant?.metadata?.contextId;
  const taskId = lastAssistant?.metadata?.state === 'input-required'
    ? lastAssistant.metadata.taskId
    : undefined;
  if (contextId !== undefined) nonEmpty(contextId, 'assistant.metadata.contextId', 128);
  if (taskId !== undefined) nonEmpty(taskId, 'assistant.metadata.taskId', 128);
  if (!taskId && credentials.length) parts.push(...credentialParts(credentials));

  return {
    tenant: '',
    message: {
      messageId: messageId(),
      contextId: contextId ?? '',
      taskId: taskId ?? '',
      role: Role.ROLE_USER,
      parts,
      metadata: undefined,
      extensions: [],
      referenceTaskIds: [],
    },
    configuration: undefined,
    metadata: undefined,
  };
}


function transport(client: iCoDerAdapterClient): iCoDerClient {
  const candidate = (client as { client?: iCoDerClient }).client ?? client;
  if (!candidate || typeof candidate !== 'object' || !('http' in candidate)) {
    throw new TypeError('an authenticated iCoDer SDK client is required');
  }
  return candidate as iCoDerClient;
}


function isLoopback(hostname: string): boolean {
  return hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '[::1]';
}


function baseUrl(client: iCoDerAdapterClient): URL {
  const value = transport(client).http.defaults.baseURL;
  if (typeof value !== 'string' || !value) throw new TypeError('SDK baseURL is required');
  const parsed = new URL(value);
  if (parsed.username || parsed.password) throw new TypeError('SDK baseURL must not contain credentials');
  if (parsed.protocol !== 'https:' && !(parsed.protocol === 'http:' && isLoopback(parsed.hostname))) {
    throw new TypeError('SDK baseURL must use HTTPS except on loopback');
  }
  return parsed;
}


/** Build a same-origin fetch implementation with authoritative iCoDer auth. */
export function createFetchImplementation(client: iCoDerAdapterClient): typeof fetch {
  const core = transport(client);
  const base = baseUrl(client);
  return async (input: string | URL | Request, init: RequestInit = {}) => {
    const url = input instanceof Request
      ? new URL(input.url)
      : new URL(input.toString(), base);
    if (url.origin !== base.origin || url.username || url.password) {
      throw new TypeError('A2A fetch is restricted to the configured SDK origin');
    }
    const token = core.accessToken;
    if (!token) throw new TypeError('A2A fetch requires an access token');
    const headers = new Headers(input instanceof Request ? input.headers : undefined);
    new Headers(init.headers).forEach((value, key) => headers.set(key, value));
    headers.delete('Cookie');
    headers.delete('Proxy-Authorization');
    headers.set('Authorization', `Bearer ${token}`);
    headers.set('A2A-Version', '1.0');
    const method = (init.method ?? (input instanceof Request ? input.method : 'GET')).toUpperCase();
    const body = method === 'GET' || method === 'HEAD'
      ? undefined
      : (init.body ?? (input instanceof Request ? input.body : undefined));
    const requestInit: RequestInit & { duplex?: 'half' } = {
      ...init,
      method,
      headers,
      body,
      signal: init.signal ?? (input instanceof Request ? input.signal : undefined),
      redirect: 'error',
      credentials: 'omit',
      ...(body ? { duplex: 'half' as const } : {}),
    };
    return globalThis.fetch(url, requestInit);
  };
}


/** Create the official A2A ClientFactory with iCoDer authentication. */
export function createA2AClientFactory(
  client: iCoDerAdapterClient,
  options?: Partial<ClientFactoryOptions>,
): ClientFactory {
  const fetchImpl = createFetchImplementation(client);
  const legacyCompat = { enabled: true };
  const defaults: ClientFactoryOptions = {
    transports: [new JsonRpcTransportFactory({ fetchImpl, legacyCompat })],
    cardResolver: new DefaultAgentCardResolver({ fetchImpl, legacyCompat }),
  };
  const merged = options
    ? ClientFactoryOptions.createFrom(defaults, options)
    : defaults;
  return new ClientFactory(merged);
}


const SETTLED_STATES = new Set<TaskState>([
  TaskState.TASK_STATE_COMPLETED,
  TaskState.TASK_STATE_FAILED,
  TaskState.TASK_STATE_CANCELED,
  TaskState.TASK_STATE_REJECTED,
  TaskState.TASK_STATE_INPUT_REQUIRED,
  TaskState.TASK_STATE_AUTH_REQUIRED,
]);

const TASK_STATE_LABELS: Record<number, string> = {
  [TaskState.TASK_STATE_UNSPECIFIED]: 'unknown',
  [TaskState.TASK_STATE_SUBMITTED]: 'submitted',
  [TaskState.TASK_STATE_WORKING]: 'working',
  [TaskState.TASK_STATE_COMPLETED]: 'completed',
  [TaskState.TASK_STATE_FAILED]: 'failed',
  [TaskState.TASK_STATE_CANCELED]: 'canceled',
  [TaskState.TASK_STATE_REJECTED]: 'rejected',
  [TaskState.TASK_STATE_INPUT_REQUIRED]: 'input-required',
  [TaskState.TASK_STATE_AUTH_REQUIRED]: 'auth-required',
  [TaskState.UNRECOGNIZED]: 'unknown',
};


function stateLabel(state: TaskState): string {
  return TASK_STATE_LABELS[state] ?? 'unknown';
}


function statusMessage(status: TaskStatus | undefined): string | undefined {
  const value = status?.message?.parts
    .filter((part) => part.content?.$case === 'text')
    .map((part) => part.content?.value)
    .join(' ');
  return value || undefined;
}


function bytesToBase64(value: Uint8Array): string {
  if (value.byteLength > MAX_FILE_BYTES) {
    throw new RangeError('A2A raw output exceeds the adapter file limit');
  }
  let binary = '';
  for (let offset = 0; offset < value.length; offset += 32_768) {
    binary += String.fromCharCode(...value.subarray(offset, offset + 32_768));
  }
  return globalThis.btoa(binary);
}


/** Convert an official A2A event iterable to Vercel AI SDK UI message chunks. */
export function toUIMessageStream(
  stream: ReturnType<Client['sendMessageStream']>,
  options: StreamConversionOptions = {},
): ReadableStream<CortiUIMessageChunk> {
  const activeTextIds = new Set<string>();
  let sequence = 0;
  let finalStatus: TaskStatus | undefined;
  let metadata: ResponseMetadata = {
    contextId: '',
    taskId: '',
    credits: 0,
    state: 'unknown',
  };

  const closeActiveText = (
    controller: ReadableStreamDefaultController<CortiUIMessageChunk>,
  ) => {
    for (const id of activeTextIds) {
      controller.enqueue({ type: 'text-end', id });
      activeTextIds.delete(id);
    }
  };

  const emitParts = (
    controller: ReadableStreamDefaultController<CortiUIMessageChunk>,
    parts: Part[],
    sourceId: string,
    lastChunk: boolean,
  ) => {
    const text = parts
      .filter((part) => part.content?.$case === 'text')
      .map((part) => part.content?.value)
      .join(' ');
    if (text) {
      const id = sourceId || `text-${++sequence}`;
      if (!activeTextIds.has(id)) {
        activeTextIds.add(id);
        controller.enqueue({ type: 'text-start', id });
      }
      controller.enqueue({ type: 'text-delta', id, delta: text });
      if (lastChunk) {
        controller.enqueue({ type: 'text-end', id });
        activeTextIds.delete(id);
      }
    }
    for (const part of parts.filter((item) => item.content?.$case !== 'text')) {
      if (part.content?.$case === 'data') {
        controller.enqueue({
          type: 'data-json',
          id: `data-${++sequence}`,
          data: part.content.value as JSONValue,
        } as CortiUIMessageChunk);
      } else if (part.content?.$case === 'url') {
        controller.enqueue({
          type: 'file',
          url: part.content.value,
          mediaType: part.mediaType || 'application/octet-stream',
        });
      } else if (part.content?.$case === 'raw') {
        controller.enqueue({
          type: 'file',
          url: `data:${part.mediaType || 'application/octet-stream'};base64,${bytesToBase64(part.content.value)}`,
          mediaType: part.mediaType || 'application/octet-stream',
        });
      }
    }
  };

  const emitStatus = (
    controller: ReadableStreamDefaultController<CortiUIMessageChunk>,
    status: TaskStatus,
  ) => {
    const data: CortiStatusUpdate = {
      state: stateLabel(status.state),
      ...(statusMessage(status) ? { message: statusMessage(status) } : {}),
    };
    controller.enqueue({
      type: 'data-status-update',
      id: `status-${++sequence}`,
      data,
    } as CortiUIMessageChunk);
  };

  const setMessageMetadata = (message: Message, state: string) => {
    metadata = {
      contextId: message.contextId || metadata.contextId,
      taskId: message.taskId || metadata.taskId,
      credits: typeof message.metadata?.credits === 'number'
        ? message.metadata.credits
        : metadata.credits,
      state,
    };
  };

  return new ReadableStream<CortiUIMessageChunk>({
    async start(controller) {
      try {
        options.callbacks?.onStart?.();
        controller.enqueue({ type: 'start', messageId: messageId() });
        for await (const event of stream) {
          options.callbacks?.onEvent?.(event);
          const payload = event.payload;
          if (!payload) continue;
          if (payload.$case === 'task') {
            const task = payload.value;
            const status = task.status;
            metadata = {
              contextId: task.contextId,
              taskId: task.id,
              credits: typeof task.metadata?.credits === 'number'
                ? task.metadata.credits
                : metadata.credits,
              state: status ? stateLabel(status.state) : 'unknown',
            };
            if (status && !SETTLED_STATES.has(status.state)) emitStatus(controller, status);
            if (status?.message && SETTLED_STATES.has(status.state)) {
              emitParts(controller, status.message.parts, status.message.messageId, true);
            }
            if (status && SETTLED_STATES.has(status.state)) finalStatus = status;
          } else if (payload.$case === 'message') {
            const message = payload.value;
            setMessageMetadata(message, 'completed');
            emitParts(controller, message.parts, message.messageId, true);
            finalStatus = {
              state: TaskState.TASK_STATE_COMPLETED,
              message,
              timestamp: undefined,
            };
          } else if (payload.$case === 'statusUpdate') {
            const update = payload.value;
            const status = update.status;
            if (!status) continue;
            metadata = {
              contextId: update.contextId || metadata.contextId,
              taskId: update.taskId || metadata.taskId,
              credits: typeof update.metadata?.credits === 'number'
                ? update.metadata.credits
                : metadata.credits,
              state: stateLabel(status.state),
            };
            if (!SETTLED_STATES.has(status.state)) emitStatus(controller, status);
            if (status.message && SETTLED_STATES.has(status.state)) {
              emitParts(controller, status.message.parts, status.message.messageId, true);
            }
            if (SETTLED_STATES.has(status.state)) finalStatus = status;
          } else if (payload.$case === 'artifactUpdate') {
            const update = payload.value;
            if (update.artifact) {
              metadata = {
                ...metadata,
                contextId: update.contextId || metadata.contextId,
                taskId: update.taskId || metadata.taskId,
                credits: typeof update.metadata?.credits === 'number'
                  ? update.metadata.credits
                  : metadata.credits,
              };
              emitParts(
                controller,
                update.artifact.parts,
                update.artifact.artifactId,
                update.lastChunk,
              );
            }
          }
        }
        closeActiveText(controller);
        if (!finalStatus || !SETTLED_STATES.has(finalStatus.state)) {
          throw new Error('A2A stream ended before a settled status');
        }
        options.callbacks?.onFinish?.(finalStatus);
        controller.enqueue({ type: 'message-metadata', messageMetadata: metadata });
        controller.enqueue({
          type: 'finish',
          finishReason: 'stop',
          messageMetadata: { credits: metadata.credits },
        });
        controller.close();
      } catch (cause) {
        closeActiveText(controller);
        if (cause instanceof Error && cause.name === 'AbortError') {
          controller.enqueue({ type: 'abort' });
          controller.close();
          return;
        }
        const safe = new Error('A2A stream conversion failed');
        try {
          options.callbacks?.onError?.(safe);
        } catch {
          // Callback failures must not replace the stable adapter error.
        }
        controller.enqueue({ type: 'error', errorText: safe.message });
        controller.enqueue({ type: 'finish', finishReason: 'error' });
        controller.close();
      }
    },
  });
}
