import type { HubCard } from './agentHubApi';

const HUB_LAUNCH_MATURITIES = new Set(['runnable', 'production-ready', 'production']);

export function isHubLaunchCandidateCard(card: unknown): card is HubCard {
  if (!card || typeof card !== 'object') return false;
  const candidate = card as Partial<HubCard>;
  return candidate.runnable === true
    && candidate.pack_status === 'executable'
    && candidate.launch_candidate_ready === true
    && Array.isArray(candidate.launch_candidate_blockers)
    && candidate.launch_candidate_blockers.length === 0
    && typeof candidate.maturity === 'string'
    && HUB_LAUNCH_MATURITIES.has(candidate.maturity)
    && typeof candidate.agent_id === 'string'
    && candidate.agent_id.length > 0
    && typeof candidate.a2a_endpoint === 'string'
    && candidate.a2a_endpoint.length > 0
    && typeof candidate.run_url === 'string'
    && candidate.run_url.length > 0
    && typeof candidate.clone_url === 'string'
    && candidate.clone_url.length > 0;
}

export function filterHubLaunchCandidateCards(cards: unknown): HubCard[] {
  return Array.isArray(cards) ? cards.filter(isHubLaunchCandidateCard) : [];
}
