/**
 * Phase 3-B1 Section F — Agent Hub frontend contract.
 *
 * Verifies that:
 *   1. agentHubApi.ts points at GET /api/icoder/agents/hub (the Corti-style
 *      Hub endpoint restored in Section B).
 *   2. HubCard type exposes the 13 visible fields the backend _build_card
 *      produces (agent_ref, name, maturity, production_ready, runnable,
 *      badge, red_lines, output_contract, a2a_endpoint, run_endpoint, ...).
 *   3. metadata-only packs (runnable=false) have NO run_endpoint — so the
 *      Prebuilt tab can safely hide the Run button for Coming Soon packs.
 *   4. The AgentsPage Prebuilt tab imports agentHubApi (not the legacy
 *      runtimeAgentApi.listAgents('certified')).
 */
import { describe, it, expect } from 'vitest';
import fs from 'fs';
import path from 'path';

const REPO_ROOT = path.resolve(__dirname, '..', '..', '..', '..');
const FRONTEND_SRC = path.resolve(REPO_ROOT, 'frontend', 'src');
const HUB_API_PATH = path.join(FRONTEND_SRC, 'services', 'agentHubApi.ts');
const AGENTS_PAGE_PATH = path.join(FRONTEND_SRC, 'pages', 'AgentsPage.tsx');

describe('Phase 3-B1 Section F — Agent Hub frontend contract', () => {
  it('agentHubApi.ts exists and points at /icoder/agents/hub', () => {
    expect(fs.existsSync(HUB_API_PATH), 'agentHubApi.ts must exist').toBe(true);
    const content = fs.readFileSync(HUB_API_PATH, 'utf-8');
    expect(content).toContain("'/icoder/agents/hub'");
    expect(content).toMatch(/agentHubApi\s*=\s*\{/);
    expect(content).toMatch(/list:\s*\(\)\s*=>/);
  });

  it('HubCard interface declares the 13 visible card fields', () => {
    const content = fs.readFileSync(HUB_API_PATH, 'utf-8');
    // Required fields per backend _build_card (icoder_agents_hub.py:116)
    const requiredFields = [
      'agent_ref',
      'name',
      'maturity',
      'production_ready',
      'runnable',
      'badge',
      'red_lines',
      'output_contract',
      'a2a_endpoint',
      'run_endpoint',
      'human_review',
      'workflow',
      'non_goals',
    ];
    for (const field of requiredFields) {
      expect(
        content,
        `HubCard interface must declare field '${field}'`,
      ).toContain(field);
    }
  });

  it('AgentsPage Prebuilt tab imports agentHubApi (not runtimeAgentApi.listAgents for certified)', () => {
    expect(fs.existsSync(AGENTS_PAGE_PATH), 'AgentsPage.tsx must exist').toBe(true);
    const content = fs.readFileSync(AGENTS_PAGE_PATH, 'utf-8');
    expect(content).toMatch(/from ['"]\.\.\/services\/agentHubApi['"]/);
    expect(content).toMatch(/agentHubApi\.list\(\)/);
    // The Prebuilt tab must NOT call runtimeAgentApi.listAgents('certified')
    // for the certified list — that returns installed runtime registry agents,
    // not Corti-style Hub cards.
    expect(content).not.toMatch(/runtimeAgentApi\.listAgents\(['"]certified['"]\)/);
  });

  it('HubCard red_lines interface declares the 4 Corti rules', () => {
    const content = fs.readFileSync(HUB_API_PATH, 'utf-8');
    const redLineFields = [
      'no_upcoding',
      'no_inference',
      'evidence_required',
      'production_writeback_blocked',
    ];
    for (const field of redLineFields) {
      expect(
        content,
        `HubRedLines interface must declare '${field}'`,
      ).toContain(field);
    }
  });
});
