// Phase 7 Gate 12 — iCoDer Partner Reference App server.
//
// Minimum viable HIS/EMR-side backend that:
//   1. Holds ICODER_API_CLIENT_SECRET in env (NEVER ships to browser)
//   2. Exchanges client_credentials for short-lived access_token at iCoDer
//   3. Serves the HIS/EMR shell that loads <icoder-embedded>
//
// Partners copy this file, swap in their auth/Patient DB, and ship.

import express from 'express';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));

// ─── env ────────────────────────────────────────────────────────────────
function requiredEnv(name) {
  const v = process.env[name];
  if (!v) {
    console.error(`[partner-ref-app] missing required env var: ${name}`);
    console.error(`[partner-ref-app] copy .env.example to .env and fill in values`);
    process.exit(1);
  }
  return v;
}

const BASE_URL = process.env.ICODER_BASE_URL || 'http://localhost:8000';
const TOKEN_URL = process.env.ICODER_TOKEN_URL || `${BASE_URL}/api/oauth/realms/icoder/token`;
const CLIENT_ID = process.env.ICODER_API_CLIENT_ID || '';
const CLIENT_SECRET = process.env.ICODER_API_CLIENT_SECRET || '';
const AGENT_REF = process.env.ICODER_AGENT_REF || 'medical-coding-agent';
const ORG_ID = process.env.ICODER_ORGANIZATION_ID || '';
const PORT = parseInt(process.env.PORT || '4400', 10);

// ─── token cache (in-process; replace with Redis in prod) ──────────────
let cachedToken = null; // { value, expiresAt }

async function getAccessToken() {
  // Reuse cached token if it has >60s of life left
  const now = Date.now();
  if (cachedToken && cachedToken.expiresAt - now > 60_000) {
    return cachedToken.value;
  }

  if (!CLIENT_ID || !CLIENT_SECRET) {
    throw new Error(
      'ICODER_API_CLIENT_ID or ICODER_API_CLIENT_SECRET not set. ' +
      'Partner must provision an API client at POST /api/clients (Phase 7 Gate 5).'
    );
  }

  // OAuth2 client_credentials grant — standard form-urlencoded POST.
  const body = new URLSearchParams({
    grant_type: 'client_credentials',
    client_id: CLIENT_ID,
    client_secret: CLIENT_SECRET,
    scope: 'agents:run runs:read',
  });

  const resp = await fetch(TOKEN_URL, {
    method: 'POST',
    headers: { 'content-type': 'application/x-www-form-urlencoded' },
    body,
  });

  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`token exchange failed (${resp.status}): ${text}`);
  }

  const json = await resp.json();
  cachedToken = {
    value: json.access_token,
    expiresAt: now + (json.expires_in ?? 3600) * 1000,
  };
  return cachedToken.value;
}

// ─── app ────────────────────────────────────────────────────────────────
const app = express();

app.use((req, res, next) => {
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('X-Frame-Options', 'DENY');
  res.setHeader('Referrer-Policy', 'strict-origin-when-cross-origin');
  next();
});

// Liveness probe
app.get('/healthz', (_req, res) => {
  res.json({ ok: true, ts: Date.now() });
});

// Partner frontend calls this to get a short-lived token WITHOUT exposing
// the secret. The secret stays in this server's process memory.
app.get('/token', async (_req, res) => {
  try {
    const token = await getAccessToken();
    res.json({ access_token: token, token_type: 'bearer', expires_in: 3600 });
  } catch (e) {
    console.error('[partner-ref-app] /token error:', e.message);
    res.status(502).json({ code: 'TOKEN_EXCHANGE_FAILED', message: e.message });
  }
});

// Config endpoint — non-secret partner config for the frontend
app.get('/config.js', (_req, res) => {
  res.setHeader('content-type', 'application/javascript; charset=utf-8');
  res.setHeader('cache-control', 'no-cache, must-revalidate');
  res.send(`// auto-generated from server env
window.icoderPartnerConfig = {
  baseUrl: ${JSON.stringify(BASE_URL)},
  agentRef: ${JSON.stringify(AGENT_REF)},
  organizationId: ${JSON.stringify(ORG_ID)},
  needsTokenFromServer: ${(!CLIENT_ID || !CLIENT_SECRET).toString()},
};`);
});

// Static shell
app.use(express.static(join(__dirname, '..', 'public')));

const server = app.listen(PORT, () => {
  console.log(`[partner-ref-app] listening on http://localhost:${PORT}`);
  console.log(`[partner-ref-app] ICODER_BASE_URL = ${BASE_URL}`);
  console.log(`[partner-ref-app] agent = ${AGENT_REF}`);
  if (!CLIENT_ID || !CLIENT_SECRET) {
    console.log(`[partner-ref-app] WARNING: ICODER_API_CLIENT_ID/SECRET not set — /token will fail`);
    console.log(`[partner-ref-app]          partner user must paste a Console JWT directly`);
  }
});

// Graceful shutdown
process.on('SIGTERM', () => server.close(() => process.exit(0)));
process.on('SIGINT', () => server.close(() => process.exit(0)));
