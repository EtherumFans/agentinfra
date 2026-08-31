import fs from 'fs';
import path from 'path';

import { describe, expect, it } from 'vitest';


const ROOT = path.resolve(__dirname, '..', '..', '..', '..');
const page = fs.readFileSync(path.join(ROOT, 'frontend/src/pages/BillingPage.tsx'), 'utf-8');
const api = fs.readFileSync(path.join(ROOT, 'frontend/src/services/api.ts'), 'utf-8');


describe('development Agent Run billing UI contract', () => {
  it('labels the ledger as a local simulation without fake payment claims', () => {
    expect(page).toContain('当前为本地开发账本模拟');
    expect(page).toContain('不连接支付机构');
    expect(page).toContain('尚未接入真实支付机构；此功能不可用');
  });

  it('uses the authenticated stale-reservation reconciliation endpoint', () => {
    expect(api).toContain("'/billing/run-settlements/reconcile-stale'");
    expect(page).toContain('billingApi.reconcileStaleRunSettlements(3600)');
    expect(page).toContain('结算中记录只转为可重试，不免除成本');
    expect(page).toContain('result.data.marked_retryable');
  });

  it('keeps released and failed settlement states visibly distinct', () => {
    expect(page).toContain("item.status === 'RELEASED'");
    expect(page).toContain("item.status === 'SETTLEMENT_FAILED'");
  });
});
