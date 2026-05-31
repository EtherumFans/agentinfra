// iCoDer SDK — TypeScript Types

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: User;
}

export interface User {
  id: string;
  username: string;
  email: string;
  full_name: string;
  role: UserRole;
  department: string;
  is_active: boolean;
}

export type UserRole = 'admin' | 'coder' | 'dept_head' | 'insurance' | 'qc' | 'clinician' | 'it';

export interface Encounter {
  id?: string;
  encounter_id?: string;
  patient_id?: string;
  department?: string;
  status?: string;
  raw_text?: string;
  created_at?: string;
}

export interface Document {
  id?: string;
  encounter_id?: string;
  content: string;
  template_key?: string;
}

export interface ClinicalEvidence {
  id: string;
  entity_type: string;
  text: string;
  code?: string;
  confidence?: number;
}

export interface CodeCandidate {
  id: string;
  code: string;
  name: string;
  finding: string;
  status: string;
  confidence?: number;
  evidences?: string[];
}

export interface Review {
  id?: string;
  review_id?: string;
  encounter_id?: string;
  status?: string;
  primary_diagnosis?: { code: string; name: string; judgment: string };
  main_procedure?: { code: string; name: string; judgment: string };
  candidates?: CodeCandidate[];
  evidences?: ClinicalEvidence[];
  processing_time_ms?: number;
  pipeline_id?: string;
  human_review_status?: string;
  primary_diagnosis_name?: string;
  created_at?: string;
}

export interface FactDiagnosis {
  diagnosis: string;
  icd10cm_code?: string;
  status?: string;
  evidence?: string;
}

export interface FactProcedure {
  procedure: string;
  icd9cm3_code?: string;
  status?: string;
  evidence?: string;
}

export interface FactExtractionResult {
  chief_complaint?: string;
  diagnosis_facts?: FactDiagnosis[];
  procedure_facts?: FactProcedure[];
  negated_findings?: { finding: string; evidence?: string }[];
  timing_facts?: Record<string, string>;
  documentation_overview?: Record<string, string>;
}

export interface FactExtractResponse {
  facts: FactExtractionResult;
  raw_output: string;
  credits_consumed: number;
}

export interface AgentTemplate {
  id: string;
  name: string;
  description: string;
  category: string;
  system_prompt?: string;
  expert_ids?: string[];
}

export interface Expert {
  id: string;
  name: string;
  description?: string;
  category?: string;
  is_published?: boolean;
  system_prompt?: string;
  mcp_servers?: McpServer[];
}

export interface McpServer {
  id: string;
  name: string;
  url: string;
}

export interface TextGenTemplate {
  key: string;
  name: string;
  desc: string;
  category: string;
  sample: string;
}

export interface TextGenResponse {
  output: string;
  credits_consumed: number;
}

export interface GoldCase {
  id: string;
  department: string;
  diagnosis_group: string;
  original_primary_diagnosis: string;
  gold_primary_diagnosis: string;
  difficulty: string;
}

export interface EvaluationSummary {
  primary_diag_accuracy: number;
  main_proc_accuracy: number;
  evidence_completeness_avg: number;
  hallucination_rate: number;
  missing_code_recall: number;
  avg_overall_score: number;
  total_cases: number;
  per_case_results: any[];
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface UsageSummary {
  total_requests: number;
  credits_used: number;
  avg_response_time_ms: number;
  tokens_used?: number;
}

export interface ClientCredentials {
  clientId: string;
  clientSecret: string;
  baseURL?: string;
}
