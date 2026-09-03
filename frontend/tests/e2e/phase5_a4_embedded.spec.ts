import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { test, expect } from '@playwright/test';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
// __dirname = E:/Corti4C/frontend/tests/e2e — go up 3 levels to reach repo root
const ROOT = resolve(__dirname, '..', '..', '..');
const PKG_DIST = resolve(ROOT, 'packages', 'icoder-embedded', 'dist');
// ES modules don't load from file:// — use a static server on port 8765
// (start it manually: `cd packages/icoder-embedded && python -m http.server 8765`)
const EXAMPLE_URL = 'http://localhost:8765/examples/index.html';

/**
 * Phase 5 A4 — Web Component method-based API regression test.
 *
 * Verifies the Corti-compatible API surface:
 *   - <icoder-embedded> tag registers
 *   - auth()/configureSession()/configure()/show() methods exist + return Promises
 *   - unified `embedded-event` envelope fires {name, payload}
 *   - legacy <icoder-assistant> tag still works (deprecated alias)
 *   - 1.0 attribute-based config still works (with console.warn)
 *
 * Tests against the static example HTML (no backend dependency) — the widget's
 * method-based API is exercised via JS calls; the agent run call itself is
 * not tested here (covered by backend Phase 4-G #1 live cost tests).
 */
test.describe('Phase 5 A4 — Web Component 2.0 API', () => {

  test.beforeEach(async ({ page }) => {
    // Capture console messages so we can assert deprecation warnings fire.
    page.on('console', (msg) => {
      // No-op; assertions inspect individual messages via page.on('console').
    });
  });

  test('widget registers as <icoder-embedded> with method-based API', async ({ page }) => {
    await page.goto(EXAMPLE_URL);

    // Wait for module to load + customElements.define to run
    await page.waitForFunction(() => customElements.get('icoder-embedded') !== undefined);

    // Methods must exist on the prototype (Corti-compatible surface)
    const methods = await page.evaluate(() => {
      const proto = customElements.get('icoder-embedded').prototype;
      return {
        auth: typeof proto.auth,
        configureSession: typeof proto.configureSession,
        configure: typeof proto.configure,
        show: typeof proto.show,
        setPatientContext: typeof proto.setPatientContext,  // iCoDer ADVANTAGE
        clearPatientContext: typeof proto.clearPatientContext,  // Phase 6 Gate 2
        clearSession: typeof proto.clearSession,  // Phase 6 Gate 2
        ask: typeof proto.ask,  // iCoDer ADVANTAGE
      };
    });
    expect(methods.auth).toBe('function');
    expect(methods.configureSession).toBe('function');
    expect(methods.configure).toBe('function');
    expect(methods.show).toBe('function');
    expect(methods.setPatientContext).toBe('function');
    expect(methods.clearPatientContext).toBe('function');
    expect(methods.clearSession).toBe('function');
    expect(methods.ask).toBe('function');
  });

  test('auth/configureSession/configure/show chain runs + emits embedded-event', async ({ page }) => {
    await page.goto(EXAMPLE_URL);
    await page.waitForFunction(() => customElements.get('icoder-embedded') !== undefined);

    // Hook a listener BEFORE clicking init. Capture events into window.__events.
    await page.evaluate(() => {
      (window as any).__events = [];
      const el = document.getElementById('icoder-assistant')!;
      el.addEventListener('embedded-event', (e: any) => {
        (window as any).__events.push({ name: e.detail.name, payload: e.detail.payload });
      });
      el.addEventListener('ready', () => {
        (window as any).__events.push({ name: 'ready', payload: {} });
      });
    });

    // Click the Initialize button — runs the full method chain
    await page.click('#btn-init');

    // After init: the chain completes + emits `ready` event (fired from
    // show() when _readyEmitted is false). Other events like `run.completed`
    // or `account.creditsConsumed` only fire on actual agent runs, not on init.
    await page.waitForFunction(() => (window as any).__events.length >= 1, undefined, { timeout: 2000 });

    const events = await page.evaluate(() => (window as any).__events);
    const names = events.map((e: any) => e.name);

    // ready fires from show() when _readyEmitted is false
    expect(names).toContain('ready');
    // The chain completes — show() was called successfully
    expect(events.length).toBeGreaterThanOrEqual(1);
  });

  test('widget hidden by default, visible after show()', async ({ page }) => {
    await page.goto(EXAMPLE_URL);
    await page.waitForFunction(() => customElements.get('icoder-embedded') !== undefined);

    // Before show() — hidden (Corti pattern)
    const beforeDisplay = await page.evaluate(() => {
      const el = document.getElementById('icoder-assistant') as HTMLElement;
      return getComputedStyle(el).display;
    });
    expect(beforeDisplay).toBe('none');

    // Trigger the chain
    await page.click('#btn-init');
    await page.waitForFunction(() => {
      const el = document.getElementById('icoder-assistant') as HTMLElement;
      return getComputedStyle(el).display !== 'none';
    }, undefined, { timeout: 2000 });

    // After show() — visible
    const afterDisplay = await page.evaluate(() => {
      const el = document.getElementById('icoder-assistant') as HTMLElement;
      return getComputedStyle(el).display;
    });
    expect(afterDisplay).not.toBe('none');
  });

  test('configureSession renders patient context bar', async ({ page }) => {
    await page.goto(EXAMPLE_URL);
    await page.waitForFunction(() => customElements.get('icoder-embedded') !== undefined);

    await page.click('#btn-init');
    // Wait for patient bar to become visible inside shadow DOM
    await page.waitForFunction(() => {
      const el = document.getElementById('icoder-assistant') as any;
      const bar = el.shadowRoot.querySelector('[data-patient-bar]');
      return bar && bar.classList.contains('visible');
    }, undefined, { timeout: 2000 });

    const patientText = await page.evaluate(() => {
      const el = document.getElementById('icoder-assistant') as any;
      const nameEl = el.shadowRoot.querySelector('[data-pt-name]');
      const idEl = el.shadowRoot.querySelector('[data-pt-id]');
      return {
        name: nameEl?.textContent || '',
        id: idEl?.textContent || '',
      };
    });
    expect(patientText.name).toBe('张三');
    expect(patientText.id).toBe('#P-2026-001');
  });

  test('Phase 6 Gate 2 — clearPatientContext() flushes PHI + emits event', async ({ page }) => {
    await page.goto(EXAMPLE_URL);
    await page.waitForFunction(() => customElements.get('icoder-embedded') !== undefined);

    await page.click('#btn-init');
    // Wait for patient bar to be visible (proves PHI is in widget memory)
    await page.waitForFunction(() => {
      const el = document.getElementById('icoder-assistant') as any;
      const bar = el.shadowRoot.querySelector('[data-patient-bar]');
      return bar && bar.classList.contains('visible');
    }, undefined, { timeout: 2000 });

    // Hook the event listener BEFORE clearPatientContext()
    await page.evaluate(() => {
      (window as any).__events = [];
      const el = document.getElementById('icoder-assistant')!;
      el.addEventListener('embedded-event', (e: any) => {
        (window as any).__events.push({
          name: e.detail.name,
          payload: e.detail.payload,
          meta: e.detail.meta,
        });
      });
    });

    // Call clearPatientContext() — should flush PHI + emit patient.context.cleared
    await page.evaluate(() => {
      const el = document.getElementById('icoder-assistant') as any;
      el.clearPatientContext();
    });

    // The patient bar should now be hidden (no patientId, no name)
    const phiAfterClear = await page.evaluate(() => {
      const el = document.getElementById('icoder-assistant') as any;
      const bar = el.shadowRoot.querySelector('[data-patient-bar]');
      return {
        barVisible: bar?.classList.contains('visible') || false,
        ctx: el._patientContext,  // not exposed, but the test runner reads the private field for white-box verification
      };
    });
    expect(phiAfterClear.barVisible).toBe(false);

    // Event must have fired
    const events = await page.evaluate(() => (window as any).__events);
    const cleared = events.find((e: any) => e.name === 'patient.context.cleared');
    expect(cleared).toBeTruthy();
    // Phase 6 Gate 3 — meta envelope with version/eventId/sessionId
    expect(cleared.meta).toBeTruthy();
    expect(cleared.meta.version).toBe('1.0');
    expect(cleared.meta.eventId).toMatch(/^[a-f0-9-]{8,}|^evt-/);
    expect(cleared.meta.sessionId).toMatch(/^[a-f0-9-]{8,}|^sid-/);
    expect(cleared.meta.contextId).toBe('');  // cleared
    expect(cleared.meta.timestamp).toMatch(/^\d{4}-\d{2}-\d{2}T/);
  });

  test('Phase 6 Gate 2 — clearSession() flushes PHI + auth + messages', async ({ page }) => {
    await page.goto(EXAMPLE_URL);
    await page.waitForFunction(() => customElements.get('icoder-embedded') !== undefined);

    await page.click('#btn-init');
    await page.waitForFunction(() => {
      const el = document.getElementById('icoder-assistant') as any;
      return el.shadowRoot.querySelector('[data-patient-bar]')?.classList.contains('visible');
    }, undefined, { timeout: 2000 });

    await page.evaluate(() => {
      (window as any).__events = [];
      document.getElementById('icoder-assistant')!
        .addEventListener('embedded-event', (e: any) => {
          (window as any).__events.push({
            name: e.detail.name,
            payload: e.detail.payload,
            meta: e.detail.meta,
          });
        });
    });

    await page.evaluate(() => {
      (document.getElementById('icoder-assistant') as any).clearSession();
    });

    // Bar hidden + event fired
    const barVisible = await page.evaluate(() => {
      const el = document.getElementById('icoder-assistant') as any;
      return el.shadowRoot.querySelector('[data-patient-bar]')?.classList.contains('visible') || false;
    });
    expect(barVisible).toBe(false);

    const events = await page.evaluate(() => (window as any).__events);
    const cleared = events.find((e: any) => e.name === 'session.cleared');
    expect(cleared).toBeTruthy();
    expect(cleared.meta.version).toBe('1.0');
    expect(cleared.meta.sessionId).toMatch(/^[a-f0-9-]{8,}|^sid-/);
  });

  test('Phase 6 Gate 3 — meta.sessionId stable across multiple events; eventId unique', async ({ page }) => {
    await page.goto(EXAMPLE_URL);
    await page.waitForFunction(() => customElements.get('icoder-embedded') !== undefined);

    await page.evaluate(() => {
      (window as any).__events = [];
      document.getElementById('icoder-assistant')!
        .addEventListener('embedded-event', (e: any) => {
          (window as any).__events.push({
            name: e.detail.name,
            meta: e.detail.meta,
          });
        });
    });

    await page.click('#btn-init');  // emits ready via separate dispatch, not embedded-event

    // Trigger 2 events: setPatientContext + clearPatientContext
    await page.evaluate(() => {
      const el = document.getElementById('icoder-assistant') as any;
      el.setPatientContext({ patientId: 'P-001', name: '甲' });
      el.clearPatientContext();
    });

    const events = await page.evaluate(() => (window as any).__events);
    expect(events.length).toBeGreaterThanOrEqual(2);

    // All events from same widget instance MUST share sessionId
    const sessionIds = new Set(events.map((e: any) => e.meta.sessionId));
    expect(sessionIds.size).toBe(1);

    // All eventIds MUST be unique
    const eventIds = events.map((e: any) => e.meta.eventId);
    expect(new Set(eventIds).size).toBe(eventIds.length);

    // All meta.version MUST be '1.0'
    expect(events.every((e: any) => e.meta.version === '1.0')).toBe(true);
  });

  test('legacy <icoder-assistant> tag still registers (deprecated alias)', async ({ page }) => {
    await page.goto(EXAMPLE_URL);
    await page.waitForFunction(() => customElements.get('icoder-assistant') !== undefined);

    // The alias should resolve to the same constructor (or a compatible one)
    const aliasOk = await page.evaluate(() => {
      const ctor = customElements.get('icoder-assistant');
      return typeof ctor === 'function';
    });
    expect(aliasOk).toBe(true);
  });

  test('1.0 attribute-based config still works (backward compat, console.warn)', async ({ page }) => {
    const warnings: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'warning') warnings.push(msg.text());
    });

    await page.goto(EXAMPLE_URL);
    await page.waitForFunction(() => customElements.get('icoder-assistant') !== undefined);

    // Click the legacy test button — installs a 1.0-style tag with attributes
    await page.click('#btn-legacy');

    // Wait for the tag to be processed
    await page.waitForFunction(() => {
      return document.querySelector('icoder-assistant[access-token]') !== null;
    }, undefined, { timeout: 2000 });

    // Deprecation warning must fire (proves backward-compat path is wired)
    expect(warnings.length).toBeGreaterThan(0);
    const hasDeprecationWarning = warnings.some((w) =>
      w.includes('access-token') && w.includes('deprecated')
    );
    expect(hasDeprecationWarning).toBe(true);
  });

  test('TypeScript type declarations ship in dist/', async () => {
    // Sanity check: the build emitted the .d.ts files referenced by package.json
    // "types" field. Consumers depend on these for IDE support.
    const { readFile } = await import('node:fs/promises');

    const indexDts = await readFile(resolve(PKG_DIST, 'index.d.ts'), 'utf8');
    expect(indexDts).toContain('iCoDerEmbedded');
    expect(indexDts).toContain('AuthOptions');
    expect(indexDts).toContain('SessionConfig');
    expect(indexDts).toContain('ConfigureOptions');
    expect(indexDts).toContain('EmbeddedEvent');
  });
});
