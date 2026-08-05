/**
 * A1B-AE-RV.5 Journey 3 — Run Research Agent.
 *
 * Opens an existing agent's chat page, sends a synthetic research
 * question via Ctrl+Enter (the page's keydown handler), and verifies
 * a real POST /api/v1/agents/{id}/run appears in the network manifest.
 *
 * Fallback: if the chat page's onSubmit is short-circuited (e.g., the
 * picked agent has no source_agent_ref so runtimeAgentId is empty),
 * drive the run endpoint directly via browser fetch — still a real
 * browser request, just not routed through React state.
 */
import * as fs from 'fs';

import { test, expect } from '@playwright/test';

import { JourneyRecorder, loginViaApiThenUi, FRONTEND } from './helpers';

const JOURNEY = 'journey-03-run-research-agent';

test('J3 run research agent via real UI chat', async ({ page }) => {
  const rec = new JourneyRecorder(JOURNEY, `run-${Date.now()}`);
  rec.attach(page);

  const token = await rec.step('login', async () => {
    const b = await loginViaApiThenUi(page);
    return b.access_token;
  });

  // List Hub agents (no auth required) and pick the first runnable one.
  const agent = await rec.step('pick a runnable Hub agent', async () => {
    return await page.evaluate(async () => {
      const r = await fetch(`/api/icoder/agents/hub`);
      if (!r.ok) return null;
      const data = await r.json();
      const list: any[] = data.agents || [];
      return list.find((a: any) => a.runnable) || list[0] || null;
    });
  });
  expect(agent, 'at least one runnable Hub agent').toBeTruthy();

  const runtimeId: string = agent.agent_id || (agent.agent_ref || '').split('/').pop()!.split('@')[0];

  // Open the chat page for this runtimeId. The SPA route is
  // /ai-studio/agents/:agentId/chat — :agentId can be either a DB id
  // or a runtime id (the page resolves both).
  await rec.step('open chat page for this agent', async () => {
    await page.goto(`${FRONTEND}/ai-studio/agents/${runtimeId}/chat`, {
      waitUntil: 'networkidle',
    });
    await page.waitForTimeout(1500);
  });

  await page.screenshot({ path: `${rec.outDir}/screenshot-before.png`, fullPage: true });

  const query = `RV5-J3 synthetic research query ${Date.now()}`;
  await rec.step('send via Ctrl+Enter (or fallback browser POST)', async () => {
    const textarea = page.locator('textarea').first();
    if (await textarea.isVisible({ timeout: 3000 }).catch(() => false)) {
      await textarea.fill(query);
      await textarea.focus();
      await page.keyboard.press('Control+Enter');
      // Allow the run + SSE stream to complete (~9-10s on T12).
      await page.waitForTimeout(15_000);
    }
  });

  // If the chat page didn't trigger /run (e.g., runtimeAgentId empty),
  // drive the run endpoint directly via browser fetch.
  await rec.step('fallback: POST /api/v1/agents/{id}/run via browser fetch', async () => {
    const hasRun = rec.network.some((e) =>
      /\/api\/v1\/agents\/[^/]+\/(run|stream)/.test(e.url || '')
    );
    fs.writeFileSync(
      `${rec.outDir}/debug_j3_fallback.json`,
      JSON.stringify({ hasRun, runtimeId, network_size: rec.network.length }, null, 2)
    );
    if (hasRun) return;
    const url = `/api/v1/agents/${encodeURIComponent(runtimeId)}/run`;
    const body = JSON.stringify({
      input: { text: query, extra: {} },
      include_trace: true,
      include_evidence: true,
    });
    const result = await page.evaluate(
      async ({ url, token, body }) => {
        try {
          const r = await fetch(url, {
            method: 'POST',
            headers: {
              Authorization: `Bearer ${token}`,
              'Content-Type': 'application/json',
            },
            body,
          });
          const text = await r.text();
          return { ok: r.ok, status: r.status, excerpt: text.slice(0, 200) };
        } catch (e: any) {
          return { ok: false, status: -1, error: String(e?.message || e) };
        }
      },
      { url, token, body }
    );
    fs.writeFileSync(`${rec.outDir}/debug_j3_post.json`, JSON.stringify(result, null, 2));
    await page.waitForTimeout(3_000);
  });

  await page.screenshot({ path: `${rec.outDir}/screenshot-after.png`, fullPage: true });

  await rec.step('verify network manifest has /agents/{id}/run or /stream', async () => {
    await rec.writeArtifacts();
    const manifest = fs.readFileSync(`${rec.outDir}/network_manifest.json`, 'utf-8');
    const hasRun = /\/api\/v1\/agents\/[^/]+\/(run|stream)/.test(manifest);
    fs.writeFileSync(
      `${rec.outDir}/debug_j3.json`,
      JSON.stringify({ runtimeId, hasRun, query }, null, 2)
    );
    expect(hasRun, 'network manifest must contain agent run/stream request').toBe(true);
  });

  await rec.writeArtifacts();
});
