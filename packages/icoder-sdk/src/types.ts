// iCoDer SDK — TypeScript Types

export interface TokenResponse {
  access_token: string;
  refresh_token?: string;
  token_type: string;
  expires_in?: number;
  scope?: string;
  realm?: string | null;
  user?: User;
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

export interface FactItem {
  group: string;
  text: string;
  value: string;
}

export interface FactExtractRequest {
  context: Array<{ type: 'text'; text: string }>;
  outputLanguage?: string;
}

export interface FactExtractResponse {
  facts: FactItem[];
  outputLanguage: string;
  usageInfo: { creditsConsumed: number };
}

export interface AgentTemplate {
  id: string;
  name: string;
  description: string;
  category: string;
  system_prompt?: string;
  expert_ids?: string[];
}

export type AgentOutputFieldType =
  | 'string'
  | 'boolean'
  | 'integer'
  | 'number'
  | 'object'
  | 'array';

export interface AgentOutputFieldSchema {
  type: AgentOutputFieldType;
  properties?: Record<string, AgentOutputFieldSchema>;
  required?: string[];
  additionalProperties?: false | AgentOutputFieldSchema;
  items?: AgentOutputFieldSchema;
  enum?: unknown[];
  const?: unknown;
  minimum?: number;
  maximum?: number;
  minLength?: number;
  maxLength?: number;
  pattern?: string;
  minItems?: number;
  maxItems?: number;
  uniqueItems?: boolean;
  'x-order'?: 'nondecreasing' | 'strictly_increasing';
}

export type AgentOutputRelationOperator =
  | 'equals'
  | 'not_equals'
  | 'present'
  | 'absent'
  | 'empty'
  | 'non_empty'
  | 'equals_path'
    | 'not_equals_path'
    | 'length_equals'
    | 'in'
    | 'not_in'
    | 'gt'
    | 'gte'
    | 'lt'
    | 'lte'
    | 'count_where_equals'
    | 'contains_field_equals_path'
    | 'disjoint_fields';

export interface AgentOutputFieldPredicate {
  path: string;
  operator: AgentOutputRelationOperator;
  value?: unknown;
    other_path?: string;
    where?: AgentOutputFieldPredicate[];
    item_path?: string;
    other_item_path?: string;
}

  export interface AgentOutputFieldRelation {
    id: string;
    for_each?: string;
    when: AgentOutputFieldPredicate[];
  must: AgentOutputFieldPredicate[];
  }

  export interface AgentOutputEvidenceBinding {
    id: string;
    for_each: string;
    text_path: string;
    span_path?: string;
    start_path?: string;
    end_path?: string;
    document_id_path?: string;
    document_version_path?: string;
  }

  export interface AgentOutputCrossAgentRelation {
    id: string;
    local_path: string;
    local_item_path?: string;
    upstream_agent_id: string;
    upstream_path: string;
    upstream_item_path: string;
    operator:
      | 'equals_upstream'
      | 'scalar_in_upstream_items'
      | 'local_items_subset_upstream_items'
      | 'local_items_overlap_upstream_items';
    normalization?: 'none' | 'medical_code';
    required?: boolean;
  }

export interface AgentHubOutputContract {
  schema_ref: string | null;
  required_fields: string[];
  optional_fields: string[];
  field_types: Record<string, AgentOutputFieldType>;
  field_schemas: Record<string, AgentOutputFieldSchema>;
    field_relations?: AgentOutputFieldRelation[];
    evidence_bindings?: AgentOutputEvidenceBinding[];
    cross_agent_relations?: AgentOutputCrossAgentRelation[];
}

export interface AgentHubRuntimeReadiness {
  structural_status: 'ready' | 'blocked';
  configuration_status:
    | 'not_checked'
    | 'local_ready'
    | 'configured_not_live_verified'
    | 'unavailable';
  run_action_enabled: boolean;
  reason: string;
  runtime_dependencies: string[];
  external_llm_required: boolean;
  live_health_verified: boolean;
  semantic_validation_status: 'verified' | 'not_verified';
  production_approval_status: 'approved' | 'not_approved';
}

export interface AgentHubCard {
  agent_id: string;
  agent_ref: string;
  name: string;
  description: string;
  category: string;
  use_case?: string;
  runnable: boolean;
  launch_candidate_ready: boolean;
  production_ready: boolean;
  human_review: string;
  execution_path: string;
  execution_target: string;
  runtime_readiness: AgentHubRuntimeReadiness;
  output_contract: AgentHubOutputContract;
  [key: string]: unknown;
}

export interface AgentHubResponse {
  agents: AgentHubCard[];
  total: number;
  source: string;
  schema_version: '1.3';
}

export interface AgentHubTenantRuntimeReadiness {
  structural_status: 'ready' | 'blocked';
  configuration_status: 'local_ready' | 'configured' | 'unavailable';
  run_action_enabled: boolean;
  reason: string;
  runtime_dependencies: string[];
  llm_required: boolean;
  live_health_verified: boolean;
  connectivity_status: 'not_applicable' | 'not_run' | 'verified' | 'expired' | 'failed';
  semantic_validation_status: 'verified' | 'not_verified';
  production_approval_status: 'approved' | 'not_approved';
}

export interface AgentHubTenantReadinessEvidence {
  scope: 'tenant_configuration_and_connectivity';
  selection_mode: 'inherit' | 'pinned';
  selection_version: number;
  deployment_id: string | null;
  provider_id: string | null;
  configuration_probe_status: string;
  canary_checked_at: string | null;
  canary_expires_at: string | null;
}

export interface AgentHubTenantReadinessItem {
  agent_id: string;
  execution_target: string;
  runtime_readiness: AgentHubTenantRuntimeReadiness;
  evidence: AgentHubTenantReadinessEvidence;
}

export interface AgentHubTenantReadinessResponse {
  agents: AgentHubTenantReadinessItem[];
  total: number;
  generated_at: string;
  schema_version: '1.0';
}

/** A2A v0.3 discovery card returned by /api/icoder/agents/{id}/card. */
export interface A2ALegacyAgentCard {
  name: string;
  description: string;
  url: string;
  version: string;
  provider: string;
  documentationUrl?: string;
  capabilities: {
    streaming: boolean;
    pushNotifications: boolean;
    stateTransitionHistory: boolean;
    extensions?: Array<Record<string, unknown>>;
  };
  skills: Array<{
    id: string;
    name: string;
    description: string;
    inputSchema?: Record<string, unknown>;
    outputSchema?: Record<string, unknown>;
    examples?: Array<Record<string, unknown>>;
  }>;
  defaultInputModes: string[];
  defaultOutputModes: string[];
  securitySchemes: Record<string, unknown>;
  metadata?: Record<string, unknown>;
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
  /** Managed by the SDK after the first token exchange. */
  accessToken?: string;
  baseURL?: string;
}
