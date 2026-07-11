/**
 * Runtime Agent API client — /api/runtime/* standard endpoints (agent lifecycle,
 * registry, medical-coding, rule-engine).
 *
 * Phase 3-B2 (2026-07-05): `runAgent` (POST /api/runtime/agents/{ref}/run) is
 * deprecated — the A2A mainline `runAgentViaA2A` (POST /api/icoder/agents/{id}/
 * v1/message:send) is the canonical execution path. `runAgent` is retained
 * only for AgentDetailPage's test-input flow until that page is rewired.
 */

import axios from 'axios';
import type {
  RuntimeStatus, DataPolicy, RegistryHealth, FallbackStats, ShadowStats,
  InstalledAgent, RuntimeRunResult, MedicalCodingStatus, RuleEngineStatus,
  RunTraceResponse,
} from '../types/runtime';

const api = axios.create({ baseURL: '/api/runtime', timeout: 30000 });

// Auth token interceptor
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// A2A mainline client — POST /api/icoder/agents/{agentId}/v1/message:send
// JSON-RPC 2.0 envelope + A2A-Protocol-Version: 0.3 header.
const a2aApi = axios.create({ baseURL: '/api/icoder/agents', timeout: 60000 });
a2aApi.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  config.headers['A2A-Protocol-Version'] = '0.3';
  config.headers['Content-Type'] = 'application/json';
  return config;
});

// Phase 4-F (2026-07-09): Unified Agent Run client —
// POST /api/v1/agents/{agent_id}/run — thin facade that routes to
// CodingRuntimeDispatcher (medical-coding) or ProviderRegistry (others).
const unifiedRunApi = axios.create({ baseURL: '/api/v1/agents', timeout: 60000 });
unifiedRunApi.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  config.headers['Content-Type'] = 'application/json';
  return config;
});

/** Phase 4-F: response envelope from POST /api/v1/agents/{id}/run.
 * Uniform across all iCoDer built agents — 13 fields per prompt §9.1. */
export interface AgentRunResponse {
  agent_id: string;
  run_id: string;
  trace_id: string;
  runtime_mode: string;
  latency_ms: number;
  cost: Record<string, unknown>;
  summary: string;
  result: Record<string, unknown>;
  evidence: Array<Record<string, unknown>>;
  warnings: string[];
  manual_review_required: boolean;
  trace_events: Array<Record<string, unknown>>;
  error: boolean;
  error_reason: string;
}

/**
 * Map an A2A JSON-RPC success envelope to RuntimeRunResult.
 *
 * The v2 8-field MedicalCodingAgentOutputV2 lives in
 * `result.parts[*]` where `part.kind === 'data'`. Orchestrator trace
 * fields (expert_id, latency_ms, ...) live in `part.metadata` under
 * `orchestrator_*` keys (projected by `_MedicalCodingV2ProjectingHandler`
 * in app/main.py). The frontend RuntimeRunResult is a flat projection
 * that the existing MedicalCodingPage consumes.
 */
function _mapA2AResultToRunResult(agentId: string, envelope: any): RuntimeRunResult {
  if (envelope?.error) {
    const err = envelope.error;
    const detail = err.message || err.data?.message || 'A2A error';
    throw { response: { data: { detail, error_code: err.code } }, message: detail };
  }
  const result = envelope?.result;
  if (!result || result.kind !== 'message') {
    throw { message: 'A2A response missing result.message' };
  }
  const dataPart = (result.parts || []).find(
    (p: any) => p?.kind === 'data' && p?.data,
  );
  if (!dataPart) {
    throw { message: 'A2A response missing data part' };
  }
  const v2 = dataPart.data || {};
  const partMeta = dataPart.metadata || {};
  const meta = result.metadata || {};
  const runId =
    meta.run_id || partMeta.run_id || v2?.trace_refs?.run_id || '';
  const codeAssignment = v2.code_assignment || {};
  const valSummary = v2.validation_summary || {};
  const humanReview = v2.human_review || {};
  const traceRefs = v2.trace_refs || {};
  const docAnalysis = v2.documentation_analysis || {};

  // Build audit_trail from orchestrator_* metadata keys.
  const audit_trail: any[] = [];
  for (const [k, v] of Object.entries(partMeta)) {
    if (k.startsWith('orchestrator_')) {
      audit_trail.push({
        step: k.replace('orchestrator_', ''),
        result: '',
        payload: typeof v === 'object' && v !== null ? v : { value: v },
      });
    }
  }

  // Evidences — flatten the 4 documentation_analysis buckets.
  const evidences = [
    ...(docAnalysis.diagnosis_evidence || []),
    ...(docAnalysis.procedure_evidence || []),
    ...(docAnalysis.negated_findings || []),
    ...(docAnalysis.historical_conditions || []),
  ];

  return {
    run_id: runId,
    agent_ref: `icoder/${agentId}`,
    status: 'success',
    output: JSON.stringify(v2, null, 2),
    structured: v2,
    primary_diagnosis: codeAssignment.primary_diagnosis || {
      code: '',
      description: '',
      confidence: 0,
      category: '',
      evidence: [],
    },
    secondary_diagnoses: codeAssignment.secondary_diagnoses || [],
    procedures: codeAssignment.procedures || [],
    issues_found: valSummary.issues_found || [],
    audit_trail,
    processing_time_ms: partMeta.orchestrator_latency_ms || 0,
    token_usage: { input_tokens: 0, output_tokens: 0 },
    errors: [],
    evidences,
    mode: traceRefs.mode,
    extracted_diagnoses: [],
    review_conclusion: humanReview.review_conclusion,
    manual_review_required: humanReview.review_required,
    encounter_summary: v2.encounter_summary,
    documentation_gaps: v2.documentation_gaps || [],
    uncodable_items: v2.uncodable_items || [],
    corti_validation_summary: {
      passed: valSummary.passed,
      issues_found: valSummary.issues_found || [],
      manual_review_required: valSummary.manual_review_required,
      rule_set: valSummary.rule_set,
      fired_rules: valSummary.fired_rules || [],
    },
    human_review: humanReview,
    trace_refs: traceRefs,
    // Phase 3-B2 Loop 3: pre-rendered Markdown from
    // app.icoder.markdown_generator (backend). Absent on non-medical-coding
    // agents or when generation fails — frontend will auto-generate.
    markdown: v2.markdown,
  } as RuntimeRunResult;
}

/**
 * Phase 4-F1 (2026-07-10): Map the 13-field AgentRunResponse envelope to the
 * RuntimeRunResult shape so AgentChatPage's MessageBubble (Copy JSON/Markdown,
 * Event Inspector link, Rendered/JSON tabs, latency badge) continues to work
 * without touching the rendering layer.
 *
 * The unified endpoint returns a uniform envelope across all iCoDer built
 * agents. Medical Coding Agent runs via the G001 `corti_like_fast` path
 * (CodingRuntimeDispatcher) and returns ~9-10s on T12. A2A runs route to
 * InboundHandler + MedCodER 5-stage pipeline and 60s-timeout — we avoid
 * that path on chat now.
 */
function _mapAgentRunResponseToRuntimeRunResult(
  agentId: string,
  resp: AgentRunResponse,
): RuntimeRunResult {
  const result = (resp.result || {}) as Record<string, unknown>;
  const evidence = resp.evidence || [];
  const warnings = resp.warnings || [];
  const traceEvents = resp.trace_events || [];
  const traceRefs = (result.trace_refs || {}) as Record<string, unknown>;
  const codeAssignment = (result.code_assignment || {}) as Record<string, unknown>;
  const valSummary = (result.validation_summary || {}) as Record<string, unknown>;
  const humanReview = (result.human_review || {}) as Record<string, unknown>;

  // Audit trail from trace_events (each event has step/latency/expert_id).
  const audit_trail: any[] = traceEvents.map((ev: any) => ({
    step: ev.step || ev.event || ev.name || '',
    result: ev.result || '',
    payload: ev.payload || ev,
  }));

  // Evidences — pass through; backend already shapes them per-agent.
  const evidences: any[] = (evidence as any[]).map((ev: any) => ev);

  return {
    run_id: resp.run_id || '',
    agent_ref: `icoder/${agentId}`,
    status: resp.error ? 'error' : 'success',
    output: JSON.stringify(result, null, 2),
    structured: result,
    primary_diagnosis: (codeAssignment.primary_diagnosis || {
      code: '',
      description: '',
      confidence: 0,
      category: '',
      evidence: [],
    }) as any,
    secondary_diagnoses: (codeAssignment.secondary_diagnoses || []) as any[],
    procedures: (codeAssignment.procedures || []) as any[],
    issues_found: warnings,
    audit_trail,
    processing_time_ms: resp.latency_ms || 0,
    token_usage: { input_tokens: 0, output_tokens: 0 },
    errors: resp.error ? [resp.error_reason || resp.summary || 'agent run failed'] : [],
    evidences,
    mode: resp.runtime_mode,
    extracted_diagnoses: [],
    review_conclusion: humanReview.review_conclusion as string | undefined,
    manual_review_required: resp.manual_review_required,
    encounter_summary: result.encounter_summary as string | undefined,
    documentation_gaps: (result.documentation_gaps || []) as any[],
    uncodable_items: (result.uncodable_items || []) as any[],
    corti_validation_summary: {
      passed: valSummary.passed as boolean | undefined,
      issues_found: warnings,
      manual_review_required: resp.manual_review_required,
      rule_set: valSummary.rule_set as string | undefined,
      fired_rules: (valSummary.fired_rules || []) as any[],
    },
    human_review: humanReview as any,
    trace_refs: { ...traceRefs, trace_id: resp.trace_id } as any,
    markdown: (result.markdown as string | undefined) || undefined,
    // Phase 4-F1 additions for chat UI consumption
    summary: resp.summary,
    latency_ms: resp.latency_ms,
    runtime_mode: resp.runtime_mode,
    cost: resp.cost,
    trace_id: resp.trace_id,
    trace_events: traceEvents,
    error: resp.error,
    error_reason: resp.error_reason,
  } as unknown as RuntimeRunResult & {
    summary: string;
    latency_ms: number;
    runtime_mode: string;
    cost: Record<string, unknown>;
    trace_id: string;
    trace_events: Array<Record<string, unknown>>;
    error: boolean;
    error_reason: string;
  };
}

export const runtimeAgentApi = {
  // ── Status ──
  getStatus: () => api.get<RuntimeStatus>('/status').then(r => r.data),

  // ── Data Policy ──
  getDataPolicy: () => api.get<DataPolicy>('/data-policy').then(r => r.data),

  // ── Registry ──
  getRegistryHealth: () => api.get<RegistryHealth>('/registry/health').then(r => r.data),
  getRegistryInconsistencies: () => api.get('/registry/inconsistencies').then(r => r.data),
  repairRegistry: (direction = 'registry_to_db') =>
    api.post('/registry/repair', { direction }).then(r => r.data),

  // ── Agents ──
  listAgents: (agentType = '') =>
    api.get<{ agents: InstalledAgent[]; total: number }>('/agents', { params: { agent_type: agentType } }).then(r => r.data),
  installAgent: (name: string, version: string, agentType = 'community') =>
    api.post('/agents/install', { agent_name: name, agent_version: version, agent_type: agentType }).then(r => r.data),
  /** @deprecated Phase 3-B2 — use runAgentViaA2A (A2A mainline). Only kept
   * for AgentDetailPage's test-input flow; will be removed when that page
   * is rewired to A2A. */
  runAgent: (agentRef: string, input: string) =>
    api.post<RuntimeRunResult>(`/agents/${encodeURIComponent(agentRef)}/run`, { input }).then(r => r.data),
  /** A2A mainline: POST /api/icoder/agents/{agentId}/v1/message:send.
   * Sends a JSON-RPC 2.0 message/send envelope and projects the v2 8-field
   * response back to RuntimeRunResult for compatibility with the existing UI.
   * Phase 4-D: accepts extra `parts` (DataPart for attached JSON context
   * files via "Add context"). After each run, syncs liveCost from billing
   * balance delta. */
  runAgentViaA2A: (agentId: string, input: string, extraParts: any[] = []) => {
    const parts: any[] = [
      { kind: 'text', text: input },
      ...extraParts,
    ];
    const runPromise = a2aApi.post(`/${encodeURIComponent(agentId)}/v1/message:send`, {
      jsonrpc: '2.0',
      id: `icoder-${Date.now()}`,
      method: 'message/send',
      params: {
        message: {
          role: 'user',
          messageId: `msg-${Date.now()}`,
          parts,
          metadata: {},
        },
      },
    }).then(r => _mapA2AResultToRunResult(agentId, r.data));
    // Sync live cost after run completes (non-blocking — don't block UI on balance fetch)
    runPromise.then(() => {
      // Dynamic import to avoid circular dependency (store imports from services)
      import('../store').then(({ useCostStore }) => {
        import('./api').then(({ billingApi }) => {
          billingApi.balance().then((r: any) => {
            const bal = r.data?.balance;
            if (typeof bal === 'number') {
              useCostStore.getState().syncFromBalance(bal);
            }
          }).catch(() => {});
        });
      });
    }).catch(() => {});
    return runPromise;
  },
  agentLifecycle: (agentRef: string, action: string) =>
    api.post(`/agents/${encodeURIComponent(agentRef)}/lifecycle`, { action }).then(r => r.data),

  // ── Runs (recent runs overview; full trace at /api/runtime/runs/{id}/trace)
  listRuns: (agentRef = '', limit = 50) =>
    api.get<{ runs: RuntimeRunResult[]; total: number }>('/runs', { params: { agent_ref: agentRef, limit } }).then(r => r.data),

  // Phase 3-D1 Task 4: RunTrace Corti-parity Viewer — 9-step timeline
  getRunTrace: (runId: string) =>
    api.get<RunTraceResponse>(`/runs/${encodeURIComponent(runId)}/trace`).then(r => r.data),

  // Phase 4-G #3: RunHistory list — recent run summaries for the dropdown.
  // Phase 5 A6: optional `days` param filters by created_at >= now - days.
  // GET /api/runtime/runs/history?agent_id=X&limit=50&days=30 → {items, total}
  getRunHistory: (agentId = '', limit = 50, days = 0) =>
    api.get<{ items: any[]; total: number }>(
      '/runs/history',
      { params: { agent_id: agentId, limit, ...(days > 0 ? { days } : {}) } },
    ).then(r => r.data),

  // ── Observability ──
  getFallbackStats: (hours = 24) =>
    api.get<FallbackStats>('/observability/fallback', { params: { hours } }).then(r => r.data),
  getShadowStats: (hours = 24) =>
    api.get<ShadowStats>('/observability/shadow', { params: { hours } }).then(r => r.data),

  // ── Audit ──
  getAuditLog: (eventType = '', limit = 100) =>
    api.get('/audit-log', { params: { event_type: eventType, limit } }).then(r => r.data),

  // ── Medical Coding ──
  getMedicalCodingStatus: () =>
    api.get<MedicalCodingStatus>('/medical-coding/status').then(r => r.data),

  // ── Rule Engine ──
  getRuleEngineStatus: () =>
    api.get<RuleEngineStatus>('/rule-engine/status').then(r => r.data),
  validateRules: (ruleSet: string, structuredOutput: Record<string, unknown>, context: Record<string, unknown> = {}) =>
    api.post('/rule-engine/validate', { rule_set: ruleSet, structured_output: structuredOutput, context }).then(r => r.data),
  getRules: () => api.get('/rule-engine/rules').then(r => r.data),

  // ── Phase 4-F (2026-07-09): Unified Agent Run API ──
  // POST /api/v1/agents/{agent_id}/run — thin facade that routes any
  // iCoDer built agent to its appropriate runtime (CodingRuntimeDispatcher
  // for medical-coding, ProviderRegistry for everything else). Returns a
  // uniform 13-field envelope consumed by AgentDetailPage's chat UI.
  //
  // Phase 5 B-2: accepts both full agent_ref (`icoder/medical-coding-agent@2.0.0`)
  // and short agent_id (`medical-coding-agent`) — normalizes to short form
  // since backend `_agent_id_from_ref` expects that. Fixes the 404 when the
  // URL contains the un-cloned Hub agent_ref (e.g. user clicks "自定义" on a
  // Hub card rather than "使用智能体" which clones first).
  agentRun: (
    agentId: string,
    input: string,
    options: {
      runtime_mode?: string;
      extra?: Record<string, unknown>;
      include_trace?: boolean;
      include_evidence?: boolean;
      api_client_id?: string;
    } = {},
  ) => {
    const shortId = agentId.split('/').pop()!.split('@')[0];
    const body = {
      input: { text: input, extra: options.extra || {} },
      runtime_mode: options.runtime_mode,
      include_trace: options.include_trace ?? true,
      include_evidence: options.include_evidence ?? true,
      api_client_id: options.api_client_id || undefined,
    };
    return unifiedRunApi.post(`/${encodeURIComponent(shortId)}/run`, body).then(
      r => r.data as AgentRunResponse,
    );
  },

  /** Phase 4-F1 (2026-07-10): Unified run path for AgentChatPage — wraps
   * `agentRun()` and maps the 13-field AgentRunResponse to RuntimeRunResult
   * so the existing MessageBubble rendering layer keeps working. On
   * `resp.error=true`, throws a structured error with `error_reason` so the
   * caller surfaces a structured error bubble instead of silent fail.
   *
   * Medical Coding Agent default: `runtime_mode="corti_like_fast"` (G001,
   * ~9-10s on T12) — the A2A MedCodER 5-stage path 60s-timeouts.
   *
   * Phase 4-G #1 (2026-07-10): After a successful run with a populated
   * `cost.amount`, push that amount into `useCostStore` so the TopBar live
   * counter updates immediately (no need to wait for the next billing
   * balance poll).
   *
   * Phase 4-G #2 (2026-07-10): Forwards the selected `api_client_id`
   * through to the backend so the run is attributed to that OAuth client
   * (logged in trace metadata; future: route through client-scoped
   * credentials).
   */
  runAgentUnified: (
    agentId: string,
    input: string,
    options: {
      runtime_mode?: string;
      extra?: Record<string, unknown>;
      include_trace?: boolean;
      include_evidence?: boolean;
      api_client_id?: string;
    } = {},
  ) => {
    const runPromise = runtimeAgentApi
      .agentRun(agentId, input, options)
      .then(resp => {
        if (resp?.error) {
          const reason = resp.error_reason || resp.summary || 'agent run failed';
          throw {
            response: { data: { detail: reason, error_reason: resp.error_reason } },
            message: reason,
          };
        }
        // Phase 4-G #1: accumulate live cost from the response envelope so
        // the TopBar counter updates instantly after each run. The backend
        // computes `cost.amount` from token usage × pricing; if absent (mock
        // or zero-token runs), fall through to the existing balance-poll
        // path in `runAgentViaA2A`.
        const costAmount = typeof resp?.cost?.amount === 'number' ? resp.cost.amount : 0;
        if (costAmount > 0) {
          // Dynamic import to avoid circular dep (store imports from services).
          import('../store').then(({ useCostStore }) => {
            useCostStore.getState().addCost(costAmount);
          }).catch(() => {});
        }
        return _mapAgentRunResponseToRuntimeRunResult(agentId, resp);
      });
    return runPromise;
  },
};
