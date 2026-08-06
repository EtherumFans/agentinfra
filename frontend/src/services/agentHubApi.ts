// Phase 3-B1 Section F — Agent Hub API service.
//
// Backend contract: GET /api/icoder/agents/hub returns Hub cards
// (pack-mastered from official_agents/**/agent_pack.json). See
// backend/app/api/icoder_agents_hub.py:197 (operation_id=icoder_agents_hub_list_v1).
//
// Card shape (per _build_card in icoder_agents_hub.py:116):
//   - agent_ref, name, display_name, category, maturity, production_ready
//   - runnable (true only for MVP+runnable+production-ready packs)
//   - badge (e.g. "MVP / AI-assisted", "Coming Soon / Metadata only")
//   - red_lines (no_upcoding, no_inference, evidence_required,
//     production_writeback_blocked)
//   - output_contract (schema_ref + required_fields)
//   - a2a_endpoint (None for metadata-only) — canonical A2A path
//   - run_endpoint (None for metadata-only) — compat shim
//
// Frontend rules:
//   - Prebuilt tab renders Hub cards (replaces runtimeAgentApi.listAgents
//     for the product browsing experience).
//   - metadata-only packs (runnable=false) show "Coming Soon" badge +
//     no Run button.
//   - expert-stubs and internal_engine are excluded by the backend filter
//     (_is_visible in icoder_agents_hub.py:65).

import api from './api';

export interface HubRedLines {
  no_upcoding: boolean;
  no_inference: boolean;
  evidence_required: boolean;
  production_writeback_blocked: boolean;
}

export interface HubOutputContract {
  schema_ref: string | null;
  required_fields: string[];
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

export interface CloneResponse {
  project_agent_id: string;
  runtime_agent_id: string;
  source_agent_ref: string;
  chat_url: string;
  customize_url: string;
  run_url: string;
  cloned: boolean; // true = new clone (201), false = existing (200, idempotent)
}

export const agentHubApi = {
  list: (useCase?: string) =>
    api.get<HubListResponse>('/icoder/agents/hub', {
      params: useCase ? { use_case: useCase } : undefined,
    }),
  // Phase 3-B2 Loop 1 (Gap 2.3): Clone a prebuilt Agent into the caller's org.
  // Idempotent — returns 201 on first clone, 200 with existing record on dup.
  clone: (agentId: string, body?: { name?: string; description?: string; project_id?: string }) =>
    api.post<CloneResponse>(`/icoder/agents/${encodeURIComponent(agentId)}/clone`, body || {}),
};
