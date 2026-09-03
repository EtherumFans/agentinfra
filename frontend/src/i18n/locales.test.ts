/**
 * locales.test.ts — i18n key parity test (C10).
 *
 * Enforces:
 *   1. Every key in zh-CN has a matching key in en-US (and vice versa).
 *   2. No key value is empty in either locale.
 *   3. The C10 additions (diagnosisNumber, topKClickHint,
 *      extractedDiagnosesCount, noDiseaseName, confidencePercent,
 *      positionRange) are present in both locales.
 *   4. Placeholder sets in interpolation templates match across locales.
 */
import { describe, it, expect } from 'vitest';

import { locales } from './locales';

const zhCN = locales['zh-CN'];
const enUS = locales['en-US'];

const placeholders = (s: string): string[] =>
  Array.from(s.matchAll(/\{\{(\w+)\}\}/g)).map((m) => m[1]).sort();

describe('i18n locale parity', () => {
  it('has identical key sets in zh-CN and en-US', () => {
    const zhKeys = Object.keys(zhCN).sort();
    const enKeys = Object.keys(enUS).sort();
    expect(zhKeys).toEqual(enKeys);
  });

  it('has no empty values in zh-CN', () => {
    for (const [k, v] of Object.entries(zhCN)) {
      expect(v, `zh-CN:${k}`).toBeTruthy();
      expect(v.trim(), `zh-CN:${k}`).not.toBe('');
    }
  });

  it('has no empty values in en-US', () => {
    for (const [k, v] of Object.entries(enUS)) {
      expect(v, `en-US:${k}`).toBeTruthy();
      expect(v.trim(), `en-US:${k}`).not.toBe('');
    }
  });

  it('has all 6 C10 keys in both locales', () => {
    const c10Keys = [
      'diagnosisNumber',
      'topKClickHint',
      'extractedDiagnosesCount',
      'noDiseaseName',
      'confidencePercent',
      'positionRange',
    ];
    for (const k of c10Keys) {
      expect(zhCN, `zh-CN missing ${k}`).toHaveProperty(k);
      expect(enUS, `en-US missing ${k}`).toHaveProperty(k);
    }
  });

  it('C10 placeholder sets match across locales', () => {
    const c10Keys = [
      'diagnosisNumber',
      'topKClickHint',
      'extractedDiagnosesCount',
      'noDiseaseName',
      'confidencePercent',
      'positionRange',
    ];
    for (const k of c10Keys) {
      const zh = placeholders(zhCN[k as keyof typeof zhCN]);
      const en = placeholders(enUS[k as keyof typeof enUS]);
      expect(en, `placeholder mismatch for ${k}`).toEqual(zh);
    }
  });

  it('all {{ }} placeholders are balanced', () => {
    const check = (locale: string, dict: Record<string, string>) => {
      for (const [k, v] of Object.entries(dict)) {
        const opens = (v.match(/\{\{/g) || []).length;
        const closes = (v.match(/\}\}/g) || []).length;
        expect(opens, `${locale}:${k} opens`).toBe(closes);
      }
    };
    check('zh-CN', zhCN as unknown as Record<string, string>);
    check('en-US', enUS as unknown as Record<string, string>);
  });

  it('diagnosisNumber template includes {{n}}', () => {
    expect(placeholders(zhCN.diagnosisNumber)).toContain('n');
    expect(placeholders(enUS.diagnosisNumber)).toContain('n');
  });

  it('topKClickHint template includes {{k}}', () => {
    expect(placeholders(zhCN.topKClickHint)).toContain('k');
    expect(placeholders(enUS.topKClickHint)).toContain('k');
  });

  it('extractedDiagnosesCount template includes {{n}}', () => {
    expect(placeholders(zhCN.extractedDiagnosesCount)).toContain('n');
    expect(placeholders(enUS.extractedDiagnosesCount)).toContain('n');
  });
});
