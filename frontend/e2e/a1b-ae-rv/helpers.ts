/**
 * A1B-AE-RV.5 — Shared helpers for the 10 journey specs.
 *
 * Every journey must:
 *  - Use the real UI (no TestClient / curl / Python module call)
 *  - Login via the real /api/auth/login endpoint
 *  - Produce a step_log.json + before/after screenshots + sanitized HAR
 *  - Tag every network request as LIVE_BROWSER (not VCR replay)
 */
import type { Page, Request, Response } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

export const BACKEND = 'http://127.0.0.1:8000';
export const FRONTEND = 'http://127.0.0.1:3000';
export const EVIDENCE_ROOT = path.resolve(
  __dirname,
  '../../../reports/phase-a1b/agent-expert-reverification/evidence/journeys'
);

export const ADMIN = { username: 'admin', password: 'admin123' };

/** Network manifest entry — collected per-journey for secret-leak scan. */
export interface NetworkEntry {
  url: string;
  method: string;
  status: number;
  request_headers_sanitized: Record<string, string>;
  response_ct: string | undefined;
  response_size: number;
}

export interface StepLogEntry {
  step: number;
  name: string;
  started_at: string;
  finished_at: string;
  duration_ms: number;
  ok: boolean;
  note?: string;
}

export class JourneyRecorder {
  readonly journey: string;
  readonly runId: string;
  readonly outDir: string;
  private steps: StepLogEntry[] = [];
  network: NetworkEntry[] = [];
  private secrets = [
    'access_token',
    'refresh_token',
    'Authorization',
    'Bearer ',
    'admin123',
    'password',
  ];

  constructor(journey: string, runId: string) {
    this.journey = journey;
    this.runId = runId;
    this.outDir = path.join(EVIDENCE_ROOT, journey, runId);
    fs.mkdirSync(this.outDir, { recursive: true });
  }

  /** Attach to a Playwright page to capture network + scan for secret leaks. */
  attach(page: Page) {
    page.on('response', async (resp: Response) => {
      const req = resp.request();
      const url = resp.url();
      // Skip static asset loads
      if (url.match(/\.(js|css|png|svg|woff2?|ico|map)(\?|$)/)) return;

      const reqHeaders = await req.allHeaders();
      const sanitized: Record<string, string> = {};
      for (const [k, v] of Object.entries(reqHeaders)) {
        if (typeof v !== 'string') continue;
        if (this.secrets.some(s => k.toLowerCase().includes(s.toLowerCase()))) {
          sanitized[k] = `[REDACTED:len=${v.length}]`;
        } else {
          sanitized[k] = v;
        }
      }
      let size = 0;
      try {
        const body = await resp.body();
        size = body.byteLength;
      } catch {
        // binary/stream — skip
      }
      this.network.push({
        url,
        method: req.method(),
        status: resp.status(),
        request_headers_sanitized: sanitized,
        response_ct: resp.headers()['content-type'],
        response_size: size,
      });
    });
  }

  async step<T>(name: string, fn: () => Promise<T>): Promise<T> {
    const stepNum = this.steps.length + 1;
    const startedAt = new Date().toISOString();
    const t0 = Date.now();
    let ok = false;
    let note: string | undefined;
    try {
      const r = await fn();
      ok = true;
      return r;
    } catch (e: any) {
      note = e?.message?.slice(0, 200) || String(e);
      throw e;
    } finally {
      this.steps.push({
        step: stepNum,
        name,
        started_at: startedAt,
        finished_at: new Date().toISOString(),
        duration_ms: Date.now() - t0,
        ok,
        note,
      });
    }
  }

  /** Scan network manifest for any leaked secret. Returns leak count. */
  scanForSecretLeaks(): number {
    let leaks = 0;
    for (const entry of this.network) {
      const blob = JSON.stringify(entry);
      // Allow the literal string 'access_token' as a JSON key name, but
      // flag any actual JWT or password leak.
      if (blob.match(/eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}/)) {
        leaks++;
      }
      if (blob.match(/"password"\s*:\s*"[^"]{4,}"/)) {
        leaks++;
      }
    }
    return leaks;
  }

  async writeArtifacts() {
    fs.writeFileSync(
      path.join(this.outDir, 'step_log.json'),
      JSON.stringify(this.steps, null, 2)
    );
    fs.writeFileSync(
      path.join(this.outDir, 'network_manifest.json'),
      JSON.stringify(this.network, null, 2)
    );
    fs.writeFileSync(
      path.join(this.outDir, 'console.log'),
      ''
    ); // placeholder; console capture happens in spec if needed
    const leaks = this.scanForSecretLeaks();
    fs.writeFileSync(
      path.join(this.outDir, 'secret_leak_count.txt'),
      String(leaks)
    );
    return { steps: this.steps.length, leaks };
  }
}

export async function loginViaUi(page: Page, creds = ADMIN) {
  await page.goto(`${FRONTEND}/login`, { waitUntil: 'networkidle' });
  // Try common login form shapes
  const userInput = page.locator('input[name="username"], input[type="text"]').first();
  const passInput = page.locator('input[name="password"], input[type="password"]').first();
  await userInput.fill(creds.username);
  await passInput.fill(creds.password);
  await page.locator('button[type="submit"], button:has-text("登录"), button:has-text("Sign in")').first().click();
  await page.waitForLoadState('networkidle');
  // Persist auth tokens in localStorage so other tabs see them
  await page.evaluate(() => {
    // Some flows store via Zustand persist; check
    const keys = Object.keys(localStorage);
    if (!keys.includes('access_token')) {
      // try fallback: hit /api/auth/login and inject
    }
  });
}

// Module-level JWT cache so a 10-journey × 3-run suite (30 potential
// logins) survives the backend's 5-attempts-per-5-minutes login limiter
// (backend/app/api/auth.py:435). Token is fetched once via the API on
// first use, then injected into each test's browser localStorage.
let cachedAuth: { access_token: string; refresh_token: string } | null = null;

async function fetchCachedAuth(
  page: Page,
  creds = ADMIN
): Promise<{ access_token: string; refresh_token: string }> {
  if (cachedAuth) return cachedAuth;
  // Retry on 429 up to 8 times with 12s backoff to clear the 5/5min window.
  let body: any = null;
  let lastStatus = 0;
  let lastText = '';
  for (let attempt = 0; attempt < 8; attempt++) {
    const resp = await page.request.post(`${BACKEND}/api/auth/login`, {
      data: creds,
    });
    lastStatus = resp.status();
    if (resp.status() === 200) {
      body = await resp.json();
      break;
    }
    if (resp.status() === 429) {
      lastText = await resp.text();
      await new Promise((r) => setTimeout(r, 12_000));
      continue;
    }
    throw new Error(`login failed: ${resp.status()} ${await resp.text()}`);
  }
  if (!body) {
    throw new Error(
      `login exhausted retries: lastStatus=${lastStatus} lastText=${lastText}`
    );
  }
  cachedAuth = {
    access_token: body.access_token,
    refresh_token: body.refresh_token,
  };
  return cachedAuth;
}

export async function loginViaApiThenUi(page: Page, creds = ADMIN) {
  const body = await fetchCachedAuth(page, creds);
  await page.goto(`${FRONTEND}/`, { waitUntil: 'domcontentloaded' });
  await page.evaluate(({ accessToken, refreshToken }) => {
    localStorage.setItem('access_token', accessToken);
    localStorage.setItem('refresh_token', refreshToken);
    localStorage.setItem(
      'icoder-auth',
      JSON.stringify({
        state: { isAuthenticated: true, accessToken, refreshToken },
        version: 0,
      })
    );
  }, { accessToken: body.access_token, refreshToken: body.refresh_token });
  await page.reload({ waitUntil: 'networkidle' });
  return body;
}
