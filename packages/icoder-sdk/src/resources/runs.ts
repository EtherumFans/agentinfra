/**
 * Phase 6 Gate 4 — Runs / RunHistory / RunTrace resources.
 *
 * This module targets the unified agent-run endpoint
 * (POST /api/v1/agents/{agent_id}/run) shipped in Phase 4-F2, plus the
 * observability endpoints (run_history table — alembic 010; run_trace
 * store — alembic 009). The legacy RuntimeResource in runtime.ts targets
 * the older /api/runtime/* surface and is preserved for backward compat.
 *
 * The unified response envelope (Phase 6 Gate 5) carries trace_url so
 * embedders can deep-link to the frontend RunTrace viewer.
 */

import type { AxiosInstance } from 'axios';
import { requestConfig, type iCoDerRequestOptions } from '../request-options.js';

// ── AgentRunResponse (mirror of backend/app/api/agent_run.py:AgentRunResponse) ──

export interface AgentRunCost {
  amount: number;
  currency: 'CNY' | 'USD' | string;
}

export interface AgentRunRequestInput {
  text: string;
  extra?: Record<string, unknown>;
  documents?: AgentRunSourceDocument[];
  upstream_results?: AgentRunUpstreamResult[];
}

export interface AgentRunSourceDocument {
  document_id: string;
  text: string;
  document_version?: string;
  document_type?: string;
  normalization?: 'none' | 'NFC' | 'NFKC';
}

export interface AgentRunUpstreamResult {
  agent_id: string;
  result: Record<string, unknown>;
  run_id: string;
  schema_ref: string;
  /** Server proof returned with the upstream AgentRunResponse. */
  attestation: string;
}

export interface AgentRunRequest {
  input: AgentRunRequestInput;
  runtime_mode?: 'corti_like_fast' | 'medcoder_deep' | string;
  /** Required when authenticating with client_credentials. */
  purpose_of_use?: 'treatment' | 'payment' | 'healthcare_operations'
    | 'quality_improvement' | 'research' | 'public_health';
  include_trace?: boolean;
  include_evidence?: boolean;
}

export interface AgentRunResponse {
  agent_id: string;
  run_id: string;
  trace_id: string;
  /** Phase 6 Gate 5 — frontend deep-link to RunTrace viewer. */
  trace_url: string;
  runtime_mode: string;
  latency_ms: number;
  cost: AgentRunCost | Record<string, unknown>;
  billing?: Record<string, unknown>;
  summary: string;
  result: Record<string, unknown>;
  schema_ref: string;
  result_attestation: string;
  evidence: Array<Record<string, unknown>>;
  warnings: string[];
  manual_review_required: boolean;
  trace_events: Array<Record<string, unknown>>;
  error: boolean;
  error_reason: string;
}

export interface RunStatusResponse {
  run_id: string;
  status: string;
  terminal: boolean;
  agent_id: string;
  trace_id: string;
  runtime_mode: string;
  latency_ms: number;
  cost_amount: number;
  cost_currency: string;
  error: boolean;
  error_reason?: string | null;
  cancel_reason?: string | null;
  cancelled_at?: string | null;
  cancelled_by_user_id?: string | null;
  created_at?: string | null;
  trace_retention_days: number;
  trace_events_purged_at?: string | null;
  trace_events_purged_count: number;
}

export type RunCancelOutcome =
  | 'ALREADY_COMPLETE'
  | 'CANCELLED'
  | 'RECORDED_ONLY';

export interface RunCancelResponse {
  run_id: string;
  outcome: RunCancelOutcome;
  status: string;
  message: string;
  cancel_reason?: string | null;
  cancelled_at?: string | null;
}

export interface RunTraceTokenRenewResponse {
  run_id: string;
  trace_token: string;
  expires_at: number;
  events_url: string;
  trace_url: string;
  trace_retention_days: number;
}

export interface RunSseEvent {
  event: string;
  data: Record<string, unknown>;
  id?: string;
}

export interface RunStreamRetryOptions {
  /** Total connection attempts, including the first one. */
  maxAttempts?: number;
  initialDelayMs?: number;
  maxDelayMs?: number;
  /** Symmetric delay jitter in the range 0..1. Set 0 for deterministic tests. */
  jitterRatio?: number;
  signal?: AbortSignal;
  lastEventId?: string;
  /** Per-connection timeout, cancellation, headers and additive query fields. */
  requestOptions?: iCoDerRequestOptions;
}

export class RunEventStreamError extends Error {
  constructor(
    message: string,
    readonly httpStatus?: number,
    readonly retryable = false,
    readonly errorCode?: string,
  ) {
    super(message);
    this.name = 'RunEventStreamError';
  }
}

export class RunEventRetentionError extends RunEventStreamError {
  constructor(
    httpStatus: number,
    errorCode: string,
    readonly retentionDays?: number,
  ) {
    super(
      `iCoDer run event cursor is outside retention (HTTP ${httpStatus})`,
      httpStatus,
      false,
      errorCode,
    );
    this.name = 'RunEventRetentionError';
  }
}

async function runEventHttpError(response: Response): Promise<RunEventStreamError> {
  let errorCode: string | undefined;
  let retentionDays: number | undefined;
  try {
    const body = await response.json() as Record<string, unknown>;
    const detail = body.detail;
    if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
      const safeDetail = detail as Record<string, unknown>;
      if (typeof safeDetail.code === 'string' && /^[A-Z0-9_]{1,64}$/.test(safeDetail.code)) {
        errorCode = safeDetail.code;
      }
      if (Number.isInteger(safeDetail.retention_days) && Number(safeDetail.retention_days) > 0) {
        retentionDays = Number(safeDetail.retention_days);
      }
    }
  } catch {
    // Never retain or surface arbitrary response bodies; they may contain PHI.
  }
  if (response.status === 410 && errorCode && (
    errorCode === 'SSE_CURSOR_EXPIRED' ||
    errorCode === 'SSE_TRACE_EXPIRED' ||
    errorCode === 'TRACE_EXPIRED'
  )) {
    return new RunEventRetentionError(response.status, errorCode, retentionDays);
  }
  return new RunEventStreamError(
    `iCoDer run event stream failed (HTTP ${response.status})`,
    response.status,
    false,
    errorCode,
  );
}

async function* parseRunSseStream(
  stream: ReadableStream<Uint8Array>,
): AsyncGenerator<RunSseEvent> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  const parseFrame = (frame: string): RunSseEvent | undefined => {
    let event = 'message';
    let id: string | undefined;
    const dataLines: string[] = [];
    for (const line of frame.split(/\r?\n/)) {
      if (line.startsWith(':')) continue;
      if (line.startsWith('event:')) event = line.slice(6).trimStart();
      else if (line.startsWith('id:')) id = line.slice(3).trimStart();
      else if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart());
    }
    if (!dataLines.length) return undefined;
    let data: unknown;
    try {
      data = JSON.parse(dataLines.join('\n'));
    } catch (error) {
      throw new RunEventStreamError('iCoDer returned malformed SSE JSON', undefined, false);
    }
    if (!data || typeof data !== 'object' || Array.isArray(data)) {
      throw new RunEventStreamError('iCoDer returned a non-object SSE event', undefined, false);
    }
    return { event, data: data as Record<string, unknown>, ...(id ? { id } : {}) };
  };

  try {
    for (;;) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      buffer = buffer.replace(/\r\n/g, '\n');
      let boundary = buffer.indexOf('\n\n');
      while (boundary >= 0) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const parsed = parseFrame(frame);
        if (parsed) yield parsed;
        boundary = buffer.indexOf('\n\n');
      }
      if (done) break;
    }
    const trailing = parseFrame(buffer);
    if (trailing) yield trailing;
  } finally {
    reader.releaseLock();
  }
}

function isTerminalRunEvent(event: RunSseEvent): boolean {
  return event.event === 'stream.completed' || event.data.name === 'stream.completed';
}

function validateRetryOptions(options: RunStreamRetryOptions) {
  const maxAttempts = options.maxAttempts ?? 4;
  const initialDelayMs = options.initialDelayMs ?? 250;
  const maxDelayMs = options.maxDelayMs ?? 4000;
  const jitterRatio = options.jitterRatio ?? 0.2;
  if (!Number.isInteger(maxAttempts) || maxAttempts < 1) {
    throw new RangeError('maxAttempts must be a positive integer');
  }
  if (initialDelayMs < 0 || maxDelayMs < 0 || maxDelayMs < initialDelayMs) {
    throw new RangeError('retry delays are invalid');
  }
  if (jitterRatio < 0 || jitterRatio > 1) {
    throw new RangeError('jitterRatio must be between 0 and 1');
  }
  return { maxAttempts, initialDelayMs, maxDelayMs, jitterRatio };
}

function retryDelay(
  retryIndex: number,
  initialDelayMs: number,
  maxDelayMs: number,
  jitterRatio: number,
) {
  const base = Math.min(maxDelayMs, initialDelayMs * (2 ** retryIndex));
  const jitter = 1 + ((Math.random() * 2 - 1) * jitterRatio);
  return Math.max(0, Math.min(maxDelayMs, base * jitter));
}

async function waitForRetry(delayMs: number, signal?: AbortSignal) {
  if (signal?.aborted) throw signal.reason ?? new DOMException('Aborted', 'AbortError');
  if (delayMs === 0) return;
  await new Promise<void>((resolve, reject) => {
    const timer = setTimeout(resolve, delayMs);
    signal?.addEventListener('abort', () => {
      clearTimeout(timer);
      reject(signal.reason ?? new DOMException('Aborted', 'AbortError'));
    }, { once: true });
  });
}

// ── RunHistory (alembic 010) ────────────────────────────────────────────

export interface RunHistoryItem {
  run_id: string;
  agent_id: string;
  agent_ref?: string;
  user_id?: string;
  api_client_id?: string;
  started_at: string;
  finished_at?: string;
  latency_ms: number;
  cost_amount: number;
  cost_currency: string;
  status: 'success' | 'failed' | 'timeout' | string;
  error_reason?: string;
  runtime_mode?: string;
  input_chars?: number;
  output_chars?: number;
}

export interface RunHistoryListResponse {
  items: RunHistoryItem[];
  total: number;
}

// ── RunTrace (alembic 009) ──────────────────────────────────────────────

export interface RunTraceEvent {
  step: string;
  status?: string;
  duration_ms?: number;
  ts?: string;
  metadata?: Record<string, unknown>;
}

export interface RunTraceSummary {
  agent_id: string;
  trace_id: string;
  run_status: string;
  runtime_mode: string;
  latency_ms: number;
  cost: { amount: number; currency: string };
  error: boolean;
  error_reason?: string | null;
  trace_capture_status: string;
  created_at?: string | null;
  review_signal: {
    state: 'required' | 'not_required' | 'not_recorded' | string;
    sources: string[];
    authoritative: false;
  };
}

export interface RunTraceTimelineResponse {
  run_id: string;
  timeline: RunTraceEvent[];
  step_count: number;
  summary: RunTraceSummary;
}

export interface RunTraceRawResponse {
  run_id: string;
  events: RunTraceEvent[];
  summary: RunTraceSummary;
}

// ── A2A v0.3 envelope (mirror of app/icoder/agent_runtime/a2a_facade.py) ──

// ── Resources ───────────────────────────────────────────────────────────

export class RunsResource {
  constructor(private http: AxiosInstance) {}

  /**
   * POST /api/v1/agents/{agent_id}/run — unified agent run facade.
   *
   * Routes to either CodingRuntimeDispatcher (medical-coding-agent) or
   * ProviderRegistry (8 PureLLM agents). Returns the unified envelope
   * with trace_id + trace_url (Phase 6 Gate 5).
   *
   * Idempotency: pass an explicit idempotencyKey to deduplicate. The
   * server-side cache is Phase 7; the client always sends the header.
   */
  run(
    agentId: string,
    body: AgentRunRequest,
    idempotencyKey?: string,
    options?: iCoDerRequestOptions,
  ) {
    const headers: Record<string, string> = {};
    if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey;
    return this.http.post<AgentRunResponse>(
      `/api/v1/agents/${encodeURIComponent(agentId)}/run`,
      body,
      requestConfig(options, {}, headers),
    );
  }

  /**
   * Convenience: run with text-only input (skips the nested envelope).
   */
  runText(agentId: string, text: string, opts: {
    runtime_mode?: string;
    idempotencyKey?: string;
    purpose_of_use?: AgentRunRequest['purpose_of_use'];
    documents?: AgentRunSourceDocument[];
    upstream_results?: AgentRunUpstreamResult[];
  } = {}, options?: iCoDerRequestOptions) {
    return this.run(agentId, {
      input: {
        text,
        documents: opts.documents,
        upstream_results: opts.upstream_results,
      },
      runtime_mode: opts.runtime_mode,
      purpose_of_use: opts.purpose_of_use,
    }, opts.idempotencyKey, options);
  }

  /** GET /api/v1/runs/{run_id} — authoritative lifecycle state. */
  get(runId: string, options?: iCoDerRequestOptions) {
    return this.http.get<RunStatusResponse>(
      `/api/v1/runs/${encodeURIComponent(runId)}`,
      requestConfig(options),
    );
  }

  /**
   * POST /api/v1/runs/{run_id}/cancel.
   *
   * Callers must inspect ``outcome``. ``RECORDED_ONLY`` means the request was
   * audited but the provider call is still running; it is never reported as a
   * successful cancellation.
   */
  cancel(runId: string, reason = '', options?: iCoDerRequestOptions) {
    return this.http.post<RunCancelResponse>(
      `/api/v1/runs/${encodeURIComponent(runId)}/cancel`,
      { reason },
      requestConfig(options),
    );
  }

  /** Renew a run-bound trace authorization using the configured bearer identity. */
  renewTraceToken(runId: string, options?: iCoDerRequestOptions) {
    return this.http.post<RunTraceTokenRenewResponse>(
      `/api/v1/runs/${encodeURIComponent(runId)}/trace-token`,
      undefined,
      requestConfig(options),
    );
  }

  /**
   * Open the signed, PHI-safe run lifecycle SSE stream.
   *
   * ``traceToken`` is the ``token`` query value from ``AgentRunResponse.trace_url``.
   * It is deliberately supplied separately so this SDK never fetches an arbitrary
   * URL returned by a server.
   */
  async streamEvents(
    runId: string,
    traceToken: string,
    signal?: AbortSignal,
    lastEventId?: string,
    options?: iCoDerRequestOptions,
  ): Promise<ReadableStream<Uint8Array>> {
    if (!traceToken) throw new Error('traceToken is required');
    if (lastEventId && (lastEventId.length > 128 || /[\r\n\0]/.test(lastEventId))) {
      throw new Error('lastEventId is malformed');
    }
    if (options?.maxRetries !== undefined && options.maxRetries !== 0) {
      throw new RangeError('run event streams require maxRetries to be 0');
    }
    if (signal && options?.abortSignal && signal !== options.abortSignal) {
      throw new TypeError('run event stream received conflicting abort signals');
    }
    const baseURL = (this.http.defaults.baseURL || '').replace(/\/$/, '');
    const domainHeaders: Record<string, string> = { Accept: 'text/event-stream' };
    if (lastEventId) domainHeaders['Last-Event-ID'] = lastEventId;
    const config = requestConfig(options, { token: traceToken }, domainHeaders);
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(config.params ?? {})) {
      if (value !== undefined && value !== null) query.append(key, String(value));
    }
    const signals = [options?.abortSignal ?? signal].filter(
      (value): value is AbortSignal => value !== undefined,
    );
    if (config.timeout !== undefined) signals.push(AbortSignal.timeout(config.timeout));
    const boundedSignal = signals.length > 1 ? AbortSignal.any(signals) : signals[0];
    const response = await fetch(
      `${baseURL}/api/v1/runs/${encodeURIComponent(runId)}/events?${query}`,
      {
        method: 'GET',
        headers: { ...((config.headers ?? {}) as Record<string, string>) },
        signal: boundedSignal,
      },
    );
    if (!response.ok) {
      throw await runEventHttpError(response);
    }
    if (!response.headers.get('content-type')?.startsWith('text/event-stream')) {
      throw new RunEventStreamError('iCoDer returned a non-SSE run event response');
    }
    if (!response.body) throw new RunEventStreamError('iCoDer returned an empty run event stream');
    return response.body;
  }

  /**
   * Yield parsed lifecycle events while reconnecting only bounded transport
   * failures.  The last acknowledged SSE ID is preserved across attempts.
   * A signed-token 401 triggers one bearer-authenticated renewal per failed
   * connection; authorization, cursor and protocol errors are never hidden.
   */
  async *streamEventsResilient(
    runId: string,
    traceToken: string,
    options: RunStreamRetryOptions = {},
  ): AsyncGenerator<RunSseEvent> {
    if (!traceToken) throw new Error('traceToken is required');
    const retry = validateRetryOptions(options);
    let currentToken = traceToken;
    let lastEventId = options.lastEventId;

    for (let attempt = 0; attempt < retry.maxAttempts; attempt += 1) {
      if (options.signal?.aborted) {
        throw options.signal.reason ?? new DOMException('Aborted', 'AbortError');
      }
      try {
        const stream = await this.streamEvents(
          runId,
          currentToken,
          options.signal,
          lastEventId,
          options.requestOptions,
        );
        let completed = false;
        for await (const event of parseRunSseStream(stream)) {
          if (event.id) lastEventId = event.id;
          completed ||= isTerminalRunEvent(event);
          yield event;
        }
        if (completed) return;
        throw new RunEventStreamError(
          'iCoDer run event stream ended before completion', undefined, true,
        );
      } catch (error) {
        if (options.signal?.aborted || (error instanceof Error && error.name === 'AbortError')) {
          throw error;
        }
        const streamError = error instanceof RunEventStreamError ? error : undefined;
        const canRenew = streamError?.httpStatus === 401;
        const retryableTransport = streamError?.retryable || error instanceof TypeError;
        if (!canRenew && !retryableTransport) throw error;
        if (attempt + 1 >= retry.maxAttempts) throw error;
        if (canRenew) {
          const renewed = await this.renewTraceToken(runId, options.requestOptions);
          currentToken = renewed.data.trace_token;
        }
        await waitForRetry(
          retryDelay(attempt, retry.initialDelayMs, retry.maxDelayMs, retry.jitterRatio),
          options.signal,
        );
      }
    }
  }
}

export class RunHistoryResource {
  constructor(private http: AxiosInstance) {}

  /**
   * GET /api/runtime/runs/history — paginated run history.
   *
   * Returns the run_history table (alembic 010). Filter by agent_id,
   * days window, or both.
   */
  list(
    params: { agent_id?: string; days?: number; limit?: number; offset?: number } = {},
    options?: iCoDerRequestOptions,
  ) {
    return this.http.get<RunHistoryListResponse>(
      '/api/runtime/runs/history', requestConfig(options, params),
    );
  }
}

export class RunTraceResource {
  constructor(private http: AxiosInstance) {}

  /**
   * GET /api/runtime/runs/{run_id}/trace?format=timeline
   *
   * Returns the display-safe timeline (sorted by ts). Default format.
   */
  timeline(runId: string, options?: iCoDerRequestOptions) {
    return this.http.get<RunTraceTimelineResponse>(
      `/api/runtime/runs/${encodeURIComponent(runId)}/trace`,
      requestConfig(options, { format: 'timeline' }),
    );
  }

  /**
   * GET /api/runtime/runs/{run_id}/trace?format=raw
   *
   * Returns the raw event dump (for debugging).
   */
  raw(runId: string, options?: iCoDerRequestOptions) {
    return this.http.get<RunTraceRawResponse>(
      `/api/runtime/runs/${encodeURIComponent(runId)}/trace`,
      requestConfig(options, { format: 'raw' }),
    );
  }
}
