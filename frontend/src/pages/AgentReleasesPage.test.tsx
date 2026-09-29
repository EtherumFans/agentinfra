// @vitest-environment jsdom
import React from 'react';
import { afterEach, expect, test, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import Page from './AgentReleasesPage';
import api from '../services/api';
vi.mock('../services/api',()=>({default:{get:vi.fn(),post:vi.fn(),put:vi.fn()}}));
vi.mock('../store',()=>({useAuthStore:(s:any)=>s({currentOrgId:'one'})}));
afterEach(()=>{cleanup();vi.clearAllMocks();});
function setup(gate:any=undefined) {
  vi.mocked(api.get).mockImplementation(async (url:any)=>({data:url.endsWith('/releases')?
    {evaluation_gate:gate,active_version:'1.0.1',status:'published',draft_changed:true,releases:[
      {version:'1.0.1',active:true,created_at:'2026-09-08T00:00:00Z'},
      {version:'1.0.0',active:false,created_at:'2026-09-07T00:00:00Z'}]}:
    {id:'doc',name:'文书',system_prompt:'saved'}}));
  vi.mocked(api.put).mockResolvedValue({data:{id:'doc',system_prompt:'edited'}});
  vi.mocked(api.post).mockResolvedValue({data:{error:false,draft_preview:true}});
  render(<MemoryRouter initialEntries={['/agents/doc/releases']}><Routes><Route path="/agents/:agentId/releases" element={<Page/>}/></Routes></MemoryRouter>);
}
test('saving edited draft does not publish and unsaved edits prevent publication',async()=>{
  setup();
  const input=await screen.findByRole('textbox',{name:'草稿系统提示词'});
  fireEvent.change(input,{target:{value:'edited'}});
  expect((screen.getByRole('button',{name:'发布草稿'}) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole('button',{name:'保存草稿'}));
  await waitFor(()=>expect(api.put).toHaveBeenCalled());
  expect(api.post).not.toHaveBeenCalled();
});
test('preview is explicit and historical integration retains selected version',async()=>{
  setup();
  fireEvent.click(await screen.findByRole('button',{name:'调试草稿'}));
  await waitFor(()=>expect(api.post).toHaveBeenCalledWith('/v1/agents/doc/run',
    expect.objectContaining({preview_draft:true}),expect.anything()));
  const links=screen.getAllByRole('link',{name:'集成此版本'});
  expect(links[1].getAttribute('href')).toContain('version=1.0.0');
});

test('required evaluation blocks the publish button',async()=>{setup({required:true,passed:false,can_publish:false});const button=await screen.findByRole('button',{name:'发布草稿'});expect((button as HTMLButtonElement).disabled).toBe(true);expect((screen.getByLabelText('强制发布评测') as HTMLInputElement).checked).toBe(true);fireEvent.click(button);expect(api.post).not.toHaveBeenCalled();});
