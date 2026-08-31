import fs from 'fs';
import path from 'path';

import { describe, expect, it } from 'vitest';

const REPO_ROOT = path.resolve(__dirname, '..', '..', '..', '..');
const RUNTIME_API_PATH = path.join(
  REPO_ROOT,
  'frontend',
  'src',
  'services',
  'runtimeApi.ts',
);
const AGENT_DETAIL_PATH = path.join(
  REPO_ROOT,
  'frontend',
  'src',
  'pages',
  'AgentDetailPage.tsx',
);

describe('Agent Hub A2A streaming contract', () => {
  it('uses the authenticated A2A message/stream SSE transport', () => {
    const source = fs.readFileSync(RUNTIME_API_PATH, 'utf-8');

    expect(source).toContain('/v1/message:stream');
    expect(source).toContain("method: 'message/stream'");
    expect(source).toContain("'A2A-Protocol-Version': '0.3'");
    expect(source).toContain("response.body.getReader()");
    expect(source).toContain("'data-status-update'");
    expect(source).toContain("'text-delta'");
    expect(source).toContain("'data-json'");
    expect(source).toContain("'data-provider-progress'");
    expect(source).toContain("'data-tool-call-delta'");
    expect(source).toContain("'data-provider-usage'");
    expect(source).toContain('signal: handlers.signal');
    expect(source).toContain('message.contextId = handlers.context_id');
  });

  it('keeps the server context id across turns and aborts stale streams', () => {
    const source = fs.readFileSync(AGENT_DETAIL_PATH, 'utf-8');

    expect(source).toContain('runtimeAgentApi.agentStream');
    expect(source).toContain('signal: abortController.signal');
    expect(source).toContain('context_id: activeContextRef.current || undefined');
    expect(source).toContain('activeContextRef.current = resp.context_id');
    expect(source).toContain('onProviderProgress:');
    expect(source).toContain('onToolEvent:');
    expect(source).toContain('activeContextRef.current = \'\'');
  });
});
