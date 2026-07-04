// iCoDer - API Client
import axios, { AxiosError } from 'axios';
import type {
  TokenResponse, Encounter, Review, PaginatedResponse,
  CodeSearchResult, RuleResult,
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

// Customers (Embedded Assistant end-user mgmt — Corti parity)
export const customersApi = {
  list: (params: { search?: string; region?: string; page?: number; page_size?: number } = {}) =>
    api.get<{ customers: any[]; total: number; page: number; page_size: number }>('/customers', { params }),
  get: (customerId: string) => api.get<any>(`/customers/${encodeURIComponent(customerId)}`),
  create: (data: { display_name: string; customer_id_suffix: string; region: 'us' | 'eu' | 'cn' }) =>
    api.post<any>('/customers', data),
  delete: (customerId: string) => api.delete(`/customers/${encodeURIComponent(customerId)}`),
};

// Templates (Beta) — Corti /templates parity
export const templatesApi = {
  list: (params: { search?: string; category?: string; language?: string; page?: number; page_size?: number } = {}) =>
    api.get<{ templates: any[]; total: number; page: number; page_size: number }>('/templates', { params }),
  get: (id: string) => api.get<any>(`/templates/${id}`),
  create: (data: {
    name: string; description?: string; content?: string;
    category?: string; language?: string; scope?: string;
  }) => api.post<any>('/templates', data),
  delete: (id: string) => api.delete(`/templates/${id}`),
};

// Tickets Portal — Corti /tickets parity (in-app equivalent)
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
// Agent Definitions (Corti-style /rest/v1/agent_definitions)
// Phase 2.1-C: migrated from /api/agents to /rest/v1/agent_definitions
// 9 management endpoints (list/get/create/update/delete/categories/
// templates/version/clone). A2A discovery (list+card) remains on
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
  clone: (id: string, name?: string, description?: string) =>
    api.post(`/rest/v1/agent_definitions/${id}/clone`, { name, description }),
};

// A2A Protocol
// Backend routes (see app/icoder/agent_runtime/a2a/a2a_routes.py):
//   GET  /.well-known/agent.json              (root, no /api prefix)
//   GET  /api/icoder/agents                   (list, optional ?capability=)
//   GET  /api/icoder/agents/{id}/card         (single AgentCard)
//   GET  /api/icoder/tasks/{id}               (stub, 501)
//   POST /api/icoder/tasks/{id}/cancel        (stub, 501)
// chain/coordinate/listTasks/createTask/retryTask have no backend endpoint.
// getTask/cancelTask also have no backend endpoint (Phase 5 A2A Task stub, not yet implemented).
export const a2aApi = {
  agentCard: () => axios.get('/.well-known/agent.json'),
  discoverAgents: (capability = '') =>
    api.get<{ agents: any[] }>('/icoder/agents', { params: { capability } }),
  getAgentCard: (id: string) => api.get(`/icoder/agents/${id}/card`),
};

// Settings / Config
export const configApi = {
  get: () => api.get('/health'),
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

export default api;
