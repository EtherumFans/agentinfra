/** Runtime API resource — agent execution, lifecycle, observability. */

import type { AxiosInstance } from 'axios';

export interface InstalledAgent {
  agent_ref: string; name: string; version: string; description: string;
  category: string; icon: string; agent_type: string; status: string;
  installed_at: string; publisher_name: string;
  expert_count: number; tool_count: number; tier: number; usage_count: number;
}

export interface RuntimeRunResult {
  run_id: string; agent_ref: string; status: string; output: string;
  primary_diagnosis: Record<string, unknown>;
  secondary_diagnoses: Record<string, unknown>[];
  procedures: Record<string, unknown>[];
  issues_found: Record<string, unknown>[];
  audit_trail: Record<string, unknown>[];
  processing_time_ms: number;
  safety?: Record<string, unknown>;
}

export class RuntimeResource {
  constructor(private http: AxiosInstance) {}

  status() { return this.http.get('/api/runtime/status'); }
  dataPolicy() { return this.http.get('/api/runtime/data-policy'); }

  listAgents(agentType = '') {
    return this.http.get<{ agents: InstalledAgent[]; total: number }>(
      '/api/runtime/agents', { params: { agent_type: agentType } }
    );
  }

  installAgent(name: string, version: string, agentType = 'community') {
    return this.http.post('/api/runtime/agents/install', { agent_name: name, agent_version: version, agent_type: agentType });
  }

  runAgent(agentRef: string, input: string) {
    return this.http.post<RuntimeRunResult>(`/api/runtime/agents/${encodeURIComponent(agentRef)}/run`, { input });
  }

  agentLifecycle(agentRef: string, action: 'enable' | 'disable' | 'uninstall' | 'rollback') {
    return this.http.post(`/api/runtime/agents/${encodeURIComponent(agentRef)}/lifecycle`, { action });
  }

  listRuns(agentRef = '', limit = 50) { return this.http.get('/api/runtime/runs', { params: { agent_ref: agentRef, limit } }); }
  getRun(runId: string) { return this.http.get(`/api/runtime/runs/${runId}`); }
  fallbackStats(hours = 24) { return this.http.get('/api/runtime/observability/fallback', { params: { hours } }); }
  shadowStats(hours = 24) { return this.http.get('/api/runtime/observability/shadow', { params: { hours } }); }
  auditLog(eventType = '', limit = 100) { return this.http.get('/api/runtime/audit-log', { params: { event_type: eventType, limit } }); }
  medicalCodingStatus() { return this.http.get('/api/runtime/medical-coding/status'); }
  testMedicalCoding(text: string) { return this.http.post('/api/runtime/medical-coding/test', { encounter_text: text }); }
  ruleEngineStatus() { return this.http.get('/api/runtime/rule-engine/status'); }
  ruleEngineRules() { return this.http.get('/api/runtime/rule-engine/rules'); }
  validateRules(ruleSet: string, output: Record<string, unknown>, context: Record<string, unknown> = {}) {
    return this.http.post('/api/runtime/rule-engine/validate', { rule_set: ruleSet, structured_output: output, context });
  }
  registryHealth() { return this.http.get('/api/runtime/registry/health'); }
  registryRepair(direction = 'registry_to_db') { return this.http.post('/api/runtime/registry/repair', { direction }); }
}
