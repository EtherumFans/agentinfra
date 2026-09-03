import { describe, expect, it } from 'vitest';

import {
  DEVELOPER_API_ENDPOINTS,
  buildCredentialEnv,
  buildMedicalCodingSnippets,
  buildQuickstartSdkSnippets,
} from '../developerSdkCode';

describe('developer SDK copy surfaces', () => {
  it('uses real OAuth and Facts APIs without embedding a client secret', () => {
    const snippets = buildQuickstartSdkSnippets('https://api.cn.icoder.cloud/');
    const all = Object.values(snippets).join('\n');

    expect(snippets.javascript).toContain('authClient.authenticate(clientId, clientSecret)');
    expect(snippets.javascript).toContain('icoder.facts.extract({');
    expect(snippets.javascript).toContain('context: [{ type: "text"');
    expect(snippets.javascript).toContain('facts.usageInfo.creditsConsumed');
    expect(snippets.dotnet).toContain('AuthenticateClientCredentialsAsync(clientId, clientSecret)');
    expect(snippets.dotnet).toContain('Facts.ExtractAsync(new FactExtractionRequest');
    expect(all).not.toContain('client.oauth.getToken');
    expect(all).not.toContain('new ClientCredentials');
    expect(all).not.toContain('DiagnosisFacts');
    expect(all).not.toContain('ics_');
  });

  it('keeps the one-time secret only in the explicit environment export', () => {
    const env = buildCredentialEnv(
      'https://api.cn.icoder.cloud/',
      'client-1',
      'sentinel-secret-value',
    );
    expect(env).toContain('ICODER_BASE_URL=https://api.cn.icoder.cloud');
    expect(env).toContain('ICODER_CLIENT_ID=client-1');
    expect(env).toContain('ICODER_CLIENT_SECRET=sentinel-secret-value');
    expect(buildQuickstartSdkSnippets('https://api.cn.icoder.cloud').javascript)
      .not.toContain('sentinel-secret-value');
  });

  it('keeps Playground samples aligned to Facts, A2A and Coding contracts', () => {
    const facts = DEVELOPER_API_ENDPOINTS.find(item => item.key === 'facts-extract')!;
    expect(JSON.parse(facts.sampleBody!).context).toHaveLength(1);
    const a2a = DEVELOPER_API_ENDPOINTS.find(item => item.key === 'agents-run')!;
    expect(a2a.headers?.['A2A-Protocol-Version']).toBe('0.3');
    expect(JSON.parse(a2a.sampleBody!).params.message.parts[0].kind).toBe('text');
    const coding = DEVELOPER_API_ENDPOINTS.find(item => item.key === 'coding')!;
    expect(coding.path).toBe('/api/v1/coding/predict');
    expect(JSON.parse(coding.sampleBody!).coding_systems).toEqual(['icd10cn', 'icd9cm3']);
    expect(JSON.parse(coding.sampleBody!).filter).toEqual({
      include: [], exclude: [], expand: true,
    });
  });

  it('uses the shipped Medical Coding resource and request shape', () => {
    const snippets = buildMedicalCodingSnippets({
      baseURL: 'https://api.cn.icoder.cloud',
      text: '去标识病历',
      mode: 'corti_like_fast',
      codingSystems: ['icd10cn', 'icd9cm3'],
      includeCodes: ['E11'],
      excludeCodes: ['E11.0'],
      expand: false,
    });
    expect(snippets.javascript).toContain('icoder.medicalCoding.predict(');
    expect(snippets.javascript).not.toContain('client.codes.predict');
    const json = JSON.parse(snippets.json);
    expect(json.endpoint).toBe('/api/v1/coding/predict');
    expect(json.body).toMatchObject({
      text: '去标识病历',
      mode: 'corti_like_fast',
      coding_systems: ['icd10cn', 'icd9cm3'],
      filter: {
        include: ['E11'],
        exclude: ['E11.0'],
        expand: false,
      },
    });
  });
});
