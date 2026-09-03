import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

import { defineConfig } from '@playwright/test';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const ROOT = resolve(__dirname, '..');

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 30000,
  retries: 0,
  use: {
    headless: true,
    screenshot: 'only-on-failure',
  },
  // Playwright auto-manages a static server for the icoder-embedded example HTML.
  // The package's tsc build is also auto-run as a pre-step so dist/ is fresh.
  webServer: {
    command: 'npx http-server ../packages/icoder-embedded -p 8765 --silent',
    port: 8765,
    cwd: ROOT,
    reuseExistingServer: true,
    timeout: 30000,
  },
  projects: [
    {
      name: 'phase5-a4',
      testMatch: /phase5_a4_embedded\.spec\.ts/,
    },
  ],
});
