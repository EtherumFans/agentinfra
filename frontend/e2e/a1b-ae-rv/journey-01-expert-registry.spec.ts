/**
 * A1B-AE-RV.5 Journey 1 — Expert Registry.
 *
 * Verifies the /experts page surfaces the Corti §3.2 Expert registry
 * via real browser navigation. NO Python module, NO TestClient.
 */
import { test, expect } from '@playwright/test';
import { JourneyRecorder, loginViaApiThenUi, FRONTEND } from './helpers';

const JOURNEY = 'journey-01-expert-registry';

test('J1 expert registry visible via real UI', async ({ page }) => {
  const rec = new JourneyRecorder(JOURNEY, `run-${Date.now()}`);
  rec.attach(page);

  await rec.step('login via /api/auth/login + UI reload', async () => {
    await loginViaApiThenUi(page);
  });

  await rec.step('navigate to /experts', async () => {
    await page.goto(`${FRONTEND}/ai-studio/experts`, { waitUntil: 'networkidle' });
  });

  const visibleExperts = await rec.step('extract visible expert names', async () => {
    // Wait for the SPA to render
    await page.waitForTimeout(1500);
    // Pull text content from the main area
    const body = await page.locator('main, [role="main"], body').first().innerText();
    return body;
  });
  // Sanity: at least one of the canonical expert keys must appear
  const canonical = ['pubmed', 'clinical', 'calculator', 'intake', 'drugbank'];
  const hits = canonical.filter(k => visibleExperts.toLowerCase().includes(k));
  expect(
    hits.length,
    `expected ≥1 canonical expert key on /experts; body excerpt: ${visibleExperts.slice(0, 400)}`
  ).toBeGreaterThan(0);

  await page.screenshot({
    path: `${rec.outDir}/screenshot-after.png`,
    fullPage: true,
  });
  await rec.writeArtifacts();
});
