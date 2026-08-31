// iCoDer - API Client
import axios, { AxiosError } from 'axios';

import type {
  TokenResponse, Encounter, PaginatedResponse,
  CodeSearchResult,
} from '../types';
import { useToastStore, useAuthStore } from '../store';

const toast = (msg: string, type: 'error' | 'warning' | 'success') => {
  try { useToastStore.getState().addToast(msg, type); } catch {}
};

const api = axios.create({
  baseURL: '/api',
  timeout: 120000, // 2 min for long-running reviews
});

// Auto-attach token + tenant hint.
//
// Phase A1A Gate 4.2 — closes GATE3R_011 (frontend did not send
// Tenant-Name). The backend now treats the header as a non-authoritative
// hint: the JWT ``org_id`` claim is the source of truth. We still
// send the header for two reasons:
//   1. Audit log scoping — backend logs the hint alongside the JWT
//      value so cross-claim mismatches are visible in forensics.
//   2. Local-dev single-tenant mode — when no JWT is present (e.g.
//      unauthenticated health pings), the backend uses the header
//      to record which tenant the caller *thought* they were hitting.
// A mismatch between header and JWT now produces 400
// ``tenant_header_mismatch`` (authoritative source = JWT), so a
// stale frontend value cannot accidentally widen access.
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  const orgId = useAuthStore.getState().currentOrgId;
  if (orgId) {
    config.headers['Tenant-Name'] = orgId;
  }
  return config;
});

// Auto-refresh on 401
api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    if (error.response?.status === 401) {
      const refreshToken = localStorage.getItem('refresh_token');
      if (refreshToken && error.config && !(error.config as any)._retry) {
        (error.config as any)._retry = true;
        try {
          const { data } = await axios.post<TokenResponse>('/api/auth/refresh', { refresh_token: refreshToken });
          localStorage.setItem('access_token', data.access_token);
          localStorage.setItem('refresh_token', data.refresh_token);
          error.config.headers.Authorization = `Bearer ${data.access_token}`;
          return api(error.config);
        } catch {
          localStorage.removeItem('access_token');
          localStorage.removeItem('refresh_token');
          localStorage.removeItem('icoder-auth');
          window.location.href = '/login';
        }
      }
    }
    // Global error toast — map to readable Chinese
    if (error.response) {
      const status = error.response.status;
      const detail = (error.response.data as any)?.detail;
      if (status >= 500) {
        toast('服务器错误，请稍后重试', 'error');
      } else if (status === 429) {
        toast('请求过于频繁，请稍后重试', 'warning');
      } else if (status === 404) {
        // 404 is often expected, skip toast
      } else if (status === 403) {
        toast('权限不足，请联系管理员', 'error');
      } else if (status === 400) {
        // Map structured errors to readable Chinese
        const msg = typeof detail === 'string' ? detail :
          (Array.isArray((detail as any)?.errors) ? (detail as any).errors.join('; ') : '');
        toast(msg || '请求参数错误', 'warning');
      } else if (status === 0 || error.code === 'ECONNABORTED') {
        toast('网络连接超时，请检查网络后重试', 'error');
      } else if (!error.response && error.request) {
        toast('无法连接到服务器', 'error');
      }
    }
    return Promise.reject(error);
  },
);

// Auth
export const authApi = {
  login: (username: string, password: string) =>
    api.post<TokenResponse>('/auth/login', { username, password }),
  register: (username: string, password: string, email: string, fullName: string) =>
    api.post<TokenResponse>('/auth/register', { username, password, email, full_name: fullName }),
  refresh: (refreshToken: string) =>
    api.post<TokenResponse>('/auth/refresh', { refresh_token: refreshToken }),
  me: () => api.get('/auth/me'),
  switchOrg: (orgId: string) =>
    api.post<TokenResponse>('/auth/switch-org', { org_id: orgId }),
  forgotPassword: (email: string) =>
    api.post('/auth/forgot-password', { email }),
  changePassword: (currentPassword: string, newPassword: string) =>
    api.post('/auth/change-password', { current_password: currentPassword, new_password: newPassword }),
  resetPassword: (token: string, newPassword: string) =>
    api.post('/auth/reset-password', { token, new_password: newPassword }),
  revokeTokens: (reason = 'manual') =>
    api.post('/auth/revoke-tokens', { reason }),
};

// Organizations
export const orgApi = {
  list: () => api.get('/organizations'),
  create: (data: { name: string; plan?: string }) => api.post('/organizations', data),
  get: (orgId: string) => api.get(`/organizations/${orgId}`),
  update: (orgId: string, data: any) => api.patch(`/organizations/${orgId}`, data),
  getMembers: (orgId: string) => api.get(`/organizations/${orgId}/members`),
  invite: (orgId: string, data: { email: string; role: string }) =>
    api.post(`/organizations/${orgId}/invites`, data),
  acceptInvite: (token: string) =>
    api.post('/organizations/invites/accept', { token }),
  removeMember: (orgId: string, userId: string) =>
    api.delete(`/organizations/${orgId}/members/${userId}`),
  updateMemberRole: (orgId: string, userId: string, data: { role: string }) =>
    api.patch(`/organizations/${orgId}/members/${userId}`, data),
};

// Encounters
export const encountersApi = {
  create: (data: any) => api.post<Encounter>('/encounters', data),
  createFromText: (data: any) => api.post<Encounter>('/encounters/text', data),
  list: (page = 1, pageSize = 20, status = '') =>
    api.get<PaginatedResponse<Encounter>>('/encounters', { params: { page, page_size: pageSize, status } }),
  get: (id: string) => api.get<Encounter>(`/encounters/${id}`),
  delete: (id: string) => api.delete(`/encounters/${id}`),
};

// Codes
export const codesApi = {
  search: (query: string, codeSystem = 'ICD10_CN', topK = 10) =>
    api.post<{ results: CodeSearchResult[] }>('/codes/search', { query, code_system: codeSystem, top_k: topK }),
  explore: (code: string, codeSystem = 'ICD10_CN') =>
    api.post('/codes/explore', { code, code_system: codeSystem }),
  systems: () => api.get('/codes/systems'),
  verify: (data: any) => api.post('/codes/verify', data),
};

// Billing
export const billingApi = {
  balance: () => api.get<{
    balance: number;
    reserved: number;
    available: number;
    currency: string;
    simulation: boolean;
    ledger_authoritative: boolean;
    quota: { kind: string; limit: number | null; remaining: number; enforced: boolean };
    alerts: { low_balance: boolean; threshold: number };
  }>('/billing/balance'),
  transactions: (limit = 20) =>
    api.get<{ transactions: any[]; total: number }>('/billing/transactions', { params: { limit } }),
  addCredits: (amount: number) =>
    api.post<{ status: string; added: number; new_balance: number; simulation: boolean }>('/billing/credits', null, { params: { amount } }),
  simulateDebit: (amount: number, reference: string) =>
    api.post<{ status: string; debited: number; new_balance: number; simulation: boolean }>('/billing/simulation/debit', { amount, reference }),
  runSettlements: (limit = 20) =>
    api.get<{
      items: Array<{
        run_id: string;
        status: string;
        reserved_amount: number;
        settled_amount: number;
        currency: string;
        error_code?: string | null;
        created_at?: string | null;
      }>;
      total: number;
      simulation: boolean;
    }>('/billing/run-settlements', { params: { limit } }),
  retryRunSettlement: (runId: string) =>
    api.post(`/billing/run-settlements/${encodeURIComponent(runId)}/retry`),
  reconcileStaleRunSettlements: (olderThanSeconds = 3600) =>
    api.post<{
      simulation: boolean;
      released: number;
      marked_retryable: number;
      skipped_active: number;
      inspected: number;
      older_than_seconds: number;
    }>('/billing/run-settlements/reconcile-stale', null, {
      params: { older_than_seconds: olderThanSeconds },
    }),
};

// API Keys
export const keysApi = {
  list: () => api.get<{ keys: any[] }>('/keys'),
  create: (name: string) =>
    api.post<{ id: string; name: string; key_prefix: string; key_full: string; status: string; created_at: string }>(
      '/keys', null, { params: { name } }
    ),
  delete: (id: string) => api.delete(`/keys/${id}`),
};

// OAuth Clients
export const oauthApi = {
  // Console-internal endpoints (oauth.py) — list / create / delete
  // Sprint 1 audit reference: docs/governance/CONSOLE_API_CLIENTS_AUDIT.md
  list: () => api.get<{ clients: any[] }>('/oauth/clients'),
  create: (
    name: string,
    description = '',
    scopes = 'api:read api:write',
    tokenExpires = 3600,
    allowedAgentIds: string[] = [],
    allowedPurposes: string[] = [],
  ) => {
    const params = new URLSearchParams({
      name,
      description,
      scopes,
      token_expires_seconds: String(tokenExpires),
      allowed_agent_ids: allowedAgentIds.join(','),
      allowed_purposes: allowedPurposes.join(','),
    });
    return api.post<{
      client_id: string;
      client_secret: string;
      name: string;
      scopes: string;
      allowed_agent_ids: string[];
      allowed_purposes: string[];
    }>('/oauth/clients', params, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    });
  },
  delete: (clientId: string) => api.delete(`/oauth/clients/${clientId}`),

  // Sprint 2 Goal D — partner endpoint family (platform_api_clients.py)
  // These complement the Console-internal endpoints with full lifecycle:
  // rotate / disable / enable. Same oauth_clients DB table is shared.
  // See backend/app/api/platform_api_clients.py.
  rotate: (clientId: string) =>
    api.post<{ client_id: string; client_secret: string; name: string; scopes: string; secret_shown_at: string }>(
      `/clients/${clientId}/rotate`,
    ),
  disable: (clientId: string) =>
    api.post(`/clients/${clientId}/disable`),
  enable: (clientId: string) =>
    api.post(`/clients/${clientId}/enable`),
  updateDelegation: (
    clientId: string,
    allowedAgentIds: string[],
    allowedPurposes: string[],
  ) => api.patch(`/clients/${clientId}/delegation`, {
    allowed_agent_ids: allowedAgentIds,
    allowed_purposes: allowedPurposes,
  }),
};

// Team
export const teamApi = {
  members: () => api.get<{ members: any[] }>('/team/members'),
  invitations: () => api.get<{ invitations: any[] }>('/team/invitations'),
  invite: (email: string, role: string) =>
    api.post('/team/invite', null, { params: { email, role } }),
  updateRole: (id: string, role: string) =>
    api.put(`/team/members/${id}`, null, { params: { role } }),
  remove: (id: string) => api.delete(`/team/members/${id}`),
};

// Platform administration. These routes are platform-admin only and are
// intentionally separate from organization owner/admin membership controls.
export const platformAdminApi = {
  users: (search = '', limit = 100, offset = 0) =>
    api.get('/admin/users', { params: { search, limit, offset } }),
  updateUserAccess: (userId: string, data: {
    role?: string;
    is_active?: boolean;
    expected_token_version: number;
    reason_code: string;
    ticket_id?: string;
  }) => api.patch(`/admin/users/${userId}`, data),
  organizations: () => api.get('/admin/organizations'),
  updateOrganization: (orgId: string, data: {
    plan?: 'free' | 'pro' | 'enterprise';
    is_active?: boolean;
    reason_code: string;
    ticket_id?: string;
  }) => api.patch(`/admin/organizations/${orgId}`, data),
};

// Usage
export const usageApi = {
  summary: (days = 30) => api.get('/usage/summary', { params: { days } }),
  history: (days = 30) => api.get('/usage/history', { params: { days } }),
};

// Facts Extraction
export interface ExtractedFact {
  group: string;
  text: string;
  value: string;
}

export interface FactExtractResponse {
  facts: ExtractedFact[];
  outputLanguage: string;
  usageInfo: { creditsConsumed: number };
}

export const factsApi = {
  extract: (text: string, outputLanguage = 'zh-CN') =>
    api.post<FactExtractResponse>('/v2/tools/extract-facts', {
      context: [{ type: 'text', text }],
      outputLanguage,
    }),
};

export interface GuidedDocumentResponse {
  document: {
    name: string;
    templateId: string;
    templateVersionId: string;
    language: string;
    interactionId?: string | null;
    stringDocument: Record<string, string>;
    structuredDocument?: Record<string, unknown> | null;
    labels: Array<{ key: string; value: string }>;
  };
  usageInfo: { creditsConsumed: number };
}

export type GuidedDocumentContext =
  | { type: 'text'; text: string }
  | { type: 'facts'; facts: Array<{ text: string; group?: string }> }
  | {
      type: 'transcript';
      transcript: {
        transcripts: Array<{
          text: string;
          channel?: number;
          participant?: number;
          speakerId?: number;
          start?: number;
          end?: number;
        }>;
        metadata?: Record<string, unknown>;
      };
    };

export const guidedDocumentsApi = {
  generateDynamic: (data: {
    outputLanguage: string;
    context: GuidedDocumentContext[];
    dynamicTemplate: {
      name: string;
      generation: {
        instructions: { prompt: string };
        sections: Array<{
          heading: string;
          instructions: {
            contentPrompt: string;
            writingStylePrompt?: string;
            miscPrompt?: string;
          };
          outputSchema: Record<string, unknown>;
        }>;
      };
    };
  }) => api.post<GuidedDocumentResponse>('/v2/tools/guided-documents', data, {
    headers: { 'X-Corti-Retention-Policy': 'none' },
  }),
};

// Customers (Embedded Assistant end-user mgmt)
export const customersApi = {
  list: (params: { search?: string; region?: string; page?: number; page_size?: number } = {}) =>
    api.get<{ customers: any[]; total: number; page: number; page_size: number }>('/customers', { params }),
  get: (customerId: string) => api.get<any>(`/customers/${encodeURIComponent(customerId)}`),
  create: (data: { display_name: string; customer_id_suffix: string; region: 'us' | 'eu' | 'cn' }) =>
    api.post<any>('/customers', data),
  delete: (customerId: string) => api.delete(`/customers/${encodeURIComponent(customerId)}`),
};

// Templates (Beta)
export const templatesApi = {
  list: (params: { search?: string; category?: string; language?: string; page?: number; page_size?: number } = {}) =>
    api.get<{ templates: any[]; total: number; page: number; page_size: number }>('/templates', { params }),
  get: (id: string) => api.get<any>(`/templates/${id}`),
  create: (data: {
    name: string; description?: string; content?: string;
    category?: string; language?: string; scope?: string;
  }) => api.post<any>('/templates', data),
  update: (id: string, data: {
    name?: string; description?: string; content?: string;
    category?: string; language?: string; scope?: string;
  }) => api.patch<any>(`/templates/${id}`, data),
  publish: (id: string) => api.post<any>(`/templates/${encodeURIComponent(id)}/publish`),
  versions: (id: string) => api.get<any[]>(`/templates/${encodeURIComponent(id)}/versions`),
  delete: (id: string) => api.delete(`/templates/${id}`),
  sections: () => api.get<any[]>('/v2/tools/sections/'),
  createSection: (data: {
    name: string; description?: string; language?: string;
    specialties?: string[]; labels?: Array<{ key: string; value: string }>;
    outputSchema?: Record<string, unknown>;
  }) => api.post<any>('/v2/tools/sections/', data),
  updateSection: (id: string, data: {
    name?: string; description?: string; language?: string;
    specialties?: string[]; labels?: Array<{ key: string; value: string }>;
    outputSchema?: Record<string, unknown>;
  }) => api.patch<any>(`/v2/tools/sections/${id}`, data),
  deleteSection: (id: string) => api.delete(`/v2/tools/sections/${id}`),
  previewDocument: (interactionId: string, data: {
    context: Array<{ type: 'string'; data: string }>;
    template: {
      sections: Array<{
        key: string;
        nameOverride?: string;
        writingStyleOverride?: string;
        additionalInstructionsOverride?: string;
        contentOverride?: string;
      }>;
      description?: string;
      additionalInstructionsOverride?: string;
    };
    name?: string;
    outputLanguage: string;
    documentationMode: 'global_sequential';
  }) => api.post<{
    id: string;
    name: string;
    sections: Array<{ key: string; name: string; text: string; sort: number }>;
    outputLanguage: string;
    usageInfo: { creditsConsumed: number };
  }>(`/v2/tools/interactions/${encodeURIComponent(interactionId)}/documents/`, data, {
    headers: { 'X-Corti-Retention-Policy': 'none' },
  }),
};

// Tickets Portal (in-app equivalent)
export const ticketsApi = {
  list: (params: { search?: string; status?: string; priority?: string; created_by_me?: boolean; page?: number; page_size?: number } = {}) =>
    api.get<{ tickets: any[]; total: number; page: number; page_size: number }>('/tickets', { params }),
  get: (id: string) => api.get<any>(`/tickets/${id}`),
  create: (data: { subject: string; description?: string; priority?: 'low' | 'medium' | 'high' }) =>
    api.post<any>('/tickets', data),
  update: (id: string, data: { subject?: string; description?: string; status?: string; priority?: string }) =>
    api.patch<any>(`/tickets/${id}`, data),
  delete: (id: string) => api.delete(`/tickets/${id}`),
};

// Agents (iCoDer Agentic Framework — backend entities)
// Agent Definitions (/rest/v1/agent_definitions)
// Phase 2.1-C: migrated from /api/agents to /rest/v1/agent_definitions
// Management endpoints include explicit publish/archive/restore lifecycle
// transitions. A2A discovery (list+card) remains on
// /api/icoder/agents via a2aApi below.
export const agentsApi = {
  list: (category = '', search = '', type = 'all') =>
    api.get<{ agents: any[]; total: number }>('/rest/v1/agent_definitions', { params: { category, search, type } }),
  get: (id: string) => api.get(`/rest/v1/agent_definitions/${id}`),
  create: (data: any) => api.post('/rest/v1/agent_definitions', data),
  update: (id: string, data: any) => api.put(`/rest/v1/agent_definitions/${id}`, data),
  delete: (id: string) => api.delete(`/rest/v1/agent_definitions/${id}`),
  categories: () => api.get<{ categories: { name: string; count: number }[] }>('/rest/v1/agent_definitions/categories'),
  templates: () => api.get<{ templates: any[] }>('/rest/v1/agent_definitions/templates'),
  version: (id: string) => api.post(`/rest/v1/agent_definitions/${id}/version`),
  publish: (id: string) => api.post(`/rest/v1/agent_definitions/${id}/publish`),
  archive: (id: string) => api.post(`/rest/v1/agent_definitions/${id}/archive`),
  restore: (id: string) => api.post(`/rest/v1/agent_definitions/${id}/restore`),
  clone: (id: string, name?: string, description?: string) =>
    api.post(`/rest/v1/agent_definitions/${id}/clone`, { name, description }),
  memoryReadiness: (id: string, purpose_of_use = 'treatment') =>
    api.get(`/v2/agentic/agents/${encodeURIComponent(id)}/memory-readiness`, {
      params: { purpose_of_use },
    }),
  // A1B-AE-R.2.c — POST /api/v1/agents/quick?from_preset=...
  // Creates an Agent definition cloned from a preset catalog entry.
  // Note: agentsApi uses /rest/v1/agent_definitions; this is
  // the iCoDer A1B-AE-R.2.c preset-clone endpoint under /api/v1/agents/quick.
  quickFromPreset: (from_preset: string, overrides: Record<string, any> = {}) =>
    api.post('/v1/agents/quick', overrides, { params: { from_preset } }),
};

// Experts (A1B-AE-R.5) — GET /api/v1/experts + GET /api/v1/presets + External-Expert Gate
// baseURL is '/api' so we use '/v1/experts' here.
export const expertsApi = {
  list: () => api.get<{ experts: any[] }>('/v1/experts'),
  readiness: () => api.get<{
    expert_count: number;
    published_expert_count: number;
    mcp_server_count: number;
    active_mcp_server_count: number;
    built_in_mcp_tool_count: number;
    external_mcp_live_verified: boolean;
    production_ready: boolean;
  }>('/v1/experts/readiness'),
  presets: () => api.get<{ presets: any[] }>('/v1/presets'),
  evaluateExternalGate: (params: {
    expert_key: string;
    egress_enabled?: boolean;
    region?: string;
    provider_opt_in?: boolean;
    tenant_opt_in?: boolean;
  }) =>
    api.get<{ permitted: boolean; reason: string; expert_key: string }>(
      '/v1/experts/external-gate/evaluate',
      { params }
    ),
};

export const sttApi = {
  readiness: () => api.get<{
    configuration_status: 'configured_not_live_verified' | 'unavailable';
    verified_languages: string[];
    at_rest_encryption_enabled: boolean;
    durable_job_state: boolean;
    restart_recovery: boolean;
    queue_backend: 'in_process';
    horizontally_scalable_queue: false;
    pending_transcript_count: number;
    live_health_verified: false;
    production_ready: false;
  }>('/v2/tools/stt/readiness'),
};

// A2A Protocol
// Backend routes (see app/icoder/agent_runtime/a2a/a2a_routes.py):
//   GET  /.well-known/agent.json              (root, no /api prefix)
//   GET  /api/icoder/agents                   (list, optional ?capability=)
//   GET  /api/icoder/agents/{id}/card         (single AgentCard)
//   GET  /api/icoder/tasks/{id}               (tenant-scoped Task state)
//   POST /api/icoder/tasks/{id}/cancel        (Task state transition)
export const a2aApi = {
  agentCard: () => axios.get('/.well-known/agent.json'),
  discoverAgents: (capability = '') =>
    api.get<{ agents: any[] }>('/icoder/agents', { params: { capability } }),
  getAgentCard: (id: string) => api.get(`/icoder/agents/${id}/card`),
  getTask: (id: string) =>
    api.get(`/icoder/tasks/${encodeURIComponent(id)}`),
  cancelTask: (id: string, reason = '') =>
    api.post(`/icoder/tasks/${encodeURIComponent(id)}/cancel`, { reason }),
};

// Settings / Config
export const configApi = {
  get: () => api.get('/health'),
};

// Coding — G001 refactor (2026-07-09): Fast Coding Runtime default
// Replaces the A2A flow as the primary MedicalCodingPage Predict target.
// Fast mode: target <15s, axios timeout 45s. Deep mode: 30-60s+, axios timeout 120s.

export type CodingMode = 'corti_like_fast' | 'medcoder_deep';

export interface CodingResultCode {
  code: string;
  system: string;
  display: string;
  type: 'primary_diagnosis' | 'secondary_diagnosis' | 'procedure' | 'external_cause' | 'aftercare' | 'complication' | 'other';
  confidence: number;
  evidence: string;
  rationale: string;
  warnings: string[];
  alternatives: Array<{ code: string; name: string; score: number; source: string }>;
}

export interface CodingPredictResult {
  codes: CodingResultCode[];
  summary: string;
  runtime_mode: CodingMode;
  latency_ms: number;
  llm_provider: string;
  trace_id: string;
  run_id: string;
  cost: { amount: number; currency: string };
  raw_schema: Record<string, unknown>;
  trace_events: Array<{ step: string; status: string; ts: number; duration_ms: number; metadata: Record<string, unknown> }>;
  error: boolean;
  error_reason: string;
  filter_applied?: CodingCodeFilter | null;
  coding_systems_applied?: Array<'icd10cn' | 'icd9cm3'>;
}

export interface CodingCodeFilter {
  include: string[];
  exclude: string[];
  expand: boolean;
}

export interface CodingPricingEstimate {
  input_chars: number;
  runtime_mode: CodingMode;
  currency: 'CNY' | string;
  estimated_input_tokens_min: number;
  estimated_input_tokens_max: number;
  estimated_output_tokens_min: number;
  estimated_output_tokens_max: number;
  estimated_model_calls_min: number;
  estimated_model_calls_max: number;
  estimated_cost_min: number;
  estimated_cost_max: number;
  input_price_per_1m: number;
  output_price_per_1m: number;
  price_source: 'server_configuration' | string;
  billing_authoritative: false;
  disclaimer: string;
}

export const codingApi = {
  estimateCost: (inputChars: number, mode: CodingMode, signal?: AbortSignal) =>
    api.get<CodingPricingEstimate>('/v1/coding/pricing', {
      params: { input_chars: inputChars, mode },
      signal,
    }),
  predict: (text: string, mode: CodingMode = 'corti_like_fast', options?: {
    coding_systems?: Array<'icd10cn' | 'icd9cm3'>;
    include_evidence?: boolean;
    include_trace?: boolean;
    filter?: CodingCodeFilter;
  }) => {
    const timeout = mode === 'medcoder_deep' ? 120000 : 45000; // Fast 45s, Deep 120s
    return api.post<CodingPredictResult>('/v1/coding/predict', {
      text,
      mode,
      coding_systems: options?.coding_systems ?? ['icd10cn'],
      include_evidence: options?.include_evidence ?? true,
      include_trace: options?.include_trace ?? true,
      filter: options?.filter,
    }, { timeout });
  },
};

// Health
export const healthApi = {
  check: () => api.get('/health'),
};

export interface RuntimeStatus {
  case_id: string;
  state: string;
  duration_s: number;
  human_confirmations: string[];
  audit_count: number;
}

export interface AuditEvent {
  event_id: string;
  timestamp: string;
  case_id: string;
  event_type: string;
  actor: string;
  payload?: Record<string, unknown>;
}

export interface AuditSummary {
  review_id: string;
  pipeline_id: string;
  source: 'memory' | 'db' | 'none';
  session?: { current_state: string; execution_path: string; escalated: boolean; failed: boolean; archived: boolean };
  event_counts: Record<string, number>;
  total_audit_events: number;
  guard_outcomes: { ALLOW: number; REVIEW: number; DENY: number };
  decision_summary: DecisionSummary;
  state_timeline: StateTimelineEntry[];
  warnings: WarningEntry[];
}

export interface DecisionSummary {
  total_decisions: number;
  approved: number;
  rejected: number;
  actions?: string[];
  decisions?: { action: string; reviewer: string; decision: string; reason: string; created_at: string }[];
}

export interface StateTimelineEntry {
  from: string;
  to: string;
  type?: string;
  actor: string;
  reason?: string;
  timestamp?: string;
  created_at?: string;
}

export interface WarningEntry {
  type: string;
  actor: string;
  state?: string;
  timestamp?: string;
  created_at?: string;
}

export interface ActiveCases {
  active_cases: { case_id: string; state: string; duration_s: number; audit_events: number }[];
  count: number;
}

export interface RuntimeStateInfo {
  state: string;
  permitted_actions: string[];
  allowed_transitions: string[];
}

export const modelCatalogApi = {
  get: () => api.get('/v1/model-catalog'),
  listClinicalPackages: () => api.get('/v1/clinical-model-packages'),
  createClinicalPackage: (manifest: Record<string, unknown>) =>
    api.post('/v1/clinical-model-packages', manifest),
  submitClinicalPackage: (packageId: string, expectedVersion: number) =>
    api.post(`/v1/clinical-model-packages/${encodeURIComponent(packageId)}/submit`, {
      expected_version: expectedVersion,
    }),
  decideClinicalPackage: (packageId: string, data: {
    expected_version: number;
    decision: 'approve' | 'reject';
    review_reference_sha256: string;
    reason_code: string;
  }) => api.post(
    `/v1/clinical-model-packages/${encodeURIComponent(packageId)}/decision`, data,
  ),
  activateClinicalPackage: (
    useCase: string,
    data: {
      package_id: string;
      deployment_mode: 'development' | 'hospital_private' | 'cloud';
      expected_version: number;
      acknowledge_clinical_governance: true;
    },
  ) => api.put(
    `/v1/clinical-model-packages/activations/${encodeURIComponent(useCase)}`, data,
  ),
  rollbackClinicalPackage: (
    useCase: string,
    data: {
      package_id: string;
      deployment_mode: 'development' | 'hospital_private' | 'cloud';
      expected_version: number;
      acknowledge_clinical_governance: true;
    },
  ) => api.post(
    `/v1/clinical-model-packages/activations/${encodeURIComponent(useCase)}/rollback`, data,
  ),
  listClinicalArtifactAttestations: (packageId: string) => api.get(
    `/v1/clinical-model-packages/${encodeURIComponent(packageId)}/artifact-attestations`,
  ),
  probeSyntheticClinicalArtifact: (
    packageId: string,
    bundleBase64: string,
    expectedPackageRecordVersion: number,
  ) => api.post(
    `/v1/clinical-model-packages/${encodeURIComponent(packageId)}/synthetic-artifact-probe`,
    {
      bundle_base64: bundleBase64,
      expected_package_record_version: expectedPackageRecordVersion,
    },
  ),
  getClinicalShadowBinding: (useCase: string) => api.get(
    `/v1/clinical-model-packages/shadow-bindings/${encodeURIComponent(useCase)}`,
  ),
  bindClinicalShadowAttestation: (
    useCase: string,
    attestationId: string,
    expectedVersion: number,
  ) => api.put(
    `/v1/clinical-model-packages/shadow-bindings/${encodeURIComponent(useCase)}`,
    {
      attestation_id: attestationId,
      expected_version: expectedVersion,
      acknowledge_shadow_only: true,
    },
  ),
  rollbackClinicalShadowBinding: (
    useCase: string,
    attestationId: string,
    expectedVersion: number,
  ) => api.post(
    `/v1/clinical-model-packages/shadow-bindings/${encodeURIComponent(useCase)}/rollback`,
    {
      attestation_id: attestationId,
      expected_version: expectedVersion,
      acknowledge_shadow_only: true,
    },
  ),
  listClinicalShadowEvaluations: (useCase: string) => api.get(
    `/v1/clinical-model-packages/shadow-bindings/${encodeURIComponent(useCase)}/evaluations`,
  ),
  evaluateSyntheticClinicalShadow: (
    useCase: string,
    data: {
      expected_binding_version: number;
      bundle_base64?: string;
      fault_mode?: 'none' | 'worker_timeout' | 'malformed_response' | 'model_hash_mismatch';
      acknowledge_synthetic_only: true;
      acknowledge_fault_injection?: boolean;
    },
  ) => api.post(
    `/v1/clinical-model-packages/shadow-bindings/${encodeURIComponent(useCase)}/synthetic-evaluation`,
    data,
  ),
  createClinicalShadowEvaluationJob: (
    useCase: string,
    data: {
      expected_binding_version: number;
      fault_mode?: 'none' | 'worker_timeout' | 'malformed_response' | 'model_hash_mismatch';
      acknowledge_synthetic_only: true;
      acknowledge_fault_injection?: boolean;
    },
    idempotencyKey: string,
  ) => api.post(
    `/v1/clinical-model-packages/shadow-bindings/${encodeURIComponent(useCase)}/evaluation-jobs`,
    data,
    { headers: { 'Idempotency-Key': idempotencyKey } },
  ),
  listClinicalShadowEvaluationJobs: (useCase: string) => api.get(
    `/v1/clinical-model-packages/shadow-bindings/${encodeURIComponent(useCase)}/evaluation-jobs`,
  ),
  getClinicalShadowEvaluationJob: (jobId: string) => api.get(
    `/v1/clinical-model-packages/shadow-evaluation-jobs/${encodeURIComponent(jobId)}`,
  ),
  executeClinicalShadowEvaluationJobSimulation: (jobId: string) => api.post(
    `/v1/clinical-model-packages/shadow-evaluation-jobs/${encodeURIComponent(jobId)}/execute`,
    {},
  ),
  cancelClinicalShadowEvaluationJob: (
    jobId: string,
    reason: 'operator_request' | 'maintenance' | 'safety_stop',
  ) => api.post(
    `/v1/clinical-model-packages/shadow-evaluation-jobs/${encodeURIComponent(jobId)}/cancel`,
    { reason },
  ),
  getClinicalShadowEvaluationJobHealth: () => api.get(
    '/v1/clinical-model-packages/shadow-evaluation-jobs/health/summary',
  ),
  maintainClinicalShadowEvaluationJobsSimulation: () => api.post(
    '/v1/clinical-model-packages/shadow-evaluation-jobs/maintenance/run',
    {},
  ),
  listClinicalShadowDeadLetters: () => api.get(
    '/v1/clinical-model-packages/shadow-evaluation-jobs/dead-letters/list',
  ),
  replayClinicalShadowDeadLetter: (deadLetterId: string, idempotencyKey: string) => api.post(
    `/v1/clinical-model-packages/shadow-evaluation-jobs/dead-letters/${encodeURIComponent(deadLetterId)}/replay`,
    {},
    { headers: { 'Idempotency-Key': idempotencyKey } },
  ),
  listClinicalShadowAlertStates: () => api.get(
    '/v1/clinical-model-packages/shadow-evaluation-jobs/alerts/states',
  ),
  healthProbe: (deploymentId: string) =>
    api.post('/v1/model-catalog/health-probe', { deployment_id: deploymentId }),
  liveCanary: (deploymentId: string, maxCostCny: number) =>
    api.post('/v1/model-catalog/live-canary', {
      deployment_id: deploymentId,
      acknowledge_external_call: true,
      purpose: 'connectivity_only_no_patient_data',
      max_cost_cny: maxCostCny,
    }),
  updateSelection: (data: {
    mode: 'inherit' | 'pinned';
    deployment_id?: string;
    expected_version: number;
  }) => api.put('/v1/model-catalog/selection', data),
};

export default api;
