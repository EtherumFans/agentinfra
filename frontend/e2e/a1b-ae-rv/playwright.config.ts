import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: '.',
  timeout: 180_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [
    ['list'],
    ['junit', {
      outputFile:
        'reports/phase-a1b/agent-expert-reverification/evidence/junit/rv5_playwright_junit.xml',
    }],
  ],
  use: {
    baseURL: 'http://127.0.0.1:3000',
    headless: false,
    screenshot: 'on',
    video: 'on',
    trace: 'on',
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
    launchOptions: {
      headless: false,
    },
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
      },
    },
  ],
});
