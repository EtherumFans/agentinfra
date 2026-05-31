/**
 * Comprehensive smoke test — login once, then verify all pages load.
 */
import { test, expect } from '@playwright/test';

const ALL_PAGES = [
  '/',
  '/gold-cases', '/billing', '/usage', '/team',
  '/api-clients', '/evaluation', '/expert-library',
  '/ai-studio', '/ai-studio/agents',
  '/ai-studio/speech-to-text', '/ai-studio/text-generation',
  '/ai-studio/fact-extraction', '/ai-studio/medical-coding',
  '/ai-studio/embedded-assistant',
  '/settings', '/developer-quickstart',
  '/docs', '/release-notes', '/tickets', '/support',
];

test.describe('Full App Smoke Test', () => {

  test('all pages load without crashing', async ({ page }) => {
    test.setTimeout(120000);

    // Already authenticated via setup project
    // Check each page
    const results: string[] = [];
    for (const path of ALL_PAGES) {
      try {
        await page.goto(path, { timeout: 10000 });
        await page.waitForLoadState('domcontentloaded', { timeout: 10000 });
        await page.waitForTimeout(300);
        const url = page.url();
        if (url.includes('login')) {
          results.push(`REDIRECT: ${path} → login`);
        } else {
          results.push(`OK: ${path}`);
        }
      } catch (e: any) {
        results.push(`ERROR: ${path} — ${e.message?.slice(0, 80)}`);
      }
    }

    // Report
    console.log('\n=== Smoke Test Results ===');
    for (const r of results) console.log(r);

    const failures = results.filter(r => !r.startsWith('OK:'));
    expect(failures).toEqual([]);
  });
});
