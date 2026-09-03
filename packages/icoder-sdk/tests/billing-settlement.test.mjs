import assert from 'node:assert/strict';
import test from 'node:test';

import iCoDer from '../dist/index.js';


test('BillingResource exposes reservation-aware balance and settlement retry', async () => {
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test',
    auth: { accessToken: 'test-token' },
  });
  const calls = [];
  sdk.client.http.defaults.adapter = async (config) => {
    calls.push({ method: config.method, url: config.url, params: config.params });
    let data;
    if (config.url === '/api/billing/balance') {
      data = { balance: 1, reserved: 0.05, available: 0.95, currency: 'CNY' };
    } else if (config.url === '/api/billing/run-settlements') {
      data = {
        items: [{
          run_id: 'run/id', status: 'SETTLEMENT_FAILED',
          reserved_amount: 0.05, settled_amount: 2, currency: 'CNY',
        }],
        total: 1,
        simulation: true,
      };
    } else if (config.url === '/api/billing/run-settlements/reconcile-stale') {
      data = {
        simulation: true, released: 1, marked_retryable: 1, skipped_active: 1,
        inspected: 3, older_than_seconds: 3600,
      };
    } else {
      data = { status: 'SETTLED', settled_amount: 2, currency: 'CNY' };
    }
    return {
      data, status: 200, statusText: 'OK', headers: {}, config, request: {},
    };
  };

  const balance = await sdk.billing.balance();
  const settlements = await sdk.billing.runSettlements(7);
  const retried = await sdk.billing.retryRunSettlement('run/id');
  const reconciled = await sdk.billing.reconcileStaleRunSettlements(3600);

  assert.equal(balance.available, 0.95);
  assert.equal(settlements.items[0].status, 'SETTLEMENT_FAILED');
  assert.equal(retried.status, 'SETTLED');
  assert.equal(reconciled.released, 1);
  assert.deepEqual(calls, [
    { method: 'get', url: '/api/billing/balance', params: undefined },
    { method: 'get', url: '/api/billing/run-settlements', params: { limit: 7 } },
    { method: 'post', url: '/api/billing/run-settlements/run%2Fid/retry', params: undefined },
    { method: 'post', url: '/api/billing/run-settlements/reconcile-stale', params: { older_than_seconds: 3600 } },
  ]);
});
