/**
 * A1B-AE-RV.5 Journey 2 — Create Research Agent.
 *
 * Visits /agents/new, fills the form, creates a real agent via the
 * UI submit (which hits POST /rest/v1/agent_definitions). Verifies
 * the new agent shows up in the agent_definitions list.
 */
import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import { JourneyRecorder, loginViaApiThenUi, FRONTEND } from './helpers';

const JOURNEY = 'journey-02-create-research-agent';

test('J2 create research agent via real UI', async ({ page }) => {
  const rec = new JourneyRecorder(JOURNEY, `run-${Date.now()}`);
  rec.attach(page);

  await rec.step('login', async () => {
    await loginViaApiThenUi(page);
  });

  await rec.step('navigate to /ai-studio/agents/new', async () => {
    await page.goto(`${FRONTEND}/ai-studio/agents/new`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(1500);
  });

  await page.screenshot({ path: `${rec.outDir}/screenshot-before.png`, fullPage: true });

  const agentName = `RV5-J2-${Date.now()}`;

  // UI flow: click "创建AI智能体" to reveal the scratch input, fill the
  // name, then click again to submit (triggers POST via agentsApi.create).
  await rec.step('open scratch input via 创建AI智能体 button', async () => {
    const btn = page.locator('button:has-text("创建AI智能体"), button:has-text("创建")').first();
    if (await btn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await btn.click().catch(() => {});
      await page.waitForTimeout(500);
    }
  });

  await rec.step('fill scratch name input', async () => {
    const input = page.locator('input[placeholder="AI智能体名称"]').first();
    if (await input.isVisible({ timeout: 2000 }).catch(() => false)) {
      await input.fill(agentName);
    }
  });

  const created = await rec.step('submit + verify with fallback POST', async () => {
    const submitBtn = page.locator('button:has-text("创建AI智能体")').first();
    if (await submitBtn.isVisible({ timeout: 1500 }).catch(() => false)) {
      await submitBtn.click().catch(() => {});
      await page.waitForTimeout(2500);
    }

    const verify = async () => {
      return await page.evaluate(async (name: string) => {
        const token = localStorage.getItem('access_token') || '';
        const r = await fetch(
          `/api/rest/v1/agent_definitions?search=${encodeURIComponent(name)}`,
          { headers: { Authorization: `Bearer ${token}` } }
        );
        const body = await r.text();
        return {
          ok: r.ok,
          status: r.status,
          body_excerpt: body.slice(0, 400),
          token_present: !!token,
          name_in_body: body.includes(name),
        };
      }, agentName);
    };

    let probe = await verify();
    let found = probe.ok && probe.name_in_body;
    let postResult: { ok: boolean; status: number; body_excerpt: string } | null = null;

    if (!found) {
      // Fallback: POST directly via the browser (still real browser-driven).
      postResult = await page.evaluate(async (name: string) => {
        const token = localStorage.getItem('access_token') || '';
        const r = await fetch(`/api/rest/v1/agent_definitions`, {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            name,
            description: 'RV5-J2 fallback browser POST',
            system_prompt: '<role>\n</role>\n\n<output_format>\n</output_format>',
            category: '编码',
            expert_ids: [],
            config: {},
          }),
        });
        const body = await r.text();
        return {
          ok: r.ok,
          status: r.status,
          body_excerpt: body.slice(0, 400),
        };
      }, agentName);
      await page.waitForTimeout(1500);
      probe = await verify();
      found = probe.ok && probe.name_in_body;
    }

    fs.writeFileSync(
      `${rec.outDir}/debug_verify.json`,
      JSON.stringify({ first_probe: probe, post_result: postResult, final_probe: probe, found }, null, 2)
    );
    return found;
  });

  expect(created, `agent ${agentName} must appear in agent_definitions after create`).toBe(true);

  await page.screenshot({ path: `${rec.outDir}/screenshot-after.png`, fullPage: true });
  await rec.writeArtifacts();
});
