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

// ── AgentRunResponse (mirror of backend/app/api/agent_run.py:AgentRunResponse) ──

export interface AgentRunCost {
  amount: number;
  currency: 'CNY' | 'USD' | string;
}

export interface AgentRunRequestInput {
  text: string;
  extra?: Record<string, unknown>;
}

export interface AgentRunRequest {
  input: AgentRunRequestInput;
  runtime_mode?: 'corti_like_fast' | 'medcoder_deep' | string;
  api_client_id?: string;
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
  summary: string;
  result: Record<string, unknown>;
  evidence: Array<Record<string, unknown>>;
  warnings: string[];
  manual_review_required: boolean;
  trace_events: Array<Record<string, unknown>>;
  error: boolean;
  error_reason: string;
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

export interface RunTraceTimelineResponse {
  run_id: string;
  timeline: RunTraceEvent[];
  step_count: number;
}

export interface RunTraceRawResponse {
  run_id: string;
  events: RunTraceEvent[];
}

// ── A2A v0.3 envelope (mirror of app/icoder/agent_runtime/a2a_facade.py) ──

export interface A2AMessagePart {
  kind: 'text' | 'data' | 'file';
  text?: string;
  data?: Record<string, unknown>;
  uri?: string;
  mime_type?: string;
}

export interface A2AMessage {
  message_id: string;
  role: 'user' | 'agent';
  parts: A2AMessagePart[];
}

export interface A2AEnvelope {
  jsonrpc: '2.0';
  id: string;
  result?: {
    agent_id: string;
    run_id: string;
    trace_id: string;
    context_id: string;
    message_id: string;
    status: 'completed' | 'failed' | string;
    message?: A2AMessage;
  };
  error?: { code: number; message: string; data?: Record<string, unknown> };
}

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
  run(agentId: string, body: AgentRunRequest, idempotencyKey?: string) {
    const headers: Record<string, string> = {};
    if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey;
    return this.http.post<AgentRunResponse>(
      `/api/v1/agents/${encodeURIComponent(agentId)}/run`,
      body,
      { headers },
    );
  }

  /**
   * Convenience: run with text-only input (skips the nested envelope).
   */
  runText(agentId: string, text: string, opts: { runtime_mode?: string; idempotencyKey?: string } = {}) {
    return this.run(agentId, {
      input: { text },
      runtime_mode: opts.runtime_mode,
    }, opts.idempotencyKey);
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
  list(params: { agent_id?: string; days?: number; limit?: number; offset?: number } = {}) {
    return this.http.get<RunHistoryListResponse>('/api/runtime/runs/history', { params });
  }
}

export class RunTraceResource {
  constructor(private http: AxiosInstance) {}

  /**
   * GET /api/runtime/runs/{run_id}/trace?format=timeline
   *
   * Returns the display-safe timeline (sorted by ts). Default format.
   */
  timeline(runId: string) {
    return this.http.get<RunTraceTimelineResponse>(
      `/api/runtime/runs/${encodeURIComponent(runId)}/trace`,
      { params: { format: 'timeline' } },
    );
  }

  /**
   * GET /api/runtime/runs/{run_id}/trace?format=raw
   *
   * Returns the raw event dump (for debugging).
   */
  raw(runId: string) {
    return this.http.get<RunTraceRawResponse>(
      `/api/runtime/runs/${encodeURIComponent(runId)}/trace`,
      { params: { format: 'raw' } },
    );
  }
}

// ── Future: SSE client (Phase 7 candidate) ──────────────────────────────
//
// When the backend ships SSE streaming for agent_run (planned Phase 7),
// the SDK will need an EventSource-based consumer. Skeleton:
//
//   export class SSEClient {
//     constructor(private baseUrl: string, private getToken: () => string) {}
//     stream(agentId: string, body: AgentRunRequest): EventSource {
//       const url = new URL(`${this.baseUrl}/api/v1/agents/${agentId}/run/stream`);
//       // EventSource doesn't support custom headers — pass token in query
//       url.searchParams.set('access_token', this.getToken());
//       return new EventSource(url.toString());
//     }
//   }
//
// Not implemented in Phase 6 Gate 4 — agent_run is request/response only.
