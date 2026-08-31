// @vitest-environment jsdom

/**
 * Phase 3-B1 Section F — Agent Hub frontend contract.
 *
 * Verifies that:
 *   1. agentHubApi.ts points at GET /api/icoder/agents/hub (the Corti-style
 *      Hub endpoint restored in Section B).
 *   2. HubCard type exposes the 13 visible fields the backend _build_card
 *      produces (agent_ref, name, maturity, production_ready, runnable,
 *      badge, red_lines, output_contract, a2a_endpoint, run_endpoint, ...).
 *   3. the client boundary rejects metadata-only, MVP, non-runnable, blocked,
 *      and actionless cards even if an older backend returns them.
 *   4. The AgentsPage Prebuilt tab imports agentHubApi (not the legacy
 *      runtimeAgentApi.listAgents('certified')).
 */
import fs from 'fs';
import path from 'path';

import { describe, it, expect } from 'vitest';
import {
  filterHubLaunchCandidateCards,
} from '../agentHubVisibility';
import type { HubCard, HubTenantReadinessResponse } from '../agentHubApi';
import { mergeHubTenantReadiness } from '../agentHubReadiness';

const REPO_ROOT = path.resolve(__dirname, '..', '..', '..', '..');
const FRONTEND_SRC = path.resolve(REPO_ROOT, 'frontend', 'src');
const HUB_API_PATH = path.join(FRONTEND_SRC, 'services', 'agentHubApi.ts');
const AGENTS_PAGE_PATH = path.join(FRONTEND_SRC, 'pages', 'AgentsPage.tsx');

describe('Phase 3-B1 Section F — Agent Hub frontend contract', () => {
  it('agentHubApi.ts exists and points at /icoder/agents/hub', () => {
    expect(fs.existsSync(HUB_API_PATH), 'agentHubApi.ts must exist').toBe(true);
    const content = fs.readFileSync(HUB_API_PATH, 'utf-8');
    expect(content).toContain("'/icoder/agents/hub'");
    expect(content).toContain("'/icoder/agents/hub/readiness'");
    expect(content).toMatch(/agentHubApi\s*=\s*\{/);
    // Phase 4-F2: list() now accepts an optional useCase param for the
    // Corti-style use_case dropdown filter (Phase 3-B2 Loop 4). The regex
    // accepts zero or one parameter.
    expect(content).toMatch(/list:\s*(?:async\s*)?\([^)]*\)\s*=>/);
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
      'execution_path',
      'execution_target',
      'runtime_readiness',
    ];
    for (const field of requiredFields) {
      expect(
        content,
        `HubCard interface must declare field '${field}'`,
      ).toContain(field);
    }
  });

  it('declares and renders truthful four-axis runtime readiness', () => {
    const api = fs.readFileSync(HUB_API_PATH, 'utf-8');
    const page = fs.readFileSync(AGENTS_PAGE_PATH, 'utf-8');

    expect(api).toContain('structural_status');
    expect(api).toContain('configuration_status');
    expect(api).toContain('run_action_enabled');
    expect(api).toContain('live_health_verified');
    expect(api).toContain('semantic_validation_status');
    expect(api).toContain('production_approval_status');
    expect(api).toContain('mergeHubTenantReadiness');
    expect(api).toContain('listWithTenantReadiness');
    expect(page).toContain('card.runtime_readiness?.run_action_enabled === true');
    expect(page).toContain('disabled={isCloningThis || !runActionEnabled}');
    expect(page).toContain('agentSemanticNotVerified');
  });

  it('AgentsPage Prebuilt tab imports agentHubApi (not runtimeAgentApi.listAgents for certified)', () => {
    expect(fs.existsSync(AGENTS_PAGE_PATH), 'AgentsPage.tsx must exist').toBe(true);
    const content = fs.readFileSync(AGENTS_PAGE_PATH, 'utf-8');
    expect(content).toMatch(/from ['"]\.\.\/services\/agentHubApi['"]/);
    // Phase 4-F2: list() may be called with an optional useCase arg
    // (Phase 3-B2 Loop 4 — Corti-style use_case dropdown filter).
    expect(content).toMatch(/agentHubApi\.listWithTenantReadiness\(/);
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

  it('Hub output contract exposes the strict typed field allowlist', () => {
    const content = fs.readFileSync(HUB_API_PATH, 'utf-8');
    expect(content).toContain('required_fields: string[]');
    expect(content).toContain('optional_fields: string[]');
    expect(content).toContain('field_types: Record<string');
    expect(content).toContain('field_schemas: Record<string, HubOutputFieldSchema>');
    expect(content).toContain('field_relations?: HubOutputFieldRelation[]');
    expect(content).toContain('for_each?: string');
    expect(content).toContain('evidence_bindings?: HubOutputEvidenceBinding[]');
    expect(content).toContain('cross_agent_relations?: HubOutputCrossAgentRelation[]');
    expect(content).toContain("normalization?: 'none' | 'medical_code'");
    expect(content).toContain("| 'length_equals'");
    expect(content).toContain("| 'in'");
    expect(content).toContain("| 'gte'");
    expect(content).toContain("| 'count_where_equals'");
    expect(content).toContain("| 'disjoint_fields'");
    expect(content).toContain('additionalProperties?: false | HubOutputFieldSchema');
    expect(content).toContain('enum?: unknown[]');
    expect(content).toContain('minimum?: number');
    expect(content).toContain('maxItems?: number');
    expect(content).toContain("'x-order'?: 'nondecreasing' | 'strictly_increasing'");
  });

  it('fails closed to executable non-MVP launch candidates with action URLs', () => {
    const ready = {
      agent_id: 'diagnosis-extractor',
      maturity: 'runnable',
      pack_status: 'executable',
      runnable: true,
      launch_candidate_ready: true,
      launch_candidate_blockers: [],
      a2a_endpoint: '/api/icoder/agents/diagnosis-extractor/v1/message:send',
      run_url: '/api/icoder/agents/diagnosis-extractor/v1/message:send',
      clone_url: '/api/icoder/agents/diagnosis-extractor/clone',
    } as unknown as HubCard;
    const variants = [
      ready,
      { ...ready, maturity: 'metadata-only' },
      { ...ready, maturity: 'mvp' },
      { ...ready, runnable: false },
      { ...ready, pack_status: 'metadata_only' },
      { ...ready, launch_candidate_ready: false, launch_candidate_blockers: ['blocked'] },
      { ...ready, run_url: null },
      { ...ready, clone_url: null },
    ];

    expect(filterHubLaunchCandidateCards(variants)).toEqual([ready]);
    expect(filterHubLaunchCandidateCards(null)).toEqual([]);
  });

  it('merges only complete tenant-bound readiness and preserves four-axis truth', () => {
    const card = {
      agent_id: 'diagnosis-extractor',
      execution_target: 'pure_llm',
      runtime_readiness: {
        structural_status: 'ready',
        configuration_status: 'not_checked',
        run_action_enabled: false,
        reason: 'tenant_runtime_readiness_requires_authentication',
        runtime_dependencies: ['llm_gateway'],
        external_llm_required: true,
        live_health_verified: false,
        semantic_validation_status: 'not_verified',
        production_approval_status: 'not_approved',
      },
    } as unknown as HubCard;
    const payload: HubTenantReadinessResponse = {
      schema_version: '1.0',
      generated_at: '2026-08-23T00:00:00Z',
      total: 1,
      agents: [{
        agent_id: card.agent_id,
        execution_target: card.execution_target,
        runtime_readiness: {
          structural_status: 'ready',
          configuration_status: 'configured',
          run_action_enabled: true,
          reason: 'tenant_model_configuration_present',
          runtime_dependencies: ['llm_gateway'],
          llm_required: true,
          live_health_verified: true,
          connectivity_status: 'verified',
          semantic_validation_status: 'not_verified',
          production_approval_status: 'not_approved',
        },
        evidence: {
          scope: 'tenant_configuration_and_connectivity',
          selection_mode: 'pinned',
          selection_version: 3,
          deployment_id: 'deepseek',
          provider_id: 'deepseek',
          configuration_probe_status: 'not_run',
          canary_checked_at: '2026-08-23T00:00:00Z',
          canary_expires_at: '2026-08-23T00:15:00Z',
        },
      }],
    };

    const merged = mergeHubTenantReadiness([card], payload);

    expect(merged[0].runtime_readiness).toMatchObject({
      configuration_status: 'configured_live_verified',
      run_action_enabled: true,
      live_health_verified: true,
      connectivity_status: 'verified',
      semantic_validation_status: 'not_verified',
      production_approval_status: 'not_approved',
    });
  });

  it('fails the entire Hub closed on missing, duplicate, or inconsistent readiness', () => {
    const cards = ['diagnosis-extractor', 'procedure-extractor'].map(agentId => ({
      agent_id: agentId,
      execution_target: 'pure_llm',
      runtime_readiness: {
        structural_status: 'ready',
        configuration_status: 'not_checked',
        run_action_enabled: true,
        reason: 'unsafe-old-backend',
        runtime_dependencies: ['llm_gateway'],
        external_llm_required: true,
        live_health_verified: false,
        semantic_validation_status: 'not_verified',
        production_approval_status: 'not_approved',
      },
    })) as unknown as HubCard[];
    const partial = {
      schema_version: '1.0',
      generated_at: '2026-08-23T00:00:00Z',
      total: 1,
      agents: [{
        agent_id: cards[0].agent_id,
        execution_target: 'pure_llm',
        runtime_readiness: {
          structural_status: 'ready',
          configuration_status: 'configured',
          run_action_enabled: true,
          reason: 'configured',
          runtime_dependencies: ['llm_gateway'],
          llm_required: true,
          live_health_verified: true,
          connectivity_status: 'not_run',
          semantic_validation_status: 'not_verified',
          production_approval_status: 'not_approved',
        },
        evidence: {
          scope: 'tenant_configuration_and_connectivity',
          selection_mode: 'pinned',
          selection_version: 1,
          deployment_id: 'deepseek',
          provider_id: 'deepseek',
          configuration_probe_status: 'not_run',
          canary_checked_at: null,
          canary_expires_at: null,
        },
      }],
    };

    const failedClosed = mergeHubTenantReadiness(cards, partial);

    expect(failedClosed).toHaveLength(2);
    expect(failedClosed.every(card => (
      card.runtime_readiness.configuration_status === 'not_checked'
      && card.runtime_readiness.run_action_enabled === false
      && card.runtime_readiness.live_health_verified === false
    ))).toBe(true);
  });
});
