import fs from 'fs';
import path from 'path';

import { describe, expect, it } from 'vitest';

const REPO_ROOT = path.resolve(__dirname, '..', '..', '..', '..');
const PAGE_PATH = path.join(REPO_ROOT, 'frontend', 'src', 'pages', 'SpeechToTextPage.tsx');
const DOCS_PATH = path.join(REPO_ROOT, 'frontend', 'src', 'pages', 'DocsPage.tsx');
const LOCALES_PATH = path.join(REPO_ROOT, 'frontend', 'src', 'i18n', 'locales.ts');

describe('Speech To Text launch-candidate truthfulness contract', () => {
  it('authenticates the realtime socket and never invents credits', () => {
    const source = fs.readFileSync(PAGE_PATH, 'utf-8');

    expect(source).toContain('speech-to-text?token=${encodeURIComponent(accessToken)}');
    expect(source).toContain("usage: 'not-reported'");
    expect(source).toContain('creditsConsumed={0}');
    expect(source).not.toContain('credits: 0.000001');
    expect(source).not.toContain('setSttCredits');
  });

  it('states the verified server language and uses real SDK entry points', () => {
    const page = fs.readFileSync(PAGE_PATH, 'utf-8');
    const docs = fs.readFileSync(DOCS_PATH, 'utf-8');
    const locales = fs.readFileSync(LOCALES_PATH, 'utf-8');

    expect(page).toContain('Medvoice 已验证：zh-CN');
    expect(page).toContain('client.speechToText.createTranscript');
    expect(page).toContain('client.SpeechToText.CreateTranscriptAsync');
    expect(page).not.toContain('icoder_speech');
    expect(page).not.toContain('iCoDer.Speech');
    expect(docs).not.toContain('中英混合');
    expect(locales).not.toContain('bilingual (ZH/EN)');
  });
});
