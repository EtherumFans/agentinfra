/**
 * Runtime Agent API client — /api/runtime/* standard endpoints (agent lifecycle,
 * registry, medical-coding, rule-engine).
 */

import axios from 'axios';
import type {
  RuntimeStatus, DataPolicy, RegistryHealth, FallbackStats, ShadowStats,
  InstalledAgent, RuntimeRunResult, MedicalCodingStatus, RuleEngineStatus,
} from '../types/runtime';

const api = axios.create({ baseURL: '/api/runtime', timeout: 30000 });

// Auth token interceptor
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

export const runtimeAgentApi = {
  // ── Status ──
  getStatus: () => api.get<RuntimeStatus>('/status').then(r => r.data),

  // ── Data Policy ──
  getDataPolicy: () => api.get<DataPolicy>('/data-policy').then(r => r.data),

  // ── Registry ──
  getRegistryHealth: () => api.get<RegistryHealth>('/registry/health').then(r => r.data),
  getRegistryInconsistencies: () => api.get('/registry/inconsistencies').then(r => r.data),
  repairRegistry: (direction = 'registry_to_db') =>
    api.post('/registry/repair', { direction }).then(r => r.data),

  // ── Agents ──
  listAgents: (agentType = '') =>
    api.get<{ agents: InstalledAgent[]; total: number }>('/agents', { params: { agent_type: agentType } }).then(r => r.data),
  installAgent: (name: string, version: string, agentType = 'community') =>
    api.post('/agents/install', { agent_name: name, agent_version: version, agent_type: agentType }).then(r => r.data),
  runAgent: (agentRef: string, input: string) =>
    api.post<RuntimeRunResult>(`/agents/${encodeURIComponent(agentRef)}/run`, { input }).then(r => r.data),
  agentLifecycle: (agentRef: string, action: string) =>
    api.post(`/agents/${encodeURIComponent(agentRef)}/lifecycle`, { action }).then(r => r.data),

  // ── Runs (recent runs overview; full trace at /api/m2a/runs/{id})
  listRuns: (agentRef = '', limit = 50) =>
    api.get<{ runs: RuntimeRunResult[]; total: number }>('/runs', { params: { agent_ref: agentRef, limit } }).then(r => r.data),

  // ── Observability ──
  getFallbackStats: (hours = 24) =>
    api.get<FallbackStats>('/observability/fallback', { params: { hours } }).then(r => r.data),
  getShadowStats: (hours = 24) =>
    api.get<ShadowStats>('/observability/shadow', { params: { hours } }).then(r => r.data),

  // ── Audit ──
  getAuditLog: (eventType = '', limit = 100) =>
    api.get('/audit-log', { params: { event_type: eventType, limit } }).then(r => r.data),

  // ── Medical Coding ──
  getMedicalCodingStatus: () =>
    api.get<MedicalCodingStatus>('/medical-coding/status').then(r => r.data),
  testMedicalCoding: (encounterText: string) =>
    api.post('/medical-coding/test', { encounter_text: encounterText }).then(r => r.data),

  // ── Rule Engine ──
  getRuleEngineStatus: () =>
    api.get<RuleEngineStatus>('/rule-engine/status').then(r => r.data),
  validateRules: (ruleSet: string, structuredOutput: Record<string, unknown>, context: Record<string, unknown> = {}) =>
    api.post('/rule-engine/validate', { rule_set: ruleSet, structured_output: structuredOutput, context }).then(r => r.data),
  getRules: () => api.get('/rule-engine/rules').then(r => r.data),
};
