/**
 * CDI API client — /api/v1/cdi/* (Phase 5 Track D P0 Gate 5).
 *
 * Wires the frontend workbench to the real backend CDI endpoints:
 *   POST /runs                       — run orchestrator on chart_excerpt
 *   GET  /runs/{case_id}             — load persisted case
 *   POST /queries/{id}/transition    — lifecycle transition
 *   GET  /audit/dashboard            — RBAC'd auditor view
 *
 * Boundary: this client must NOT call any medical-coding endpoint.
 */

import axios from 'axios';

// ---------------------------------------------------------------------------
// Types — mirror backend Pydantic schemas (backend/app/api/cdi.py)
// ---------------------------------------------------------------------------

export type LifecycleState =
  | 'DRAFT'
  | 'PENDING_CDI_REVIEW'
  | 'APPROVED'
  | 'SENT_TO_CLINICIAN'
  | 'VIEWED'
  | 'RESPONDED'
  | 'DOCUMENTATION_UPDATED'
  | 'REVALIDATED'
  | 'CLOSED'
  | 'CANCELLED'
  | 'ESCALATED'
  | 'EXPIRED';

export type NLQVerdict = 'PASS' | 'BLOCK' | 'PENDING';

export interface StageTrace {
  stage: string;
  provider: string;
  model: string;
  latency_ms: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  run_id: string;
  trace_id: string;
  degraded: boolean;
  error_reason?: string;
  expert_id?: string;
}

export interface EvidenceSpan {
  document_id: string;
  quote: string;
  char_start?: number;
  char_end?: number;
  documented_at?: string;
}

export interface DocumentationGapDTO {
  gap_id: string;
  gap_type: string;
  description: string;
  why_it_matters: string;
  evidence_span: EvidenceSpan;
  minimal_clarification_needed: string;
}

export interface ProviderQueryDTO {
  query_id: string;
  gap_id: string;
  topic: string;
  reason: string;
  evidence_span: EvidenceSpan;
  evidence_spans?: EvidenceSpan[];
  query_text: string;
  response_options: string[];
  priority: 'routine' | 'urgent';
  lifecycle_state: LifecycleState;
  nlq_gate_verdict: NLQVerdict;
  nlq_gate_block_reasons: string[];
}

export type QueryAuditStatus =
  | 'NEEDS_QUERY_DRAFT'
  | 'NEEDS_CDI_REWRITE'
  | 'NEEDS_EVIDENCE_REWRITE'
  | 'NEEDS_NON_LEADING_REWRITE'
  | 'REWRITE_CANDIDATE_GENERATED'
  | 'REJECTED_AS_INELIGIBLE'
  | 'REJECTED_AS_UNNECESSARY'
  | 'REJECTED_BY_CLAIM_EVIDENCE'
  | 'REJECTED_BY_SEMANTIC_NECESSITY';

export interface QueryAuditItemDTO {
  query_id: string;
  gap_id: string;
  topic?: string;
  reason?: string;
  query_text?: string;
  response_options?: string[];
  evidence_spans?: EvidenceSpan[];
  gate_reasons?: string[];
  detected_axes?: string[];
  status: QueryAuditStatus | string;
  gap_reference_valid?: boolean;
  replacement_query_id?: string;
  rewrite_attempt_status?: string;
  rewrite_attempt_reasons?: string[];
}

export interface CDIRunResponse {
  case_id: string;
  completion_state:
    | 'AUTO_PASS'
    | 'REVIEW_RECOMMENDED'
    | 'REVIEW_REQUIRED'
    | 'BLOCKED';
  chart_excerpt_preview: string;
  patient_ref: string;
  encounter_ref: string;
  encounter_summary?: { key_points: string[] };
  documentation_gaps: DocumentationGapDTO[];
  proposed_provider_queries: ProviderQueryDTO[];
  query_rewrite_queue: QueryAuditItemDTO[];
  risk_flags: { category: string; description: string }[];
  specialist_trace: SpecialistTraceEntry[];
  stage_run_ids?: Record<string, string>;
  stage_trace_ids?: Record<string, string>;
  stage_traces: StageTrace[];
  degraded: boolean;
  runtime_mode: string;
}

/**
 * Specialist Trace entry — Phase 5 Track D P0.5 Gate 5 extension.
 *
 * Each Expert (coding/pubmed/web/calculator) appears once per case with
 * its routing decision, execution mode, and audit metadata.
 */
export interface SpecialistTraceEntry {
  expert_id: string;
  consulted: boolean;
  rationale: string;
  /** "needed" | "not_needed" | "missing_inputs" | "tool_unavailable" | "degraded" */
  route_decision?: string;
  /** Machine-readable route reason code, e.g. "coding_relevant_gap". */
  route_reason?: string;
  /** One of ExpertExecutionMode (REAL_TOOL / LLM_KNOWLEDGE_ONLY / SKIPPED_* / TOOL_UNAVAILABLE / DEGRADED). */
  execution_mode?: string;
  latency_ms?: number;
  tokens?: number;
  run_id?: string;
  trace_id?: string;
}

export interface CDIHealthResponse {
  status: string;
  router: string;
  endpoints: string[];
  boundaries_enforced: string[];
}

export interface CDIAuditDashboard {
  generated_at: string;
  total_cases: number;
  total_queries: number;
  queries_by_state: Record<string, number>;
  queries_by_priority: Record<string, number>;
  breaches_critical: number;
  breaches_warning: number;
  response_category_distribution: Record<string, number>;
  average_hours_to_response: number | null;
  average_hours_to_close: number | null;
  top_gap_types: Array<[string, number]>;
  escalation_rate: number;
  note: string;
}

// ---------------------------------------------------------------------------
// Axios instance
// ---------------------------------------------------------------------------

const cdiApi = axios.create({ baseURL: '/api/v1/cdi', timeout: 120000 });

cdiApi.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  config.headers['Content-Type'] = 'application/json';
  return config;
});

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export interface RunCDIParams {
  chart_excerpt: string;
  case_id?: string;
  patient_ref?: string;
  encounter_ref?: string;
}

export async function runCDI(params: RunCDIParams): Promise<CDIRunResponse> {
  const { data } = await cdiApi.post<CDIRunResponse>('/runs', params);
  return data;
}

export async function getCDICase(caseId: string): Promise<CDIRunResponse> {
  const { data } = await cdiApi.get<CDIRunResponse>(`/runs/${caseId}`);
  return data;
}

export interface TransitionParams {
  to_state: LifecycleState;
  priority?: 'routine' | 'urgent';
  query_text?: string;
  response_options?: string[];
  evidence_quote?: string;
  topic?: string;
}

export interface TransitionResult {
  accepted: boolean;
  to_state: LifecycleState;
  sla_due_at?: string;
  nlq_gate_verdict?: NLQVerdict;
  nlq_gate_block_reasons?: string[];
}

export async function transitionQuery(
  queryId: string,
  params: TransitionParams,
): Promise<TransitionResult> {
  const { data } = await cdiApi.post<TransitionResult>(
    `/queries/${queryId}/transition`,
    params,
  );
  return data;
}

export async function cdiHealth(): Promise<CDIHealthResponse> {
  const { data } = await cdiApi.get<CDIHealthResponse>('/health');
  return data;
}

export async function getCDIAuditDashboard(): Promise<CDIAuditDashboard> {
  const { data } = await cdiApi.get<CDIAuditDashboard>('/audit/dashboard');
  return data;
}
