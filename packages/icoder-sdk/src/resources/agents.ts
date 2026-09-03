// Agents resource
import type { AxiosInstance } from 'axios';
import type {
  A2ALegacyAgentCard,
  AgentHubResponse,
  AgentHubTenantReadinessResponse,
  AgentTemplate,
  Expert,
} from '../types.js';
import { A2AResource } from './a2a.js';
import { requestConfig, type iCoDerRequestOptions } from '../request-options.js';

const HUB_CONFIGURATION_STATUSES = new Set([
  'not_checked',
  'local_ready',
  'configured_not_live_verified',
  'unavailable',
]);
const TENANT_HUB_CONFIGURATION_STATUSES = new Set([
  'local_ready',
  'configured',
  'unavailable',
]);
const TENANT_HUB_CONNECTIVITY_STATUSES = new Set([
  'not_applicable',
  'not_run',
  'verified',
  'expired',
  'failed',
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export interface AgentCloneRequest {
  name?: string;
  description?: string;
  project_id?: string;
  open_after_clone?: boolean;
}

export interface AgentCloneResponse {
  project_agent_id: string;
  runtime_agent_id: string;
  source_runtime_agent_id: string;
  source_agent_ref: string;
  chat_url: string;
  customize_url: string;
  run_url: string;
  cloned: boolean;
}

function assertAgentCloneResponse(value: unknown): asserts value is AgentCloneResponse {
  if (!isRecord(value)) {
    throw new TypeError('Malformed Agent clone response.');
  }
  const stringFields: Array<keyof AgentCloneResponse> = [
    'project_agent_id',
    'runtime_agent_id',
    'source_runtime_agent_id',
    'source_agent_ref',
    'chat_url',
    'customize_url',
    'run_url',
  ];
  if (stringFields.some((field) => typeof value[field] !== 'string' || !value[field])) {
    throw new TypeError('Agent clone response is missing a required identity or URL.');
  }
  if (typeof value.cloned !== 'boolean') {
    throw new TypeError('Agent clone response has an invalid cloned flag.');
  }
  if (value.runtime_agent_id !== value.project_agent_id) {
    throw new TypeError('Agent clone response would bypass the project runtime identity.');
  }
}

function assertAgentHubResponse(value: unknown): asserts value is AgentHubResponse {
  if (!isRecord(value) || value.schema_version !== '1.3' || !Array.isArray(value.agents)) {
    throw new TypeError('Unsupported or malformed Agent Hub response; schema_version 1.3 is required.');
  }
  for (const rawCard of value.agents) {
    if (!isRecord(rawCard) || !isRecord(rawCard.runtime_readiness)) {
      throw new TypeError('Agent Hub schema 1.3 card is missing runtime_readiness.');
    }
    const readiness = rawCard.runtime_readiness;
    const valid =
      (readiness.structural_status === 'ready' || readiness.structural_status === 'blocked') &&
      HUB_CONFIGURATION_STATUSES.has(String(readiness.configuration_status)) &&
      typeof readiness.run_action_enabled === 'boolean' &&
      typeof readiness.reason === 'string' &&
      Array.isArray(readiness.runtime_dependencies) &&
      readiness.runtime_dependencies.every((item) => typeof item === 'string') &&
      typeof readiness.external_llm_required === 'boolean' &&
      typeof readiness.live_health_verified === 'boolean' &&
      (readiness.semantic_validation_status === 'verified' ||
        readiness.semantic_validation_status === 'not_verified') &&
      (readiness.production_approval_status === 'approved' ||
        readiness.production_approval_status === 'not_approved');
    if (!valid) {
      throw new TypeError('Agent Hub runtime_readiness failed schema 1.3 validation.');
    }
    if (
      readiness.run_action_enabled === true &&
      (readiness.structural_status !== 'ready' ||
        readiness.configuration_status === 'not_checked' ||
        readiness.configuration_status === 'unavailable')
    ) {
      throw new TypeError('Agent Hub runtime_readiness enables an unavailable Agent.');
    }
    if (
      (readiness.configuration_status === 'local_ready' &&
        readiness.external_llm_required !== false) ||
      (readiness.configuration_status === 'configured_not_live_verified' &&
        readiness.external_llm_required !== true)
    ) {
      throw new TypeError('Agent Hub runtime_readiness dependency classification is inconsistent.');
    }
  }
}

function assertAgentHubTenantReadinessResponse(
  value: unknown,
): asserts value is AgentHubTenantReadinessResponse {
  if (
    !isRecord(value) ||
    value.schema_version !== '1.0' ||
    !Array.isArray(value.agents) ||
    !Number.isInteger(value.total) ||
    value.total !== value.agents.length ||
    typeof value.generated_at !== 'string'
  ) {
    throw new TypeError(
      'Unsupported or malformed tenant Agent Hub readiness response; schema_version 1.0 is required.',
    );
  }
  const seen = new Set<string>();
  for (const item of value.agents) {
    if (
      !isRecord(item) ||
      typeof item.agent_id !== 'string' || !item.agent_id ||
      typeof item.execution_target !== 'string' || !item.execution_target ||
      seen.has(item.agent_id) ||
      !isRecord(item.runtime_readiness) ||
      !isRecord(item.evidence)
    ) {
      throw new TypeError('Tenant Agent Hub readiness contains an invalid or duplicate Agent item.');
    }
    seen.add(item.agent_id);
    const readiness = item.runtime_readiness;
    const evidence = item.evidence;
    const valid =
      (readiness.structural_status === 'ready' || readiness.structural_status === 'blocked') &&
      TENANT_HUB_CONFIGURATION_STATUSES.has(String(readiness.configuration_status)) &&
      typeof readiness.run_action_enabled === 'boolean' &&
      typeof readiness.reason === 'string' &&
      Array.isArray(readiness.runtime_dependencies) &&
      readiness.runtime_dependencies.every((entry) => typeof entry === 'string') &&
      typeof readiness.llm_required === 'boolean' &&
      typeof readiness.live_health_verified === 'boolean' &&
      TENANT_HUB_CONNECTIVITY_STATUSES.has(String(readiness.connectivity_status)) &&
      (readiness.semantic_validation_status === 'verified' ||
        readiness.semantic_validation_status === 'not_verified') &&
      (readiness.production_approval_status === 'approved' ||
        readiness.production_approval_status === 'not_approved') &&
      evidence.scope === 'tenant_configuration_and_connectivity' &&
      (evidence.selection_mode === 'inherit' || evidence.selection_mode === 'pinned') &&
      Number.isInteger(evidence.selection_version) && Number(evidence.selection_version) >= 0 &&
      (evidence.deployment_id === null || typeof evidence.deployment_id === 'string') &&
      (evidence.provider_id === null || typeof evidence.provider_id === 'string') &&
      typeof evidence.configuration_probe_status === 'string' &&
      (evidence.canary_checked_at === null || typeof evidence.canary_checked_at === 'string') &&
      (evidence.canary_expires_at === null || typeof evidence.canary_expires_at === 'string');
    if (!valid) {
      throw new TypeError('Tenant Agent Hub runtime readiness failed schema 1.0 validation.');
    }
    if (
      readiness.live_health_verified === true &&
      readiness.connectivity_status !== 'verified'
    ) {
      throw new TypeError('Tenant Agent Hub readiness claims live health without verified connectivity.');
    }
    if (
      readiness.run_action_enabled === true &&
      (readiness.structural_status !== 'ready' ||
        readiness.configuration_status === 'unavailable' ||
        readiness.connectivity_status === 'failed')
    ) {
      throw new TypeError('Tenant Agent Hub readiness enables an unavailable Agent.');
    }
    if (
      (readiness.configuration_status === 'local_ready' && readiness.llm_required !== false) ||
      (readiness.configuration_status === 'configured' && readiness.llm_required !== true)
    ) {
      throw new TypeError('Tenant Agent Hub readiness dependency classification is inconsistent.');
    }
  }
}

export type AgentConnectorType = 'registry' | 'mcp' | 'agent' | 'a2a' | 'schema';
export type ConnectorRedirectPolicy = 'deny' | 'same-origin';
export type BuiltinRegistryKey =
  | 'memory'
  | 'clinical-trials'
  | 'drugbank'
  | 'medical-calculator'
  | 'medical-coding'
  | 'posos'
  | 'pubmed'
  | 'interviewing'
  | 'web-search';

export interface MCPConnectorConfig {
  url: string;
  transport?: 'streamable-http';
  auth_policy?: 'none' | 'bearer' | 'oauth2';
  tool_allowlist?: string[];
  connect_timeout_seconds?: number;
  total_timeout_seconds?: number;
  max_attempts?: number;
  max_response_bytes?: number;
  concurrency_limit?: number;
  redirect_policy?: ConnectorRedirectPolicy;
  max_redirects?: number;
}

export interface A2AConnectorConfig {
  endpoint: string;
  agent_card_url?: string | null;
  agent_card_digest: string;
  versions?: ['1.0'];
  bindings: Array<'JSONRPC' | 'HTTP+JSON'>;
  auth_policy?: 'none' | 'bearer' | 'oauth2';
  connect_timeout_seconds?: number;
  total_timeout_seconds?: number;
  max_attempts?: number;
  max_response_bytes?: number;
  concurrency_limit?: number;
  redirect_policy?: ConnectorRedirectPolicy;
  max_redirects?: number;
}

export interface RegistryConnectorConfig {
  registry_key: BuiltinRegistryKey;
  version?: string;
  capabilities?: string[];
  total_timeout_seconds?: number;
  max_response_bytes?: number;
}

export interface InternalAgentConnectorConfig {
  target_agent_id: string;
  capabilities?: string[];
  max_fan_out?: number;
  total_timeout_seconds?: number;
  max_response_bytes?: number;
}

export interface SchemaConnectorConfig {
  input_schema?: Record<string, unknown> | null;
  output_schema?: Record<string, unknown> | null;
  schema_ref?: string | null;
}

export type AgentConnectorConfig =
  | MCPConnectorConfig
  | A2AConnectorConfig
  | RegistryConnectorConfig
  | InternalAgentConnectorConfig
  | SchemaConnectorConfig;
export type ConnectorDataClassification = 'non_phi' | 'deidentified' | 'phi' | 'restricted';
export type ConnectorPurposeOfUse =
  | 'treatment'
  | 'payment'
  | 'healthcare_operations'
  | 'quality_improvement'
  | 'research'
  | 'public_health'
  | 'system_operations';

export interface AgentConnectorCredentialMetadata {
  present: boolean;
  provider?: string | null;
  secret_type?: string | null;
  fingerprint?: string | null;
  status?: string | null;
  version?: number | null;
  rotated_at?: string | null;
}

export interface AgentConnector {
  id: string;
  agent_id: string;
  type: AgentConnectorType;
  name: string;
  description: string;
  enabled: boolean;
  config: AgentConnectorConfig;
  target_agent_id?: string | null;
  normalized_url?: string | null;
  schema_ref?: string | null;
  schema_digest?: string | null;
  version: number;
  credential: AgentConnectorCredentialMetadata;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface AgentConnectorCreateRequest {
  type: AgentConnectorType;
  name: string;
  description?: string;
  enabled?: boolean;
  config: AgentConnectorConfig;
}

export interface AgentConnectorUpdateRequest {
  expected_version: number;
  name?: string;
  description?: string;
  enabled?: boolean;
  config?: AgentConnectorConfig;
}

export interface ConnectorCredentialBindRequest {
  provider: 'vault' | 'kms' | 'secret-manager';
  secret_ref: string;
  secret_type: 'bearer' | 'oauth2-client' | 'api-key';
  expected_version?: number;
}

export interface ConnectorGraphNode {
  id: string;
  connector_id: string;
  operation: string;
  required?: boolean;
  idempotent?: boolean;
  include_text?: boolean;
  input_keys?: string[];
  depends_on?: string[];
  when?: {
    input_key: string;
    operator: 'exists' | 'equals' | 'not_equals' | 'in';
    value?: string | number | boolean | Array<string | number | boolean> | null;
  };
  data_classification?: ConnectorDataClassification;
  purpose_of_use?: ConnectorPurposeOfUse;
}

export interface ConnectorGraph {
  version: '1.0';
  enabled: boolean;
  execution_mode: 'sequential' | 'parallel';
  max_concurrency: number;
  nodes: ConnectorGraphNode[];
  revision: number;
}

export interface ConnectorGraphPutRequest extends Omit<ConnectorGraph, 'revision'> {
  expected_revision: number;
}

export type MemoryConsentPurpose =
  | 'treatment'
  | 'healthcare_operations'
  | 'quality_improvement';

export interface MemoryConsent {
  id: string;
  agent_id: string;
  user_id: string;
  purpose_of_use: MemoryConsentPurpose;
  legal_basis: 'user-consent';
  authority_class: 'authenticated_user_self_service';
  patient_authority_verified: false;
  phi_storage_allowed: false;
  retention_days: number;
  status: 'active' | 'revoked' | 'expired';
  expires_at: string;
  revoked_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface MemoryConsentGrantRequest {
  purpose_of_use?: MemoryConsentPurpose;
  retention_days?: number;
  expires_in_days?: number;
  acknowledgement: true;
}

export interface MemoryReadiness {
  agent_id: string;
  purpose_of_use: MemoryConsentPurpose;
  consent_status: 'missing' | 'active' | 'revoked' | 'expired';
  persisted_memory_count: number;
  retention_days?: number | null;
  expires_at?: string | null;
  encryption_enabled: boolean;
  semantic_required: boolean;
  semantic_provider: Record<string, unknown>;
  lexical_fallback_available: true;
  native_ml_in_api_process: false;
  patient_authority_verified: false;
  phi_storage_allowed: false;
  operationally_configured: boolean;
}

export class AgentsResource {
  private readonly a2a: A2AResource;

  constructor(
    private http: AxiosInstance,
    getAccessToken?: () => string | undefined,
  ) {
    this.a2a = new A2AResource(http, getAccessToken);
  }

  async list(
    category?: string,
    search?: string,
    options?: iCoDerRequestOptions,
  ): Promise<{ agents: any[] }> {
    const { data } = await this.http.get(
      '/api/rest/v1/agent_definitions',
      requestConfig(options, { category, search }),
    );
    return data;
  }

  /** Corti-style prebuilt Agent Hub. Only launch-candidate cards are runnable. */
  async hub(useCase?: string, options?: iCoDerRequestOptions): Promise<AgentHubResponse> {
    const { data } = await this.http.get(
      '/api/icoder/agents/hub',
      requestConfig(options, { use_case: useCase }),
    );
    assertAgentHubResponse(data);
    return data;
  }

  /** Authenticated, tenant-bound configuration and expiring connectivity evidence. */
  async hubReadiness(options?: iCoDerRequestOptions): Promise<AgentHubTenantReadinessResponse> {
    const { data } = await this.http.get(
      '/api/icoder/agents/hub/readiness', requestConfig(options),
    );
    assertAgentHubTenantReadinessResponse(data);
    return data;
  }

  async card(agentId: string, options?: iCoDerRequestOptions): Promise<A2ALegacyAgentCard> {
    const { data } = await this.http.get(
      `/api/icoder/agents/${encodeURIComponent(agentId)}/card`,
      requestConfig(options),
    );
    return data;
  }

  /** Clone a governed Hub Agent into the active tenant project. */
  async clone(
    agentId: string,
    request: AgentCloneRequest = {},
    options?: iCoDerRequestOptions,
  ): Promise<AgentCloneResponse> {
    const { data } = await this.http.post(
      `/api/icoder/agents/${encodeURIComponent(agentId)}/clone`,
      request,
      requestConfig(options),
    );
    assertAgentCloneResponse(data);
    return data;
  }

  async get(id: string, options?: iCoDerRequestOptions): Promise<any> {
    const { data } = await this.http.get(
      `/api/rest/v1/agent_definitions/${encodeURIComponent(id)}`,
      requestConfig(options),
    );
    return data;
  }

  async create(
    config: { name: string; description?: string; category?: string; system_prompt?: string; expert_ids?: string[] },
    options?: iCoDerRequestOptions,
  ): Promise<any> {
    const { data } = await this.http.post(
      '/api/rest/v1/agent_definitions', config, requestConfig(options),
    );
    return data;
  }

  async update(
    id: string,
    config: Record<string, unknown>,
    options?: iCoDerRequestOptions,
  ): Promise<any> {
    const { data } = await this.http.put(
      `/api/rest/v1/agent_definitions/${encodeURIComponent(id)}`,
      config,
      requestConfig(options),
    );
    return data;
  }

  async delete(id: string, options?: iCoDerRequestOptions): Promise<void> {
    await this.http.delete(
      `/api/rest/v1/agent_definitions/${encodeURIComponent(id)}`,
      requestConfig(options),
    );
  }

  /** List tenant-scoped Connector resources configured for an Agent. */
  async listConnectors(
    agentId: string,
    options?: iCoDerRequestOptions,
  ): Promise<{ connectors: AgentConnector[]; total: number }> {
    const { data } = await this.http.get(
      `/api/v2/agentic/agents/${encodeURIComponent(agentId)}/connectors`,
      requestConfig(options),
    );
    return data;
  }

  async createConnector(
    agentId: string,
    request: AgentConnectorCreateRequest,
    options?: iCoDerRequestOptions,
  ): Promise<AgentConnector> {
    const { data } = await this.http.post(
      `/api/v2/agentic/agents/${encodeURIComponent(agentId)}/connectors`,
      request,
      requestConfig(options),
    );
    return data;
  }

  async updateConnector(
    agentId: string,
    connectorId: string,
    request: AgentConnectorUpdateRequest,
    options?: iCoDerRequestOptions,
  ): Promise<AgentConnector> {
    const { data } = await this.http.patch(
      `/api/v2/agentic/agents/${encodeURIComponent(agentId)}/connectors/${encodeURIComponent(connectorId)}`,
      request,
      requestConfig(options),
    );
    return data;
  }

  async deleteConnector(
    agentId: string,
    connectorId: string,
    options?: iCoDerRequestOptions,
  ): Promise<void> {
    await this.http.delete(
      `/api/v2/agentic/agents/${encodeURIComponent(agentId)}/connectors/${encodeURIComponent(connectorId)}`,
      requestConfig(options),
    );
  }

  async bindConnectorCredential(
    agentId: string,
    connectorId: string,
    request: ConnectorCredentialBindRequest,
    options?: iCoDerRequestOptions,
  ): Promise<AgentConnectorCredentialMetadata> {
    const { data } = await this.http.put(
      `/api/v2/agentic/agents/${encodeURIComponent(agentId)}/connectors/${encodeURIComponent(connectorId)}/credential`,
      request,
      requestConfig(options),
    );
    return data;
  }

  async deleteConnectorCredential(
    agentId: string,
    connectorId: string,
    options?: iCoDerRequestOptions,
  ): Promise<void> {
    await this.http.delete(
      `/api/v2/agentic/agents/${encodeURIComponent(agentId)}/connectors/${encodeURIComponent(connectorId)}/credential`,
      requestConfig(options),
    );
  }

  async connectorGraph(agentId: string, options?: iCoDerRequestOptions): Promise<ConnectorGraph> {
    const { data } = await this.http.get(
      `/api/v2/agentic/agents/${encodeURIComponent(agentId)}/connector-graph`,
      requestConfig(options),
    );
    return data;
  }

  async putConnectorGraph(
    agentId: string,
    request: ConnectorGraphPutRequest,
    options?: iCoDerRequestOptions,
  ): Promise<ConnectorGraph> {
    const { data } = await this.http.put(
      `/api/v2/agentic/agents/${encodeURIComponent(agentId)}/connector-graph`,
      request,
      requestConfig(options),
    );
    return data;
  }

  async deleteConnectorGraph(
    agentId: string,
    expectedRevision: number,
    options?: iCoDerRequestOptions,
  ): Promise<void> {
    await this.http.delete(
      `/api/v2/agentic/agents/${encodeURIComponent(agentId)}/connector-graph`,
      requestConfig(options, { expected_revision: expectedRevision }),
    );
  }

  async grantMemoryConsent(
    agentId: string,
    request: MemoryConsentGrantRequest,
    options?: iCoDerRequestOptions,
  ): Promise<MemoryConsent> {
    const { data } = await this.http.post(
      `/api/v2/agentic/agents/${encodeURIComponent(agentId)}/memory-consent`,
      request,
      requestConfig(options),
    );
    return data;
  }

  async memoryConsent(
    agentId: string,
    purposeOfUse: MemoryConsentPurpose = 'treatment',
    options?: iCoDerRequestOptions,
  ): Promise<MemoryConsent> {
    const { data } = await this.http.get(
      `/api/v2/agentic/agents/${encodeURIComponent(agentId)}/memory-consent`,
      requestConfig(options, { purpose_of_use: purposeOfUse }),
    );
    return data;
  }

  async memoryReadiness(
    agentId: string,
    purposeOfUse: MemoryConsentPurpose = 'treatment',
    options?: iCoDerRequestOptions,
  ): Promise<MemoryReadiness> {
    const { data } = await this.http.get(
      `/api/v2/agentic/agents/${encodeURIComponent(agentId)}/memory-readiness`,
      requestConfig(options, { purpose_of_use: purposeOfUse }),
    );
    return data;
  }

  async revokeMemoryConsent(
    agentId: string,
    purposeOfUse: MemoryConsentPurpose = 'treatment',
    options?: iCoDerRequestOptions,
  ): Promise<void> {
    await this.http.delete(
      `/api/v2/agentic/agents/${encodeURIComponent(agentId)}/memory-consent`,
      requestConfig(options, { purpose_of_use: purposeOfUse }),
    );
  }

  async run(
    id: string,
    input: string,
    stream = false,
    options?: iCoDerRequestOptions,
  ): Promise<any> {
    if (stream) return this.stream(id, input, undefined, options);
    return this.a2a.messageSend(id, input, {}, options);
  }

  /** Stream agent response via SSE. Returns a ReadableStream of string chunks. */
  async stream(
    id: string,
    input: string,
    signal?: AbortSignal,
    options?: iCoDerRequestOptions,
  ): Promise<ReadableStream<Uint8Array>> {
    return this.a2a.messageStream(id, input, { signal }, options);
  }

  async templates(options?: iCoDerRequestOptions): Promise<{ templates: AgentTemplate[] }> {
    const { data } = await this.http.get(
      '/api/rest/v1/agent_definitions/templates', requestConfig(options),
    );
    return data;
  }
}

export class ExpertsResource {
  constructor(private http: AxiosInstance) {}

  async list(
    category?: string,
    search?: string,
    options?: iCoDerRequestOptions,
  ): Promise<{ experts: Expert[]; total: number }> {
    const { data } = await this.http.get(
      '/api/v1/experts',
      requestConfig(options, { category, search }),
    );
    return data;
  }

  async get(id: string, options?: iCoDerRequestOptions): Promise<Expert> {
    const { data } = await this.http.get<Expert>(
      `/api/v1/experts/${encodeURIComponent(id)}`,
      requestConfig(options),
    );
    return data;
  }

  async mcpServers(
    id: string,
    authorizationType?: string,
    options?: iCoDerRequestOptions,
  ): Promise<Array<Record<string, unknown>>> {
    const { data } = await this.http.get<Array<Record<string, unknown>>>(
      `/api/v1/experts/${encodeURIComponent(id)}/mcp_servers`,
      requestConfig(options, { authorization_type: authorizationType }),
    );
    return data;
  }

  async reconcileRegistry(options?: iCoDerRequestOptions): Promise<Record<string, unknown>> {
    const { data } = await this.http.get<Record<string, unknown>>(
      '/api/v1/experts/registry/reconcile',
      requestConfig(options),
    );
    return data;
  }

  async readiness(options?: iCoDerRequestOptions): Promise<ExpertCapabilityReadiness> {
    const { data } = await this.http.get<ExpertCapabilityReadiness>(
      '/api/v1/experts/readiness',
      requestConfig(options),
    );
    return data;
  }
}

export interface ExpertCapabilityReadiness {
  expert_count: number;
  published_expert_count: number;
  mcp_server_count: number;
  active_mcp_server_count: number;
  mcp_authorization_type_counts: Record<string, number>;
  built_in_mcp_tool_count: number;
  tenant_scope_enforced: true;
  credentials_exposed: false;
  external_mcp_live_verified: false;
  aggregate_only: true;
  production_ready: boolean;
}
