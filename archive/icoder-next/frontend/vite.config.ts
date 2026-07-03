import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The on-prem API has two prefixes: /agents (A2A discovery) and /api (coding-review).
// Both must be proxied to the backend in dev. The vanilla <icoder-embedded> widget
// fetches ${baseURL}/api/... with baseURL="" (same-origin), so the proxy carries it.
const BACKEND = process.env.ICODER_API_URL || "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/agents": { target: BACKEND, changeOrigin: true },
      "/api": { target: BACKEND, changeOrigin: true },
      "/healthz": { target: BACKEND, changeOrigin: true },
    },
  },
  build: { outDir: "dist", emptyOutDir: true },
});
