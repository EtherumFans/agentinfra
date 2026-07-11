/**
 * Phase 5 Track B-2 — AUDIT_BLOCKER_FIX regression test
 *
 * Context: AgentDetailPage previously failed to load Hub prebuilt agents
 * (e.g. icoder/medical-coding-agent@2.0.0) because the fallback chain
 * only checked agentsApi.get (DB) → runtimeAgentApi.listAgents (community)
 * → agentsApi.templates (templates). Hub agents are none of those, so
 * the page rendered "未找到智能体".
 *
 * Fix: added a 4th fallback that calls agentHubApi.list() + filters by
 * agent_ref. This test verifies the fix by navigating to a Hub agent URL
 * and asserting the page renders the agent name instead of the error.
 *
 * Run: npx playwright test phase5_b2_hub_agent_detail
 */
import { test, expect } from '@playwright/test';

test.describe('Phase 5 B-2: Hub agent detail page', () => {
  test('loads Hub prebuilt agent without "未找到智能体" error', async ({ page }) => {
    test.setTimeout(30000);

    // medical-coding-agent@2.0.0 is a Hub prebuilt that previously triggered
    // the not-found fallback. URL-encode the agent_ref for the path segment.
    const url = '/ai-studio/agents/icoder%2Fmedical-coding-agent%402.0.0';
    await page.goto(url, { timeout: 15000 });
    await page.waitForLoadState('domcontentloaded', { timeout: 15000 });
    // Allow fallback chain (4 API calls in sequence) to settle.
    await page.waitForTimeout(2000);

    // Must NOT show the not-found error.
    await expect(page.getByText('未找到智能体')).toHaveCount(0);

    // Should show the agent name somewhere on the page.
    // The Hub card exposes name='医学编码智能体' which AgentDetailPage
    // sets into the agent name input via setAgentName.
    const nameInput = page.getByRole('textbox', { name: '例如：骨科编码审核助手' });
    await expect(nameInput).toHaveValue('医学编码智能体');
  });
});
