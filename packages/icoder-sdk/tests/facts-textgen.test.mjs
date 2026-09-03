import assert from 'node:assert/strict';
import test from 'node:test';

import iCoDer from '../dist/index.js';


test('FactsResource uses the Corti-compatible v2 request and server usage', async () => {
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test',
    auth: { accessToken: 'test-token' },
  });
  let call;
  sdk.client.http.defaults.adapter = async (config) => {
    call = config;
    return {
      data: {
        facts: [{ group: 'diagnosis', text: '高血压', value: '高血压' }],
        outputLanguage: 'zh-CN',
        usageInfo: { creditsConsumed: 0.011 },
      },
      status: 200,
      statusText: 'OK',
      headers: {},
      config,
      request: {},
    };
  };

  const result = await sdk.facts.extract('诊断：高血压。');
  assert.equal(call.url, '/api/v2/tools/extract-facts');
  assert.deepEqual(JSON.parse(call.data), {
    context: [{ type: 'text', text: '诊断：高血压。' }],
    outputLanguage: 'zh-CN',
  });
  assert.equal(result.usageInfo.creditsConsumed, 0.011);
  assert.equal(result.facts[0].group, 'diagnosis');
});


test('TextGenResource delegates to zero-retention Guided Documents', async () => {
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test',
    auth: { accessToken: 'test-token' },
  });
  let call;
  sdk.client.http.defaults.adapter = async (config) => {
    call = config;
    return {
      data: {
        document: { stringDocument: { 出院小结: '生成结果' } },
        usageInfo: { creditsConsumed: 0.007 },
      },
      status: 200,
      statusText: 'OK',
      headers: { 'x-corti-retention-policy': 'acknowledged' },
      config,
      request: {},
    };
  };

  const result = await sdk.textGen.generate('去标识病历', {
    template: '出院小结',
    outputLanguage: 'zh-CN',
  });
  assert.equal(call.url, '/api/v2/tools/guided-documents');
  assert.equal(call.headers['X-Corti-Retention-Policy'], 'none');
  const body = JSON.parse(call.data);
  assert.equal(body.context[0].text, '去标识病历');
  assert.equal(body.dynamicTemplate.generation.sections[0].outputSchema.type, 'string');
  assert.deepEqual(result, { output: '生成结果', credits_consumed: 0.007 });
  await assert.rejects(
    () => sdk.textGen.generate('去标识病历', { docName: '患者姓名' }),
    /docName.*not supported/,
  );
});


test('TextGenResource rejects unacknowledged zero-retention responses', async () => {
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test',
    auth: { accessToken: 'test-token' },
  });
  sdk.client.http.defaults.adapter = async (config) => ({
    data: { document: { stringDocument: { note: 'unsafe to display' } }, usageInfo: { creditsConsumed: 0 } },
    status: 200,
    statusText: 'OK',
    headers: {},
    config,
    request: {},
  });
  await assert.rejects(
    () => sdk.textGen.generate('去标识病历'),
    /zero-retention policy/,
  );
});
