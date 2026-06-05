// iCoDer Frontend - TypeScript Types

export interface User {
  id: string;
  username: string;
  email: string;
  full_name: string;
  role: UserRole;
  department: string;
  is_active: boolean;
  created_at: string;
}

export type UserRole = 'admin' | 'coder' | 'dept_head' | 'insurance' | 'qc' | 'clinician' | 'it';

export interface OrgInfo {
  id: string;
  name: string;
  slug: string;
  plan: string;
  role: string;
  is_default: boolean;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: User;
  organizations?: OrgInfo[];
  current_org_id?: string;
}

export interface Encounter {
  id: string;
  encounter_id: string;
  patient_id: string;
  department: string;
  admission_time: string | null;
  discharge_time: string | null;
  admission_reason: string | null;
  existing_diagnosis_codes: ExistingCode[];
  existing_procedure_codes: ExistingCode[];
  status: string;
  documents: Document[];
  created_at: string;
  updated_at: string;
}

export interface Document {
  id: string;
  doc_type: string;
  title: string;
  content: string;
  doc_order: number;
  created_at: string;
}

export interface ExistingCode {
  code: string;
  name: string;
}

export interface CodeCandidate {
  id: string;
  finding: string;
  code_system: string;
  code: string;
  name: string;
  score: number;
  chapter?: string;
  evidence_ids: string[];
  status: string;
  rule_checks?: RuleCheck[];
  human_decision?: string;
  human_reason?: string;
  modified_code?: string;
  modified_name?: string;
}

export interface RuleCheck {
  rule_id: string;
  rule_name: string;
  status: 'pass' | 'warn' | 'fail';
  message: string;
}

export interface ClinicalEvidence {
  id: string;
  doc_type: string;
  text: string;
  entity_type: string;
  supports_codes: string[];
  certainty: string;
  negation: boolean;
  confidence: number;
  start_char?: number;
  end_char?: number;
}

export interface ValidationSummary {
  total_codes: number;
  supported: number;
  needs_review: number;
  unsupported: number;
  evidence_binding_rate: number;
  documentation_gaps: number;
  drg_risks: number;
  pipeline_errors: number;
}

export interface Review {
  id: string;
  review_id: string;
  encounter_id: string;
  agent_version: string;
  model_used: string;
  primary_diagnosis: PrimaryDiagnosis | null;
  main_procedure: MainProcedure | null;
  secondary_diagnoses: SecondaryCode[];
  other_procedures: SecondaryCode[];
  diagnosis_analysis: AnalysisItem[];
  procedure_analysis: AnalysisItem[];
  documentation_gaps: DocumentationGap[];
  uncodable_items: UncodableItem[];
  drg_impact: DrgImpact | null;
  human_checklist: string[];
  validation_summary: ValidationSummary | null;
  report_markdown: string | null;
  report_html: string | null;
  human_review_status: string;
  reviewed_by: string | null;
  reviewer_notes: string | null;
  processing_time_ms: number | null;
  error_message: string | null;
  candidates: CodeCandidate[];
  evidences: ClinicalEvidence[];
  created_at: string;
  updated_at: string;
}

export interface PrimaryDiagnosis {
  code: string;
  name: string;
  confidence: number;
  evidence_ids: string[];
  judgment: string;
}

export interface MainProcedure {
  code: string;
  name: string;
  confidence: number;
  evidence_ids: string[];
  judgment: string;
}

export interface SecondaryCode {
  code: string;
  name: string;
  score: number;
}

export interface AnalysisItem {
  finding: string;
  code: string;
  name: string;
  score: number;
  evidence?: string;
}

export interface DocumentationGap {
  severity: string;
  type: string;
  description: string;
  suggestion: string;
}

export interface UncodableItem {
  finding: string;
  reason: string;
  evidence_text: string;
}

export interface DrgImpact {
  drg_risks?: DrgRisk[];
  recommendations?: string[];
  potential_group?: {
    estimated_group: string;
    confidence: string;
    note: string;
  };
  // Extended fields from agent pipeline
  estimated_drg?: string;
  specificity_risks?: Array<{ code?: string; name?: string; description?: string; message?: string }>;
  mcc_cc_analysis?: {
    mcc_count?: number;
    cc_count?: number;
    missing?: string[];
  };
  code_mismatch_risks?: Array<{ description?: string; message?: string }>;
  dip_impact?: {
    estimated_points?: number;
    estimated_payment?: number;
  };
  [key: string]: any; // Allow additional dynamic fields from pipeline
}

export interface DrgRisk {
  type: string;
  severity: 'low' | 'medium' | 'high';
  description: string;
}

export interface GoldCase {
  id: string;
  case_id: string;
  department: string;
  diagnosis_group: string;
  original_primary_diagnosis: string;
  original_primary_diag_name: string;
  original_main_procedure?: string;
  original_main_proc_name?: string;
  gold_primary_diagnosis: string;
  gold_primary_diag_name: string;
  gold_main_procedure?: string;
  gold_main_proc_name?: string;
  gold_secondary_diagnoses?: SecondaryCode[];
  gold_other_procedures?: SecondaryCode[];
  missing_codes?: ExistingCode[];
  unsupported_codes?: ExistingCode[];
  documentation_gaps?: DocumentationGap[];
  difficulty: string;
  source: string;
  tags?: string[];
  reviewer?: string;
  agent_accuracy?: number;
  last_evaluated_at?: string;
  created_at: string;
  updated_at: string;
}

export interface EvaluationSummary {
  total_cases: number;
  correct: number;
  primary_dx_match_rate: number;
  per_case: EvalCaseResult[];
  per_category: Record<string, { total: number; correct: number; rate: number }>;
  elapsed_seconds: number;
  execution_mode: string;
}

export interface EvalCaseResult {
  case_id: string;
  category: string;
  title: string;
  expected_dx: string;
  actual_dx: string;
  correct: boolean;
  run_id: string;
  latency_ms: number;
}

export interface CodeSearchResult {
  code: string;
  name: string;
  score: number;
  chapter?: string;
  parent_code?: string;
  valid: boolean;
}

export interface RuleResult {
  rule_id: string;
  rule_set: string;
  title: string;
  content: string;
  relevance: number;
  category?: string;
  examples?: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}
