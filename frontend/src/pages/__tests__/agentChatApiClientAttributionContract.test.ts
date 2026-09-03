import fs from 'fs';
import path from 'path';

import { describe, expect, it } from 'vitest';


const SOURCE = fs.readFileSync(
  path.resolve(__dirname, '..', 'AgentChatPage.tsx'),
  'utf-8',
);
const AGENTS_SOURCE = fs.readFileSync(
  path.resolve(__dirname, '..', 'AgentsPage.tsx'),
  'utf-8',
);
const DETAIL_SOURCE = fs.readFileSync(
  path.resolve(__dirname, '..', 'AgentDetailPage.tsx'),
  'utf-8',
);


describe('Agent Chat API Client attribution boundary', () => {
  it('does not let the browser self-assert a machine identity', () => {
    expect(SOURCE).not.toContain('api_client_id:');
    expect(SOURCE).not.toContain('selectedApiClient');
  });

  it('does not render an API Client attribution selector', () => {
    for (const page of [SOURCE, AGENTS_SOURCE, DETAIL_SOURCE]) {
      expect(page).not.toContain('oauthApi.list()');
      expect(page).not.toContain('selectedApiClient');
    }
  });

  it('runs and loads history by project Agent identity, never the source ref', () => {
    expect(SOURCE).toContain('const runtimeAgentId = effectiveAgentId;');
    expect(SOURCE).toContain('const sourceRuntimeAgentId = (() =>');
    expect(SOURCE).toContain('runAgentUnified(runtimeAgentId');
    expect(SOURCE).toContain('getRunHistory(runtimeAgentId');
    expect(SOURCE).not.toContain('const runtimeAgentId = (() =>');
  });
});
