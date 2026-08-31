import fs from 'fs';
import path from 'path';

import { describe, expect, it } from 'vitest';

const REPO_ROOT = path.resolve(__dirname, '..', '..', '..', '..');
const FACTS_PAGE = path.join(REPO_ROOT, 'frontend', 'src', 'pages', 'FactExtractionPage.tsx');
const TEXT_PAGE = path.join(REPO_ROOT, 'frontend', 'src', 'pages', 'TextGenerationPage.tsx');
const API_PATH = path.join(REPO_ROOT, 'frontend', 'src', 'services', 'api.ts');

describe('Facts and Guided Documents truthfulness contract', () => {
  it('uses the live v2 facts contract and only reports server usage', () => {
    const page = fs.readFileSync(FACTS_PAGE, 'utf-8');
    const api = fs.readFileSync(API_PATH, 'utf-8');

    expect(api).toContain("api.post<FactExtractResponse>('/v2/tools/extract-facts'");
    expect(api).toContain("context: [{ type: 'text', text }]");
    expect(page).toContain('data.usageInfo.creditsConsumed');
    expect(page).not.toContain('credits: 0.000001');
    expect(page).not.toContain('credits_consumed ||');
    expect(page).not.toContain('/facts/extract');
  });

  it('generates through zero-retention Guided Documents without client-bypass claims', () => {
    const page = fs.readFileSync(TEXT_PAGE, 'utf-8');
    const api = fs.readFileSync(API_PATH, 'utf-8');

    expect(api).toContain("api.post<GuidedDocumentResponse>('/v2/tools/guided-documents'");
    expect(api).toContain("'X-Corti-Retention-Policy': 'none'");
    expect(page).toContain("response.headers['x-corti-retention-policy'] !== 'acknowledged'");
    expect(page).toContain('response.data.usageInfo.creditsConsumed');
    expect(page).not.toContain('credits: 0.000001');
    expect(page).not.toContain('Text Generation API has been deprecated');
    expect(page).not.toContain('跳过安全检查');
  });
});
