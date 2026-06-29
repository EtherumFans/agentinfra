/** Agent Hub API client — /api/icoder/agents/* P1.0-B endpoints.
 *
 * Complements runtimeApi.ts (which talks to /api/runtime/*). The Agent Hub
 * surface consolidates registry + A2A + health + requirements into one
 * discoverable namespace for the Agent Hub product page.
 */

import axios from 'axios';

const api = axios.create({ baseURL: '/api/icoder/agents', timeout: 30000 });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

export interface AgentHubSummary {
  agent_ref: string;
  name: string;
  version?: string;
  description?: string;
  status: string;
  tier?: number | null;
  tier_label?: string | null;
  experimental?: boolean | null;
  production_ready?: boolean | null;
  agent_type?: string;
  category?: string;
}

export interface AgentHubList {
  agents: AgentHubSummary[];
  total: number;
  registry_status: string;
}

export interface AgentHealth {
  agent_id: string;
  registry: { available: boolean };
  faiss_index?: { available: boolean; ready?: boolean; loading?: boolean; error?: string | null; applies_to?: boolean };
  llm_provider?: { available: boolean; status?: string; model?: string; provider?: string };
  mcp_tools?: { available: boolean; registered?: string[]; count?: number };
  recorder?: { available: boolean; active?: boolean; kind?: string };
  overall: 'ready' | 'degraded' | 'blocked' | 'unknown';
  blockers?: string[];
}

export interface AgentRequirement {
  kind: string;
  path?: string;
  description?: string;
  present?: boolean;
  size_bytes?: number;
}

export interface AgentMcpTool {
  name: string;
  description: string;
  registered: boolean;
  stage?: string;
}

export interface AgentEnvVar {
  name: string;
  description: string;
  set: boolean;
  value: string;
}

export interface AgentRequirements {
  agent_id: string;
  agent_ref: string;
  format_version: string;
  agent_type: string;
  tier: number;
  tier_label: string;
  experimental: boolean;
  production_ready: boolean;
  permissions: Record<string, unknown>;
  files: AgentRequirement[];
  mcp_tools: AgentMcpTool[];
  env_vars: AgentEnvVar[];
  experts: Array<{ id: string; role: string }>;
  requirements: Record<string, unknown>;
  human_review_required_when: unknown[];
}

export interface AgentCard {
  name: string;
  description: string;
  version: string;
  capabilities?: Record<string, unknown>;
  skills?: Array<Record<string, unknown>>;
  metadata?: Record<string, unknown>;
  [k: string]: unknown;
}

export interface AgentNotFound {
  error_code: 'AGENT_NOT_FOUND';
  agent_id: string;
  message: string;
}

export const agentHubApi = {
  list: () => api.get<AgentHubList>('/').then((r) => r.data),
  getCard: (agentId: string) =>
    api.get<AgentCard>(`/${encodeURIComponent(agentId)}/card`).then((r) => r.data),
  getHealth: (agentId: string) =>
    api.get<AgentHealth>(`/${encodeURIComponent(agentId)}/health`).then((r) => r.data),
  getRequirements: (agentId: string) =>
    api.get<AgentRequirements>(`/${encodeURIComponent(agentId)}/requirements`).then((r) => r.data),
};