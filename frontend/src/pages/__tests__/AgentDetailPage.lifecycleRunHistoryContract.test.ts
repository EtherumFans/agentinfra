// @vitest-environment node

import fs from 'fs';
import path from 'path';

import { describe, expect, it } from 'vitest';

const REPO_ROOT = path.resolve(__dirname, '..', '..', '..', '..');
const PAGE_PATH = path.join(REPO_ROOT, 'frontend', 'src', 'pages', 'AgentDetailPage.tsx');
const API_PATH = path.join(REPO_ROOT, 'frontend', 'src', 'services', 'api.ts');

describe('Agent detail lifecycle and run-history contract', () => {
  it('has no user-facing fake gold-standard evaluation action', () => {
    const page = fs.readFileSync(PAGE_PATH, 'utf-8');

    expect(page).not.toContain('runEvaluation');
    expect(page).not.toContain('evalResult');
    expect(page).not.toContain('Agent evaluation endpoint removed');
    expect(page).not.toContain('DEFERRED');
    expect(page).not.toContain('primary_dx_accuracy');
    expect(page).not.toContain('primary_proc_accuracy');
  });

  it('shows persisted runtime history and an honest empty state', () => {
    const page = fs.readFileSync(PAGE_PATH, 'utf-8');

    expect(page).toContain('runtimeAgentApi.getRunHistory');
    expect(page).toContain('runHistory.map');
    expect(page).toContain('agentRunHistoryEmpty');
    expect(page).toContain('agentRunHistoryRefresh');
    expect(page).toContain('setRunHistoryError(message)');
    expect(page).toContain('role="alert"');
    expect(page).not.toContain('catch { /* silently fail */ }');
  });

  it('uses explicit project Agent lifecycle endpoints and disables runs fail closed', () => {
    const page = fs.readFileSync(PAGE_PATH, 'utf-8');
    const api = fs.readFileSync(API_PATH, 'utf-8');

    expect(api).toContain('/rest/v1/agent_definitions/${id}/publish');
    expect(api).toContain('/rest/v1/agent_definitions/${id}/archive');
    expect(api).toContain('/rest/v1/agent_definitions/${id}/restore');
    expect(page).toContain("handleLifecycleAction('publish')");
    expect(page).toContain("handleLifecycleAction('archive')");
    expect(page).toContain("handleLifecycleAction('restore')");
    expect(page).toContain('agent.lifecycle.run_action_enabled !== true');
    expect(page).toContain('disabled={runActionDisabled}');
  });

  it('does not misrepresent project Agents as separately installed registry entries', () => {
    const page = fs.readFileSync(PAGE_PATH, 'utf-8');

    expect(page).toContain('setAgentRef(a.id)');
    expect(page).toContain('setRuntimeStatus(a.lifecycle.state');
    expect(page).toContain('!dynamicProjectAgent && <button');
    expect(page).not.toContain('¥0.000000');
  });
});
