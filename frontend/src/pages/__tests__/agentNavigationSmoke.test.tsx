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
import fs from 'fs';
import path from 'path';

import { describe, it, expect } from 'vitest';

const REPO_ROOT = path.resolve(__dirname, '..', '..', '..', '..');
const APP_TSX = path.resolve(REPO_ROOT, 'frontend', 'src', 'App.tsx');
const LAYOUT_TSX = path.resolve(REPO_ROOT, 'frontend', 'src', 'components', 'layout', 'Layout.tsx');

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

const NON_PAGE_ELEMENTS = new Set([
  'Navigate',
  'Outlet',
  'Layout',
  'ProtectedRoute',
  'PlatformAdminRoute',
]);

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
      // Phase 7 Gate 13 (2026-07-14): EmbeddedAssistantPage restored for
      // Corti parity at /ai-studio/embedded-assistant.
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

  it('TextGeneration and EmbeddedAssistant standalone tools are routed for Corti parity', () => {
    const textGenRoutes = routes.filter((r) => r.element.includes('TextGeneration'));
    expect(textGenRoutes.length).toBeGreaterThan(0);
    expect(textGenRoutes.some(route => route.path === 'ai-studio/text-generation')).toBe(true);

    const appContent = fs.readFileSync(APP_TSX, 'utf-8');
    expect(appContent).toContain("lazy(() => import('./pages/TextGenerationPage'))");
    expect(appContent).not.toMatch(/path="ai-studio\/text-generation"[^>]*element=\{<Navigate/);

    const layoutContent = fs.readFileSync(LAYOUT_TSX, 'utf-8');
    expect(layoutContent).toContain("to: '/ai-studio/text-generation'");
    expect(layoutContent).toContain('label: t.textGeneration');
  });

  it('AI Studio capability cards route to their live standalone workbenches', () => {
    const overview = fs.readFileSync(
      path.join(REPO_ROOT, 'frontend', 'src', 'pages', 'AIStudioOverviewPage.tsx'),
      'utf-8',
    );
    for (const target of [
      '/ai-studio/speech-to-text',
      '/ai-studio/text-generation',
      '/ai-studio/embedded-assistant',
      '/ai-studio/fact-extraction',
      '/ai-studio/medical-coding',
    ]) {
      expect(overview).toContain(`exploreHref: '${target}'`);
    }
    expect(overview).not.toContain('are placeholder entries routed');
  });
});
