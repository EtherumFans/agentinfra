// Phase 7 Gate 2 — entry that imports both @icoder/sdk and @icoder/embedded.
// Bundled by esbuild into dist/bundle.js (see build.mjs).

import iCoDer, { RunsResource } from '@icoder/sdk';
import ICoDerEmbedded from '@icoder/embedded';

// Use the imports so esbuild keeps them in the bundle.
export const __sdk_class_name = iCoDer.name;
export const __sdk_runs_resource = RunsResource.name;
export const __embedded_class_name = ICoDerEmbedded.name;

// Demonstrate constructing the SDK client (axios will be live at runtime).
export const client = new iCoDer({
  baseURL: 'http://localhost:8000',
  auth: { accessToken: 'placeholder' },
});

console.log('[bundle] sdk:', iCoDer.name, 'embedded:', ICoDerEmbedded.name);
