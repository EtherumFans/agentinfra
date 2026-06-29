// iCoDer - API Client
import axios, { AxiosError } from 'axios';
import type {
  TokenResponse, Encounter, Review, GoldCase, PaginatedResponse,
  EvaluationSummary, CodeSearchResult, RuleResult,
} from '../types';
import { useToastStore } from '../store';

const toast = (msg: string, type: 'error' | 'warning' | 'success') => {
  try { useToastStore.getState().addToast(msg, type); } catch {}
};

const api = axios.create({
  baseURL: '/api',
  timeout: 120000, // 2 min for long-running reviews
});

// Auto-attach token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
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

// Reviews
export const reviewsApi = {
  create: (encounterId: string) =>
    api.post<Review>('/reviews', { encounter_id: encounterId }),
  createAsync: (encounterId: string) =>
    api.post<{ task_id: string; status: string; review_id: string | null; encounter_id: string }>(
      '/reviews', { encounter_id: encounterId }, { params: { async: true } }
    ),
  taskStatus: (taskId: string) =>
    api.get<any>(`/reviews/tasks/${taskId}`),
  list: (page = 1, pageSize = 20, status = '') =>
    api.get<PaginatedResponse<Review>>('/reviews', { params: { page, page_size: pageSize, status } }),
  get: (id: string) => api.get<Review>(`/reviews/${id}`),
  reviewCandidate: (reviewId: string, candidateId: string, data: any) =>
    api.put<Review>(`/reviews/${reviewId}/candidates/${candidateId}/review`, data),
  complete: (reviewId: string, data: any) =>
    api.put<Review>(`/reviews/${reviewId}/complete`, data),
  getReportMd: (id: string) => api.get<string>(`/reviews/${id}/report/markdown`),
  getReportHtml: (id: string) => api.get<string>(`/reviews/${id}/report/html`),
  batch: (encounterIds: string[]) => api.post('/reviews/batch', { encounter_ids: encounterIds }),
};

// Codes
export const codesApi = {
  search: (query: string, codeSystem = 'ICD10_CN', topK = 10) =>
    api.post<{ results: CodeSearchResult[] }>('/codes/search', { query, code_system: codeSystem, top_k: topK }),
  explore: (code: string, codeSystem = 'ICD10_CN') =>
    api.post('/codes/explore', { code, code_system: codeSystem }),
  systems: () => api.get('/codes/systems'),
  validate: (code: string, codeSystem = 'ICD10_CN') =>
    api.get('/codes/validate', { params: { code, code_system: codeSystem } }),
  verify: (data: any) => api.post('/codes/verify', data),
};


// Gold Cases
export const goldCasesApi = {
  create: (data: any) => api.post<GoldCase>('/gold-cases', data),
  list: (page = 1, pageSize = 20) =>
    api.get<PaginatedResponse<GoldCase>>('/gold-cases', { params: { page, page_size: pageSize } }),
  get: (id: string) => api.get<GoldCase>(`/gold-cases/${id}`),
  delete: (id: string) => api.delete(`/gold-cases/${id}`),
};

// Evaluation
export const evaluationApi = {
  run: (goldCaseIds?: string[]) =>
    api.post<EvaluationSummary>('/evaluation/run', goldCaseIds),
};

// Billing
export const billingApi = {
  balance: () => api.get<{ balance: number; currency: string }>('/billing/balance'),
  transactions: (limit = 20) =>
    api.get<{ transactions: any[]; total: number }>('/billing/transactions', { params: { limit } }),
  addCredits: (amount: number) =>
    api.post<{ status: string; added: number; new_balance: number }>('/billing/credits', null, { params: { amount } }),
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
  list: () => api.get<{ clients: any[] }>('/oauth/clients'),
  create: (name: string, description = '', scopes = 'api:read api:write', tokenExpires = 3600) => {
    const params = new URLSearchParams({ name, description, scopes, token_expires_seconds: String(tokenExpires) });
    return api.post<{ client_id: string; client_secret: string; name: string; scopes: string }>('/oauth/clients', params, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    });
  },
  delete: (clientId: string) => api.delete(`/oauth/clients/${clientId}`),
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

// Usage
export const usageApi = {
  summary: (days = 30) => api.get('/usage/summary', { params: { days } }),
  history: (days = 30) => api.get('/usage/history', { params: { days } }),
};

// Facts Extraction
export const factsApi = {
  extract: (text: string, outputLanguage = 'zh-CN') =>
    api.post<{ facts: any[]; raw_output: string; credits_consumed: number }>('/facts/extract', { text, output_language: outputLanguage }),
};

// Text Generation
export const textGenApi = {
  generate: (text: string, style = 'general', maxTokens = 2048, temperature = 0.1, disableGuardrails = false) =>
    api.post<{ output: string; model: string }>('/text-gen/generate', {
      text, style, max_tokens: maxTokens, temperature, disable_guardrails: disableGuardrails,
    }),
  templates: () => api.get<{ templates: any[] }>('/text-gen/templates'),
};

// Customers (Embedded Assistant end-user mgmt — Corti parity)
export const customersApi = {
  list: (params: { search?: string; region?: string; page?: number; page_size?: number } = {}) =>
    api.get<{ customers: any[]; total: number; page: number; page_size: number }>('/customers', { params }),
  get: (customerId: string) => api.get<any>(`/customers/${encodeURIComponent(customerId)}`),
  create: (data: { display_name: string; customer_id_suffix: string; region: 'us' | 'eu' | 'cn' }) =>
    api.post<any>('/customers', data),
  delete: (customerId: string) => api.delete(`/customers/${encodeURIComponent(customerId)}`),
};

// Experts
export const expertsApi = {
  list: (category = '', search = '', type = 'all') =>
    api.get<{ experts: any[]; total: number }>('/experts', { params: { category, search, type } }),
  get: (id: string) => api.get(`/experts/${id}`),
  create: (data: any) => api.post('/experts', data),
  update: (id: string, data: any) => api.put(`/experts/${id}`, data),
  delete: (id: string) => api.delete(`/experts/${id}`),
  run: (id: string, input: string, conversationHistory: any[] = []) =>
    api.post<{ expert_id: string; output: string; model: string }>(`/experts/${id}/run`, { input, conversation_history: conversationHistory }),
  categories: () => api.get<{ categories: { name: string; count: number }[] }>('/experts/categories'),
  addMcpServer: (expertId: string, data: any) => api.post(`/experts/${expertId}/mcp-servers`, data),
  removeMcpServer: (expertId: string, serverId: string) => api.delete(`/experts/${expertId}/mcp-servers/${serverId}`),
};

// BYO Expert (MCP wrapping)
export const byoExpertApi = {
  discover: (mcpUrl: string) => api.post('/experts/byo/discover', null, { params: { mcp_url: mcpUrl } }),
  create: (mcpUrl: string, systemPrompt: string, name: string) =>
    api.post('/experts/byo/create-expert', null, { params: { mcp_url: mcpUrl, system_prompt: systemPrompt, name } }),
};

// Memory (Conversation Memory)
export const memoryApi = {
  save: (sessionId: string, role: string, content: string, expertId?: string, agentId?: string) =>
    api.post('/experts/memory/save', null, { params: { session_id: sessionId, role, content, expert_id: expertId, agent_id: agentId } }),
  recall: (query: string, limit = 5, agentId?: string) =>
    api.get('/experts/memory/recall', { params: { query, limit, agent_id: agentId } }),
  context: (sessionId: string) =>
    api.get('/experts/memory/context', { params: { session_id: sessionId } }),
  profile: () => api.get('/experts/memory/profile'),
};

// Agents (iCoDer Agentic Framework — backend entities)
export const agentsApi = {
  list: (category = '', search = '', type = 'all') =>
    api.get<{ agents: any[]; total: number }>('/agents', { params: { category, search, type } }),
  get: (id: string) => api.get(`/agents/${id}`),
  create: (data: any) => api.post('/agents', data),
  update: (id: string, data: any) => api.put(`/agents/${id}`, data),
  delete: (id: string) => api.delete(`/agents/${id}`),
  categories: () => api.get<{ categories: { name: string; count: number }[] }>('/agents/categories'),
  templates: () => api.get<{ templates: any[] }>('/agents/templates'),
  version: (id: string) => api.post(`/agents/${id}/version`),
  clone: (id: string, name?: string, description?: string) =>
    api.post(`/agents/${id}/clone`, { name, description }),
};

// A2A Protocol
export const a2aApi = {
  agentCard: () => api.get('/experts/a2a/.well-known/agent.json'),
  discoverAgents: (capability = '') => api.get('/experts/a2a/agents', { params: { capability } }),
  createTask: (description: string, query: string, capabilities: string) =>
    api.post('/experts/a2a/tasks', null, { params: { description, query, capabilities } }),
  listTasks: () => api.get('/experts/a2a/tasks'),
  getTask: (id: string) => api.get(`/experts/a2a/tasks/${id}`),
  cancelTask: (id: string) => api.post(`/experts/a2a/tasks/${id}/cancel`),
  retryTask: (id: string) => api.post(`/experts/a2a/tasks/${id}/retry`),
  chain: (data: any) => api.post('/experts/a2a/chain', data),
  coordinate: (data: any) => api.post('/experts/a2a/tasks', null, { params: data }),
};

// Settings / Config
export const configApi = {
  get: () => api.get('/health'),
};

// Health
export const healthApi = {
  check: () => api.get('/health'),
};

// STT (Speech-to-Text)
export const sttApi = {
  punctuate: (text: string) =>
    api.post<{ text: string }>('/experts/stt/punctuate', { text }),
};

// Runtime — deterministic safety framework state + audit
export const runtimeApi = {
  status: (caseId: string) =>
    api.get<RuntimeStatus>(`/runtime/status/${caseId}`),
  audit: (caseId: string, limit?: number) =>
    api.get<{ case_id: string; events: AuditEvent[]; total: number }>(
      `/runtime/audit/${caseId}`, { params: { limit } }
    ),
  summary: (reviewId: string) =>
    api.get<AuditSummary>(`/runtime/summary/${reviewId}`),
  trace: (pipelineId: string) =>
    api.get(`/runtime/trace/${pipelineId}`),
  review: (caseId: string, action: string, rationale: string, decision: string) =>
    api.post<{ status: string; state: string }>(`/runtime/review/${caseId}`, {
      case_id: caseId, action, rationale, decision,
    }),
  ducActions: () =>
    api.get<{ duc_actions: string[] }>('/runtime/duc/actions'),
  stale: (maxAgeHours?: number) =>
    api.get<{ stale_cases: string[]; count: number }>('/runtime/stale', {
      params: { max_age_hours: maxAgeHours },
    }),
  active: () =>
    api.get<ActiveCases>('/runtime/active'),
  states: () =>
    api.get<{ states: RuntimeStateInfo[] }>('/runtime/states'),
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

// Code Tables Management
export const codeTablesApi = {
  list: () =>
    api.get<{ tables: any[] }>('/code-tables'),
  get: (tableId: string) =>
    api.get(`/code-tables/${tableId}`),
  create: (data: { name: string; description?: string; code_system?: string; version?: string; source_type?: string; institution?: string }) =>
    api.post<{ id: string; name: string }>('/code-tables', data),
  delete: (tableId: string) =>
    api.delete(`/code-tables/${tableId}`),
  map: (code: string, codeSystem?: string) =>
    api.post<{ query_code: string; results: Record<string, { table_id: string; table_name: string; source_type: string; code: string; name: string; valid: boolean; is_default: boolean }> }>(
      '/code-tables/map', { code, code_system: codeSystem }
    ),
};

export default api;
