import fs from 'fs';
import path from 'path';

import { describe, expect, it } from 'vitest';

const REPO_ROOT = path.resolve(__dirname, '..', '..', '..', '..');
const PAGE_PATH = path.join(
  REPO_ROOT,
  'frontend',
  'src',
  'pages',
  'MedicalCodingPage.tsx',
);
const DOCS_PATH = path.join(
  REPO_ROOT,
  'frontend',
  'src',
  'pages',
  'DocsPage.tsx',
);

describe('Medical Coding pricing and developer path contract', () => {
  it('uses the authenticated server-side pricing range instead of a fake per-character rate', () => {
    const source = fs.readFileSync(PAGE_PATH, 'utf-8');

    expect(source).toContain('codingApi.estimateCost');
    expect(source).toContain('estimated_cost_min');
    expect(source).toContain('estimated_cost_max');
    expect(source).toContain('billing quote');
    expect(source).not.toContain('charCount * 0.00001');
    expect(source).not.toContain('(data.latency_ms / 1000) * 0.02');
    expect(source).toContain('Number(data.cost?.amount ?? 0)');
    expect(source).not.toContain('placeholder rate');
    expect(source).toContain('launch-candidate-banner');
    expect(source).not.toContain('mvp-banner');
  });

  it('documents the current coding and authenticated A2A streaming routes', () => {
    const source = fs.readFileSync(DOCS_PATH, 'utf-8');

    expect(source).toContain('/api/v1/coding/predict');
    expect(source).toContain('/api/icoder/agents/{agent_id}/v1/message:stream');
    expect(source).not.toContain("path: '/api/agents'");
  });

  it('wires the visible Corti code filter and removes the unsupported confidence control', () => {
    const source = fs.readFileSync(PAGE_PATH, 'utf-8');

    expect(source).toContain('filter: {');
    expect(source).toContain('include: includeCodes');
    expect(source).toContain('exclude: excludeCodes');
    expect(source).toContain('expand: expandResults');
    expect(source).toContain('selectedSystems.length < 1');
    expect(source).toContain("prev.includes(sys) || prev.length >= 2");
    expect(source).toContain('coding_systems: selectedSystems');
    expect(source).not.toContain('confidenceThreshold');
    expect(source).not.toContain('setConfidenceThreshold');
  });
});
