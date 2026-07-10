/**
 * Phase 3-B0 Section E — Agent navigation smoke test.
 *
 * Asserts that every route declared in App.tsx has a corresponding page
 * module that renders without crashing. Catches orphan routes pointing
 * to deleted pages, and nav links that lead nowhere.
 *
 * Strategy:
 *   1. Parse App.tsx to extract every `Route path="..."` element.
 *   2. For each route, confirm the referenced page module exists.
 *   3. For pages marked as deleted in P1.2 / Phase 2.1-A
 *      (Doctor, MethodCompare, RunTrace, Marketplace, old AgentHub),
 *      confirm they're NOT in App.tsx.
 *
 * This is a static analysis test — it does not mount React or run a browser.
 * The vitest config already covers runtime rendering via React Testing
 * Library in other suites.
 */
import { describe, it, expect } from 'vitest';
import fs from 'fs';
import path from 'path';

const REPO_ROOT = path.resolve(__dirname, '..', '..', '..', '..');
const APP_TSX = path.resolve(REPO_ROOT, 'frontend', 'src', 'App.tsx');

interface RouteEntry {
  path: string;
  element: string;
}

function parseRoutesFromAppTsx(): RouteEntry[] {
  const content = fs.readFileSync(APP_TSX, 'utf-8');
  const routes: RouteEntry[] = [];
  // Match <Route path="..." element={...} /> — handle multi-line and nested
  const routeRegex = /<Route\s+[^>]*?path="([^"]+)"[^>]*?element=\{([^}]+)\}[^>]*?\/>/g;
  for (const match of content.matchAll(routeRegex)) {
    const routePath = match[1];
    const element = match[2].trim();
    routes.push({ path: routePath, element });
  }
  return routes;
}

function parsePageImports(): Record<string, string> {
  /** Returns map of componentName → imported module path. */
  const content = fs.readFileSync(APP_TSX, 'utf-8');
  const imports: Record<string, string> = {};
  // Match: import X from './pages/X';
  const staticImportRegex = /import\s+(\w+)\s+from\s+'(\.\/pages\/[^']+)'/g;
  for (const m of content.matchAll(staticImportRegex)) {
    imports[m[1]] = m[2];
  }
  // Match: const X = lazy(() => import('./pages/X'));
  const lazyImportRegex = /const\s+(\w+)\s+=\s+lazy\(\(\)\s+=>\s+import\('(\.\/pages\/[^']+)'\)\)/g;
  for (const m of content.matchAll(lazyImportRegex)) {
    imports[m[1]] = m[2];
  }
  return imports;
}

const NON_PAGE_ELEMENTS = new Set(['Navigate', 'Outlet', 'Layout']);

describe('Phase 3-B0 — Agent navigation smoke', () => {
  const routes = parseRoutesFromAppTsx();
  const imports = parsePageImports();

  it('App.tsx has at least 5 routes', () => {
    expect(routes.length).toBeGreaterThan(5);
  });

  it('every Route element references a known page import (or non-page element)', () => {
    for (const route of routes) {
      const match = route.element.match(/<(\w+)/);
      if (!match) continue;
      const componentName = match[1];
      // Skip non-page elements like <Navigate />, <Outlet />, <Layout />
      if (NON_PAGE_ELEMENTS.has(componentName)) continue;
      expect(
        imports[componentName],
        `Route "${route.path}" references <${componentName} /> but no import found`,
      ).toBeTruthy();
    }
  });

  it('every imported page module file exists', () => {
    for (const [componentName, importPath] of Object.entries(imports)) {
      const resolved = path.resolve(REPO_ROOT, 'frontend', 'src', importPath + '.tsx');
      const altResolved = path.resolve(REPO_ROOT, 'frontend', 'src', importPath + '/index.tsx');
      const exists = fs.existsSync(resolved) || fs.existsSync(altResolved);
      expect(
        exists,
        `Import ${componentName} → ${importPath} but file not found at ${resolved}`,
      ).toBe(true);
    }
  });

  it('deleted P1.2 / Phase 2.1-A pages are NOT in App.tsx', () => {
    const deletedPages = [
      'DoctorPage',
      'MethodComparePage',
      'MarketplacePage',
      'AgentHubPage',
      // Phase 3-B2 Loop 0 (2026-07-05): EmbeddedAssistant physically deleted,
      // TextGeneration route entries removed (file kept as orphan for implicit
      // backend-capability dependencies).
      'EmbeddedAssistantPage',
      // Phase 4-F2 (2026-07-10): RunTracePage is KEPT — it's the dedicated
      // trace viewer required by §4.3 ("Dedicated RunTrace page must be
      // usable"). Previously listed as deleted (P1.2), but F2 restores it
      // to display trace_events persisted by the unified endpoint.
    ];
    const appContent = fs.readFileSync(APP_TSX, 'utf-8');
    for (const deleted of deletedPages) {
      expect(
        appContent,
        `Deleted page ${deleted} should not appear in App.tsx`,
      ).not.toContain(deleted);
    }
  });

  it('MedicalCodingPage is routed under /ai-studio/medical-coding', () => {
    const medicalCodingRoutes = routes.filter(
      (r) => r.element.includes('MedicalCodingPage'),
    );
    expect(medicalCodingRoutes.length).toBeGreaterThan(0);
    const hasAiStudioPath = medicalCodingRoutes.some(
      (r) => r.path === 'ai-studio/medical-coding',
    );
    expect(hasAiStudioPath, 'MedicalCodingPage must be routed at ai-studio/medical-coding').toBe(true);
  });

  it('no route path contains "agent-hub" (Phase 2.1-A deletion)', () => {
    for (const route of routes) {
      expect(
        route.path,
        `Route ${route.path} resurrects deleted agent-hub path`,
      ).not.toMatch(/agent-hub/);
    }
  });

  it('TextGeneration and EmbeddedAssistant routes are deprecated (Phase 3-B2 Loop 0)', () => {
    // Phase 3-B2 Loop 0 (2026-07-05): TextGeneration route entries removed
    // (file kept as orphan), EmbeddedAssistantPage physically deleted.
    // Old paths now redirect to /ai-studio/agents via <Navigate> rules.
    const textGenRoutes = routes.filter((r) => r.element.includes('TextGeneration'));
    const embeddedRoutes = routes.filter((r) => r.element.includes('EmbeddedAssistant'));
    expect(textGenRoutes.length, 'TextGeneration routes must be removed').toBe(0);
    expect(embeddedRoutes.length, 'EmbeddedAssistant routes must be removed').toBe(0);

    // Verify old paths redirect to Agent Hub.
    const appContent = fs.readFileSync(APP_TSX, 'utf-8');
    expect(appContent).toContain('ai-studio/text-generation');
    expect(appContent).toContain('ai-studio/embedded-assistant');
    const textGenRedirect = /path="ai-studio\/text-generation"[^>]*element=\{<Navigate[^>]+to="\/ai-studio\/agents"/;
    const embeddedRedirect = /path="ai-studio\/embedded-assistant"[^>]*element=\{<Navigate[^>]+to="\/ai-studio\/agents"/;
    expect(textGenRedirect.test(appContent), 'ai-studio/text-generation must redirect to /ai-studio/agents').toBe(true);
    expect(embeddedRedirect.test(appContent), 'ai-studio/embedded-assistant must redirect to /ai-studio/agents').toBe(true);
  });
});
