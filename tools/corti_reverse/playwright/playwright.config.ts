import { defineConfig, devices } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

const ARTIFACTS = path.resolve(__dirname, '..', '..', '..', 'artifacts', 'corti_reverse');
const SCREENSHOTS = path.join(ARTIFACTS, 'screenshots');
const TRACES = path.join(ARTIFACTS, 'traces');
const HARS = path.join(ARTIFACTS, 'hars');
const AUTH = path.join(ARTIFACTS, '.auth');

for (const dir of [SCREENSHOTS, TRACES, HARS, AUTH]) {
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
}

const BASE_URL = process.env.CORTI_BASE_URL || 'https://console.corti.app/';

export default defineConfig({
  testDir: '.',
  timeout: 120_000,
  expect: { timeout: 30_000 },
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: [
    ['list'],
    ['json', {
      outputFile: path.join(ARTIFACTS, 'corti_probe_report.json'),
    }],
    ['html', {
      outputFolder: path.join(ARTIFACTS, 'corti_probe_html_report'),
      open: 'never',
    }],
  ],
  use: {
    baseURL: BASE_URL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    // HAR is recorded per-test via context.routeFromHAR / recordHar in the spec.
    // Global storageState path — populated by auth.setup.ts when CORTI_STORAGE_STATE env var is set.
    storageState: process.env.CORTI_STORAGE_STATE
      ? path.resolve(process.env.CORTI_STORAGE_STATE)
      : undefined,
    viewport: { width: 1500, height: 873 },
    ignoreHTTPSErrors: true,
    // Corti is hosted in EU/US; permit slow network.
    navigationTimeout: 60_000,
    actionTimeout: 30_000,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
