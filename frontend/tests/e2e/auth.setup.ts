/**
 * Global auth setup — runs once before all E2E tests.
 * Logs in via API and saves browser storage state.
 */
import { test as setup, expect } from '@playwright/test';

const AUTH_FILE = 'tests/e2e/.auth.json';

setup('authenticate', async ({ request, page }) => {
  const resp = await request.post('/api/auth/login', {
    data: { username: 'admin', password: 'admin123' },
  });
  expect(resp.status()).toBe(200);
  const data = await resp.json();
  expect(data.access_token).toBeTruthy();

  // Set tokens + Zustand auth state in browser
  await page.goto('/');
  await page.evaluate(({ accessToken, refreshToken }) => {
    localStorage.setItem('access_token', accessToken);
    localStorage.setItem('refresh_token', refreshToken);
    // Zustand persist key — tells the app we're authenticated
    localStorage.setItem('icoder-auth', JSON.stringify({
      state: { isAuthenticated: true, accessToken, refreshToken },
      version: 0,
    }));
  }, { accessToken: data.access_token, refreshToken: data.refresh_token });

  await page.context().storageState({ path: AUTH_FILE });
});
