import { describe, expect, it } from 'vitest';

import { buildAgentRunSnippets } from '../agentSdkCode';

describe('buildAgentRunSnippets', () => {
  it('uses the shipped JavaScript and Python SDK Agent Run APIs', () => {
    const snippets = buildAgentRunSnippets({
      agentId: 'database-id',
      agentRef: 'icoder/note-completeness-agent',
      baseURL: 'https://api.cn.icoder.cloud/',
      runtimeMode: 'corti_like_fast',
    });

    expect(snippets.javascript).toContain('import iCoDer from "@icoder/sdk";');
    expect(snippets.javascript).toContain('icoder.runs.runText(');
    expect(snippets.javascript).toContain('auth: { accessToken: process.env.ICODER_ACCESS_TOKEN }');
    expect(snippets.python).toContain('from icoder_sdk import iCoDerClient, iCoDerConfig');
    expect(snippets.python).toContain('client.runs.run_text(');
    expect(snippets.curl).toContain('/api/v1/agents/database-id/run');
    expect(snippets.curl).toContain('Bearer $ICODER_ACCESS_TOKEN');

    const json = JSON.parse(snippets.json);
    expect(json.endpoint).toBe('/api/v1/agents/database-id/run');
    expect(json.body.runtime_mode).toBe('corti_like_fast');
    expect(json.body.include_trace).toBe(true);
    expect(json.body.include_evidence).toBe(true);
  });

  it('falls back from a full official ref to its URL-safe short id', () => {
    const snippets = buildAgentRunSnippets({
      agentRef: 'icoder/note-completeness-agent@2.0.0',
      baseURL: 'http://127.0.0.1:8000',
    });
    const all = Object.values(snippets).join('\n');

    expect(snippets.curl).toContain('/api/v1/agents/note-completeness-agent/run');
    expect(all).not.toContain('client.agents.run');
    expect(all).not.toContain('client.agent(');
    expect(all).not.toContain('from icoder import');
    expect(all).not.toContain('apiKey:');
    expect(all).not.toContain('/api/icoder/agents/note-completeness-agent/v1/message:send');
  });
});
