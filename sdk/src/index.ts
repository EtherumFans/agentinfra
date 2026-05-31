/* iCoDer JavaScript SDK — main client

Usage:
  import { iCoDerClient } from '@icoder/sdk';
  const client = new iCoDerClient({ apiKey: 'ics_...', baseURL: 'http://localhost:8000' });
  const review = await client.reviews.create(encounterId);
*/

import type {
  ClientConfig, TokenResponse, User, Encounter, Review, Expert,
  BillingBalance, Transaction, UsageSummary, GoldCase,
  PaginatedResponse, CodeCandidate,
} from './types';

export type * from './types';

export class iCoDerClient {
  private baseURL: string;
  private accessToken: string | null;
  private refreshToken: string | null;
  private onTokenRefresh?: ClientConfig['onTokenRefresh'];

  constructor(config: ClientConfig = {}) {
    this.baseURL = config.baseURL?.replace(/\/$/, '') || 'http://localhost:8000';
    this.accessToken = config.accessToken || null;
    this.refreshToken = config.refreshToken || null;
    this.onTokenRefresh = config.onTokenRefresh;

    // If apiKey provided, use it as bearer token
    if (config.apiKey && !this.accessToken) {
      this.accessToken = config.apiKey;
    }
  }

  // ==================== Auth ====================

  async login(username: string, password: string): Promise<TokenResponse> {
    const res = await this._post('/api/auth/login', { username, password });
    const data = res.data as TokenResponse;
    this.accessToken = data.access_token;
    this.refreshToken = data.refresh_token;
    this.onTokenRefresh?.({ access_token: data.access_token, refresh_token: data.refresh_token });
    return data;
  }

  async refreshAuth(): Promise<void> {
    if (!this.refreshToken) throw new Error('No refresh token available');
    const res = await this._post('/api/auth/refresh', { refresh_token: this.refreshToken });
    const data = res.data as TokenResponse;
    this.accessToken = data.access_token;
    this.refreshToken = data.refresh_token;
    this.onTokenRefresh?.({ access_token: data.access_token, refresh_token: data.refresh_token });
  }

  // ==================== Encounters ====================

  encounters = {
    create: async (data: Record<string, any>): Promise<Encounter> => {
      const res = await this._post('/api/encounters', data); return res.data;
    },
    createFromText: async (raw_text: string, department = 'General', patient_id = 'ANONYMOUS'): Promise<Encounter> => {
      const res = await this._post('/api/encounters/text', { raw_text, department, patient_id }); return res.data;
    },
    list: async (page = 1, pageSize = 20, status = ''): Promise<PaginatedResponse<Encounter>> => {
      const res = await this._get('/api/encounters', { params: { page, page_size: pageSize, status } }); return res.data;
    },
    get: async (id: string): Promise<Encounter> => {
      const res = await this._get(`/api/encounters/${id}`); return res.data;
    },
    delete: async (id: string): Promise<void> => { await this._delete(`/api/encounters/${id}`); },
  };

  // ==================== Reviews (Core Pipeline) ====================

  reviews = {
    create: async (encounterId: string): Promise<Review> => {
      const res = await this._post('/api/reviews', { encounter_id: encounterId }); return res.data;
    },
    list: async (page = 1, pageSize = 20, status = ''): Promise<PaginatedResponse<Review>> => {
      const res = await this._get('/api/reviews', { params: { page, page_size: pageSize, status } }); return res.data;
    },
    get: async (id: string): Promise<Review> => {
      const res = await this._get(`/api/reviews/${id}`); return res.data;
    },
    reviewCandidate: async (reviewId: string, candidateId: string, data: Record<string, any>): Promise<Review> => {
      const res = await this._put(`/api/reviews/${reviewId}/candidates/${candidateId}/review`, data); return res.data;
    },
    complete: async (reviewId: string): Promise<Review> => {
      const res = await this._put(`/api/reviews/${reviewId}/complete`, {}); return res.data;
    },
    getReportMd: async (id: string): Promise<string> => {
      const res = await this._get(`/api/reviews/${id}/report/markdown`); return res.data;
    },
    getReportHtml: async (id: string): Promise<string> => {
      const res = await this._get(`/api/reviews/${id}/report/html`); return res.data;
    },
  };

  // ==================== Experts ====================

  experts = {
    list: async (category = '', search = '', type = 'all'): Promise<{ experts: Expert[]; total: number }> => {
      const res = await this._get('/api/experts', { params: { category, search, type } }); return res.data;
    },
    get: async (id: string): Promise<Expert> => {
      const res = await this._get(`/api/experts/${id}`); return res.data;
    },
    run: async (expertId: string, input: string, history: { role: string; content: string }[] = []): Promise<{ output: string }> => {
      const res = await this._post(`/api/experts/${expertId}/run`, { input, conversation_history: history }); return res.data;
    },
    registry: async (): Promise<{ experts: Expert[]; capabilities: string[] }> => {
      const res = await this._get('/api/experts/registry'); return res.data;
    },
    searchByCapability: async (capability: string): Promise<{ experts: Expert[] }> => {
      const res = await this._get('/api/experts/registry/search', { params: { capability } }); return res.data;
    },
    create: async (data: Record<string, any>): Promise<Expert> => {
      const res = await this._post('/api/experts', data); return res.data;
    },
    delete: async (id: string): Promise<void> => { await this._delete(`/api/experts/${id}`); },
  };

  // ==================== Codes ====================

  codes = {
    search: async (query: string, codeSystem = 'ICD10_CN', topK = 10): Promise<{ results: CodeCandidate[] }> => {
      const res = await this._post('/api/codes/search', { query, code_system: codeSystem, top_k: topK }); return res.data;
    },
    systems: async (): Promise<{ systems: { id: string; name: string; count: number }[] }> => {
      const res = await this._get('/api/codes/systems'); return res.data;
    },
    validate: async (code: string, codeSystem = 'ICD10_CN'): Promise<{ valid: boolean }> => {
      const res = await this._post('/api/codes/validate', { code, code_system: codeSystem }); return res.data;
    },
  };

  // ==================== Billing ====================

  billing = {
    balance: async (): Promise<BillingBalance> => {
      const res = await this._get('/api/billing/balance'); return res.data;
    },
    transactions: async (limit = 20): Promise<{ transactions: Transaction[] }> => {
      const res = await this._get('/api/billing/transactions', { params: { limit } }); return res.data;
    },
    addCredits: async (amount: number): Promise<{ new_balance: number }> => {
      const res = await this._post('/api/billing/credits', null, { params: { amount } }); return res.data;
    },
  };

  // ==================== Usage ====================

  usage = {
    summary: async (days = 30): Promise<UsageSummary> => {
      const res = await this._get('/api/usage/summary', { params: { days } }); return res.data;
    },
    history: async (days = 30): Promise<{ history: Record<string, any>[] }> => {
      const res = await this._get('/api/usage/history', { params: { days } }); return res.data;
    },
  };

  // ==================== Team ====================

  team = {
    members: async (): Promise<{ members: Record<string, any>[] }> => {
      const res = await this._get('/api/team/members'); return res.data;
    },
    invite: async (email: string, role: string): Promise<Record<string, any>> => {
      const res = await this._post('/api/team/invite', null, { params: { email, role } }); return res.data;
    },
  };

  // ==================== Gold Cases ====================

  goldCases = {
    create: async (data: Record<string, any>): Promise<GoldCase> => {
      const res = await this._post('/api/gold-cases', data); return res.data;
    },
    list: async (page = 1, pageSize = 20): Promise<PaginatedResponse<GoldCase>> => {
      const res = await this._get('/api/gold-cases', { params: { page, page_size: pageSize } }); return res.data;
    },
  };

  // ==================== OAuth (M2M) ====================

  oauth = {
    getToken: async (clientId: string, clientSecret: string, scope = 'api:read api:write'): Promise<{ access_token: string }> => {
      const body = new URLSearchParams({ grant_type: 'client_credentials', client_id: clientId, client_secret: clientSecret, scope });
      const res = await this._fetch('/api/oauth/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: body.toString(),
      });
      this.accessToken = res.data.access_token;
      return res.data;
    },
  };

  // ==================== HTTP ====================

  private async _fetch(path: string, init: RequestInit = {}): Promise<{ data: any; status: number }> {
    const url = `${this.baseURL}${path}`;
    const headers: Record<string, string> = { 'Content-Type': 'application/json', ...(init.headers as Record<string, string> || {}) };

    if (this.accessToken) {
      headers['Authorization'] = `Bearer ${this.accessToken}`;
    }

    const resp = await fetch(url, { ...init, headers });

    if (resp.status === 401 && this.refreshToken && path !== '/api/auth/refresh') {
      await this.refreshAuth();
      headers['Authorization'] = `Bearer ${this.accessToken}`;
      const retry = await fetch(url, { ...init, headers });
      return { data: await retry.json().catch(() => null), status: retry.status };
    }

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }));
      throw new ApiError(resp.status, err.detail || 'Request failed', err);
    }

    const contentType = resp.headers.get('content-type') || '';
    const data = contentType.includes('application/json') ? await resp.json() : await resp.text();
    return { data, status: resp.status };
  }

  private _get(path: string, opts?: { params?: Record<string, any> }) {
    const qs = opts?.params ? '?' + new URLSearchParams(opts.params).toString() : '';
    return this._fetch(`${path}${qs}`);
  }

  private _post(path: string, body: any, opts?: { params?: Record<string, any> }) {
    const qs = opts?.params ? '?' + new URLSearchParams(opts.params).toString() : '';
    return this._fetch(`${path}${qs}`, { method: 'POST', body: body ? JSON.stringify(body) : undefined });
  }

  private _put(path: string, body: any) {
    return this._fetch(path, { method: 'PUT', body: JSON.stringify(body) });
  }

  private _delete(path: string) {
    return this._fetch(path, { method: 'DELETE' });
  }
}

export class ApiError extends Error {
  constructor(public status: number, message: string, public body?: any) {
    super(message);
    this.name = 'ApiError';
  }
}

export default iCoDerClient;
