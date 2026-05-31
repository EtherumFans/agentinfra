import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
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
