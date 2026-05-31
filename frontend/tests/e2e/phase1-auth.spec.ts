/**
 * Phase 1 — Auth & Navigation E2E Tests
 */
import { test, expect } from '@playwright/test';

test.describe('Authentication Gates', () => {

  test('12a — unauthenticated access to /billing redirects to /login', async ({ browser }) => {
    const ctx = await browser.newContext({ storageState: undefined });
    const page = await ctx.newPage();
    await page.goto('/billing');
    await page.waitForTimeout(1500);
    expect(page.url()).toContain('/login');
    await ctx.close();
  });

  test('12b — unauthenticated access to /team redirects to /login', async ({ browser }) => {
    const ctx = await browser.newContext({ storageState: undefined });
    const page = await ctx.newPage();
    await page.goto('/team');
    await page.waitForTimeout(1500);
    expect(page.url()).toContain('/login');
    await ctx.close();
  });

  test('12c — unauthenticated access to /settings redirects to /login', async ({ browser }) => {
    const ctx = await browser.newContext({ storageState: undefined });
    const page = await ctx.newPage();
    await page.goto('/settings');
    await page.waitForTimeout(1500);
    expect(page.url()).toContain('/login');
    await ctx.close();
  });
});

test.describe('Authenticated State', () => {

  test('logged-in user sees home page', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(1000);
    expect(page.url()).not.toContain('/login');
  });

  test('auth state survives page reload', async ({ page }) => {
    await page.goto('/');
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1000);
    expect(page.url()).not.toContain('/login');
  });
});
