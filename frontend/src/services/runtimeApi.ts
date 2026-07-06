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
   * response back to RuntimeRunResult for compatibility with the existing UI. */
  runAgentViaA2A: (agentId: string, input: string) =>
    a2aApi.post(`/${encodeURIComponent(agentId)}/v1/message:send`, {
      jsonrpc: '2.0',
      id: `icoder-${Date.now()}`,
      method: 'message/send',
      params: {
        message: {
          role: 'user',
          messageId: `msg-${Date.now()}`,
          parts: [{ kind: 'text', text: input }],
          metadata: {},
        },
      },
    }).then(r => _mapA2AResultToRunResult(agentId, r.data)),
  agentLifecycle: (agentRef: string, action: string) =>
    api.post(`/agents/${encodeURIComponent(agentRef)}/lifecycle`, { action }).then(r => r.data),

  // ── Runs (recent runs overview; full trace at /api/m2a/runs/{id})
  listRuns: (agentRef = '', limit = 50) =>
    api.get<{ runs: RuntimeRunResult[]; total: number }>('/runs', { params: { agent_ref: agentRef, limit } }).then(r => r.data),

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
};
