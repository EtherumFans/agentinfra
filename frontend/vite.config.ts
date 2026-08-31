/// <reference types="vitest" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          return id.includes('node_modules') ? 'vendor' : undefined;
        },
      },
    },
  },
  test: {
    // Phase 2-G (2026-07-02): exclude Playwright e2e specs from vitest.
    // Both frontend/e2e/*.spec.ts and frontend/tests/e2e/*.spec.ts are
    // Playwright files (run via `npx playwright test`), not vitest unit
    // tests. Without this exclude, vitest picks them up and fails on
    // browser-launch / page-goto calls that only Playwright provides.
    exclude: [
      'e2e/**',
      'tests/e2e/**',
      '**/node_modules/**',
      '**/dist/**',
    ],
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: process.env.VITE_API_TARGET || 'http://localhost:8000',
        changeOrigin: true,
        ws: true,
        bypass(req) {
          // Don't proxy frontend-only routes that happen to start with /api
          const frontendApiRoutes = ['/api-clients'];
          if (frontendApiRoutes.some(r => req.url?.startsWith(r))) {
            return req.url;
          }
        },
      },
      '/ws': {
        target: 'ws://localhost:8001',
        changeOrigin: true,
        ws: true,
      },
    },
  },
});
