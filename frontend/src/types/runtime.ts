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

export interface MarketplacePackage {
  id: string;
  name: string;
  version: string;
  description: string;
  category: string;
  icon: string;
  agent_type: string;
  publisher_name: string;
  publisher_email?: string;
  expert_count: number;
  tool_count: number;
  downloads: number;
  published_at: string;
  integrity?: { sha256: string };
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
