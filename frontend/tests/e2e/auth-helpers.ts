import type { Page } from '@playwright/test';

export const CREDENTIALS = {
  admin: { username: 'admin', password: 'admin123' },
};

export async function logout(page: Page): Promise<void> {
  await page.evaluate(() => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('icoder-auth');
  });
  await page.reload();
  await page.waitForTimeout(500);
}
