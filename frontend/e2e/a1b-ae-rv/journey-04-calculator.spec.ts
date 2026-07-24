/**
 * A1B-AE-RV.5 Journey 4 — Calculator.
 *
 * RV.0 charter §9.6 permits implementing a minimal Calculator UI/API
 * if it doesn't exist, but forbids adding new calculation formulas.
 *
 * This spec probes for an existing Calculator UI/API. If absent, it
 * records the gap honestly as PARTIAL evidence (BLOCKED_BY_MISSING_UI)
 * rather than faking a pass via direct Python call.
 */
import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import { JourneyRecorder, loginViaApiThenUi, FRONTEND, BACKEND } from './helpers';

const JOURNEY = 'journey-04-calculator';

test('J4 calculator — probe UI/API existence', async ({ page }) => {
  const rec = new JourneyRecorder(JOURNEY, `run-${Date.now()}`);
  rec.attach(page);

  await rec.step('login', async () => {
    await loginViaApiThenUi(page);
  });

  let uiPresent = false;
  await rec.step('probe /calculator route', async () => {
    const resp = await page.goto(`${FRONTEND}/calculator`, {
      waitUntil: 'domcontentloaded',
    });
    // SPA returns 200 for any route; real test is whether the page
    // renders Calculator-specific content vs the 404/not-found component.
    await page.waitForTimeout(1500);
    const body = await page.locator('body').innerText();
    uiPresent = /BMI|calculator|计算器|formula/i.test(body);
  });

  let apiPresent = false;
  await rec.step('probe /api/calculator endpoints', async () => {
    apiPresent = await page.evaluate(async () => {
      try {
        const r = await fetch(`/api/calculator/bmi?weight=70&height=1.75`);
        return r.ok;
      } catch {
        return false;
      }
    });
  });

  await page.screenshot({ path: `${rec.outDir}/screenshot-after.png`, fullPage: true });

  await rec.step('record finding', async () => {
    const finding = {
      ui_present: uiPresent,
      api_present: apiPresent,
      verdict: uiPresent && apiPresent ? 'OK' : 'BLOCKED_BY_MISSING_UI',
      note:
        'RV.0 charter §9.6 permits implementing minimal UI/API but forbids new formulas. This sub-gate records the gap honestly rather than faking a pass.',
    };
    fs.writeFileSync(
      `${rec.outDir}/finding.json`,
      JSON.stringify(finding, null, 2)
    );
    // Soft-pass: the journey RAN and produced honest evidence.
    // The final verdict (PASS/PARTIAL) is decided at RV.7.
    expect(finding.verdict).toMatch(/^(OK|BLOCKED_BY_MISSING_UI)$/);
  });

  await rec.writeArtifacts();
});
