import type {
  HubCard,
  HubTenantReadinessEvidence,
  HubTenantReadinessItem,
  HubTenantReadinessResponse,
  HubTenantRuntimeReadiness,
} from './agentHubApi';

const tenantConfigurationStatuses = new Set(['local_ready', 'configured', 'unavailable']);
const connectivityStatuses = new Set([
  'not_applicable', 'not_run', 'verified', 'expired', 'failed',
]);

export const failClosedHubCards = (cards: HubCard[]): HubCard[] => cards.map(card => ({
  ...card,
  runtime_readiness: {
    ...card.runtime_readiness,
    configuration_status: 'not_checked',
    run_action_enabled: false,
    reason: 'tenant_runtime_readiness_unavailable',
    live_health_verified: false,
    connectivity_status: undefined,
  },
}));

const isTenantReadinessItem = (value: unknown): value is HubTenantReadinessItem => {
  if (!value || typeof value !== 'object') return false;
  const item = value as Partial<HubTenantReadinessItem>;
  const readiness = item.runtime_readiness as Partial<HubTenantRuntimeReadiness> | undefined;
  const evidence = item.evidence as Partial<HubTenantReadinessEvidence> | undefined;
  if (
    typeof item.agent_id !== 'string'
    || !item.agent_id
    || typeof item.execution_target !== 'string'
    || !item.execution_target
    || !readiness
    || !evidence
  ) return false;
  if (
    !['ready', 'blocked'].includes(String(readiness.structural_status))
    || !tenantConfigurationStatuses.has(String(readiness.configuration_status))
    || typeof readiness.run_action_enabled !== 'boolean'
    || typeof readiness.reason !== 'string'
    || !Array.isArray(readiness.runtime_dependencies)
    || !readiness.runtime_dependencies.every(item => typeof item === 'string')
    || typeof readiness.llm_required !== 'boolean'
    || typeof readiness.live_health_verified !== 'boolean'
    || !connectivityStatuses.has(String(readiness.connectivity_status))
    || !['verified', 'not_verified'].includes(String(readiness.semantic_validation_status))
    || !['approved', 'not_approved'].includes(String(readiness.production_approval_status))
  ) return false;
  if (
    evidence.scope !== 'tenant_configuration_and_connectivity'
    || !['inherit', 'pinned'].includes(String(evidence.selection_mode))
    || !Number.isInteger(evidence.selection_version)
    || Number(evidence.selection_version) < 0
    || (evidence.deployment_id !== null && typeof evidence.deployment_id !== 'string')
    || (evidence.provider_id !== null && typeof evidence.provider_id !== 'string')
    || typeof evidence.configuration_probe_status !== 'string'
    || (evidence.canary_checked_at !== null && typeof evidence.canary_checked_at !== 'string')
    || (evidence.canary_expires_at !== null && typeof evidence.canary_expires_at !== 'string')
  ) return false;
  if (readiness.live_health_verified && readiness.connectivity_status !== 'verified') return false;
  if (readiness.run_action_enabled && (
    readiness.structural_status !== 'ready'
    || readiness.configuration_status === 'unavailable'
    || readiness.connectivity_status === 'failed'
  )) return false;
  if (readiness.llm_required && readiness.configuration_status === 'local_ready') return false;
  if (!readiness.llm_required && readiness.configuration_status === 'configured') return false;
  return true;
};

/**
 * Merge authenticated, tenant-bound readiness into public Hub cards.
 * Any schema mismatch, duplicate, missing Agent, or target mismatch keeps the
 * entire list fail closed; partial readiness must never enable a subset.
 */
export const mergeHubTenantReadiness = (
  cards: HubCard[],
  payload: HubTenantReadinessResponse | unknown,
): HubCard[] => {
  const failClosed = failClosedHubCards(cards);
  if (!payload || typeof payload !== 'object') return failClosed;
  const response = payload as Partial<HubTenantReadinessResponse>;
  if (
    response.schema_version !== '1.0'
    || !Array.isArray(response.agents)
    || !Number.isInteger(response.total)
    || response.total !== response.agents.length
    || typeof response.generated_at !== 'string'
  ) return failClosed;

  const readinessByAgent = new Map<string, HubTenantReadinessItem>();
  for (const value of response.agents) {
    if (!isTenantReadinessItem(value) || readinessByAgent.has(value.agent_id)) {
      return failClosed;
    }
    readinessByAgent.set(value.agent_id, value);
  }

  const merged: HubCard[] = [];
  for (const card of cards) {
    const tenant = readinessByAgent.get(card.agent_id);
    if (
      !tenant
      || tenant.execution_target !== card.execution_target
      || tenant.runtime_readiness.llm_required
        !== card.runtime_readiness.external_llm_required
    ) return failClosed;
    const readiness = tenant.runtime_readiness;
    const configurationStatus = readiness.configuration_status === 'configured'
      ? readiness.live_health_verified
        ? 'configured_live_verified'
        : 'configured_not_live_verified'
      : readiness.configuration_status;
    merged.push({
      ...card,
      runtime_readiness: {
        structural_status: readiness.structural_status,
        configuration_status: configurationStatus,
        run_action_enabled: readiness.run_action_enabled,
        reason: readiness.reason,
        runtime_dependencies: [...readiness.runtime_dependencies],
        external_llm_required: readiness.llm_required,
        live_health_verified: readiness.live_health_verified,
        connectivity_status: readiness.connectivity_status,
        semantic_validation_status: readiness.semantic_validation_status,
        production_approval_status: readiness.production_approval_status,
      },
    });
  }
  return merged;
};
