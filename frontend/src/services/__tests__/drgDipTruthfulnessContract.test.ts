import fs from 'fs';
import path from 'path';

import { describe, expect, it } from 'vitest';

const REPO_ROOT = path.resolve(__dirname, '..', '..', '..', '..');
const LOCALES_PATH = path.join(REPO_ROOT, 'frontend', 'src', 'i18n', 'locales.ts');
const EMBEDDED_PATH = path.join(
  REPO_ROOT,
  'packages',
  'icoder-embedded',
  'src',
  'icoder-assistant.ts',
);

describe('DRG/DIP non-authoritative truthfulness contract', () => {
  it('does not present the development heuristic as payment analysis', () => {
    const locales = fs.readFileSync(LOCALES_PATH, 'utf-8');
    const embedded = fs.readFileSync(EMBEDDED_PATH, 'utf-8');

    expect(locales).not.toContain('DRG/DIP 支付分析');
    expect(locales).not.toContain('DRG/DIP payment analysis');
    expect(locales).toContain('DRG/DIP 风险复核（非结算）');
    expect(locales).toContain('no official group, weight, score, or payment result');

    expect(embedded).toContain('DRG/DIP 风险复核');
    expect(embedded).toContain('不要预测官方分组、权重、分值或支付金额');
    expect(embedded).not.toContain('编码对 DRG 分组和医保支付的影响');
  });
});
