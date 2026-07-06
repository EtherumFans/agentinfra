// Phase 3-B1 Section F — Agent Hub API service.
//
// Backend contract: GET /api/icoder/agents/hub returns Corti-style Hub cards
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
//     for the Corti-style product browsing experience).
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
  maturity: string; // 'metadata-only' | 'stub' | 'mvp' | 'runnable' | 'production-ready'
  production_ready: boolean;
  human_review: string; // 'required' | 'optional' | 'not_required'
  hidden_from_hub: boolean;
  runnable: boolean;
  badge: string;
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
  // Phase 3-B2 Loop 1 (Gap 2.3): Corti-style action URLs.
  clone_url: string | null; // POST /api/icoder/agents/{agent_id}/clone
  chat_url: string | null; // template: /agents/{project_agent_id}/chat
  customize_url: string | null; // template: /ai-studio/agents/{project_agent_id}
  run_url: string | null; // A2A mainline URL
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
