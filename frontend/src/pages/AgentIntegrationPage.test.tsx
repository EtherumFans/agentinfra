// @vitest-environment jsdom
import React from 'react';
import { afterEach, expect, test, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import Page from './AgentIntegrationPage';
import api from '../services/api';
vi.mock('../services/api', () => ({default: {get:vi.fn(), post:vi.fn()}}));
vi.mock('../store', () => ({useAuthStore: (selector:any) => selector({currentOrgId:'one'})}));
afterEach(() => { cleanup(); vi.clearAllMocks(); });
const manifest = {agent_id:'doc',name:'文书助手',version:'1.0.1',configuration_digest:'a'.repeat(64),run_path:'/api/v1/agents/doc/run'};
function renderPage() {
  return render(<MemoryRouter initialEntries={['/agents/doc/integration']}><Routes><Route path="/agents/:agentId/integration" element={<Page/>}/></Routes></MemoryRouter>);
}
test('unpublished or inaccessible agent cannot generate integration or run', async () => {
  vi.mocked(api.get).mockRejectedValue(new Error('not published'));
  renderPage();
  await screen.findByRole('alert');
  expect(screen.queryByRole('button',{name:'运行合成文书检查'})).toBeNull();
  expect(api.post).not.toHaveBeenCalled();
});
test('explicit check binds configuration and links to run trace', async () => {
  vi.mocked(api.get).mockResolvedValue({data:manifest});
  vi.mocked(api.post).mockResolvedValue({data:{error:false,run_id:'run-test'}});
  renderPage();
  fireEvent.click(await screen.findByRole('button',{name:'运行合成文书检查'}));
  await screen.findByRole('link',{name:'查看本次运行记录'});
  expect(api.post).toHaveBeenCalledWith('/v1/agents/doc/run', expect.objectContaining({
    expected_agent_version:'1.0.1', expected_configuration_digest:manifest.configuration_digest,
    purpose_of_use:'quality_improvement',
  }), expect.anything());
  expect(screen.getByRole('link',{name:'查看本次运行记录'}).getAttribute('href')).toBe('/runs/run-test/trace');
});
test('changed configuration is not presented as a completed check', async () => {
  vi.mocked(api.get).mockResolvedValue({data:manifest});
  vi.mocked(api.post).mockRejectedValue({response:{data:{detail:{error:'integration_configuration_changed'}}}});
  renderPage();
  fireEvent.click(await screen.findByRole('button',{name:'运行合成文书检查'}));
  await waitFor(()=>expect(screen.getByRole('alert').textContent).toContain('integration_configuration_changed'));
  expect(screen.queryByRole('link',{name:'查看本次运行记录'})).toBeNull();
});

test('JSON input validates required text and selected purpose is used in the call',async()=>{
 vi.mocked(api.get).mockResolvedValue({data:manifest});vi.mocked(api.post).mockResolvedValue({data:{error:false,run_id:'r',executed_agent_version:'1.0.1'}});
 renderPage();await screen.findByLabelText('接入用途');
 fireEvent.change(screen.getByLabelText('接入用途'),{target:{value:'research'}});
 fireEvent.change(screen.getByLabelText('接入输入方式'),{target:{value:'json'}});
 fireEvent.change(screen.getByLabelText('集成检查资料'),{target:{value:'{"unknown":"invalid"}'}});
 expect((screen.getByText('运行合成文书检查') as HTMLButtonElement).disabled).toBe(true);
 fireEvent.change(screen.getByLabelText('集成检查资料'),{target:{value:'{"text":"synthetic"}'}});
 fireEvent.click(screen.getByText('运行合成文书检查'));
 await waitFor(()=>expect(api.post).toHaveBeenCalledWith(expect.any(String),expect.objectContaining({input:{text:'synthetic'},purpose_of_use:'research'}),expect.any(Object)));
 await screen.findByText(/执行版本已匹配/);
});
