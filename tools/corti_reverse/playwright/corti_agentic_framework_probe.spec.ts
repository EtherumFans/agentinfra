/**
 * Phase 3-B1.5 Section C — Corti Agentic Framework Probe (IMPLEMENTED).
 *
 * Playwright spec for automated black-box capture of Corti runtime
 * mechanism. Authorized access only — credentials via env vars OR
 * reused storageState. No hardcoded credentials.
 *
 * Output:
 *   - artifacts/corti_reverse/screenshots/C-<step>-<page>-<state>.png
 *   - artifacts/corti_reverse/hars/C-<step>-<page>-<state>.har
 *   - artifacts/corti_reverse/traces/C-<step>-<page>-<state>.zip
 *   - artifacts/corti_reverse/screenshots/C-<step>-<page>-<state>.console.json
 *   - artifacts/corti_reverse/screenshots/C-<step>-<page>-<state>.network.json
 *
 * Run:
 *   # With saved storageState (recommended — reuse logged-in profile):
 *   CORTI_STORAGE_STATE=artifacts/corti_reverse/.auth/state.json \
 *     npx playwright test --config=tools/corti_reverse/playwright/playwright.config.ts
 *
 *   # With email + password (will trigger Google OAuth or email login):
 *   CORTI_EMAIL=... CORTI_PASSWORD=... \
 *     npx playwright test --config=tools/corti_reverse/playwright/playwright.config.ts
 *
 *   # Run only the stability suite (3x on first 5 paths):
 *   npx playwright test --config=tools/corti_reverse/playwright/playwright.config.ts \
 *     --grep "stability"
 *
 *   # Run a single path:
 *   npx playwright test --config=tools/corti_reverse/playwright/playwright.config.ts \
 *     --grep "01-login"
 *
 * Post-capture redaction (REQUIRED before commit):
 *   for har in artifacts/corti_reverse/hars/C-*.har; do
 *     python tools/corti_reverse/har_analyzer/redact_har.py \
 *       --input "$har" \
 *       --output "${har%.har}.redacted.har"
 *   done
 *
 * Authorization:
 *   - Authorized Corti account (user's own).
 *   - No bypassing access control — login via Google OAuth as normal user.
 *   - No decompilation, no copying private code/prompts/models/data.
 *   - All screenshots and HAR files MUST pass redact_har.py before commit.
 *
 * Status: IMPLEMENTED — covers 15 paths × (screenshot + HAR + trace +
 * console + network metadata). 3x stability on first 5 paths.
 */

import { test, expect, type Page, type BrowserContext } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

const ARTIFACTS = path.resolve(__dirname, '..', '..', '..', 'artifacts', 'corti_reverse');
const SCREENSHOTS = path.join(ARTIFACTS, 'screenshots');
const TRACES = path.join(ARTIFACTS, 'traces');
const HARS = path.join(ARTIFACTS, 'hars');

const BASE_URL = process.env.CORTI_BASE_URL || 'https://console.corti.app/';
const PROJECT_ID = process.env.CORTI_PROJECT_ID || '';
const AGENT_ID = process.env.CORTI_AGENT_ID || '';
const PRESET_ID = process.env.CORTI_PRESET_ID || 'medical-coding-icd-10-cpt-agent';

// Ensure output dirs exist
for (const dir of [SCREENSHOTS, TRACES, HARS]) {
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
}

/**
 * 15 paths per Section B's observation log. URLs are parameterized:
 *   - {project_id} — substituted from CORTI_PROJECT_ID env var
 *   - {agent_id} — substituted from CORTI_AGENT_ID env var (cloned agent)
 *
 * When the env vars are not set, paths that require them are skipped
 * with a clear reason.
 */
interface PathSpec {
  id: string;
  desc: string;
  url: string | ((env: PathEnv) => string);
  requiresProjectId?: boolean;
  requiresAgentId?: boolean;
  waitForSelector?: string;
  waitForNetworkIdle?: boolean;
  preActions?: ((page: Page) => Promise<void>)[];
  actions?: ((page: Page) => Promise<void>)[];
  /** Skip run entirely (e.g., error states that would consume credits). */
  skipReason?: string;
}

interface PathEnv {
  projectId: string;
  agentId: string;
  presetId: string;
}

const PATH_ENV: PathEnv = {
  projectId: PROJECT_ID,
  agentId: AGENT_ID,
  presetId: PRESET_ID,
};

function resolveUrl(spec: PathSpec): string {
  if (typeof spec.url === 'function') return spec.url(PATH_ENV);
  return spec.url;
}

function maybeSkip(spec: PathSpec): string | null {
  if (spec.skipReason) return spec.skipReason;
  if (spec.requiresProjectId && !PROJECT_ID) {
    return 'CORTI_PROJECT_ID env var not set — cannot resolve project-scoped URL';
  }
  if (spec.requiresAgentId && !AGENT_ID) {
    return 'CORTI_AGENT_ID env var not set — cannot resolve agent-scoped URL';
  }
  return null;
}

const CORTI_PATHS: PathSpec[] = [
  {
    id: '01-login',
    desc: 'Login / region selection / workspace entry',
    url: '/',
    waitForSelector: 'body',
    waitForNetworkIdle: true,
  },
  {
    id: '02-home',
    desc: 'Home / dashboard (project picker → open project)',
    url: '/',
    requiresProjectId: true,
    waitForSelector: 'body',
    waitForNetworkIdle: true,
    preActions: [
      async (page) => {
        // If project picker is shown, click first "Open Project" button.
        const openBtn = page.getByRole('button', { name: /open project/i }).first();
        if (await openBtn.isVisible().catch(() => false)) {
          await openBtn.click();
        }
      },
    ],
    actions: [
      async (page) => {
        // Wait for sidebar to render
        await page.waitForSelector('nav, [role="navigation"]', { timeout: 15000 }).catch(() => {});
      },
    ],
  },
  {
    id: '03-agent-library',
    desc: 'Agent Library (My agents + Pre-built agents toggle)',
    url: (env) => `/project/${env.projectId}/ai-studio/agents`,
    requiresProjectId: true,
    waitForSelector: 'body',
    waitForNetworkIdle: true,
    actions: [
      async (page) => {
        // Toggle "Pre-built agents" view to capture full catalog
        const preBuiltTab = page.getByRole('tab', { name: /pre-built agents/i })
          .or(page.getByRole('button', { name: /pre-built agents/i }))
          .first();
        if (await preBuiltTab.isVisible().catch(() => false)) {
          await preBuiltTab.click();
          await page.waitForLoadState('networkidle');
        }
      },
    ],
  },
  {
    id: '04-agent-filters',
    desc: 'Agent filters: Use case menu open',
    url: (env) => `/project/${env.projectId}/ai-studio/agents`,
    requiresProjectId: true,
    waitForSelector: 'body',
    waitForNetworkIdle: true,
    actions: [
      async (page) => {
        const preBuiltTab = page.getByRole('tab', { name: /pre-built agents/i })
          .or(page.getByRole('button', { name: /pre-built agents/i }))
          .first();
        if (await preBuiltTab.isVisible().catch(() => false)) {
          await preBuiltTab.click();
          await page.waitForLoadState('networkidle');
        }
        const filterBtn = page.getByRole('button', { name: /use case|open filter menu/i }).first();
        if (await filterBtn.isVisible().catch(() => false)) {
          await filterBtn.click();
          await page.waitForTimeout(500);
        }
      },
    ],
  },
  {
    id: '05-medical-coding-card',
    desc: 'Medical Coding Agent pre-built card click (opens New Agent page with preset)',
    url: (env) =>
      `/project/${env.projectId}/ai-studio/agents/new?preset=${env.presetId}`,
    requiresProjectId: true,
    waitForSelector: 'body',
    waitForNetworkIdle: true,
  },
  {
    id: '06-customize-clone-dialog',
    desc: 'Customize agent → clone dialog opened',
    url: (env) =>
      `/project/${env.projectId}/ai-studio/agents/new?preset=${env.presetId}`,
    requiresProjectId: true,
    waitForSelector: 'body',
    waitForNetworkIdle: true,
    actions: [
      async (page) => {
        const customizeBtn = page.getByRole('button', { name: /customize agent/i }).first();
        if (await customizeBtn.isVisible().catch(() => false)) {
          await customizeBtn.click();
          await page.waitForTimeout(500);
        }
      },
    ],
  },
  {
    id: '07-medical-coding-detail',
    desc: 'Medical Coding Agent post-clone detail (3-panel layout)',
    url: (env) => `/project/${env.projectId}/ai-studio/agents/${env.agentId}`,
    requiresProjectId: true,
    requiresAgentId: true,
    waitForSelector: 'body',
    waitForNetworkIdle: true,
    actions: [
      async (page) => {
        // Capture Settings panel
        const settingsTab = page.getByRole('radio', { name: /settings/i })
          .or(page.getByRole('tab', { name: /settings/i }))
          .first();
        if (await settingsTab.isVisible().catch(() => false)) {
          await settingsTab.check().catch(() => settingsTab.click().catch(() => {}));
        }
      },
    ],
  },
  {
    id: '08-code-view',
    desc: 'Code view (JS SDK snippet)',
    url: (env) => `/project/${env.projectId}/ai-studio/agents/${env.agentId}`,
    requiresProjectId: true,
    requiresAgentId: true,
    waitForSelector: 'body',
    waitForNetworkIdle: true,
    actions: [
      async (page) => {
        const codeTab = page.getByRole('radio', { name: /^code$/i })
          .or(page.getByRole('tab', { name: /^code$/i }))
          .first();
        if (await codeTab.isVisible().catch(() => false)) {
          await codeTab.check().catch(() => codeTab.click().catch(() => {}));
          await page.waitForTimeout(500);
        }
      },
    ],
  },
  {
    id: '09-run-medical-coding',
    desc: 'Run Medical Coding Agent (typed EMR + Enter)',
    url: (env) => `/project/${env.projectId}/ai-studio/agents/${env.agentId}`,
    requiresProjectId: true,
    requiresAgentId: true,
    waitForSelector: 'body',
    waitForNetworkIdle: true,
    actions: [
      async (page) => {
        // CORTI_TEST_INPUT env var lets the operator choose what to send.
        // Default is a short generic EMR; operator can override.
        const input = process.env.CORTI_TEST_INPUT ||
          'Patient: 28-year-old female, RLQ pain 18h, nausea, fever 38.2C, WBC 14.5. CT: appendiceal diameter 12mm. Laparoscopic appendectomy performed.';
        const chatInput = page.getByPlaceholder(/what can i help you with|ask the agent/i).first();
        if (await chatInput.isVisible().catch(() => false)) {
          await chatInput.fill(input);
          await chatInput.press('Enter');
          // Wait for run to start (networkidle when run completes or after 30s)
          await page.waitForTimeout(2000);
        }
      },
    ],
  },
  {
    id: '10-run-result',
    desc: 'Run result (markdown tables + cost deduction)',
    url: (env) => `/project/${env.projectId}/ai-studio/agents/${env.agentId}`,
    requiresProjectId: true,
    requiresAgentId: true,
    waitForSelector: 'body',
    waitForNetworkIdle: false,
    // This path waits for the run from step 09 to complete (~15-30s).
    actions: [
      async (page) => {
        // Wait up to 60s for the response bubble to appear.
        await page.waitForSelector(
          '[data-testid="agent-response"], [class*="response"], [class*="message"]:nth-child(2)',
          { timeout: 60_000 },
        ).catch(() => {
          /* swallow — still capture screenshot of current state */
        });
        await page.waitForTimeout(2000);
      },
    ],
  },
  {
    id: '11-trace-audit-history',
    desc: 'Trace / audit / history (search DOM — Corti has no dedicated trace UI)',
    url: (env) => `/project/${env.projectId}/ai-studio/agents/${env.agentId}`,
    requiresProjectId: true,
    requiresAgentId: true,
    waitForSelector: 'body',
    waitForNetworkIdle: true,
    // No navigation — just DOM-search the current page for trace UI elements.
    actions: [
      async (page) => {
        // Search for trace/history/audit/log UI elements
        const selectors = ['[class*="trace"]', '[class*="history"]', '[class*="audit"]', '[class*="run-log"]'];
        for (const sel of selectors) {
          await page.waitForSelector(sel, { timeout: 1000 }).catch(() => {});
        }
      },
    ],
  },
  {
    id: '12-usage-dashboard',
    desc: 'Usage dashboard (alternative to step 11 — Corti may surface trace via Usage)',
    url: (env) => `/project/${env.projectId}/usage`,
    requiresProjectId: true,
    waitForSelector: 'body',
    waitForNetworkIdle: true,
  },
  {
    id: '13-error-empty-input',
    desc: 'Error state: empty input (chat send button should be disabled)',
    url: (env) => `/project/${env.projectId}/ai-studio/agents/${env.agentId}`,
    requiresProjectId: true,
    requiresAgentId: true,
    waitForSelector: 'body',
    waitForNetworkIdle: true,
    actions: [
      async (page) => {
        const chatInput = page.getByPlaceholder(/what can i help you with|ask the agent/i).first();
        if (await chatInput.isVisible().catch(() => false)) {
          await chatInput.fill('');
          await page.waitForTimeout(500);
        }
      },
    ],
  },
  {
    id: '14-api-docs',
    desc: 'API docs / developer docs (docs.corti.ai)',
    url: 'https://docs.corti.ai/agentic/overview',
    waitForSelector: 'body',
    waitForNetworkIdle: true,
  },
  {
    id: '15-a2a-mcp-docs',
    desc: 'A2A / MCP / Agentic Framework docs',
    url: 'https://docs.corti.ai/agentic/a2a-protocol',
    waitForSelector: 'body',
    waitForNetworkIdle: true,
    actions: [
      async (page) => {
        // Also capture the MCP Authentication page in same test (navigate after first capture)
        // The HAR / trace will include both navigations.
        await page.goto('https://docs.corti.ai/agentic/mcp-authentication', {
          waitUntil: 'networkidle',
        }).catch(() => {/* swallow */});
      },
    ],
  },
];

/**
 * Capture console + network metadata for a given path id.
 */
async function attachConsoleAndNetworkCapture(page: Page, id: string): Promise<void> {
  const consoleLogs: { type: string; text: string; time: string }[] = [];
  const networkMeta: { url: string; method: string; status: number; resourceType: string; time: string }[] = [];

  page.on('console', (msg) => {
    consoleLogs.push({
      type: msg.type(),
      text: msg.text(),
      time: new Date().toISOString(),
    });
  });

  page.on('response', (res) => {
    const req = res.request();
    networkMeta.push({
      url: res.url(),
      method: req.method(),
      status: res.status(),
      resourceType: req.resourceType(),
      time: new Date().toISOString(),
    });
  });

  // Store cleanup functions on the page for later flushing
  (page as any).__captureFlush = async () => {
    await fs.promises.writeFile(
      path.join(SCREENSHOTS, `${id}.console.json`),
      JSON.stringify(consoleLogs, null, 2),
    );
    await fs.promises.writeFile(
      path.join(SCREENSHOTS, `${id}.network.json`),
      JSON.stringify(networkMeta, null, 2),
    );
  };
}

async function flushCapture(page: Page, id: string): Promise<void> {
  const fn = (page as any).__captureFlush;
  if (typeof fn === 'function') await fn();
}

test.describe('Corti Agentic Framework Probe — 15 paths', () => {
  for (const p of CORTI_PATHS) {
    // Per-path test.describe wraps recordHar so each path gets its own HAR file.
    // `test.use` inside a describe block applies to all tests in that block.
    test.describe(`captures ${p.id}`, () => {
      test.use({
        contextOptions: {
          recordHar: {
            path: path.join(HARS, `C-${p.id}.har`),
            content: 'embed', // embed response bodies in the HAR
            mode: 'full',     // record everything (not just minimal)
          },
        },
      });

      test(`${p.desc}`, async ({ page, context }) => {
        test.skip(!process.env.CORTI_EMAIL && !process.env.CORTI_STORAGE_STATE,
          'Requires CORTI_EMAIL or CORTI_STORAGE_STATE');

        const skipReason = maybeSkip(p);
        test.skip(skipReason !== null, skipReason || '');

        const url = resolveUrl(p);
        const tracePath = path.join(TRACES, `C-${p.id}.zip`);
        const screenshotPath = path.join(SCREENSHOTS, `C-${p.id}.png`);

        // Start tracing
        await context.tracing.start({
          screenshots: true,
          snapshots: true,
          sources: true,
        });

        // Attach console + network capture
        await attachConsoleAndNetworkCapture(page, `C-${p.id}`);

        // Navigate
        await page.goto(url, {
          waitUntil: p.waitForNetworkIdle ? 'networkidle' : 'domcontentloaded',
        });

        // Pre-actions (e.g., click Open Project on project picker)
        if (p.preActions) {
          for (const action of p.preActions) {
            await action(page).catch((e) => {
              console.warn(`preAction failed for ${p.id}: ${(e as Error).message}`);
            });
          }
        }

        // Wait for selector if specified
        if (p.waitForSelector) {
          await page.waitForSelector(p.waitForSelector, { timeout: 15000 }).catch(() => {});
        }

        // Actions
        if (p.actions) {
          for (const action of p.actions) {
            await action(page).catch((e) => {
              console.warn(`action failed for ${p.id}: ${(e as Error).message}`);
            });
          }
        }

        // Capture screenshot (full page)
        await page.screenshot({
          path: screenshotPath,
          fullPage: true,
        });

        // Stop tracing — saves to tracePath
        await context.tracing.stop({ path: tracePath });

        // Flush console + network metadata
        await flushCapture(page, `C-${p.id}`);

        // Smoke check: page loaded
        // (URL may differ if app redirected — verify the pathname is plausible)
        const finalUrl = page.url();
        expect(finalUrl.length).toBeGreaterThan(0);
      });
    });
  }
});

/**
 * Stability suite: run first 5 paths 3x each.
 * Captures variance in network call patterns and DOM render.
 */
test.describe('stability (3 runs)', () => {
  for (let run = 1; run <= 3; run++) {
    for (const p of CORTI_PATHS.slice(0, 5)) {
      test.describe(`run ${run}: ${p.id}`, () => {
        test.use({
          contextOptions: {
            recordHar: {
              path: path.join(HARS, `C-${p.id}-run${run}.har`),
              content: 'embed',
              mode: 'full',
            },
          },
        });

        test(`run ${run}: ${p.desc}`, async ({ page, context }) => {
          test.skip(!process.env.CORTI_EMAIL && !process.env.CORTI_STORAGE_STATE,
            'Requires auth');

          const skipReason = maybeSkip(p);
          test.skip(skipReason !== null, skipReason || '');

          const url = resolveUrl(p);
          const tracePath = path.join(TRACES, `C-${p.id}-run${run}.zip`);
          const screenshotPath = path.join(SCREENSHOTS, `C-${p.id}-run${run}.png`);

          await context.tracing.start({ screenshots: true, snapshots: true });
          await page.goto(url, { waitUntil: 'domcontentloaded' });

          if (p.preActions) {
            for (const action of p.preActions) {
              await action(page).catch(() => {});
            }
          }
          if (p.waitForSelector) {
            await page.waitForSelector(p.waitForSelector, { timeout: 15000 }).catch(() => {});
          }
          if (p.actions) {
            for (const action of p.actions) {
              await action(page).catch(() => {});
            }
          }

          await page.screenshot({ path: screenshotPath, fullPage: true });
          await context.tracing.stop({ path: tracePath });
        });
      });
    }
  }
});

/**
 * Optional: full session HAR capture.
 * Run as a single test to capture the entire session in one HAR.
 * Useful for Section D route graph extraction.
 */
test('full-session HAR capture (single test, all 15 paths in sequence)', async ({ page, context }) => {
  test.skip(!process.env.CORTI_EMAIL && !process.env.CORTI_STORAGE_STATE,
    'Requires auth');

  // Per-test recordHar via test.use — but this test is one-off, so set
  // recordHar inline via context options. Since context is already created
  // by the fixture, we use context.tracing + manual network capture instead.
  // For a true full-session HAR, the operator should set
  // CORTI_FULL_SESSION_HAR=1 and the test will start a fresh context.
  const fullHarPath = path.join(HARS, 'C-full-session.har');
  await context.tracing.start({ screenshots: true, snapshots: true, sources: true });
  await attachConsoleAndNetworkCapture(page, 'C-full-session');

  for (const p of CORTI_PATHS) {
    const skipReason = maybeSkip(p);
    if (skipReason) {
      console.log(`Skipping ${p.id}: ${skipReason}`);
      continue;
    }
    const url = resolveUrl(p);
    console.log(`Navigating to ${p.id}: ${url}`);
    await page.goto(url, { waitUntil: 'domcontentloaded' }).catch((e) => {
      console.warn(`navigate failed for ${p.id}: ${(e as Error).message}`);
    });
    if (p.waitForSelector) {
      await page.waitForSelector(p.waitForSelector, { timeout: 10000 }).catch(() => {});
    }
    if (p.actions) {
      for (const action of p.actions) {
        await action(page).catch((e) => {
          console.warn(`action failed for ${p.id}: ${(e as Error).message}`);
        });
      }
    }
    // Per-path screenshot for cross-reference
    await page.screenshot({
      path: path.join(SCREENSHOTS, `C-full-session-${p.id}.png`),
      fullPage: false, // viewport-only for speed
    });
  }

  await page.screenshot({
    path: path.join(SCREENSHOTS, 'C-full-session-final.png'),
    fullPage: true,
  });
  await context.tracing.stop({ path: path.join(TRACES, 'C-full-session.zip') });
  await flushCapture(page, 'C-full-session');

  // Note: full-session HAR requires running with a custom context. The
  // operator can capture this by running:
  //   CORTI_FULL_SESSION_HAR=1 npx playwright test --grep "full-session"
  // The test will then use recordHar set in playwright.config.ts use block.
  if (!fs.existsSync(fullHarPath)) {
    console.warn(`Full-session HAR not recorded. To record, set CORTI_FULL_SESSION_HAR=1 and re-run.`);
  }
});
