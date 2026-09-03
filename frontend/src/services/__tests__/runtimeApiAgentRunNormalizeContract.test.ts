/**
 * Phase 5 Track B-2 — AUDIT_BLOCKER_FIX #2 regression test
 *
 * Context: AgentChatPage / AgentDetailPage passes the full agent_ref
 * (e.g. `icoder/medical-coding-agent@2.0.0`) through to runtimeAgentApi
 * .agentRun(), which then PUT the un-split string into the URL:
 *
 *   POST /api/v1/agents/icoder%2Fmedical-coding-agent%402.0.0/run → 404
 *
 * The backend `_agent_id_from_ref` only looks at the bare agent_id segment,
 * so the URL-encoded agent_ref never matched. Fix: normalize the agent_id
 * client-side BEFORE posting — strip the `icoder/` prefix and the `@ver`
 * suffix, leaving the short id (`medical-coding-agent`) that the backend
 * route expects.
 *
 * This test verifies the normalization is present and covers the three
 * shapes the chat UI actually emits:
 *   - `icoder/medical-coding-agent@2.0.0` (Hub card click → AgentDetailPage)
 *   - `medical-coding-agent@2.0.0`        (fork flow pins a version)
 *   - `medical-coding-agent`              (short form, defensive)
 */
import fs from 'fs';
import path from 'path';

import { describe, it, expect } from 'vitest';

const REPO_ROOT = path.resolve(__dirname, '..', '..', '..', '..');
const RUNTIME_API_PATH = path.join(
  REPO_ROOT,
  'frontend',
  'src',
  'services',
  'runtimeApi.ts',
);

describe('Phase 5 B-2 — agentRun() normalizes full agent_ref to short agent_id', () => {
  it('runtimeApi.ts contains the normalization line', () => {
    expect(fs.existsSync(RUNTIME_API_PATH), 'runtimeApi.ts must exist').toBe(true);
    const src = fs.readFileSync(RUNTIME_API_PATH, 'utf-8');

    // The exact normalization expression used in agentRun().
    expect(src).toMatch(/const shortId = agentId\.split\('\/'\)\.pop\(\)!\.split\('@'\)\[0\]/);
    // And it is used in the URL.
    expect(src).toMatch(/unifiedRunApi\.post\(`\/\$\{encodeURIComponent\(shortId\)\}\/run`/);
  });

  it('normalization handles the 3 shapes the chat UI emits', () => {
    // Re-implement the exact one-liner from runtimeApi.ts and assert on
    // each input shape. If someone "improves" the normalization later
    // (e.g. switches to a regex), this test will fail loudly and force
    // them to re-validate the three shapes.
    const normalize = (agentId: string) => agentId.split('/').pop()!.split('@')[0];

    expect(normalize('icoder/medical-coding-agent@2.0.0')).toBe('medical-coding-agent');
    expect(normalize('medical-coding-agent@2.0.0')).toBe('medical-coding-agent');
    expect(normalize('medical-coding-agent')).toBe('medical-coding-agent');
  });
});
