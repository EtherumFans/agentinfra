#!/usr/bin/env node
// iCoDer External Agent Consumer — Sprint 2 Goal F
//
// Proves the Developer Golden Path is real by calling iCoDer as an EXTERNAL
// consumer would:
//   - Reads config from env vars (no hardcoded values)
//   - Uses ONLY public REST API + optional @icoder/sdk
//   - NEVER imports internal backend modules
//   - NEVER touches the database
//
// Flow:
//   1. Exchange client_credentials for an access token (POST /api/oauth/token)
//   2. Call POST /api/v1/agents/{id}/run with a Generic Agent
//   3. Print run_id, trace_id, cost, and agent output
//
// Usage:
//   cp .env.example .env  &&  edit .env
//   node run-agent.mjs                # auto: SDK if installed, else REST
//   node run-agent.mjs --mode sdk     # force SDK path
//   node run-agent.mjs --mode rest    # force pure REST path

import { setTimeout as sleep } from 'node:timers/promises';

// ─── Config from env ───────────────────────────────────────────────────────
const BASE_URL = (process.env.ICODER_BASE_URL || 'http://localhost:8000').replace(/\/+$/, '');
const CLIENT_ID = process.env.ICODER_API_CLIENT_ID;
const CLIENT_SECRET = process.env.ICODER_API_CLIENT_SECRET;
const AGENT_ID = process.env.ICODER_AGENT_ID || 'translator-blank';
const INPUT_TEXT = process.env.ICODER_INPUT_TEXT || 'Hello world from Sprint 2 Goal F.';
const modeIdx = process.argv.indexOf('--mode');
const MODE = modeIdx !== -1 && process.argv[modeIdx + 1]
  ? process.argv[modeIdx + 1]
  : 'auto';

if (!CLIENT_ID || !CLIENT_SECRET) {
  console.error('✗ Missing ICODER_API_CLIENT_ID or ICODER_API_CLIENT_SECRET env vars.');
  console.error('  Copy .env.example to .env and fill in the values from Console > API Clients.');
  process.exit(2);
}

// ─── Step 1: client_credentials token exchange (pure REST) ────────────────
async function fetchAccessToken() {
  // OAuth 2.0 client_credentials grant per RFC 6749 §4.4.
  // iCoDer canonical endpoint: POST /api/oauth/token (realm hint-only).
  // Scope handling: omit the `scope` param unless the caller set
  // ICODER_OAUTH_SCOPE explicitly. The server will then grant the client's
  // full capability set (whatever was configured at create time), which
  // avoids invalid_scope rejections when the consumer doesn't know which
  // specific scopes the client was issued.
  const url = `${BASE_URL}/api/oauth/token`;
  const body = new URLSearchParams({
    grant_type: 'client_credentials',
    client_id: CLIENT_ID,
    client_secret: CLIENT_SECRET,
  });
  const explicitScope = process.env.ICODER_OAUTH_SCOPE;
  if (explicitScope) {
    body.set('scope', explicitScope);
  }

  console.log(`→ POST ${url}`);
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  });

  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`token exchange failed: HTTP ${res.status} — ${text}`);
  }

  const json = await res.json();
  const token = json.access_token;
  if (!token) {
    throw new Error(`token exchange returned no access_token: ${JSON.stringify(json)}`);
  }
  console.log(`✓ access token received (expires_in=${json.expires_in ?? 'n/a'}s, token_type=${json.token_type ?? 'Bearer'})`);
  return token;
}

// ─── Step 2a: Pure REST path — POST /api/v1/agents/{id}/run ───────────────
async function runViaRest(accessToken) {
  const url = `${BASE_URL}/api/v1/agents/${encodeURIComponent(AGENT_ID)}/run`;
  // Schema (backend/app/api/agent_run.py:AgentRunRequest):
  //   {input: {text, extra?}, runtime_mode?, ...}
  const payload = {
    input: { text: INPUT_TEXT },
    runtime_mode: 'corti_like_fast',
  };

  console.log(`→ POST ${url}`);
  const res = await fetch(url, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${accessToken}`,
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`agent run failed: HTTP ${res.status} — ${text}`);
  }
  return await res.json();
}

// ─── Step 2b: SDK path — @icoder/sdk ──────────────────────────────────────
async function runViaSdk(accessToken) {
  // Resolve SDK from local workspace. If consumer installed it via npm, this
  // resolves from node_modules instead.
  let sdkPath = '@icoder/sdk';
  let ICoDer;
  try {
    ({ default: ICoDer } = await import(sdkPath));
  } catch {
    // Fall back to local workspace path (dev only)
    try {
      const path = await import('node:path');
      const url = await import('node:url');
      const candidate = path.resolve('../../packages/icoder-sdk/dist/index.js');
      const fileUrl = url.pathToFileURL(candidate).href;
      ({ default: ICoDer } = await import(fileUrl));
      console.log(`⚠ SDK loaded from local workspace: ${candidate}`);
      console.log(`  (publishing to npm will remove this fallback)`);
    } catch (e) {
      throw new Error(
        `@icoder/sdk not installed. Run "npm install @icoder/sdk" or use --mode rest. Cause: ${e.message}`,
      );
    }
  }

  const client = new ICoDer({
    baseURL: BASE_URL,
    auth: { accessToken },
  });

  console.log(`→ icoder.runs.runText("${AGENT_ID}", "${INPUT_TEXT.slice(0, 40)}...")`);
  // Canonical SDK entrypoint — see packages/icoder-sdk/src/resources/runs.ts
  const { data: run, error } = await client.runs.runText(AGENT_ID, INPUT_TEXT, {
    runtime_mode: 'corti_like_fast',
  });

  if (error) {
    throw new Error(`SDK returned error: ${JSON.stringify(error)}`);
  }
  return run;
}

// ─── Step 3: Print result ─────────────────────────────────────────────────
function prettyRun(result) {
  // The run envelope (per backend/app/api/agent_run.py:AgentRunResponse) has
  // the LLM output under ``result.markdown`` and the raw provider response
  // under ``result.raw_provider_response.content``. ``summary`` is the
  // first paragraph of the markdown.
  const result_obj = result.result || {};
  const raw = result_obj.raw_provider_response || {};
  const output = result_obj.markdown
    || result_obj.summary
    || raw.content
    || (typeof result.output === 'string' ? result.output : JSON.stringify(result.output ?? {}));
  const out = {
    run_id: result.run_id,
    trace_id: result.trace_id,
    trace_url: result.trace_url,
    status: result_obj.status,
    latency_ms: result.latency_ms,
    llm_provider: result.llm_provider,
    backend_provider: result_obj.backend_provider,
    cost: result.cost,
    runtime_mode: result.runtime_mode,
    error: result.error,
    error_reason: result.error_reason,
    output_preview: typeof output === 'string' ? output.slice(0, 240) : JSON.stringify(output).slice(0, 240),
  };
  return JSON.stringify(out, null, 2);
}

// ─── Main ─────────────────────────────────────────────────────────────────
async function main() {
  console.log('═'.repeat(72));
  console.log('  iCoDer External Agent Consumer — Sprint 2 Goal F Verification');
  console.log(`  backend  : ${BASE_URL}`);
  console.log(`  agent    : ${AGENT_ID}`);
  console.log(`  mode     : ${MODE}`);
  console.log('═'.repeat(72));

  // Step 1 — token exchange (always pure REST, even in SDK mode, so the
  // consumer proves it can authenticate independently of any SDK helper).
  const token = await fetchAccessToken();

  // Step 2 — invoke agent
  let run;
  if (MODE === 'rest') {
    run = await runViaRest(token);
  } else if (MODE === 'sdk') {
    run = await runViaSdk(token);
  } else {
    // auto: try SDK, fall back to REST
    try {
      run = await runViaSdk(token);
    } catch (e) {
      console.warn(`⚠ SDK path failed (${e.message}); falling back to REST`);
      run = await runViaRest(token);
    }
  }

  // Step 3 — verdict
  console.log('─'.repeat(72));
  console.log(prettyRun(run));
  console.log('─'.repeat(72));

  if (run.error) {
    console.error(`✗ Agent returned error=true (reason=${run.error_reason || 'unknown'})`);
    process.exit(1);
  }

  console.log('✓ Goal F verified: external consumer received a structured response from iCoDer.');
}

main().catch((err) => {
  console.error('✗ Verification failed:', err.message);
  process.exit(1);
});
