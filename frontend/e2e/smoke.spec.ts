import { test, expect } from '@playwright/test';

const PAGES = [
  { path: '/', name: 'Home' },
  { path: '/developer-quickstart', name: 'Developer Quickstart' },
  { path: '/docs', name: 'Docs' },
  { path: '/release-notes', name: 'Release Notes' },
  { path: '/ai-studio', name: 'AI Studio Overview' },
  { path: '/ai-studio/agents', name: 'Agents' },
  { path: '/ai-studio/speech-to-text', name: 'Speech To Text' },
  { path: '/ai-studio/text-generation', name: 'Text Generation' },
  { path: '/ai-studio/fact-extraction', name: 'Fact Extraction' },
  { path: '/ai-studio/medical-coding', name: 'Medical Coding' },
  { path: '/ai-studio/embedded-assistant', name: 'Embedded Assistant' },
  { path: '/api-clients', name: 'API Clients' },
  { path: '/team', name: 'Team' },
  { path: '/billing', name: 'Billing' },
  { path: '/usage', name: 'Usage' },
  { path: '/settings', name: 'Settings' },
  { path: '/gold-cases', name: 'Gold Cases' },
  { path: '/evaluation', name: 'Evaluation' },
  { path: '/expert-library', name: 'Expert Library' },
  { path: '/support', name: 'Support' },
];

for (const { path, name } of PAGES) {
  test(`${name} page loads`, async ({ page }) => {
    // Set auth bypass
    await page.goto('/login');
    await page.evaluate(() => {
      localStorage.setItem('access_token', 'e2e-test-token');
      localStorage.setItem('icoder-auth', JSON.stringify({
        state: {
          user: { id: '1', username: 'e2e', full_name: 'E2E Test', role: 'admin', department: 'IT', is_active: true },
          accessToken: 'e2e-test-token',
          refreshToken: 'e2e-refresh',
          isAuthenticated: true,
        },
        version: 0,
      }));
    });
    await page.goto(path);
    await expect(page.locator('body')).toBeVisible();
  });
}
