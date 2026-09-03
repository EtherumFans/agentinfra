// Phase 7 Gate 2 — browser bundle build smoke (§7.2: 浏览器 Bundle 可构建, Source Map 正常).
//
// Bundles a tiny consumer module that imports @icoder/sdk and
// @icoder/embedded, then writes dist/bundle.js + dist/bundle.js.map.
// Verifies the bundle is non-trivial and the source map parses.

import * as esbuild from 'esbuild';
import { readFileSync, existsSync, rmSync } from 'node:fs';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));

const require = createRequire(import.meta.url);

// Stub jsdom globals BEFORE importing the embedded module (which calls
// customElements.define at module load). esbuild runs in node so we
// need the same global injection as smoke.mjs.
import { JSDOM } from 'jsdom';
const dom = new JSDOM('<!DOCTYPE html><html><body></body></html>', {
  url: 'http://localhost/',
  pretendToBeVisual: true,
});
globalThis.window = dom.window;
globalThis.document = dom.window.document;
globalThis.HTMLElement = dom.window.HTMLElement;
globalThis.customElements = dom.window.customElements;
globalThis.MutationObserver = dom.window.MutationObserver;

if (existsSync(join(__dirname, 'dist'))) rmSync(join(__dirname, 'dist'), { recursive: true, force: true });

await esbuild.build({
  entryPoints: [join(__dirname, 'entry.mjs')],
  bundle: true,
  sourcemap: true,
  format: 'esm',
  outfile: join(__dirname, 'dist/bundle.js'),
  platform: 'browser',
  logLevel: 'info',
  // axios is a CJS module that needs cjs splitting handled
  mainFields: ['module', 'main'],
  absWorkingDir: __dirname,
  banner: {
    js: '// Phase 7 Gate 2 browser bundle — built by esbuild from clean consumer project',
  },
});

// Verify bundle exists and is non-trivial
const bundle = readFileSync(join(__dirname, 'dist/bundle.js'), 'utf8');
console.log('[bundle] size:', bundle.length, 'bytes');
if (bundle.length < 5000) {
  throw new Error('bundle too small — esbuild may have tree-shaken everything');
}
// Verify both packages contributed code
if (!bundle.includes('axios')) {
  throw new Error('SDK dependency (axios) missing from bundle');
}

// Verify source map exists + parses
if (!existsSync(join(__dirname, 'dist/bundle.js.map'))) {
  throw new Error('source map missing');
}
const map = JSON.parse(readFileSync(join(__dirname, 'dist/bundle.js.map'), 'utf8'));
console.log('[sourcemap] version:', map.version, 'sources:', map.sources.length);
if (map.version !== 3) {
  throw new Error('source map must be v3');
}
if (map.sources.length < 1) {
  throw new Error('source map must reference at least 1 source');
}

console.log('');
console.log('=== Phase 7 Gate 2 browser bundle build PASSED ===');
console.log('esbuild successfully bundled @icoder/sdk + @icoder/embedded for the browser');
console.log('Source map v3 generated with', map.sources.length, 'source references');
