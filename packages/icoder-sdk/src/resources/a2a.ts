import axios, { type AxiosInstance } from 'axios';
import { AsyncCursorPager } from '../pagination.js';
import { requestConfig, type iCoDerRequestOptions } from '../request-options.js';

export interface A2ATextPart {
  kind: 'text';
  text: string;
  metadata?: Record<string, unknown>;
}

export interface A2ADataPart {
  kind: 'data';
  data: { schema: string; value?: unknown; [key: string]: unknown };
  metadata?: Record<string, unknown>;
}

export type A2APart = A2ATextPart | A2ADataPart;

export interface A2AMessage {
  kind: 'message';
  role: 'user' | 'agent' | 'orchestrator';
  messageId: string;
  contextId: string;
  parts: A2APart[] | Array<Record<string, unknown>>;
  metadata: Record<string, unknown>;
}

export interface A2AContextItem extends Record<string, unknown> {
  kind: 'message' | 'task';
  contextId: string;
}

export interface A2AContext {
  id: string;
  items: A2AContextItem[];
}

export interface A2AContextDeleted {
  kind: 'context';
  contextId: string;
  deleted: boolean;
  reason: string;
}

export interface A2ASendOptions {
  contextId?: string;
  messageId?: string;
  metadata?: Record<string, unknown>;
}

export interface A2AStreamOptions extends A2ASendOptions {
  signal?: AbortSignal;
}

export interface A2AV1Part extends Record<string, unknown> {
  text?: string;
  data?: unknown;
  /** Base64-encoded inline file output. */
  raw?: string;
  /** HTTPS file reference; the SDK does not dereference it automatically. */
  url?: string;
  filename?: string;
  mediaType?: string;
  metadata?: Record<string, unknown>;
}

export interface A2AV1Message extends Record<string, unknown> {
  role: 'ROLE_USER' | 'ROLE_AGENT';
  messageId: string;
  contextId: string;
  taskId?: string;
  parts: A2AV1Part[];
  metadata: Record<string, unknown>;
}

export type A2AV1TaskState =
  | 'TASK_STATE_UNSPECIFIED'
  | 'TASK_STATE_SUBMITTED'
  | 'TASK_STATE_WORKING'
  | 'TASK_STATE_COMPLETED'
  | 'TASK_STATE_FAILED'
  | 'TASK_STATE_CANCELED'
  | 'TASK_STATE_REJECTED'
  | 'TASK_STATE_INPUT_REQUIRED'
  | 'TASK_STATE_AUTH_REQUIRED';

export interface A2AV1Task extends Record<string, unknown> {
  id: string;
  contextId: string;
  status: {
    state: A2AV1TaskState;
    timestamp?: string | null;
    message?: A2AV1Message;
  };
  artifacts: A2AV1Artifact[];
  history: A2AV1Message[];
  metadata: Record<string, unknown>;
}

export interface A2AV1Artifact extends Record<string, unknown> {
  artifactId: string;
  name?: string | null;
  description?: string | null;
  parts: A2AV1Part[];
  metadata: Record<string, unknown>;
  extensions: string[];
}

export interface A2AV1TaskStatusUpdateEvent {
  taskId: string;
  contextId: string;
  status: A2AV1Task['status'];
  metadata: Record<string, unknown>;
}

export interface A2AV1TaskArtifactUpdateEvent {
  taskId: string;
  contextId: string;
  artifact: A2AV1Artifact;
  append: boolean;
  lastChunk: boolean;
  metadata: Record<string, unknown>;
}

export type A2AV1StreamResponse =
  | { task: A2AV1Task }
  | { message: A2AV1Message }
  | { statusUpdate: A2AV1TaskStatusUpdateEvent }
  | { artifactUpdate: A2AV1TaskArtifactUpdateEvent };

export interface A2AV1SendResult {
  message?: A2AV1Message;
  task?: A2AV1Task;
}

export interface A2AV1TaskList {
  tasks: A2AV1Task[];
  nextPageToken: string;
  pageSize: number;
  totalSize: number;
}

export interface AgenticContextSummary {
  id: string;
  agentId: string;
  taskCount: number;
  createdAt: string;
  updatedAt: string;
  expiresAt: string | null;
}

export interface AgenticContextResource extends AgenticContextSummary {
  tasks: A2AV1Task[];
}

export interface AgenticContextPage {
  contexts: AgenticContextSummary[];
  nextPageToken: string | null;
  totalSize: number;
}

export interface AgenticTaskPage {
  tasks: A2AV1Task[];
  nextPageToken: string | null;
  totalSize: number;
}

export interface AgenticArtifact extends A2AV1Artifact {}

export type AgenticArtifactObjectStatus = 'quarantined' | 'available' | 'rejected';
export type AgenticArtifactObjectClassification = 'deidentified' | 'clinical-sensitive';
export type AgenticArtifactObjectPurpose =
  | 'treatment'
  | 'payment'
  | 'healthcare_operations';

export interface AgenticArtifactObjectUpload {
  /** Canonical padded Base64, bounded by the service to 5 MiB decoded. */
  raw: string;
  filename: string;
  mediaType: 'text/plain' | 'application/json' | 'application/pdf';
  dataClassification?: AgenticArtifactObjectClassification;
}

export interface AgenticArtifactObject {
  objectId: string;
  artifactId: string;
  filename: string;
  mediaType: string;
  sizeBytes: number;
  sha256: string;
  status: AgenticArtifactObjectStatus;
  malwareScanStatus: 'pending' | 'clean' | 'infected' | 'error';
  dlpScanStatus: 'pending' | 'clear' | 'restricted' | 'blocked' | 'error';
  dataClassification: AgenticArtifactObjectClassification;
  rejectionCode: string | null;
  scanEngine: string;
  createdAt: string;
  scannedAt: string | null;
}

export interface AgenticArtifactObjectPage {
  objects: AgenticArtifactObject[];
  totalSize: number;
}

export interface AgenticArtifactDownloadAuthorization {
  objectId: string;
  expiresAt: string;
  singleUse: true;
  purposeOfUse: AgenticArtifactObjectPurpose;
  part: A2AV1Part & { url: string };
}

export interface AgenticContextListOptions {
  agentId?: string;
  from?: string;
  to?: string;
  pageSize?: number;
  pageToken?: string;
}

export interface AgenticContextTaskListOptions {
  pageSize?: number;
  pageToken?: string;
  historyLength?: number;
}

export interface A2AV1SendOptions extends A2ASendOptions {
  /** Resume a previously interrupted A2A v1 Task. */
  taskId?: string;
  returnImmediately?: boolean;
  acceptedOutputModes?: string[];
}

export interface A2AV1StreamOptions extends A2AV1SendOptions {
  signal?: AbortSignal;
}

export interface A2AV1TaskListOptions {
  contextId?: string;
  status?: A2AV1TaskState;
  pageSize?: number;
  pageToken?: string;
  statusTimestampAfter?: string;
  includeArtifacts?: boolean;
}

export interface A2AV1TaskIteratorOptions extends Omit<A2AV1TaskListOptions, 'pageToken'> {
  initialPageToken?: string;
  maxPages?: number;
}

export interface A2AV1SubscribeOptions {
  afterSequence?: number;
  lastEventId?: string;
  signal?: AbortSignal;
}

export interface AgenticTracePage {
  traces: Array<{
    trace: { id: string; name: string; start_time: string; thread_id: string };
    spans: Array<{
      name: string;
      span_id: string;
      parent_span_id?: string | null;
      start_time: string;
      attributes: Record<string, unknown>;
    }>;
  }>;
  nextPageToken: string | null;
  totalSize: number | null;
}

export type AgentUsageGranularity = 'minute' | 'hour' | 'day' | 'week';

export interface AgenticAgentUsage {
  granularity: 'day';
  from: string;
  to: string;
  totals: { invocations: number; uniqueContexts: number };
  buckets: Array<{
    periodStart: string;
    periodEnd: string;
    invocations: number;
    uniqueContexts: number;
  }>;
}

export interface A2AV1AgentCard {
  name: string;
  description: string;
  supportedInterfaces: Array<{
    url: string;
    protocolBinding: 'JSONRPC' | 'HTTP+JSON' | 'GRPC' | string;
    protocolVersion: string;
    tenant?: string;
  }>;
  provider?: { url: string; organization: string };
  version: string;
  documentationUrl?: string;
  capabilities: {
    streaming?: boolean;
    pushNotifications?: boolean;
    extendedAgentCard?: boolean;
    extensions?: Array<Record<string, unknown>>;
  };
  securitySchemes?: Record<string, unknown>;
  securityRequirements?: Array<Record<string, unknown>>;
  defaultInputModes: string[];
  defaultOutputModes: string[];
  skills: Array<{
    id: string;
    name: string;
    description: string;
    tags: string[];
    examples?: string[];
    inputModes?: string[];
    outputModes?: string[];
  }>;
}

export type AgenticFeedbackLabel =
  | 'correct' | 'complete' | 'helpful' | 'wellPresented' | 'efficient'
  | 'incorrect' | 'missingInformation' | 'irrelevant' | 'misunderstoodRequest'
  | 'unsupportedClaim' | 'unsafeOrInappropriate' | 'poorlyPresented' | 'tooVerbose'
  | 'other';

export interface AgenticFeedbackInput {
  rating: { scale: 'binary'; value: 0 | 1 };
  labels?: AgenticFeedbackLabel[];
  reason?: string;
  target?: { messageId: string };
  metadata?: {
    collectionMethod?: 'thumbs' | 'survey' | 'caseReview' | 'automatedEvaluation' | 'other';
    clientReference?: string;
    actor?: { externalId: string };
  };
}

export interface AgenticFeedback {
  id: string;
  taskId: string;
  rating: { scale: 'binary'; value: 0 | 1 };
  normalizedScore: number;
  labels: AgenticFeedbackLabel[];
  reason: string | null;
  createdAt: string;
  target?: { messageId: string } | null;
}

export interface AgenticFeedbackList { feedbacks: AgenticFeedback[] }

export interface FeedbackTrainingAuthorizationInput {
  purposeOfUse: 'quality_improvement';
  dataScope: 'feedback_metadata_only';
  expiresAt: string;
  approvalReference: string;
  acknowledgement: true;
}

export interface FeedbackTrainingAuthorization {
  id: string;
  feedbackId: string;
  taskId: string;
  trainingAuthorized: boolean;
  authorizationStatus: 'active' | 'revoked' | 'expired' | 'stale';
  purposeOfUse: 'quality_improvement';
  dataScope: 'feedback_metadata_only';
  expiresAt: string;
  createdAt: string;
  updatedAt: string;
  revokedAt: string | null;
  version: number;
}

interface JsonRpcError {
  code: number;
  message: string;
  data?: unknown;
  details?: unknown;
}

interface JsonRpcEnvelope<T> {
  jsonrpc: '2.0';
  id: string | number | null;
  result?: T;
  error?: JsonRpcError;
}

/** Safe protocol error: server details/body are deliberately not retained. */
export class A2AProtocolError extends Error {
  readonly jsonRpcCode: number;
  readonly a2aErrorCode?: string;
  readonly httpStatus?: number;

  constructor(error: JsonRpcError, httpStatus?: number) {
    const businessCode = protocolReason(error);
    super(`iCoDer A2A request failed (${businessCode || error.code})`);
    this.name = 'A2AProtocolError';
    this.jsonRpcCode = error.code;
    this.a2aErrorCode = businessCode;
    this.httpStatus = httpStatus;
  }
}

/** Safe HTTP error: Axios request/response objects are never retained. */
export class A2ATransportError extends Error {
  readonly httpStatus?: number;

  constructor(httpStatus?: number) {
    super(`iCoDer A2A transport failed${httpStatus ? ` (HTTP ${httpStatus})` : ''}`);
    this.name = 'A2ATransportError';
    this.httpStatus = httpStatus;
  }
}

function requestId(prefix: string): string {
  const randomUUID = globalThis.crypto?.randomUUID?.bind(globalThis.crypto);
  return `${prefix}-${randomUUID ? randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`}`;
}

function protocolErrorFrom(value: unknown, httpStatus?: number): A2AProtocolError | undefined {
  if (!value || typeof value !== 'object') return undefined;
  const envelope = value as Partial<JsonRpcEnvelope<unknown>>;
  if (!envelope.error || typeof envelope.error.code !== 'number') return undefined;
  return new A2AProtocolError(envelope.error, httpStatus);
}

function protocolReason(error: JsonRpcError): string | undefined {
  if (error.data && typeof error.data === 'object' && !Array.isArray(error.data)) {
    const value = (error.data as Record<string, unknown>).a2a_error_code;
    if (typeof value === 'string') return value;
  }
  const details = Array.isArray(error.data)
    ? error.data
    : Array.isArray(error.details)
      ? error.details
      : [];
  for (const detail of details) {
    if (detail && typeof detail === 'object') {
      const reason = (detail as Record<string, unknown>).reason;
      if (typeof reason === 'string') return reason;
    }
  }
  return undefined;
}

export class A2AResource {
  constructor(
    private http: AxiosInstance,
    private getAccessToken?: () => string | undefined,
  ) {}

  async messageSend(
    agentId: string,
    parts: string | A2APart[],
    options: A2ASendOptions = {},
    requestOptions?: iCoDerRequestOptions,
  ): Promise<A2AMessage> {
    const rpcId = requestId('rpc');
    const messageId = options.messageId || requestId('msg');
    const normalizedParts: A2APart[] = typeof parts === 'string'
      ? [{ kind: 'text', text: parts }]
      : parts;
    try {
      const response = await this.http.post<JsonRpcEnvelope<A2AMessage>>(
        `/api/icoder/agents/${encodeURIComponent(agentId)}/v1/message:send`,
        {
          jsonrpc: '2.0',
          id: rpcId,
          method: 'message/send',
          params: {
            message: {
              role: 'user',
              parts: normalizedParts,
              messageId,
              ...(options.contextId ? { contextId: options.contextId } : {}),
              ...(options.metadata ? { metadata: options.metadata } : {}),
            },
          },
        },
        requestConfig(
          requestOptions,
          {},
          { 'A2A-Protocol-Version': '0.3' },
        ),
      );
      const protocolError = protocolErrorFrom(response.data, response.status);
      if (protocolError) throw protocolError;
      if (!response.data.result) throw new Error('iCoDer returned an incomplete A2A response');
      return response.data.result;
    } catch (error) {
      if (error instanceof A2AProtocolError) throw error;
      if (axios.isAxiosError(error)) {
        const protocolError = protocolErrorFrom(error.response?.data, error.response?.status);
        if (protocolError) throw protocolError;
        throw new A2ATransportError(error.response?.status);
      }
      throw error;
    }
  }

  /** Open the authenticated A2A v0.3 SSE stream without buffering the turn. */
  async messageStream(
    agentId: string,
    parts: string | A2APart[],
    options: A2AStreamOptions = {},
    requestOptions?: iCoDerRequestOptions,
  ): Promise<ReadableStream<Uint8Array>> {
    const normalizedParts: A2APart[] = typeof parts === 'string'
      ? [{ kind: 'text', text: parts }]
      : parts;
    const response = await this.fetchStream(
      `/api/icoder/agents/${encodeURIComponent(agentId)}/v1/message:stream`,
      {
        method: 'POST',
        body: JSON.stringify({
          jsonrpc: '2.0',
          id: requestId('rpc'),
          method: 'message/stream',
          params: {
            message: {
              role: 'user',
              parts: normalizedParts,
              messageId: options.messageId || requestId('msg'),
              ...(options.contextId ? { contextId: options.contextId } : {}),
              ...(options.metadata ? { metadata: options.metadata } : {}),
            },
          },
        }),
      },
      requestOptions,
      {},
      {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
        'A2A-Protocol-Version': '0.3',
      },
      options.signal,
    );
    if (!response.ok) throw new A2ATransportError(response.status);
    if (!response.headers.get('content-type')?.startsWith('text/event-stream')) {
      throw new A2ATransportError(response.status);
    }
    if (!response.body) throw new A2ATransportError(response.status);
    return response.body;
  }

  async messageSendV1(
    agentId: string,
    parts: string | A2AV1Part[],
    options: A2AV1SendOptions = {},
    requestOptions?: iCoDerRequestOptions,
  ): Promise<A2AV1SendResult> {
    const normalizedParts: A2AV1Part[] = typeof parts === 'string'
      ? [{ text: parts, mediaType: 'text/plain' }]
      : parts;
    const result = await this.v1Request<A2AV1SendResult>(
      'post',
      `/api/v2/agentic/agents/${encodeURIComponent(agentId)}/message:send`,
      {
        message: {
          role: 'ROLE_USER',
          parts: normalizedParts,
          messageId: options.messageId || requestId('msg'),
          ...(options.contextId ? { contextId: options.contextId } : {}),
          ...(options.taskId ? { taskId: options.taskId } : {}),
          ...(options.metadata ? { metadata: options.metadata } : {}),
        },
        configuration: {
          returnImmediately: options.returnImmediately ?? false,
          ...(options.acceptedOutputModes
            ? { acceptedOutputModes: options.acceptedOutputModes }
            : {}),
        },
      },
      undefined,
      requestOptions,
    );
    if (!result.message && !result.task) {
      throw new Error('iCoDer returned an incomplete A2A v1 response');
    }
    return result;
  }

  /** Start a durable A2A v1 Task and consume its standard SSE updates. */
  async messageStreamV1(
    agentId: string,
    parts: string | A2AV1Part[],
    options: A2AV1StreamOptions = {},
    requestOptions?: iCoDerRequestOptions,
  ): Promise<ReadableStream<Uint8Array>> {
    const normalizedParts: A2AV1Part[] = typeof parts === 'string'
      ? [{ text: parts, mediaType: 'text/plain' }]
      : parts;
    const response = await this.fetchStream(
      `/api/v2/agentic/agents/${encodeURIComponent(agentId)}/message:stream`,
      {
        method: 'POST',
        body: JSON.stringify({
          message: {
            role: 'ROLE_USER',
            parts: normalizedParts,
            messageId: options.messageId || requestId('msg'),
            ...(options.contextId ? { contextId: options.contextId } : {}),
            ...(options.taskId ? { taskId: options.taskId } : {}),
            ...(options.metadata ? { metadata: options.metadata } : {}),
          },
          configuration: {
            returnImmediately: options.returnImmediately ?? false,
            ...(options.acceptedOutputModes
              ? { acceptedOutputModes: options.acceptedOutputModes }
              : {}),
          },
        }),
      },
      requestOptions,
      {},
      {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
        'A2A-Version': '1.0',
      },
      options.signal,
    );
    if (!response.ok) {
      let payload: unknown;
      try {
        payload = await response.json();
      } catch {
        payload = undefined;
      }
      const protocolError = protocolErrorFrom(payload, response.status);
      if (protocolError) throw protocolError;
      throw new A2ATransportError(response.status);
    }
    if (!response.headers.get('content-type')?.startsWith('text/event-stream')) {
      throw new A2ATransportError(response.status);
    }
    if (!response.body) throw new A2ATransportError(response.status);
    return response.body;
  }

  async getTaskV1(
    agentId: string,
    taskId: string,
    requestOptions?: iCoDerRequestOptions,
  ): Promise<A2AV1Task> {
    return this.v1Request<A2AV1Task>(
      'get',
      `/api/v2/agentic/agents/${encodeURIComponent(agentId)}/tasks/${encodeURIComponent(taskId)}`,
      undefined,
      undefined,
      requestOptions,
    );
  }

  async listTasksV1(
    agentId: string,
    options: A2AV1TaskListOptions = {},
    requestOptions?: iCoDerRequestOptions,
  ): Promise<A2AV1TaskList> {
    const result = await this.v1Request<A2AV1TaskList>(
      'get',
      `/api/v2/agentic/agents/${encodeURIComponent(agentId)}/tasks`,
      undefined,
      {
        pageSize: options.pageSize ?? 50,
        includeArtifacts: options.includeArtifacts ?? false,
        ...(options.contextId ? { contextId: options.contextId } : {}),
        ...(options.status ? { status: options.status } : {}),
        ...(options.pageToken ? { pageToken: options.pageToken } : {}),
        ...(options.statusTimestampAfter
          ? { statusTimestampAfter: options.statusTimestampAfter }
          : {}),
      },
      requestOptions,
    );
    if (!Array.isArray(result.tasks)) {
      throw new Error('iCoDer returned an incomplete A2A v1 Task list');
    }
    return result;
  }

  /** Lazily iterate every Task while detecting repeated or unbounded cursors. */
  iterateTasksV1(
    agentId: string,
    options: A2AV1TaskIteratorOptions = {},
    requestOptions?: iCoDerRequestOptions,
  ): AsyncCursorPager<A2AV1TaskList, A2AV1Task> {
    const { initialPageToken, maxPages, ...listOptions } = options;
    return new AsyncCursorPager(
      (pageToken) => this.listTasksV1(agentId, { ...listOptions, pageToken }, requestOptions),
      {
        items: (page) => page.tasks,
        nextPageToken: (page) => page.nextPageToken,
      },
      { initialPageToken, maxPages },
    );
  }

  async cancelTaskV1(
    agentId: string,
    taskId: string,
    requestOptions?: iCoDerRequestOptions,
  ): Promise<A2AV1Task> {
    return this.v1Request<A2AV1Task>(
      'post',
      `/api/v2/agentic/agents/${encodeURIComponent(agentId)}/tasks/${encodeURIComponent(taskId)}:cancel`,
      {},
      undefined,
      requestOptions,
    );
  }

  async waitTaskV1(
    agentId: string,
    taskId: string,
    options: { timeoutMs?: number; pollIntervalMs?: number; signal?: AbortSignal } = {},
    requestOptions?: iCoDerRequestOptions,
  ): Promise<A2AV1Task> {
    const timeoutMs = options.timeoutMs ?? 60_000;
    const pollIntervalMs = options.pollIntervalMs ?? 250;
    if (timeoutMs <= 0 || pollIntervalMs <= 0) {
      throw new RangeError('timeoutMs and pollIntervalMs must be positive');
    }
    const deadline = Date.now() + timeoutMs;
    const settled: ReadonlySet<A2AV1TaskState> = new Set([
      'TASK_STATE_COMPLETED',
      'TASK_STATE_FAILED',
      'TASK_STATE_CANCELED',
      'TASK_STATE_REJECTED',
      'TASK_STATE_INPUT_REQUIRED',
      'TASK_STATE_AUTH_REQUIRED',
    ]);
    while (true) {
      if (options.signal?.aborted) throw new Error('A2A v1 Task wait aborted');
      const task = await this.getTaskV1(agentId, taskId, requestOptions);
      if (settled.has(task.status.state)) return task;
      const remaining = deadline - Date.now();
      if (remaining <= 0) {
        throw new Error(`A2A v1 Task ${JSON.stringify(taskId)} did not reach a settled state`);
      }
      await new Promise<void>((resolve) => {
        setTimeout(resolve, Math.min(pollIntervalMs, remaining));
      });
    }
  }

  async subscribeTaskV1(
    agentId: string,
    taskId: string,
    options: A2AV1SubscribeOptions = {},
    requestOptions?: iCoDerRequestOptions,
  ): Promise<ReadableStream<Uint8Array>> {
    const afterSequence = options.afterSequence ?? 0;
    if (!Number.isInteger(afterSequence) || afterSequence < 0) {
      throw new RangeError('afterSequence must be a non-negative integer');
    }
    const response = await this.fetchStream(
      `/api/v2/agentic/agents/${encodeURIComponent(agentId)}/tasks/` +
        `${encodeURIComponent(taskId)}:subscribe`,
      {
        method: 'GET',
      },
      requestOptions,
      { afterSequence },
      {
        Accept: 'text/event-stream',
        'A2A-Version': '1.0',
        ...(options.lastEventId ? { 'Last-Event-ID': options.lastEventId } : {}),
      },
      options.signal,
    );
    if (!response.ok) {
      let payload: unknown;
      try {
        payload = await response.json();
      } catch {
        payload = undefined;
      }
      const protocolError = protocolErrorFrom(payload, response.status);
      if (protocolError) throw protocolError;
      throw new A2ATransportError(response.status);
    }
    if (!response.headers.get('content-type')?.startsWith('text/event-stream')) {
      throw new A2ATransportError(response.status);
    }
    if (!response.body) throw new A2ATransportError(response.status);
    return response.body;
  }

  async exportContextTraces(
    contextId: string,
    options: { pageSize?: number; pageToken?: string } = {},
    requestOptions?: iCoDerRequestOptions,
  ): Promise<AgenticTracePage> {
    return this.v1Request<AgenticTracePage>(
      'get',
      `/api/v2/agentic/contexts/${encodeURIComponent(contextId)}/trace`,
      undefined,
      {
        pageSize: options.pageSize ?? 50,
        ...(options.pageToken ? { pageToken: options.pageToken } : {}),
      },
      requestOptions,
    );
  }

  iterateContextTraces(
    contextId: string,
    options: { pageSize?: number; initialPageToken?: string; maxPages?: number } = {},
    requestOptions?: iCoDerRequestOptions,
  ): AsyncCursorPager<AgenticTracePage, AgenticTracePage['traces'][number]> {
    const { pageSize, initialPageToken, maxPages } = options;
    return new AsyncCursorPager(
      (pageToken) => this.exportContextTraces(
        contextId,
        { pageSize, pageToken },
        requestOptions,
      ),
      {
        items: (page) => page.traces,
        nextPageToken: (page) => page.nextPageToken,
      },
      { initialPageToken, maxPages },
    );
  }

  /** List the authenticated tenant's first-class Agentic v2 Context resources. */
  async listContextsV2(
    options: AgenticContextListOptions = {},
    requestOptions?: iCoDerRequestOptions,
  ): Promise<AgenticContextPage> {
    return this.v1Request<AgenticContextPage>(
      'get',
      '/api/v2/agentic/contexts',
      undefined,
      {
        pageSize: options.pageSize ?? 50,
        ...(options.agentId ? { agentId: options.agentId } : {}),
        ...(options.from ? { from: options.from } : {}),
        ...(options.to ? { to: options.to } : {}),
        ...(options.pageToken ? { pageToken: options.pageToken } : {}),
      },
      requestOptions,
    );
  }

  iterateContextsV2(
    options: Omit<AgenticContextListOptions, 'pageToken'> & {
      initialPageToken?: string;
      maxPages?: number;
    } = {},
    requestOptions?: iCoDerRequestOptions,
  ): AsyncCursorPager<AgenticContextPage, AgenticContextSummary> {
    const { initialPageToken, maxPages, ...listOptions } = options;
    return new AsyncCursorPager(
      (pageToken) => this.listContextsV2({ ...listOptions, pageToken }, requestOptions),
      {
        items: (page) => page.contexts,
        nextPageToken: (page) => page.nextPageToken,
      },
      { initialPageToken, maxPages },
    );
  }

  async getContextV2(
    contextId: string,
    options: { historyLength?: number } = {},
    requestOptions?: iCoDerRequestOptions,
  ): Promise<AgenticContextResource> {
    return this.v1Request<AgenticContextResource>(
      'get',
      `/api/v2/agentic/contexts/${encodeURIComponent(contextId)}`,
      undefined,
      options.historyLength === undefined
        ? undefined
        : { historyLength: options.historyLength },
      requestOptions,
    );
  }

  async deleteContextV2(
    contextId: string,
    requestOptions?: iCoDerRequestOptions,
  ): Promise<void> {
    await this.v1Request<void>(
      'delete',
      `/api/v2/agentic/contexts/${encodeURIComponent(contextId)}`,
      undefined,
      undefined,
      requestOptions,
    );
  }

  async listContextTasksV2(
    contextId: string,
    options: AgenticContextTaskListOptions = {},
    requestOptions?: iCoDerRequestOptions,
  ): Promise<AgenticTaskPage> {
    return this.v1Request<AgenticTaskPage>(
      'get',
      `/api/v2/agentic/contexts/${encodeURIComponent(contextId)}/tasks`,
      undefined,
      {
        pageSize: options.pageSize ?? 50,
        historyLength: options.historyLength ?? 0,
        ...(options.pageToken ? { pageToken: options.pageToken } : {}),
      },
      requestOptions,
    );
  }

  iterateContextTasksV2(
    contextId: string,
    options: Omit<AgenticContextTaskListOptions, 'pageToken'> & {
      initialPageToken?: string;
      maxPages?: number;
    } = {},
    requestOptions?: iCoDerRequestOptions,
  ): AsyncCursorPager<AgenticTaskPage, A2AV1Task> {
    const { initialPageToken, maxPages, ...listOptions } = options;
    return new AsyncCursorPager(
      (pageToken) => this.listContextTasksV2(
        contextId,
        { ...listOptions, pageToken },
        requestOptions,
      ),
      {
        items: (page) => page.tasks,
        nextPageToken: (page) => page.nextPageToken,
      },
      { initialPageToken, maxPages },
    );
  }

  async getContextTaskV2(
    contextId: string,
    taskId: string,
    options: { historyLength?: number } = {},
    requestOptions?: iCoDerRequestOptions,
  ): Promise<A2AV1Task> {
    return this.v1Request<A2AV1Task>(
      'get',
      `/api/v2/agentic/contexts/${encodeURIComponent(contextId)}/tasks/` +
        encodeURIComponent(taskId),
      undefined,
      options.historyLength === undefined
        ? undefined
        : { historyLength: options.historyLength },
      requestOptions,
    );
  }

  async getTaskArtifactV2(
    contextId: string,
    taskId: string,
    artifactId: string,
    requestOptions?: iCoDerRequestOptions,
  ): Promise<AgenticArtifact> {
    return this.v1Request<AgenticArtifact>(
      'get',
      `/api/v2/agentic/contexts/${encodeURIComponent(contextId)}/tasks/` +
        `${encodeURIComponent(taskId)}/artifacts/${encodeURIComponent(artifactId)}`,
      undefined,
      undefined,
      requestOptions,
    );
  }

  async uploadTaskArtifactObjectV2(
    contextId: string,
    taskId: string,
    artifactId: string,
    input: AgenticArtifactObjectUpload,
    requestOptions?: iCoDerRequestOptions,
  ): Promise<AgenticArtifactObject> {
    return this.v1Request<AgenticArtifactObject>(
      'post',
      this.artifactObjectRoot(contextId, taskId, artifactId),
      input,
      undefined,
      requestOptions,
    );
  }

  async listTaskArtifactObjectsV2(
    contextId: string,
    taskId: string,
    artifactId: string,
    requestOptions?: iCoDerRequestOptions,
  ): Promise<AgenticArtifactObjectPage> {
    return this.v1Request<AgenticArtifactObjectPage>(
      'get',
      this.artifactObjectRoot(contextId, taskId, artifactId),
      undefined,
      undefined,
      requestOptions,
    );
  }

  async authorizeTaskArtifactObjectDownloadV2(
    contextId: string,
    taskId: string,
    artifactId: string,
    objectId: string,
    options: {
      purposeOfUse: AgenticArtifactObjectPurpose;
      expiresInSeconds?: number;
    },
    requestOptions?: iCoDerRequestOptions,
  ): Promise<AgenticArtifactDownloadAuthorization> {
    return this.v1Request<AgenticArtifactDownloadAuthorization>(
      'post',
      `${this.artifactObjectRoot(contextId, taskId, artifactId)}/` +
        `${encodeURIComponent(objectId)}:authorize-download`,
      {
        purposeOfUse: options.purposeOfUse,
        expiresInSeconds: options.expiresInSeconds ?? 60,
      },
      undefined,
      requestOptions,
    );
  }

  /** Download once with this client's Bearer identity; deliberately no retry. */
  async downloadAuthorizedArtifactObjectV2(
    authorization: AgenticArtifactDownloadAuthorization,
    signal?: AbortSignal,
    requestOptions?: iCoDerRequestOptions,
  ): Promise<ArrayBuffer> {
    if (requestOptions?.maxRetries !== undefined && requestOptions.maxRetries !== 0) {
      throw new RangeError('single-use artifact downloads require maxRetries to be 0');
    }
    const baseUrl = new URL(this.http.defaults.baseURL || '');
    const signedUrl = new URL(authorization.part.url, baseUrl);
    if (signedUrl.origin !== baseUrl.origin || signedUrl.username || signedUrl.password) {
      throw new TypeError('artifact download URL must use the configured iCoDer origin');
    }
    if (signedUrl.hash || !signedUrl.pathname.startsWith('/api/v2/agentic/artifact-objects/download/')) {
      throw new TypeError('artifact download URL is outside the managed artifact endpoint');
    }
    if (signal && requestOptions?.abortSignal && signal !== requestOptions.abortSignal) {
      throw new TypeError('artifact download received conflicting abort signals');
    }
    const config = requestConfig(
      { ...requestOptions, maxRetries: 0, abortSignal: requestOptions?.abortSignal ?? signal },
      signedUrl.searchParams,
    );
    try {
      const response = await this.http.get<ArrayBuffer>(signedUrl.pathname, {
        ...config,
        responseType: 'arraybuffer',
      });
      return response.data;
    } catch (error) {
      if (axios.isAxiosError(error)) throw new A2ATransportError(error.response?.status);
      throw error;
    }
  }

  async deleteTaskArtifactObjectV2(
    contextId: string,
    taskId: string,
    artifactId: string,
    objectId: string,
    requestOptions?: iCoDerRequestOptions,
  ): Promise<void> {
    await this.v1Request<void>(
      'delete',
      `${this.artifactObjectRoot(contextId, taskId, artifactId)}/` +
        encodeURIComponent(objectId),
      undefined,
      undefined,
      requestOptions,
    );
  }

  private artifactObjectRoot(
    contextId: string,
    taskId: string,
    artifactId: string,
  ): string {
    return `/api/v2/agentic/contexts/${encodeURIComponent(contextId)}/tasks/` +
      `${encodeURIComponent(taskId)}/artifacts/${encodeURIComponent(artifactId)}/objects`;
  }

  async getAgentUsage(
    agentId: string,
    options: {
      from?: string;
      to?: string;
      granularity?: AgentUsageGranularity;
    } = {},
    requestOptions?: iCoDerRequestOptions,
  ): Promise<AgenticAgentUsage> {
    return this.v1Request<AgenticAgentUsage>(
      'get',
      `/api/v2/agentic/agents/${encodeURIComponent(agentId)}/usage`,
      undefined,
      {
        ...(options.from ? { from: options.from } : {}),
        ...(options.to ? { to: options.to } : {}),
        granularity: options.granularity ?? 'day',
      },
      requestOptions,
    );
  }

  async getAgentCard(
    agentId: string,
    requestOptions?: iCoDerRequestOptions,
  ): Promise<A2AV1AgentCard> {
    return this.v1Request<A2AV1AgentCard>(
      'get',
      `/api/v2/agentic/agents/${encodeURIComponent(agentId)}/` +
        '.well-known/agent-card.json',
      undefined,
      undefined,
      requestOptions,
    );
  }

  async submitTaskFeedback(
    contextId: string,
    taskId: string,
    feedback: AgenticFeedbackInput,
    requestOptions?: iCoDerRequestOptions,
  ): Promise<AgenticFeedback> {
    return this.v1Request<AgenticFeedback>(
      'post',
      `/api/v2/agentic/contexts/${encodeURIComponent(contextId)}/tasks/` +
        `${encodeURIComponent(taskId)}/feedback`,
      feedback,
      undefined,
      requestOptions,
    );
  }

  async listTaskFeedback(
    contextId: string,
    taskId: string,
    requestOptions?: iCoDerRequestOptions,
  ): Promise<AgenticFeedbackList> {
    return this.v1Request<AgenticFeedbackList>(
      'get',
      `/api/v2/agentic/contexts/${encodeURIComponent(contextId)}/tasks/` +
        `${encodeURIComponent(taskId)}/feedback`,
      undefined,
      undefined,
      requestOptions,
    );
  }

  async deleteTaskFeedback(
    contextId: string,
    taskId: string,
    requestOptions?: iCoDerRequestOptions,
  ): Promise<void> {
    await this.v1Request<void>(
      'delete',
      `/api/v2/agentic/contexts/${encodeURIComponent(contextId)}/tasks/` +
        `${encodeURIComponent(taskId)}/feedback`,
      undefined,
      undefined,
      requestOptions,
    );
  }

  async authorizeFeedbackForTraining(
    contextId: string,
    taskId: string,
    feedbackId: string,
    authorization: FeedbackTrainingAuthorizationInput,
    requestOptions?: iCoDerRequestOptions,
  ): Promise<FeedbackTrainingAuthorization> {
    return this.v1Request<FeedbackTrainingAuthorization>(
      'put',
      this.feedbackTrainingAuthorizationPath(contextId, taskId, feedbackId),
      authorization,
      undefined,
      requestOptions,
    );
  }

  async getFeedbackTrainingAuthorization(
    contextId: string,
    taskId: string,
    feedbackId: string,
    requestOptions?: iCoDerRequestOptions,
  ): Promise<FeedbackTrainingAuthorization> {
    return this.v1Request<FeedbackTrainingAuthorization>(
      'get',
      this.feedbackTrainingAuthorizationPath(contextId, taskId, feedbackId),
      undefined,
      undefined,
      requestOptions,
    );
  }

  async revokeFeedbackTrainingAuthorization(
    contextId: string,
    taskId: string,
    feedbackId: string,
    requestOptions?: iCoDerRequestOptions,
  ): Promise<void> {
    await this.v1Request<void>(
      'delete',
      this.feedbackTrainingAuthorizationPath(contextId, taskId, feedbackId),
      undefined,
      undefined,
      requestOptions,
    );
  }

  private feedbackTrainingAuthorizationPath(
    contextId: string,
    taskId: string,
    feedbackId: string,
  ): string {
    return `/api/v2/agentic/contexts/${encodeURIComponent(contextId)}/tasks/` +
      `${encodeURIComponent(taskId)}/feedback/${encodeURIComponent(feedbackId)}/` +
      'training-authorization';
  }

  async getContext(
    agentId: string,
    contextId: string,
    options: { limit?: number; offset?: number } = {},
    requestOptions?: iCoDerRequestOptions,
  ): Promise<A2AContext> {
    try {
      const response = await this.http.get<A2AContext>(
        `/api/icoder/agents/${encodeURIComponent(agentId)}/v1/contexts/${encodeURIComponent(contextId)}`,
        requestConfig(
          requestOptions,
          { limit: options.limit ?? 100, offset: options.offset ?? 0 },
          { 'A2A-Protocol-Version': '0.3' },
        ),
      );
      return response.data;
    } catch (error) {
      if (axios.isAxiosError(error)) {
        const protocolError = protocolErrorFrom(error.response?.data, error.response?.status);
        if (protocolError) throw protocolError;
        throw new A2ATransportError(error.response?.status);
      }
      throw error;
    }
  }

  async deleteContext(
    contextId: string,
    requestOptions?: iCoDerRequestOptions,
  ): Promise<A2AContextDeleted> {
    try {
      const response = await this.http.delete<JsonRpcEnvelope<A2AContextDeleted>>(
        `/api/icoder/contexts/${encodeURIComponent(contextId)}`,
        requestConfig(requestOptions, {}, { 'A2A-Protocol-Version': '0.3' }),
      );
      const protocolError = protocolErrorFrom(response.data, response.status);
      if (protocolError) throw protocolError;
      if (!response.data.result) throw new Error('iCoDer returned an incomplete A2A delete response');
      return response.data.result;
    } catch (error) {
      if (error instanceof A2AProtocolError) throw error;
      if (axios.isAxiosError(error)) {
        const protocolError = protocolErrorFrom(error.response?.data, error.response?.status);
        if (protocolError) throw protocolError;
        throw new A2ATransportError(error.response?.status);
      }
      throw error;
    }
  }

  private async v1Request<T>(
    method: 'get' | 'post' | 'put' | 'delete',
    path: string,
    body?: unknown,
    params?: Record<string, unknown>,
    options?: iCoDerRequestOptions,
  ): Promise<T> {
    try {
      const config = requestConfig(
        options,
        params ?? {},
        { 'A2A-Version': '1.0' },
      );
      const response = method === 'get'
        ? await this.http.get<T>(path, config)
        : method === 'delete'
          ? await this.http.delete<T>(path, config)
          : method === 'put'
            ? await this.http.put<T>(path, body, config)
            : await this.http.post<T>(path, body, config);
      const protocolError = protocolErrorFrom(response.data, response.status);
      if (protocolError) throw protocolError;
      return response.data;
    } catch (error) {
      if (error instanceof A2AProtocolError) throw error;
      if (axios.isAxiosError(error)) {
        const protocolError = protocolErrorFrom(error.response?.data, error.response?.status);
        if (protocolError) throw protocolError;
        throw new A2ATransportError(error.response?.status);
      }
      throw error;
    }
  }

  /** Prepare a same-origin SSE request with bounded Corti-style controls.
   *
   * Streaming POSTs are deliberately never replayed. A non-zero per-request
   * retry count is therefore rejected instead of silently duplicating a turn.
   */
  private async fetchStream(
    path: string,
    init: RequestInit,
    options: iCoDerRequestOptions | undefined,
    domainParams: Record<string, unknown>,
    domainHeaders: Record<string, string>,
    legacySignal?: AbortSignal,
  ): Promise<Response> {
    if (init.method === 'POST' && options?.maxRetries !== undefined && options.maxRetries !== 0) {
      throw new RangeError('streaming POST requests require maxRetries to be 0');
    }
    if (legacySignal && options?.abortSignal && legacySignal !== options.abortSignal) {
      throw new TypeError('stream request received conflicting abort signals');
    }
    const config = requestConfig(options, domainParams, domainHeaders);
    const params = new URLSearchParams();
    if (config.params instanceof URLSearchParams) {
      for (const [key, value] of config.params) params.append(key, value);
    } else if (config.params && typeof config.params === 'object') {
      for (const [key, value] of Object.entries(config.params)) {
        if (value !== undefined && value !== null) params.append(key, String(value));
      }
    }
    const baseURL = (this.http.defaults.baseURL || '').replace(/\/$/, '');
    const query = params.toString();
    const headers = {
      ...((config.headers ?? {}) as Record<string, string>),
    };
    const token = this.getAccessToken?.();
    const fallbackAuthorization = this.http.defaults.headers.common.Authorization;
    const authorization = token
      ? `Bearer ${token}`
      : typeof fallbackAuthorization === 'string'
        ? fallbackAuthorization
        : undefined;
    if (authorization) headers.Authorization = authorization;
    const signals = [options?.abortSignal ?? legacySignal].filter(
      (value): value is AbortSignal => value !== undefined,
    );
    if (config.timeout !== undefined) signals.push(AbortSignal.timeout(config.timeout));
    const signal = signals.length > 1 ? AbortSignal.any(signals) : signals[0];
    return fetch(`${baseURL}${path}${query ? `?${query}` : ''}`, {
      ...init,
      headers,
      signal,
    });
  }
}
