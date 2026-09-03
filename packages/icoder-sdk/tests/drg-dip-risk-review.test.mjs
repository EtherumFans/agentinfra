import assert from 'node:assert/strict';
import test from 'node:test';

import iCoDer from '../dist/index.js';

const governance = {
  asset_id: 'cn.drg_dip.risk_heuristics',
  version: '1.0.0-development',
  asset_type: 'risk_review_rule_pack',
  jurisdiction: 'CN_GENERIC_DEVELOPMENT',
  authority_status: 'experimental_unverified',
  license_status: 'external_review_required',
  effective_from: null,
  effective_to: null,
  billing_authoritative: false,
  manual_review_required: true,
  use_restriction: 'development_risk_review_only_not_for_grouping_payment_or_settlement',
};

function clientWith(data, capture = {}) {
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test',
    auth: { accessToken: 'test-token' },
  });
  sdk.client.http.defaults.adapter = async (config) => {
    capture.config = config;
    return { data, status: 200, statusText: 'OK', headers: {}, config, request: {} };
  };
  return sdk;
}

test('DRG/DIP resource exposes authenticated development governance', async () => {
  const capture = {};
  const sdk = clientWith(governance, capture);
  const result = await sdk.drgDipRiskReview.getGovernance();
  assert.equal(capture.config.url, '/api/drg/governance');
  assert.equal(result.billing_authoritative, false);
  assert.equal(result.manual_review_required, true);
});

test('DRG/DIP analysis normalizes input and accepts only zero-payment candidates', async () => {
  const capture = {};
  const response = {
    primary_diagnosis: { code: 'I10', name: '', description: '', confidence: 1 },
    secondary_diagnoses: [], procedures: [],
    drg_impact: {
      predicted_drg: 'FR19', drg_name: 'candidate', mdc: 'MDCF', mdc_name: '',
      adrg: 'FR1', cc_level: '', grouping_method: 'medical', coverage: true,
      payment_weight: 0, payment_estimate_yuan: 0, billing_authoritative: false,
      result_status: 'experimental_candidate',
    },
    dip_impact: {
      dip_score: 0, dip_score_ceiling: 0, payment_estimate_yuan: 0,
      note: 'not available', billing_authoritative: false,
    },
    risks: [], recommendations: [], quality_flags: {}, governance,
    manual_review_required: true, review_conclusion: 'WARNING', confidence: 0.5,
    notes: 'development only', provider: 'drg-analyzer', model: 'development',
    is_mock: false, error: false, error_reason: '',
  };
  const sdk = clientWith(response, capture);
  const result = await sdk.drgDipRiskReview.analyze({ primary_diagnosis: { code: 'I10' } });
  assert.equal(capture.config.method, 'post');
  assert.equal(capture.config.url, '/api/drg/analyze');
  assert.deepEqual(JSON.parse(capture.config.data), {
    primary_diagnosis: { code: 'I10' }, secondary_diagnoses: [], procedures: [],
    patient_gender: '', patient_age: null,
  });
  assert.equal(result.drg_impact.payment_estimate_yuan, 0);
});

test('DRG/DIP resource fails closed on billing or no-review claims', async () => {
  const sdk = clientWith({ ...governance, billing_authoritative: true });
  await assert.rejects(
    () => sdk.drgDipRiskReview.getGovernance(),
    /development-only, manual-review contract/,
  );
});

test('DRG/DIP resource rejects invalid patient input before transport', async () => {
  const sdk = clientWith(governance);
  await assert.rejects(
    () => sdk.drgDipRiskReview.analyze({
      primary_diagnosis: { code: 'I10' }, patient_age: 151,
    }),
    /patient_age/,
  );
});
