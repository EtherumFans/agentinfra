import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 60000,
  retries: 0,
  use: {
    baseURL: process.env.CI ? 'http://localhost' : 'http://localhost:3000',
    headless: true,
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'setup',
      testMatch: /auth\.setup\.ts/,
    },
    {
      name: 'e2e',
      testMatch: /.*\.spec\.ts/,
      dependencies: ['setup'],
      use: {
        storageState: 'tests/e2e/.auth.json',
      },
    },
  ],
  webServer: process.env.CI ? undefined : [
    {
      command: 'npx vite --port 3000 --host 0.0.0.0',
      port: 3000,
      reuseExistingServer: true,
      timeout: 30000,
    },
  ],
});
