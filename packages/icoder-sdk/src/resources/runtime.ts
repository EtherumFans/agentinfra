/** Runtime API resource — agent execution, lifecycle, observability. */

import type { AxiosInstance } from 'axios';
import { requestConfig, type iCoDerRequestOptions } from '../request-options.js';

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

  status(options?: iCoDerRequestOptions) {
    return this.http.get('/api/runtime/status', requestConfig(options));
  }
  dataPolicy(options?: iCoDerRequestOptions) {
    return this.http.get('/api/runtime/data-policy', requestConfig(options));
  }

  listAgents(agentType = '', options?: iCoDerRequestOptions) {
    return this.http.get<{ agents: InstalledAgent[]; total: number }>(
      '/api/runtime/agents', requestConfig(options, { agent_type: agentType }),
    );
  }

  installAgent(
    name: string,
    version: string,
    agentType = 'community',
    options?: iCoDerRequestOptions,
  ) {
    return this.http.post(
      '/api/runtime/agents/install',
      { agent_name: name, agent_version: version, agent_type: agentType },
      requestConfig(options),
    );
  }

  runAgent(agentRef: string, input: string, options?: iCoDerRequestOptions) {
    return this.http.post<RuntimeRunResult>(
      `/api/runtime/agents/${encodeURIComponent(agentRef)}/run`,
      { input },
      requestConfig(options),
    );
  }

  agentLifecycle(
    agentRef: string,
    action: 'enable' | 'disable' | 'uninstall' | 'rollback',
    options?: iCoDerRequestOptions,
  ) {
    return this.http.post(
      `/api/runtime/agents/${encodeURIComponent(agentRef)}/lifecycle`,
      { action },
      requestConfig(options),
    );
  }

  listRuns(agentRef = '', limit = 50, options?: iCoDerRequestOptions) {
    return this.http.get(
      '/api/runtime/runs', requestConfig(options, { agent_ref: agentRef, limit }),
    );
  }
  getRun(runId: string, options?: iCoDerRequestOptions) {
    return this.http.get(
      `/api/runtime/runs/${encodeURIComponent(runId)}`, requestConfig(options),
    );
  }
  fallbackStats(hours = 24, options?: iCoDerRequestOptions) {
    return this.http.get(
      '/api/runtime/observability/fallback', requestConfig(options, { hours }),
    );
  }
  shadowStats(hours = 24, options?: iCoDerRequestOptions) {
    return this.http.get(
      '/api/runtime/observability/shadow', requestConfig(options, { hours }),
    );
  }
  auditLog(eventType = '', limit = 100, options?: iCoDerRequestOptions) {
    return this.http.get(
      '/api/runtime/audit-log',
      requestConfig(options, { event_type: eventType, limit }),
    );
  }
  medicalCodingStatus(options?: iCoDerRequestOptions) {
    return this.http.get('/api/runtime/medical-coding/status', requestConfig(options));
  }
  testMedicalCoding(text: string, options?: iCoDerRequestOptions) {
    return this.http.post(
      '/api/runtime/medical-coding/test',
      { encounter_text: text },
      requestConfig(options),
    );
  }
  ruleEngineStatus(options?: iCoDerRequestOptions) {
    return this.http.get('/api/runtime/rule-engine/status', requestConfig(options));
  }
  ruleEngineRules(options?: iCoDerRequestOptions) {
    return this.http.get('/api/runtime/rule-engine/rules', requestConfig(options));
  }
  validateRules(
    ruleSet: string,
    output: Record<string, unknown>,
    context: Record<string, unknown> = {},
    options?: iCoDerRequestOptions,
  ) {
    return this.http.post(
      '/api/runtime/rule-engine/validate',
      { rule_set: ruleSet, structured_output: output, context },
      requestConfig(options),
    );
  }
  registryHealth(options?: iCoDerRequestOptions) {
    return this.http.get('/api/runtime/registry/health', requestConfig(options));
  }
  registryRepair(direction = 'registry_to_db', options?: iCoDerRequestOptions) {
    return this.http.post(
      '/api/runtime/registry/repair', { direction }, requestConfig(options),
    );
  }
}
