// @vitest-environment jsdom
import React from 'react';
import { render, screen, waitFor, cleanup } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, expect, test, vi } from 'vitest';
import Notice, { useRuntimeReadiness } from './RuntimeReadinessNotice';
import { agentHubApi } from '../../services/agentHubApi';
vi.mock('../../store', () => ({ useAuthStore: (selector: any) => selector({currentOrgId:'org-test'}) }));
vi.mock('../../services/agentHubApi', () => ({agentHubApi:{listWithTenantReadiness:vi.fn()}}));
function Workbench() {
  const state=useRuntimeReadiness('clinical-documentation-improvement-agent');
  return <MemoryRouter><button disabled={!state.enabled}>运行</button><Notice state={state}/></MemoryRouter>;
}
afterEach(cleanup);
test('missing credentials disables execution and offers recovery', async () => {
  vi.mocked(agentHubApi.listWithTenantReadiness).mockResolvedValue({data:{agents:[{agent_id:'clinical-documentation-improvement-agent',runtime_readiness:{run_action_enabled:false,reason:'credential_unavailable'}}]}} as any);
  render(<Workbench/>);
  await screen.findByText('原因：credential_unavailable');
  expect((screen.getByRole('button',{name:'运行'}) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getByRole('link',{name:'查看模型配置'}).getAttribute('href')).toBe('/models');
});
test('verified configuration enables execution', async () => {
  vi.mocked(agentHubApi.listWithTenantReadiness).mockResolvedValue({data:{agents:[{agent_id:'clinical-documentation-improvement-agent',runtime_readiness:{run_action_enabled:true,reason:'configured'}}]}} as any);
  render(<Workbench/>);
  await waitFor(() => expect((screen.getByRole('button',{name:'运行'}) as HTMLButtonElement).disabled).toBe(false));
});
test('readiness failure stays disabled', async () => {
  vi.mocked(agentHubApi.listWithTenantReadiness).mockRejectedValue(new Error('offline'));
  render(<Workbench/>);
  await screen.findByText(/原因：无法读取运行配置/);
  expect((screen.getByRole('button',{name:'运行'}) as HTMLButtonElement).disabled).toBe(true);
});
