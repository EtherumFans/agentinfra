import { readFileSync } from 'node:fs';

import { describe, expect, it } from 'vitest';


describe('API Client Agent and purpose delegation contract', () => {
  it('collects, sends, and displays server-owned delegation grants', () => {
    const page = readFileSync(
      new URL('../APIClientsPage.tsx', import.meta.url),
      'utf8',
    );
    const api = readFileSync(
      new URL('../../services/api.ts', import.meta.url),
      'utf8',
    );

    expect(page).toContain('newAgentIds');
    expect(page).toContain('newPurposes');
    expect(page).toContain('运行默认拒绝');
    expect(page).toContain('c.allowed_agent_ids');
    expect(page).toContain('c.allowed_purposes');
    expect(api).toContain('allowed_agent_ids: allowedAgentIds.join');
    expect(api).toContain('allowed_purposes: allowedPurposes.join');
    expect(api).toContain('/delegation`');
  });
});
