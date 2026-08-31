import assert from 'node:assert/strict';
import test from 'node:test';

import iCoDer from '../dist/index.js';


test('MedicalCodingResource uses predict and configuration-backed pricing paths', async () => {
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test',
    auth: { accessToken: 'test-token' },
  });
  const calls = [];
  sdk.client.http.defaults.adapter = async (config) => {
    calls.push(config);
    return {
      data: config.url.endsWith('/pricing')
        ? {
            input_chars: 600,
            runtime_mode: 'corti_like_fast',
            currency: 'CNY',
            estimated_cost_min: 0.0001,
            estimated_cost_max: 0.0009,
            billing_authoritative: false,
          }
        : { codes: [], summary: 'ok', error: false },
      status: 200,
      statusText: 'OK',
      headers: {},
      config,
      request: {},
    };
  };

  const estimate = await sdk.medicalCoding.estimateCost(600);
  const prediction = await sdk.medicalCoding.predict({
    text: '去标识病历',
    coding_systems: ['icd10cn', 'icd9cm3'],
    filter: { include: [' E11 ', 'e11'], exclude: ['E11.0'], expand: false },
  });

  assert.equal(calls[0].url, '/api/v1/coding/pricing');
  assert.deepEqual(calls[0].params, {
    input_chars: 600,
    mode: 'corti_like_fast',
  });
  assert.equal(estimate.billing_authoritative, false);
  assert.equal(calls[1].url, '/api/v1/coding/predict');
  assert.deepEqual(JSON.parse(calls[1].data).filter, {
    include: ['E11'],
    exclude: ['E11.0'],
    expand: false,
  });
  assert.deepEqual(JSON.parse(calls[1].data).coding_systems, [
    'icd10cn', 'icd9cm3',
  ]);
  assert.equal(prediction.summary, 'ok');
});


test('MedicalCodingResource rejects invalid input length before transport', async () => {
  const sdk = new iCoDer({ baseURL: 'https://api.cn.icoder.test' });
  await assert.rejects(
    () => sdk.medicalCoding.estimateCost(16001),
    /between 0 and 16000/,
  );
  await assert.rejects(
    () => sdk.medicalCoding.predict({ text: '   ' }),
    /between 1 and 16000/,
  );
  await assert.rejects(
    () => sdk.medicalCoding.predict({
      text: '去标识病历',
      filter: { include: [''] },
    }),
    /between 1 and 64 printable/,
  );
  await assert.rejects(
    () => sdk.medicalCoding.predict({
      text: '去标识病历',
      coding_systems: ['icd10cn', 'icd10cn'],
    }),
    /must not contain duplicates/,
  );
});
