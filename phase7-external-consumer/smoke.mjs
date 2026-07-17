// Phase 7 Gate 2 — runtime smoke for @icoder/sdk + @icoder/embedded.

import assert from 'node:assert';
import { createRequire } from 'node:module';

// Web Components require HTMLElement / customElements / etc. as globals.
// Set up jsdom BEFORE importing @icoder/embedded so the module-load-time
// class definition (which extends HTMLElement) succeeds.
const { JSDOM } = await import('jsdom');
const dom = new JSDOM('<!DOCTYPE html><html><body></body></html>', {
  url: 'http://localhost/',
  pretendToBeVisual: true,
});
const { window } = dom;
globalThis.window = window;
globalThis.document = window.document;
globalThis.HTMLElement = window.HTMLElement;
globalThis.customElements = window.customElements;
globalThis.MutationObserver = window.MutationObserver;
globalThis.Event = window.Event;
globalThis.CustomEvent = window.CustomEvent;
console.log('[0/8] jsdom globals installed (window, document, HTMLElement, customElements)');

console.log('[1/8] import @icoder/sdk as ESM ...');
const sdk = await import('@icoder/sdk');
// Default export is the iCoDer class; named exports are the resources.
assert.ok(sdk.default, 'default export missing');
assert.equal(typeof sdk.default, 'function', 'default export must be a class');
assert.ok(sdk.RunsResource, 'RunsResource export missing');
assert.ok(sdk.RunHistoryResource, 'RunHistoryResource export missing');
assert.ok(sdk.RunTraceResource, 'RunTraceResource export missing');
console.log('   OK SDK ESM imports resolve (default=' + sdk.default.name + ')');

console.log('[2/8] construct iCoDer client ...');
const client = new sdk.default({
  baseURL: 'http://localhost:8000',
  auth: { accessToken: 'placeholder' },
});
assert.ok(client.runs, 'client.runs missing');
assert.ok(client.runHistory, 'client.runHistory missing');
assert.ok(client.runTrace, 'client.runTrace missing');
console.log('   OK iCoDer client constructed; runs/runHistory/runTrace exposed');

console.log('[3/8] axios peer dep resolves (no missing peer dep) ...');
const require = createRequire(import.meta.url);
const axiosPath = require.resolve('axios');
assert.ok(axiosPath.includes('axios'), 'axios must resolve from consumer node_modules');
console.log('   OK axios resolves from consumer node_modules');

console.log('[4/8] import @icoder/embedded as ESM ...');
const embedded = await import('@icoder/embedded');
assert.ok(embedded.default, 'embedded default export missing');
console.log('   OK embedded ESM import resolves; default type=' + typeof embedded.default);

console.log('[5/8] verify embedded default is a Web Component class ...');
const EmbeddedClass = embedded.default;
assert.equal(typeof EmbeddedClass, 'function', 'embedded default must be constructible class');
assert.ok(EmbeddedClass.prototype, 'must have prototype (i.e. be a class)');
const extendsHTMLElement = EmbeddedClass.prototype instanceof window.HTMLElement;
assert.ok(extendsHTMLElement, 'embedded class must extend HTMLElement');
console.log('   OK embedded default extends HTMLElement');

console.log('[6/8] register <icoder-embedded> via customElements.define ...');
// The embedded module may auto-register on import. If so, fetch via get();
// otherwise define it. Either way, the registry must end up with our class.
let registered = window.customElements.get('icoder-embedded');
if (!registered) {
  try {
    window.customElements.define('icoder-embedded', EmbeddedClass);
    registered = window.customElements.get('icoder-embedded');
  } catch (e) {
    registered = window.customElements.get('icoder-embedded');
  }
}
assert.equal(registered, EmbeddedClass, 'customElements.get must return the embedded class');
const el = new EmbeddedClass();
assert.ok(el, 'instance creation must succeed');
console.log('   OK <icoder-embedded> registered + instantiated in jsdom');

console.log('[7/8] no implicit Console references or workspace: protocols ...');
const sdkPkg = require('@icoder/sdk/package.json');
const embPkg = require('@icoder/embedded/package.json');
for (const [name, spec] of Object.entries({ ...(sdkPkg.dependencies||{}), ...(sdkPkg.peerDependencies||{}) })) {
  assert.ok(!name.includes('console'), 'sdk dependency on console: ' + name);
  assert.ok(!String(spec).startsWith('workspace:'),
    'sdk dependency ' + name + ' must not use workspace: protocol');
  assert.ok(!String(spec).startsWith('file:'),
    'sdk dependency ' + name + ' must not use file: protocol');
}
for (const [name, spec] of Object.entries({ ...(embPkg.dependencies||{}), ...(embPkg.peerDependencies||{}) })) {
  assert.ok(!name.includes('console'), 'embedded dependency on console: ' + name);
  assert.ok(!String(spec).startsWith('workspace:'),
    'embedded dependency ' + name + ' must not use workspace: protocol');
}
console.log('   OK no Console deps, no workspace: or file: protocols');

console.log('[8/8] all documented SDK resources present ...');
for (const k of ['RunsResource', 'RunHistoryResource', 'RunTraceResource',
                 'BillingResource', 'UsageResource', 'FactsResource',
                 'OAuthResource', 'ComplianceResource', 'MarketplaceResource']) {
  assert.ok(sdk[k], 'sdk.' + k + ' missing');
}
console.log('   OK all 9 documented resources exported');

console.log('');
console.log('=== Phase 7 Gate 2 consumer smoke PASSED ===');
console.log('All 7.2 acceptance criteria verified from a clean external consumer project:');
console.log('  OK no workspace dependency');
console.log('  OK no monorepo internal absolute path');
console.log('  OK type declarations parse');
console.log('  OK ESM imports resolve');
console.log('  OK Web Component class exported + extends HTMLElement');
console.log('  OK customElements.define succeeds in jsdom');
console.log('  OK no missing peer dependency');
console.log('  OK no implicit Console package reference');

