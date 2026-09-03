// Phase 3-B1 Section F — Agent Hub API service.
//
// Backend contract: GET /api/icoder/agents/hub returns Hub cards
// (pack-mastered from official_agents/**/agent_pack.json). See
// backend/app/api/icoder_agents_hub.py:197 (operation_id=icoder_agents_hub_list_v1).
//
// Card shape (per _build_card in icoder_agents_hub.py:116):
//   - agent_ref, name, display_name, category, maturity, production_ready
//   - runnable (true only for executable lifecycle states)
//   - badge (e.g. "Launch candidate / AI-assisted")
//   - red_lines (no_upcoding, no_inference, evidence_required,
//     production_writeback_blocked)
//   - output_contract (schema_ref + required/optional field allowlist + JSON types)
//   - a2a_endpoint — canonical A2A path for executable packs
//   - run_endpoint — compatibility shim for executable packs
//
// Frontend rules:
//   - Prebuilt tab renders Hub cards (replaces runtimeAgentApi.listAgents
//     for the product browsing experience).
//   - only executable, runnable, non-MVP launch candidates cross this client
//     boundary; older/misconfigured backends fail closed.
//   - expert-stubs and internal_engine are excluded by the backend filter
//     (_is_visible in icoder_agents_hub.py:65).

import api from './api';
import { filterHubLaunchCandidateCards } from './agentHubVisibility';
import {
  failClosedHubCards,
  mergeHubTenantReadiness,
} from './agentHubReadiness';

export { mergeHubTenantReadiness } from './agentHubReadiness';

export interface HubRedLines {
  no_upcoding: boolean;
  no_inference: boolean;
  evidence_required: boolean;
  production_writeback_blocked: boolean;
}

export interface HubOutputContract {
  schema_ref: string | null;
  required_fields: string[];
  optional_fields: string[];
  field_types: Record<string, 'string' | 'boolean' | 'integer' | 'number' | 'object' | 'array'>;
  field_schemas: Record<string, HubOutputFieldSchema>;
  field_relations?: HubOutputFieldRelation[];
  evidence_bindings?: HubOutputEvidenceBinding[];
  cross_agent_relations?: HubOutputCrossAgentRelation[];
}

export type HubOutputRelationOperator =
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

export interface HubOutputFieldPredicate {
  path: string;
  operator: HubOutputRelationOperator;
  value?: unknown;
  other_path?: string;
  where?: HubOutputFieldPredicate[];
  item_path?: string;
  other_item_path?: string;
}

export interface HubOutputEvidenceBinding {
  id: string;
  for_each: string;
  text_path: string;
  span_path?: string;
  start_path?: string;
  end_path?: string;
  document_id_path?: string;
  document_version_path?: string;
}

export interface HubOutputCrossAgentRelation {
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

export interface HubOutputFieldRelation {
  id: string;
  for_each?: string;
  when: HubOutputFieldPredicate[];
  must: HubOutputFieldPredicate[];
}

export interface HubOutputFieldSchema {
  type: 'string' | 'boolean' | 'integer' | 'number' | 'object' | 'array';
  properties?: Record<string, HubOutputFieldSchema>;
  required?: string[];
  additionalProperties?: false | HubOutputFieldSchema;
  items?: HubOutputFieldSchema;
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

// Phase 5 Track D P0 Gate 1 (2026-07-11) — user-visible display status.
// PDF §B3 taxonomy: 5 statuses, max 2 badges per card. Frontend MUST
// render these instead of raw maturity/production_ready/human_review.
export type DisplayStatus =
  | 'preview'
  | 'available'
  | 'controlled_use'
  | 'coming_soon'
  | 'deprecated';

export type BadgeType =
  | 'preview'
  | 'available'
  | 'controlled_use'
  | 'coming_soon'
  | 'deprecated'
  | 'approval_required'
  | 'anomaly_confirmation_required'
  | 'clinical_decision_confirmation_required'
  | 'internal_only';

export interface DisplayBadge {
  type: BadgeType;
  label_zh: string;
  label_en: string;
}

export interface HubCard {
  agent_ref: string;
  agent_id: string; // short form (e.g. 'medical-coding-agent'), used in URL paths
  name: string;
  display_name: string;
  category: string;
  category_display?: string;
  // Phase 3-B2 Loop 4: top-level use_case (manifest.use_case with fallback
  // to category for pre-Loop 4 packs). Used by /hub?use_case= filter and
  // the frontend use_case dropdown.
  use_case?: string;
  icon?: string;
  version: string;
  description: string;
  /**
   * Engineering-internal fields. PDF §B1: MUST NOT be rendered directly on
   * user-facing cards. Retained for engineering dashboards / debug views.
   * Use ``display_status`` + ``display_badges`` instead.
   */
  maturity: string; // 'metadata-only' | 'stub' | 'mvp' | 'runnable' | 'production-ready'
  production_ready: boolean;
  /** Engineering-only development gate; never render as production approval. */
  pack_status: 'executable' | 'metadata_only' | 'invalid';
  launch_candidate_ready: boolean;
  launch_candidate_blockers: string[];
  external_release_gates: string[];
  execution_path: string;
  execution_target: string;
  runtime_readiness: {
    structural_status: 'ready' | 'blocked';
    configuration_status:
      | 'not_checked'
      | 'local_ready'
      | 'configured_live_verified'
      | 'configured_not_live_verified'
      | 'unavailable';
    run_action_enabled: boolean;
    reason: string;
    runtime_dependencies: string[];
    external_llm_required: boolean;
    live_health_verified: boolean;
    connectivity_status?:
      | 'not_applicable'
      | 'not_run'
      | 'verified'
      | 'expired'
      | 'failed';
    semantic_validation_status: 'verified' | 'not_verified';
    production_approval_status: 'approved' | 'not_approved';
  };
  human_review: string; // 'required' | 'optional' | 'not_required'
  hidden_from_hub: boolean;
  runnable: boolean;
  badge: string; // legacy engineering badge string (deprecated, kept for compat)
  // Phase 5 Track D P0 Gate 1: user-visible status (PDF §B3).
  display_status: DisplayStatus;
  display_badges: DisplayBadge[]; // ≤ 2 entries
  usage_boundaries: string[]; // zh + en boundary copy
  display_status_internal?: Record<string, unknown>; // engineering view (not for users)
  tags: string[];
  workflow: string;
  red_lines: HubRedLines;
  requirements: {
    min_runtime_version: string | null;
    icoder_runtime_modules: string[];
    required_models: string[];
  };
  output_contract: HubOutputContract;
  non_goals: string[];
  human_review_required_when: string[];
  a2a_endpoint: string | null;
  run_endpoint: string | null;
  // Phase 3-B2 Loop 1 (Gap 2.3): action URLs.
  clone_url: string | null; // POST /api/icoder/agents/{agent_id}/clone
  chat_url: string | null; // template: /agents/{project_agent_id}/chat
  customize_url: string | null; // template: /ai-studio/agents/{project_agent_id}
  run_url: string | null; // A2A mainline URL
  // Phase 4-D (D-6): card metadata (DD-Mon-YYYY · Creator).
  created_at?: string;
  creator?: string;
  // Phase 4-F (2026-07-09): Prebuilt Agent spec v1.3 fields — drive the
  // Agents list runtime_mode badge + the Agent Detail "Try" demo button +
  // the Settings panel runtime selector. Empty for legacy packs that
  // haven't been upgraded to v1.3 spec yet.
  default_runtime_mode?: string;
  available_runtime_modes?: string[];
  example_inputs?: Array<Record<string, unknown>>;
  example_outputs?: Array<Record<string, unknown>>;
  built_by?: string;
}

export interface HubListResponse {
  agents: HubCard[];
  total: number;
  source: string;
  schema_version: string;
}

export interface HubTenantRuntimeReadiness {
  structural_status: 'ready' | 'blocked';
  configuration_status: 'local_ready' | 'configured' | 'unavailable';
  run_action_enabled: boolean;
  reason: string;
  runtime_dependencies: string[];
  llm_required: boolean;
  live_health_verified: boolean;
  connectivity_status:
    | 'not_applicable'
    | 'not_run'
    | 'verified'
    | 'expired'
    | 'failed';
  semantic_validation_status: 'verified' | 'not_verified';
  production_approval_status: 'approved' | 'not_approved';
}

export interface HubTenantReadinessEvidence {
  scope: 'tenant_configuration_and_connectivity';
  selection_mode: 'inherit' | 'pinned';
  selection_version: number;
  deployment_id: string | null;
  provider_id: string | null;
  configuration_probe_status: string;
  canary_checked_at: string | null;
  canary_expires_at: string | null;
}

export interface HubTenantReadinessItem {
  agent_id: string;
  execution_target: string;
  runtime_readiness: HubTenantRuntimeReadiness;
  evidence: HubTenantReadinessEvidence;
}

export interface HubTenantReadinessResponse {
  agents: HubTenantReadinessItem[];
  total: number;
  generated_at: string;
  schema_version: '1.0';
}

export interface CloneResponse {
  project_agent_id: string;
  runtime_agent_id: string; // project-scoped identity used by Run/A2A
  source_runtime_agent_id: string; // server-side pinned implementation identity
  source_agent_ref: string;
  chat_url: string;
  customize_url: string;
  run_url: string;
  cloned: boolean; // true = new clone (201), false = existing (200, idempotent)
}

export const agentHubApi = {
  list: async (useCase?: string) => {
    const response = await api.get<HubListResponse>('/icoder/agents/hub', {
      params: useCase ? { use_case: useCase } : undefined,
    });
    const agents = failClosedHubCards(
      filterHubLaunchCandidateCards(response.data?.agents),
    );
    return {
      ...response,
      data: {
        ...response.data,
        agents,
        total: agents.length,
      },
    };
  },
  readiness: () => api.get<HubTenantReadinessResponse>(
    '/icoder/agents/hub/readiness',
  ),
  listWithTenantReadiness: async (useCase?: string) => {
    const [listResponse, readinessResponse] = await Promise.all([
      agentHubApi.list(useCase),
      agentHubApi.readiness().catch(() => null),
    ]);
    const agents = mergeHubTenantReadiness(
      listResponse.data.agents,
      readinessResponse?.data,
    );
    return {
      ...listResponse,
      data: {
        ...listResponse.data,
        agents,
        total: agents.length,
      },
    };
  },
  // Phase 3-B2 Loop 1 (Gap 2.3): Clone a prebuilt Agent into the caller's org.
  // Idempotent — returns 201 on first clone, 200 with existing record on dup.
  clone: (agentId: string, body?: { name?: string; description?: string; project_id?: string }) =>
    api.post<CloneResponse>(`/icoder/agents/${encodeURIComponent(agentId)}/clone`, body || {}),
};
