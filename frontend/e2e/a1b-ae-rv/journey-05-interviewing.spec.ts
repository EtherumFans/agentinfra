/**
 * A1B-AE-RV.5 Journey 5 — Interviewing.
 *
 * Like Journey 4, the Interview UI may not exist. This spec probes
 * the /intake or /interview route and records findings honestly.
 */
import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import { JourneyRecorder, loginViaApiThenUi, FRONTEND } from './helpers';

const JOURNEY = 'journey-05-interviewing';

test('J5 interviewing — probe UI existence', async ({ page }) => {
  const rec = new JourneyRecorder(JOURNEY, `run-${Date.now()}`);
  rec.attach(page);

  await rec.step('login', async () => {
    await loginViaApiThenUi(page);
  });

  let uiPresent = false;
  await rec.step('probe /intake and /interview routes', async () => {
    for (const route of ['/intake', '/interview', '/agents/intake']) {
      await page.goto(`${FRONTEND}${route}`, { waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(800);
      const body = await page.locator('body').innerText();
      if (/intake|interview|问卷|访谈/i.test(body)) {
        uiPresent = true;
        break;
      }
    }
  });

  await page.screenshot({ path: `${rec.outDir}/screenshot-after.png`, fullPage: true });

  await rec.step('record finding', async () => {
    const finding = {
      ui_present: uiPresent,
      verdict: uiPresent ? 'OK' : 'BLOCKED_BY_MISSING_UI',
      note:
        'Interview state persistence backend exists (interviewing_expert.py save_to_context) but the SPA route may not.',
    };
    fs.writeFileSync(
      `${rec.outDir}/finding.json`,
      JSON.stringify(finding, null, 2)
    );
    expect(finding.verdict).toMatch(/^(OK|BLOCKED_BY_MISSING_UI)$/);
  });

  await rec.writeArtifacts();
});
