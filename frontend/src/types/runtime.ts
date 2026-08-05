/** Runtime types — aligned with icoder_runtime RuntimeRunResult, MedicalCodingOutputSchema, etc. */

export interface RuntimeRunResult {
  run_id: string;
  agent_ref: string;
  status: 'success' | 'error' | 'timeout' | 'fallback';
  output: string;
  structured?: Record<string, unknown>;
  primary_diagnosis: DiagnosisEntry;
  secondary_diagnoses: DiagnosisEntry[];
  procedures: ProcedureEntry[];
  issues_found: CodingIssue[];
  audit_trail: AuditTrailEntry[];
  processing_time_ms: number;
  token_usage: { input_tokens: number; output_tokens: number };
  errors: RuntimeError[];
  // Extended fields — populated by full pipeline run, undefined for simple agent runs
  evidences?: any[];
  candidates?: any[];
  validation_summary?: { supported: number; needs_review: number };
  confidence_calibration?: { routing_decisions?: any[]; coding_confidences?: any[] };
  evidence_ranking?: any;
  quality_flags?: Record<string, boolean>;
  // MedCodER pipeline output (mode="medcoder" only)
  mode?: 'deepseek' | 'prompt_llm' | 'hybrid' | 'no_repair' | 'medcoder' | 'code_like_humans';
  extracted_diagnoses?: ExtractedDiagnosis[];

  // Phase 3-A Section D — Corti-style 8-field output (projected from v1 by API layer)
  // Populated when Section E wires v2 projection in runtime_platform.py.
  // All fields optional — absent when runtime returns v1-only.
  // Note: validation_summary already exists above (supported/needs_review counts);
  // Corti-style validation fields live in human_review + issues_found.
  review_conclusion?: 'PASS' | 'WARNING' | 'FAIL' | string;
  manual_review_required?: boolean;
  encounter_summary?: {
    chief_complaint?: string;
    treatment_course?: string;
    key_findings?: string[];
    document_sources?: Array<{ doc_id?: string; doc_type?: string }>;
    encounter_date?: string;
  };
  documentation_gaps?: Array<{
    gap_type?: string;
    description?: string;
    related_code?: string;
    suggestion?: string;
  }>;
  uncodable_items?: Array<{
    item_type?: string;
    text?: string;
    reason?: string;
  }>;
  corti_validation_summary?: {
    passed?: boolean;
    issues_found?: CodingIssue[];
    manual_review_required?: boolean;
    rule_set?: string;
    fired_rules?: string[];
  };
  human_review?: {
    review_conclusion?: string;
    review_required?: boolean;
    review_focus?: string[];
    notes?: string;
  };
  trace_refs?: {
    run_id?: string;
    stage_trace?: Array<Record<string, unknown>>;
    rule_fired?: string[];
    mode?: string;
    method_id?: string;
    provider?: string;
    model?: string;
  };
  // Phase 3-B2 Loop 3 (Gap 4.3) — pre-rendered Markdown for the chat UI's
  // "Rendered" tab. Populated by app.icoder.markdown_generator on the
  // backend, projected through _mapA2AResultToRunResult on the frontend.
  // When absent, the frontend falls back to auto-generating from the v2
  // 8-field JSON (Loop 3 §3 降级处理).
  markdown?: string;
}

export interface DiagnosisEntry {
  code: string;
  description: string;
  confidence: number;
  category: string;
  evidence: string[];
}

export interface ProcedureEntry {
  code: string;
  description: string;
  confidence: number;
  category: string;
  evidence: string[];
}

// ── MedCodER pipeline types (NAACL 2025 3-stage) ──

export interface EvidenceSpan {
  /** Optional client-side id (embed scenario). Not produced by runtime. */
  id?: string;
  text: string;
  char_start: number;
  char_end: number;
  doc_id?: string;
  doc_type?: string;
  /** Field this span lives in (embed scenario, M3-0 default "present_illness"). */
  field?: string;
  /** Optional match method label (exact / fuzzy / rapidfuzz / auto_bootstrap). */
  match_method?: 'exact' | 'fuzzy' | 'rapidfuzz' | 'auto_bootstrap' | string;
  /** Optional UI kind (e.g. "auto_bootstrap"). */
  kind?: string;
  /** The code this span supports (embed scenario). */
  target_code?: string;
  confidence: number;
}

export interface CandidateCode {
  code: string;
  name: string;
  score: number;
  chapter: string;
  source: 'llm' | 'retrieve' | 'differentiation_kb' | 'rerank';
}

export interface ExtractedDiagnosis {
  disease_text: string;
  supporting_evidence: EvidenceSpan[];
  llm_initial_code: string;
  retrieved_codes: CandidateCode[];
  final_top_k: CandidateCode[];
  final_confidence: number;
  rerank_notes: string;
}

export interface CodingIssue {
  severity: 'critical' | 'high' | 'medium' | 'low' | 'info';
  code: string;
  message: string;
  suggestion: string;
}

export interface AuditTrailEntry {
  step: string;
  result: string;
  duration_ms?: number;
}

export interface RuntimeError {
  code: string;
  message: string;
}

// ── Phase B: Coding Method Runtime types ────────────────────────

export type MethodFamily = 'medcoder' | 'legacy' | 'noop';

export interface CodingMethodInfo {
  method_id: string;
  method_name: string;
  method_name_en?: string;
  method_family: MethodFamily;
  stage_count: number;
  required_capabilities: Array<'llm' | 'retriever' | 'rule_set'>;
  description: string;
  available: boolean;
}

export interface ListMethodsResponse {
  methods: CodingMethodInfo[];
  capabilities: Record<'llm' | 'retriever' | 'rule_set', boolean>;
  total: number;
}

export interface MethodStageTraceEntry {
  stage_name: string;
  status: 'ok' | 'skipped' | 'failed' | 'noop' | string;
  latency_ms: number;
  output_size: number;
  notes: string;
}

export interface MethodResult {
  method_id: string;
  method_name: string;
  method_family: MethodFamily | string;
  status: 'ok' | 'unavailable' | 'error' | string;
  reason: string;
  primary_code: string;
  primary_name: string;
  primary_confidence: number;
  secondary_codes: Array<{ code: string; name: string; confidence: number; category: string }>;
  procedure_codes: Array<{ code: string; name: string; confidence: number; category: string }>;
  issues: Array<{ severity: string; code: string; message: string; suggestion: string }>;
  manual_review_required: boolean;
  confidence: number;
  stage_trace: MethodStageTraceEntry[];
  processing_time_ms: number;
}

export type CompareResultEntry = MethodResult;

export interface CompareRequest {
  emr_text: string;
  method_ids: string[];
  case_id?: string;
}

export interface CompareResponse {
  case_id: string;
  emr_chars: number;
  method_count: number;
  capabilities: Record<'llm' | 'retriever' | 'rule_set', boolean>;
  results: CompareResultEntry[];
  consensus_primary_code: string;
  // Phase D1: weighted consensus score (sum of
  // family_weight × confidence × evidence_strength per method that
  // agreed on the consensus primary). Replaces the Phase B simple
  // count of agreeing methods — weighted consensus lets MedCodER-family
  // methods with strong evidence outrank legacy-family votes even when
  // fewer in number.
  consensus_score: number;
}

export interface RunV2Request {
  emr_text: string;
  method_id?: string;
  mode?: string;
  case_id?: string;
}

export interface RunV2Response extends MethodResult {
  run_id: string;
  agent_ref: string;
}

export interface RuntimeStatus {
  started: boolean;
  started_at: string;
  execution_mode: string;
  review_coding_mode: string;
  fallback_to_legacy: boolean;
  agents_installed: number;
  providers: Record<string, { status: string; mode?: string }>;
  default_provider: string | null;
  registry_safety?: { safe: boolean; storage_path: string; issues: unknown[] };
}

export interface DataPolicy {
  allow_external_llm: boolean;
  allow_telemetry_upload: boolean;
  pii_redaction_required: boolean;
  marketplace_sync_mode: string;
  audit_log_local_only: boolean;
  persist_full_input: boolean;
}

export interface RegistryHealth {
  healthy: boolean;
  total_registry: number;
  total_db: number;
  inconsistency_count: number;
  inconsistencies: unknown[];
  registry_path: string;
  schema_version: string;
}

export interface FallbackStats {
  total_fallbacks: number;
  fallback_rate: number;
  top_errors: [string, number][];
  affected_agents: string[];
  last_fallback_at: string;
  available?: boolean;
}

export interface ShadowStats {
  total_comparisons: number;
  diagnosis_match_rate: number;
  conclusion_match_rate: number;
  procedure_match_rate: number;
  available?: boolean;
}

export interface InstalledAgent {
  agent_ref: string;
  name: string;
  version: string;
  description: string;
  category: string;
  agent_type: string;  // "certified" | "community"
  status: string;      // "installed" | "enabled" | "disabled"
  installed_at: string;
  icon: string;
  publisher_name: string;
  expert_count: number;
  tool_count: number;
  tier: number;        // 0-4 security tier
  usage_count: number;
  min_runtime_version?: string;
}

export interface MedicalCodingStatus {
  provider: string;
  mode: string;
  provider_mode: string;
  deepseek_configured: boolean;
  model: string;
  external_llm_allowed: boolean;
  pii_redaction_enabled: boolean;
  execution_mode?: string;
}

export interface RuleEngineStatus {
  status: string;
  loaded_rule_sets: string[];
  total_rule_sets: number;
}

// ── Phase 3-D1 Task 4: RunTrace Corti-parity Viewer ────────────────
// Backend: app/api/run_trace.py GET /api/runtime/runs/{run_id}/trace
// 9-step timeline (Corti parity):
//   user_message_received / planner_selected_experts / tools_list /
//   auth_resolved / scope_checked / tools_call / expert_response /
//   output_generated / completion

export type RunTraceStep =
  | 'user_message_received'
  | 'planner_selected_experts'
  | 'tools_list'
  | 'auth_resolved'
  | 'scope_checked'
  | 'tools_call'
  | 'expert_response'
  | 'output_generated'
  | 'completion';

export type RunTraceStatus = 'ok' | 'failed' | 'skipped' | string;

export interface RunTraceEvent {
  run_id: string;
  step: RunTraceStep | string;
  status?: RunTraceStatus;
  ts: number;
  duration_ms?: number;
  safe_metadata?: Record<string, unknown>;
}

export interface RunTraceResponse {
  run_id: string;
  timeline: RunTraceEvent[];
  step_count: number;
}
