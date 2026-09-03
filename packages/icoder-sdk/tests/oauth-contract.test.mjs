import assert from 'node:assert/strict';
import test from 'node:test';

import axios from 'axios';

import iCoDer, { iCoDerClient } from '../dist/index.js';

function ok(config, data) {
  return {
    data,
    status: 200,
    statusText: 'OK',
    headers: {},
    config,
    request: {},
  };
}

test('OAuthResource sends RFC 6749 form data for token and client creation', async () => {
  const sdk = new iCoDer({
    baseURL: 'https://api.cn.icoder.test',
    auth: { accessToken: 'console-token' },
  });
  const calls = [];
  sdk.client.http.defaults.adapter = async (config) => {
    calls.push(config);
    return ok(config, config.url === '/api/oauth/token'
      ? { access_token: 'tenant-token', token_type: 'Bearer', expires_in: 300 }
      : { client_id: 'client-1', client_secret: 'secret-1' });
  };

  const token = await sdk.oauth.getToken('client id/+', 'secret &=');
  const created = await sdk.oauth.createClient(
    '临床 app',
    'safe description',
    'agents:run',
    { allowedAgentIds: ['diagnosis-extractor'], allowedPurposes: ['treatment'] },
  );
  await sdk.oauth.updateDelegation(
    'client-1', ['diagnosis-extractor'], ['treatment'],
  );

  assert.equal(token.access_token, 'tenant-token');
  assert.equal(created.client_id, 'client-1');
  assert.equal(calls[0].url, '/api/oauth/token');
  assert.match(calls[0].headers['Content-Type'], /^application\/x-www-form-urlencoded/);
  assert.equal(
    String(calls[0].data),
    'grant_type=client_credentials&client_id=client+id%2F%2B&client_secret=secret+%26%3D&scope=api%3Aread+api%3Awrite',
  );
  assert.equal(calls[1].url, '/api/oauth/clients');
  assert.match(calls[1].headers['Content-Type'], /^application\/x-www-form-urlencoded/);
  assert.match(String(calls[1].data), /name=%E4%B8%B4%E5%BA%8A\+app/);
  assert.match(String(calls[1].data), /allowed_agent_ids=diagnosis-extractor/);
  assert.match(String(calls[1].data), /allowed_purposes=treatment/);
  assert.equal(calls[2].url, '/api/clients/client-1/delegation');
  assert.deepEqual(JSON.parse(calls[2].data), {
    allowed_agent_ids: ['diagnosis-extractor'],
    allowed_purposes: ['treatment'],
  });
});

test('low-level authenticate uses form data and accepts client-credential token shape', async () => {
  const originalAdapter = axios.defaults.adapter;
  let captured;
  axios.defaults.adapter = async (config) => {
    captured = config;
    return ok(config, {
      access_token: 'tenant-token',
      token_type: 'Bearer',
      expires_in: 300,
      scope: 'api:read api:write',
    });
  };
  try {
    const client = new iCoDerClient({
      baseURL: 'https://api.cn.icoder.test',
      auth: { accessToken: '' },
    });
    const token = await client.authenticate('client-id', 'client-secret');
    assert.equal(token.access_token, 'tenant-token');
  } finally {
    axios.defaults.adapter = originalAdapter;
  }

  assert.equal(captured.url, 'https://api.cn.icoder.test/api/oauth/token');
  assert.match(captured.headers['Content-Type'], /^application\/x-www-form-urlencoded/);
  assert.match(String(captured.data), /grant_type=client_credentials/);
});
